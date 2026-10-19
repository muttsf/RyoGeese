using System.Text.Json;
using System.Security.Cryptography;

namespace GpuDash;

// Test evidence only: at most two <=80x80 raw BGRA cells per selected field,
// at most twelve images total, including low-confidence A5 cooldown evidence.
// No normal-frame download, history queue, full-window image or model change.
internal sealed class FailureSamples
{
    readonly string root;
    readonly JsonElement layout;
    readonly Dictionary<string,int> counts=new();
    int savedCount;
    bool disabled;
    internal FailureSamples(string root,JsonElement assets){this.root=root;layout=assets.GetProperty("layout");}
    internal void Save(KernelModule kernels,DeviceBuffer image,int w,int h,ReadResult result,long round) {
        if(disabled||savedCount>=12)return;
        foreach(var fact in result.facts.Where(f=>(f.name=="A5.display"&&(f.reason=="OCR_LOW_CONFIDENCE"||(result.retries?.Any(t=>t.cell=="A5_value")??false)))||(f.name.EndsWith(".seconds")&&(f.reason=="OCR_LOW_CONFIDENCE"||(result.retries?.Any(t=>f.name.StartsWith(t.cell.Split('_')[0]+"."))??false))))) {
            if(savedCount>=12)return;
            int count=counts.GetValueOrDefault(fact.name);if(count>=2)continue;
            string cell=layout.GetProperty("fields").GetProperty(fact.name).GetProperty("cell").GetString()!;
            int[] rect=result.geometry.Pixels(layout.GetProperty("cells").GetProperty(cell).EnumerateArray().Select(x=>x.GetDouble()).ToArray());
            int x=rect[0],y=rect[1],cw=rect[2],ch=rect[3];
            if(cw<=0||ch<=0||cw>80||ch>80||x<0||y<0||(long)x+cw>w||(long)y+ch>h){Disable("FAILURE_TILE_BOUNDS");return;}
            using var tile=new DeviceBuffer(cw*ch*4);
            kernels.Run("crop_gpu",cw*ch*4,Cuda.Ptr(image.Pointer),(ulong)w,(ulong)h,(ulong)x,(ulong)y,(ulong)cw,(ulong)ch,Cuda.Ptr(tile.Pointer));
            byte[] bytes=Download(tile,cw*ch*4);
            try {
                Directory.CreateDirectory(root);string prefix=Path.Combine(root,$"{round:D5}_{cell}_{count+1}");
                using(var file=new FileStream(prefix+".bgra",FileMode.CreateNew,FileAccess.Write))file.Write(bytes);
                File.WriteAllText(prefix+".json",JsonSerializer.Serialize(new{round,field=fact.name,width=cw,height=ch,format="BGRA",rect,geometry=result.geometry,fact,retries=result.retries,SHA256=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),diagnosticImageDownload=true}));
                counts[fact.name]=count+1;savedCount++;
                Live.Emit(new{kind="diagnostic_tile",round,field=fact.name,bytes=bytes.Length,path=prefix+".bgra",diagnosticImageDownload=true});
            } catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
                Disable(ex.Message);return;
            }
        }
    }
    void Disable(string reason){disabled=true;Live.Emit(new{kind="diagnostic_tile_error",reason,diagnosticDisabled=true});}
    static unsafe byte[] Download(DeviceBuffer tile,int count) {
        if(count<=0||count>80*80*4||tile.Bytes!=(nuint)count)throw new ArgumentException("FAILURE_TILE_DOWNLOAD_BOUND");
        byte[] bytes=new byte[count];fixed(byte* dst=bytes)Cuda.Check(Cuda.cudaMemcpy((nint)dst,tile.Pointer,(nuint)count,2));return bytes;
    }
}
