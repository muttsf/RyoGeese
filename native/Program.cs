using GpuDash;
using System.Diagnostics;
using System.Text.Json;
using Vortice.Mathematics;

var root=PackagePaths.Reader;
Environment.SetEnvironmentVariable("CUDA_MODULE_LOADING","LAZY");
Environment.SetEnvironmentVariable("CUDA_CACHE_PATH",Path.Combine(PackagePaths.UserCache,"cuda-cache"));
Environment.SetEnvironmentVariable("CUDNN_LIB_CONFIG","FULL");
if(args.Length==4&&args[0]=="--live") {
    Environment.SetEnvironmentVariable("DASH_OFFLINE_ORT_TRACE",null);
    Environment.ExitCode=Live.Run(root,args[1],int.Parse(args[2]),int.Parse(args[3]));return;
}
if(args.Contains("--offline-diagnostic-bounds")){DiagnosticChecks.Bounds(root);return;}
Cuda.InitializeLoader();
var before=Process.GetCurrentProcess().PrivateMemorySize64;
using var bridge=new TextureBridge();
var phases=new List<object>{Memory.Snapshot("device_created_before_kernel")};
using var module=new KernelModule(Path.Combine(root,"gpu","dash.cu"),args.Contains("--compile"));
if(args.Contains("--compile")){Console.WriteLine("Offline CUDA kernel compiled; no capture.");return;}
if(args.Contains("--offline-diagnostic-gpu")){DiagnosticChecks.Gpu(root,bridge,module);return;}
if(args.Contains("--offline-retry-guards")){OfflineChecks.RetryGuards();return;}
if(args.Contains("--probe-zero")){OfflineChecks.Zero(root,bridge,module);return;}
using var texture=bridge.Texture(320,180);
using var render=bridge.Device.CreateRenderTargetView(texture);
bridge.Context.ClearRenderTargetView(render,new Color4(1,0,1,1));
using(var wrappedDevice=WindowsInterop.Device(bridge.Device)) { }
using(var surface=WindowsInterop.Surface(texture))using(var native=WindowsInterop.Texture(surface)) {
    if(native.Description.Width!=320||native.Description.Height!=180)throw new InvalidOperationException("WINRT_SURFACE_TEXTURE_ROUNDTRIP");
}
using var registered=bridge.Register(texture);
using var pixels=new DeviceBuffer(320*180*4);
using var metadata=new DeviceBuffer(4*4,true);
registered.CopyTo(pixels,320,180);metadata.Zero();
module.Run("checksum",320*180,Cuda.Ptr(pixels.Pointer),320*180,Cuda.Ptr(metadata.Pointer));
var sums=metadata.Metadata<uint>(4);
var expected=new uint[]{255,0,255,255}.Select(x=>x*320*180).ToArray();
if(!sums.SequenceEqual(expected))throw new InvalidOperationException("GPU_INTEROP_PIXEL_SUM_MISMATCH:"+JsonSerializer.Serialize(sums));
Console.WriteLine(JsonSerializer.Serialize(new {kind="OFFLINE_GPU_TEXTURE_BRIDGE",success=true,adapter=bridge.AdapterName,device=bridge.CudaDevice,sums,winrtDeviceWrapped=true,winrtSurfaceRoundtrip=true,hostImageDownload=false,privateBefore=before,privateAfter=Process.GetCurrentProcess().PrivateMemorySize64}));
if(args.Contains("--offline-bank")){OfflineChecks.InputBounds();OfflineChecks.Bank(bridge,module);}
if(args.Contains("--offline-locator")||args.Contains("--offline-reader")) {
    using var assets=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"assets_v2.json")));
    using var reader=args.Contains("--offline-reader")?new Reader(assets.RootElement,module,bridge.CudaDevice,Path.Combine(root,"证据")):null;
    phases.Add(Memory.Snapshot("model_created_before_first_read"));
    if(reader!=null)Console.WriteLine(JsonSerializer.Serialize(new{kind="OFFLINE_GPU_WARM",milliseconds=reader.Warm(),gameCapture=false,publishedFacts=false}));
    using var file=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"fixtures.json")));
    var rows=new List<object>();
    foreach(var f in file.RootElement.EnumerateArray()) {
        int w=f.GetProperty("width").GetInt32(),h=f.GetProperty("height").GetInt32();
        byte[] hostFixture=File.ReadAllBytes(f.GetProperty("path").GetString()!);
        using var image=new DeviceBuffer(hostFixture.Length);image.Upload(hostFixture);
        var started=Stopwatch.GetTimestamp();var g=Locator.Find(module,image,w,h);
        var refg=f.GetProperty("geometry");
        if(Math.Abs(g.Scale-refg.GetProperty("scale").GetDouble())>1e-8 || Math.Abs(g.Left-refg.GetProperty("left").GetDouble())>1e-6 || Math.Abs(g.Top-refg.GetProperty("top").GetDouble())>1e-6)throw new InvalidOperationException("GPU_LOCATOR_GEOMETRY_DIFF:"+JsonSerializer.Serialize(g));
        ReadResult? result=reader?.Read(image,w,h,g);
        ReadResult? roiResult=null;
        if(reader!=null) {
            int x=Math.Max(0,(int)Math.Floor(g.Left)-2),y=Math.Max(0,(int)Math.Floor(g.Top)-2);
            int cw=Math.Min(w-x,(int)Math.Ceiling(g.Left+578*g.Scale)+2-x),ch=Math.Min(h-y,(int)Math.Ceiling(g.Top+306*g.Scale)+2-y);
            using var gpuCrop=new DeviceBuffer(cw*ch*4);
            module.Run("crop_gpu",cw*ch*4,Cuda.Ptr(image.Pointer),(ulong)w,(ulong)h,(ulong)x,(ulong)y,(ulong)cw,(ulong)ch,Cuda.Ptr(gpuCrop.Pointer));
            roiResult=reader.Read(gpuCrop,cw,ch,g with{Left=g.Left-x,Top=g.Top-y});
            if(!result!.facts.SequenceEqual(roiResult.facts))throw new InvalidOperationException("GPU_CROP_FACTS_CHANGED");
        }
        phases.Add(Memory.Snapshot("after_read_"+f.GetProperty("id").GetInt32()));
        var differences=new List<object>();
        if(result!=null) {
            foreach(var expectedFact in f.GetProperty("facts").EnumerateArray()) {
                var actual=result.facts.Single(x=>x.name==expectedFact.GetProperty("name").GetString());
                var signature=new{actual.status,actual.value,actual.reason};
                var target=new{status=expectedFact.GetProperty("status").GetString(),value=expectedFact.GetProperty("value"),reason=expectedFact.GetProperty("reason").GetString()};
                if(JsonSerializer.Serialize(signature)!=JsonSerializer.Serialize(target))differences.Add(new{actual.name,actual,expected=target});
            }
        }
        rows.Add(new{id=f.GetProperty("id").GetInt32(),geometry=g,milliseconds=Stopwatch.GetElapsedTime(started).TotalMilliseconds,result,differences});
    }
    Console.WriteLine(JsonSerializer.Serialize(new{kind=reader==null?"OFFLINE_GPU_LOCATOR":"OFFLINE_GPU_READER",rows,gameCapture=false,hostImageDownload=false,privateBytes=Process.GetCurrentProcess().PrivateMemorySize64,workingSet=Process.GetCurrentProcess().WorkingSet64}));
    Console.WriteLine(JsonSerializer.Serialize(new{kind="OFFLINE_MEMORY_PHASES",phases}));
}
