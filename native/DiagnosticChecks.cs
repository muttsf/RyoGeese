using System.Text.Json;
using Vortice.Mathematics;

namespace GpuDash;
internal static class DiagnosticChecks
{
    static ReadResult Sample(Geometry g,string row="B1")=>new(new[]{new Fact(row+".seconds","target","unknown",null,"OCR_LOW_CONFIDENCE","0",.72)},g,Array.Empty<string>(),0);
    internal static void Bounds(string root) {
        using var assets=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"assets_v2.json")));
        string output=Path.Combine(root,"证据","诊断边界_"+Guid.NewGuid().ToString("N"));int passed=0;
        foreach(var c in new (double scale,double left,double top,int w,int h)[]{(3.0,4.0,4.0,2000,2000),(1.385,-1000.0,4.0,810,433),(1.385,4.0,-1000.0,810,433),(1.385,1000.0,4.0,810,433),(1.385,4.0,1000.0,810,433),(1.385,4.0,4.0,1,1)}) {
            var saver=new FailureSamples(output,assets.RootElement);var previous=Console.Out;var text=new StringWriter();
            try {
                Console.SetOut(text);
                // Null GPU arguments prove rejection and latched disable happen before GPU access.
                saver.Save(null!,null!,c.w,c.h,Sample(new(c.scale,c.left,c.top,"D_VISIBLE",0)),1);
                saver.Save(null!,null!,810,433,Sample(new(1.385,4,4,"D_VISIBLE",0)),2);
            } finally {Console.SetOut(previous);}
            string[] lines=text.ToString().Split('\n',StringSplitOptions.RemoveEmptyEntries);
            if(lines.Length!=1)throw new Exception("DIAGNOSTIC_DISABLE_NOT_LATCHED");
            using var evt=JsonDocument.Parse(lines[0]);
            if(evt.RootElement.GetProperty("reason").GetString()!="FAILURE_TILE_BOUNDS"||!evt.RootElement.GetProperty("diagnosticDisabled").GetBoolean())throw new Exception("DIAGNOSTIC_DISABLE_EVENT_INVALID");
            if(Directory.Exists(output))throw new Exception("REJECTED_TILE_WROTE_FILES");passed+=3;
        }
        foreach(double scale in new[]{1.30,1.3853693160163532,1.46})foreach(var row in Reader.EffectRows) {
            var cell=assets.RootElement.GetProperty("layout").GetProperty("cells").GetProperty(row+"_value").EnumerateArray().Select(x=>x.GetDouble()).ToArray();
            var r=new Geometry(scale,4.35,4.12,"D_VISIBLE",0).Pixels(cell);
            if(r[2]<=0||r[3]<=0||r[2]>80||r[3]>80)throw new Exception("SUPPORTED_CELL_EXCEEDS_DIAGNOSTIC_BOUND");passed++;
        }
        foreach(nuint bytes in new nuint[]{4096,4095,0}) {
            bool rejected=false;try{Locator.ValidateInput(32,32,bytes);}catch(ArgumentException ex) when(ex.Message=="LOCATOR_INPUT_BOUNDS"){rejected=true;}
            if(rejected!=(bytes<4096))throw new Exception("LOCATOR_BYTES_BOUND_REGRESSION");passed++;
        }
        foreach(double scale in new[]{1.30,1.3853693160163532,1.46}) {
            var cell=assets.RootElement.GetProperty("layout").GetProperty("fields").GetProperty("A5.display").GetProperty("cell").GetString()!;
            var rect=new Geometry(scale,4.35,4.12,"D_VISIBLE",0).Pixels(assets.RootElement.GetProperty("layout").GetProperty("cells").GetProperty(cell).EnumerateArray().Select(x=>x.GetDouble()).ToArray());
            if(rect[2]<=0||rect[3]<=0||rect[2]>80||rect[3]>80)throw new Exception("A5_DIAGNOSTIC_SIZE_BOUND");passed++;
        }
        foreach(var f in new[]{new Fact("A5.display","player","known",53,"VISIBLE_INTEGER","53",.99),new Fact("A4.display","player","unknown",null,"OCR_LOW_CONFIDENCE","53",.79)}) {
            var saver=new FailureSamples(output,assets.RootElement);
            saver.Save(null!,null!,810,433,new(new[]{f},new(1.385,4,4,"D_VISIBLE",0),Array.Empty<string>(),0),1);
            if(Directory.Exists(output))throw new Exception("UNSELECTED_A5_DIAGNOSTIC_WROTE_FILES");passed++;
        }
        {
            var saver=new FailureSamples(output,assets.RootElement);var previous=Console.Out;var text=new StringWriter();
            try{Console.SetOut(text);saver.Save(null!,null!,1,1,new(new[]{new Fact("A5.display","player","unknown",null,"OCR_LOW_CONFIDENCE","53",.79757)},new(1.385,4,4,"D_VISIBLE",0),Array.Empty<string>(),0),1);}
            finally{Console.SetOut(previous);}
            if(!text.ToString().Contains("FAILURE_TILE_BOUNDS")||Directory.Exists(output))throw new Exception("A5_BAD_RECT_REACHED_GPU");passed++;
        }
        Live.Emit(new{kind="OFFLINE_DIAGNOSTIC_BOUNDS",passed,gpuInitialized=false,gameCapture=false,sourceFramePublished=false});
    }
    internal static void Gpu(string root,TextureBridge bridge,KernelModule kernels) {
        using var assets=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"assets_v2.json")));
        string output=Path.Combine(root,"证据","诊断GPU合成图_"+Guid.NewGuid().ToString("N"));
        using var source=bridge.Texture(810,433);using var rtv=bridge.Device.CreateRenderTargetView(source);
        bridge.Context.ClearRenderTargetView(rtv,new Color4(1,0,1,1));
        using var registered=bridge.Register(source);using var image=new DeviceBuffer(810*433*4);registered.CopyTo(image,810,433);
        var saver=new FailureSamples(output,assets.RootElement);long round=0;int passed=0;
        foreach(var row in Reader.EffectRows)for(int n=0;n<4;n++)saver.Save(kernels,image,810,433,Sample(new(1.3853693160163532,4.351705385655009,4.119567108379414,"D_VISIBLE",0),row),++round);
        var files=Directory.GetFiles(output,"*.json");if(files.Length!=12)throw new Exception("DIAGNOSTIC_IMAGE_CAP_FAILED");passed++;
        long total=0;var counts=new Dictionary<string,int>();
        foreach(string file in files) {
            using var doc=JsonDocument.Parse(File.ReadAllText(file));var j=doc.RootElement;byte[] raw=File.ReadAllBytes(Path.ChangeExtension(file,".bgra"));
            int w=j.GetProperty("width").GetInt32(),h=j.GetProperty("height").GetInt32();
            if(w>80||h>80||raw.Length!=w*h*4)throw new Exception("DIAGNOSTIC_IMAGE_SIZE_FAILED");
            for(int n=0;n<raw.Length;n++)if(raw[n]!=(n%4==1?0:255))throw new Exception("DIAGNOSTIC_PIXEL_COPY_CHANGED");
            if(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(raw)).ToLowerInvariant()!=j.GetProperty("SHA256").GetString())throw new Exception("DIAGNOSTIC_HASH_CHANGED");
            string field=j.GetProperty("field").GetString()!;counts[field]=counts.GetValueOrDefault(field)+1;total+=raw.Length;passed+=3;
        }
        if(total>307200||counts.Count!=6||counts.Values.Any(n=>n!=2))throw new Exception("DIAGNOSTIC_TOTAL_BOUND_FAILED");passed++;
        // Unknown failures must still propagate. Null is a control substitute;
        // do not inject an illegal address or device fault into real hardware.
        var fatal=new FailureSamples(Path.Combine(output,"fatal"),assets.RootElement);bool propagated=false;
        try{fatal.Save(kernels,null!,810,433,Sample(new(1.385,4,4,"D_VISIBLE",0)),999);}catch(NullReferenceException){propagated=true;}
        if(!propagated)throw new Exception("UNKNOWN_FAILURE_WAS_SWALLOWED");passed++;
        // A5 shares the same twelve-image session budget with the six B/D rows.
        string mixed=output+"_A5混合预算";var mixedSaver=new FailureSamples(mixed,assets.RootElement);
        var a5=new ReadResult(new[]{new Fact("A5.display","player","unknown",null,"OCR_LOW_CONFIDENCE","53",.79757)},new(1.3853693160163532,4.351705385655009,4.119567108379414,"D_VISIBLE",0),Array.Empty<string>(),0);
        for(int n=0;n<4;n++)mixedSaver.Save(kernels,image,810,433,a5,++round);
        foreach(var row in Reader.EffectRows)for(int n=0;n<4;n++)mixedSaver.Save(kernels,image,810,433,Sample(a5.geometry,row),++round);
        var mixedFiles=Directory.GetFiles(mixed,"*.json");var mixedCounts=new Dictionary<string,int>();long mixedBytes=0;
        foreach(string file in mixedFiles) {
            using var doc=JsonDocument.Parse(File.ReadAllText(file));var j=doc.RootElement;byte[] raw=File.ReadAllBytes(Path.ChangeExtension(file,".bgra"));
            string field=j.GetProperty("field").GetString()!;mixedCounts[field]=mixedCounts.GetValueOrDefault(field)+1;mixedBytes+=raw.Length;
            if(raw.Length!=j.GetProperty("width").GetInt32()*j.GetProperty("height").GetInt32()*4||raw.Length>80*80*4)throw new Exception("MIXED_DIAGNOSTIC_SIZE");
            for(int n=0;n<raw.Length;n++)if(raw[n]!=(n%4==1?0:255))throw new Exception("A5_PIXEL_COPY_CHANGED");
            if(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(raw)).ToLowerInvariant()!=j.GetProperty("SHA256").GetString())throw new Exception("A5_PIXEL_HASH_CHANGED");passed+=3;
        }
        if(mixedFiles.Length!=12||mixedCounts.GetValueOrDefault("A5.display")!=2||mixedCounts.Values.Any(n=>n>2)||mixedBytes>307200)throw new Exception("A5_MIXED_SESSION_CAP");passed++;
        // At cap, a new valid field must return before any GPU dereference/allocation.
        mixedSaver.Save(null!,null!,810,433,Sample(a5.geometry,"D3"),++round);passed++;
        Live.Emit(new{kind="OFFLINE_A5_DIAGNOSTIC_GPU",passed,output=mixed,images=mixedFiles.Length,imageBytes=mixedBytes,counts=mixedCounts,rawPixelsMatchSyntheticGpu=true,modelLoaded=false,gameCapture=false});
        Live.Emit(new{kind="OFFLINE_DIAGNOSTIC_GPU",passed,output,images=files.Length,imageBytes=total,rawPixelsMatchSyntheticGpu=true,diagnosticImageDownload=true,gameCapture=false,modelLoaded=false});
    }
}
