using System.Diagnostics;
using System.Text.Json;
using Vortice.Mathematics;

namespace GpuDash;
internal static class OfflineChecks
{
    internal static void RetryGuards() {
        int passed=0;var meta=new int[12];meta[3]=1;
        var low=new ReadToken("0",.72,"SYNTHETIC_CONTROL");
        void Check(bool value){if(!value)throw new Exception("MASK_RETRY_GUARD_FAILED:"+passed);passed++;}
        bool Candidate(string cell="B1_value",int mode=0,ReadToken? token=null,ReadToken? native=null)=>Reader.MaskCandidate(cell,mode,token??low,native??low,meta,0);
        foreach(var row in Reader.EffectRows)Check(Candidate(row+"_value"));
        Check(Candidate("D1_value",1));Check(Candidate("A2_chg"));
        Check(Candidate("A2_chg",0,new("1",.7,"test"),new("1",.7,"test")));Check(Candidate("A2_chg",0,new("2",.7,"test"),new("2",.7,"test")));
        foreach(var token in new[]{"1","8","00","?","!","~","—","","O"})Check(!Candidate(token:new(token,.72,"test"),native:new(token,.72,"test")));
        Check(!Candidate("C2_current"));Check(!Candidate("A1_value"));Check(!Candidate("A2_chg",1));
        Check(!Candidate(token:low with{Confidence=.85}));Check(!Candidate(native:low with{Text="8"}));Check(!Candidate(native:low with{Confidence=.9}));
        Check(!Reader.MaskCandidate("B1_value",0,low,null,meta,0));Check(!Candidate(mode:2));
        foreach(var position in new[]{0,1,4}){meta[position]=1;Check(!Candidate());meta[position]=0;}
        foreach(var count in new[]{0,2}){meta[3]=count;Check(!Candidate());}meta[3]=1;
        meta[2]=1;Check(!Candidate());Check(Candidate(mode:1));
        Check(Reader.Parse("B1.seconds",new("0",.84,"test")).Item1=="unknown");
        Check(Reader.Parse("B1.seconds",new("0",.99,"test")).Item2 is int n&&n==0);
        Array.Clear(meta);meta[3]=2;
        var two=new ReadToken("53",.79757,"test");
        Check(Candidate("A5_value",1,two,two));Check(Candidate("A5_value",0,two,two));
        foreach(var text in new[]{"0","3","120","5?","5O","—","","OK","NA"})Check(!Candidate("A5_value",1,new(text,.79,"test"),new(text,.79,"test")));
        foreach(var cell in new[]{"A1_value","A3_value","A4_value","A6_value","C2_current","B1_value"})Check(!Candidate(cell,1,two,two));
        foreach(var count in new[]{0,1,3}){meta[3]=count;Check(!Candidate("A5_value",1,two,two));}meta[3]=2;
        foreach(var position in new[]{0,1,4}){meta[position]=1;Check(!Candidate("A5_value",1,two,two));meta[position]=0;}
        Check(!Candidate("A5_value",1,two with{Confidence=.85},two));Check(!Candidate("A5_value",2,two,two));
        Check(!Reader.MaskCandidate("A5_value",0,two,null,meta,0));
        Check(!Candidate("A5_value",0,two,two with{Text="58"}));Check(!Candidate("A5_value",0,two,two with{Confidence=.9}));
        meta[2]=1;Check(!Candidate("A5_value",0,two,two));Check(Candidate("A5_value",1,two,two));
        Check(Reader.Parse("A5.display",two).Item1=="unknown");Check(Reader.Parse("A5.display",two with{Confidence=.99}).Item2 is int c&&c==53);
        Live.Emit(new{kind="OFFLINE_RETRY_GUARDS",passed,syntheticTokens=true,gameCapture=false});
    }
    internal static void Zero(string root,TextureBridge bridge,KernelModule kernels) {
        using var assets=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"assets_v2.json")));
        using var reader=new Reader(assets.RootElement,kernels,bridge.CudaDevice,Path.Combine(root,"证据"));
        var samples=new FailureSamples(Path.Combine(root,"证据","限量诊断样图_"+Guid.NewGuid().ToString("N")),assets.RootElement);
        Live.Emit(new{kind="SAVED_ZERO_WARM",milliseconds=reader.Warm(),gameCapture=false});
        using var input=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"证据","归零复现","输入.json")));
        foreach(var f in input.RootElement.EnumerateArray()) {
            int w=f.GetProperty("width").GetInt32(),h=f.GetProperty("height").GetInt32();
            byte[] bgra=File.ReadAllBytes(f.GetProperty("path").GetString()!);
            using var image=new DeviceBuffer(bgra.Length);image.Upload(bgra);
            var geometry=Locator.Find(kernels,image,w,h);
            var result=reader.Read(image,w,h,geometry);
            for(int repeat=0;repeat<3;repeat++)samples.Save(kernels,image,w,h,result,f.GetProperty("id").GetInt32());
            Live.Emit(new{kind="SAVED_ZERO_RESULT",id=f.GetProperty("id").GetInt32(),geometry,result,gameCapture=false});
            var flags=System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic;
            T Field<T>(string key)=>(T)typeof(Reader).GetField(key,flags)!.GetValue(reader)!;
            var cells=Field<string[]>("cells");var meta=Field<DeviceBuffer>("metadata").Metadata<int>(cells.Length*12);
            Live.Emit(new{kind="SAVED_CELL_METADATA",id=f.GetProperty("id").GetInt32(),cells=cells.Select((cell,i)=>new{cell,data=meta.Skip(i*12).Take(12).ToArray()}),gameCapture=false});
            for(int mode=0;mode<3;mode++) {
                var requested=cells.Select((cell,i)=>(cell,i)).Where(x=>x.cell.EndsWith("_value")&&meta[x.i*12]==0&&meta[x.i*12+1]==0).Select(x=>(x.i,mode)).ToList();
                Live.Emit(new{kind="SAVED_ZERO_VARIANTS",id=f.GetProperty("id").GetInt32(),mode,tokens=Field<Ocr>("ocr").Read(Field<DeviceBuffer>("images"),meta,requested).Select(x=>new{cell=cells[x.Key],token=x.Value,components=meta[x.Key*12+3],boundary=meta[x.Key*12+4]}),gameCapture=false});
            }
            int zero=Array.IndexOf(cells,f.GetProperty("source").GetProperty("field").GetString()!.Split('.')[0]+"_value"),companion=Array.IndexOf(cells,"C2_max");
            if(companion<0)companion=Enumerable.Range(0,cells.Length).First(i=>i!=zero&&meta[i*12]==0&&meta[i*12+1]==0);
            foreach(int width in new[]{96,120,144,192,240,288,384}) {
                var m=(int[])meta.Clone();m[companion*12+5]=width/3;m[companion*12+6]=16;
                var token=Field<Ocr>("ocr").Read(Field<DeviceBuffer>("images"),m,new(){(zero,0),(companion,0)})[zero];
                Live.Emit(new{kind="SAVED_ZERO_BATCH_WIDTH_PROBE",id=f.GetProperty("id").GetInt32(),width,token,artificialCompanionDimensions=true,zeroPixelsUnchanged=true,gameCapture=false});
            }
        }
    }
    internal static void InputBounds() {
        Locator.ValidateInput(4096,2304,(nuint)(4096L*2304*4));int passed=1;
        foreach(var size in new[]{(7680,4320),(4097,2304),(4096,2305),(0,1)}) {
            try{Locator.ValidateInput(size.Item1,size.Item2,(nuint)(7680L*4320*4));throw new Exception("LOCATOR_BOUND_NOT_REJECTED");}
            catch(ArgumentException ex) when(ex.Message=="LOCATOR_INPUT_BOUNDS"){passed++;}
        }
        Live.Emit(new{kind="OFFLINE_LOCATOR_BOUNDS",passed,gameCapture=false,gpuAllocationForLargeInputs=false});
    }
    internal static void Bank(TextureBridge bridge,KernelModule kernel) {
        int checkedCases=0;
        using var source=bridge.Texture(320,180);using var rtv=bridge.Device.CreateRenderTargetView(source);
        using var bank=new FrameBank(bridge);bank.Reset(320,180);
        long ticks=Stopwatch.GetTimestamp();bridge.Context.ClearRenderTargetView(rtv,new Color4(1,0,1,1));
        if(!bank.Copy(source,320,180,ticks,1))throw new InvalidOperationException("BANK_FIRST_COPY");
        using var image=new DeviceBuffer(320*180*4);using var checksum=new DeviceBuffer(4*4,true);
        using(var first=bank.Take(0)!) {
            for(int i=1;i<=50;i++){
                ticks+=Stopwatch.Frequency/5;bridge.Context.ClearRenderTargetView(rtv,new Color4(0,1,0,1));
                if(!bank.Copy(source,320,180,ticks,i+1))throw new InvalidOperationException("BANK_OVERWRITE_LATEST");
            }
            first.CopyTo(image);checksum.Zero();kernel.Run("checksum",320*180,Cuda.Ptr(image.Pointer),320*180,Cuda.Ptr(checksum.Pointer));
            if(!checksum.Metadata<uint>(4).SequenceEqual(new uint[]{255,0,255,255}.Select(x=>x*320*180)))throw new InvalidOperationException("BANK_MUTATED_ACTIVE_READER");checkedCases++;
            try{bank.Reset(320,180);throw new Exception("RESET_DID_NOT_REJECT_ACTIVE_READER");}catch(InvalidOperationException ex) when(ex.Message=="RESET_WHILE_GPU_READER_OWNS_FRAME"){checkedCases++;}
        }
        using(var latest=bank.Take(1)!) {
            if(latest.Stamp.Ordinal!=51)throw new InvalidOperationException("BANK_BACKLOG_NOT_LATEST");checkedCases++;
            latest.CopyTo(image);checksum.Zero();kernel.Run("checksum",320*180,Cuda.Ptr(image.Pointer),320*180,Cuda.Ptr(checksum.Pointer));
            if(!checksum.Metadata<uint>(4).SequenceEqual(new uint[]{0,255,0,255}.Select(x=>x*320*180)))throw new InvalidOperationException("BANK_LATEST_WRONG_IMAGE");checkedCases++;
        }
        if(bank.Take(51)!=null)throw new InvalidOperationException("BANK_REDELIVERED_FRAME");checkedCases++;
        long generation=bank.Generation;bank.Reset(320,180,new Region(20,30,100,80));
        if(bank.Generation!=generation+1||bank.Take(0)!=null)throw new InvalidOperationException("BANK_RELOCATION_NOT_INVALIDATED");checkedCases++;
        ticks+=Stopwatch.Frequency/5;bank.Copy(source,320,180,ticks,99);
        using(var roi=bank.Take(0)!) {
            using var cropped=new DeviceBuffer(100*80*4);roi.CopyTo(cropped);checksum.Zero();kernel.Run("checksum",100*80,Cuda.Ptr(cropped.Pointer),100*80,Cuda.Ptr(checksum.Pointer));
            if(!checksum.Metadata<uint>(4).SequenceEqual(new uint[]{0,255,0,255}.Select(x=>x*100*80)))throw new InvalidOperationException("BANK_GPU_REGION_COPY");checkedCases++;
        }
        try{image.Metadata<byte>(4);throw new Exception("IMAGE_DOWNLOAD_NOT_REJECTED");}catch(ArgumentException){checkedCases++;}
        Live.Emit(new{kind="OFFLINE_GPU_BANK_CHECKS",passed=checkedCases,gameCapture=false,hostImageDownload=false});
    }
}
