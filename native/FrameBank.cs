using System.Diagnostics;
using Vortice.Direct3D11;
using Vortice.Mathematics;

namespace GpuDash;

internal record Region(int X,int Y,int Width,int Height);
internal record FrameStamp(long Ordinal,long Generation,long ReceivedTicks,long CopyQueuedTicks,long NativeTicks,int WindowWidth,int WindowHeight,Region Region);

// Three reusable GPU slots: reader, latest, writer. No CPU pixels and no frame list.
// The GPU worker owns registration/disposal; the WGC callback only submits D3D copies.
internal sealed class FrameBank:IDisposable
{
    readonly TextureBridge bridge;
    readonly object gate=new();
    ID3D11Texture2D[] textures=Array.Empty<ID3D11Texture2D>();
    RegisteredTexture[] registered=Array.Empty<RegisteredTexture>();
    readonly FrameStamp?[] stamps=new FrameStamp?[3];
    int latest=-1,reading=-1,windowWidth,windowHeight;
    long ordinal,generation,lastCopyTicks;
    bool disposed;
    Region region=new(0,0,1,1);
    internal FrameBank(TextureBridge bridge)=>this.bridge=bridge;
    internal long Generation {get {lock(gate)return generation;}}
    internal void Reset(int w,int h,Region? crop=null) {
        ValidateSize(w,h);var requested=crop??new Region(0,0,w,h);
        if(requested.X<0||requested.Y<0||requested.Width<=0||requested.Height<=0||requested.X+requested.Width>w||requested.Y+requested.Height>h)throw new ArgumentException("CAPTURE_REGION_BOUNDS");
        lock(gate) {
            if(disposed)throw new ObjectDisposedException(nameof(FrameBank));
            if(reading!=-1)throw new InvalidOperationException("RESET_WHILE_GPU_READER_OWNS_FRAME");
            ReleaseResources();region=requested;windowWidth=w;windowHeight=h;latest=-1;lastCopyTicks=0;
            Array.Clear(stamps);generation=checked(generation+1);
            var ts=new List<ID3D11Texture2D>();var rs=new List<RegisteredTexture>();
            try {for(int i=0;i<3;i++){var t=bridge.Texture(requested.Width,requested.Height);ts.Add(t);rs.Add(bridge.Register(t));}textures=ts.ToArray();registered=rs.ToArray();}
            catch {foreach(var r in rs)r.Dispose();foreach(var t in ts)t.Dispose();throw;}
        }
    }
    internal static void ValidateSize(int w,int h) {
        if(w<=0||h<=0||w>4096||h>2304)throw new ArgumentException("WINDOW_SIZE_OUTSIDE_BOUNDED_4K_PROFILE");
    }
    internal bool Copy(ID3D11Texture2D source,int w,int h,long received,long native) {
        lock(gate) {
            if(disposed||w!=windowWidth||h!=windowHeight||textures.Length!=3)return false;
            if(lastCopyTicks!=0&&Stopwatch.GetElapsedTime(lastCopyTicks,received).TotalMilliseconds<50)return false;
            int slot=Enumerable.Range(0,3).First(i=>i!=latest&&i!=reading);
            var box=new Box(region.X,region.Y,0,region.X+region.Width,region.Y+region.Height,1);
            bridge.Context.CopySubresourceRegion(textures[slot],0,0,0,0,source,0,box);
            bridge.Context.Flush();
            lastCopyTicks=received;ordinal=checked(ordinal+1);
            stamps[slot]=new(ordinal,generation,received,Stopwatch.GetTimestamp(),native,w,h,region);latest=slot;
            return true;
        }
    }
    internal Lease? Take(long lastOrdinal) {
        lock(gate) {
            if(disposed||latest<0||stamps[latest]!.Ordinal<=lastOrdinal)return null;
            if(reading!=-1)throw new InvalidOperationException("MULTIPLE_GPU_READERS");
            reading=latest;return new(this,reading,stamps[reading]!,registered[reading]);
        }
    }
    internal sealed class Lease:IDisposable {
        readonly FrameBank owner;readonly int slot;readonly RegisteredTexture resource;bool done;
        internal FrameStamp Stamp {get;}
        internal Lease(FrameBank owner,int slot,FrameStamp stamp,RegisteredTexture resource){this.owner=owner;this.slot=slot;Stamp=stamp;this.resource=resource;}
        internal long CopyTo(DeviceBuffer image) {if(done)throw new ObjectDisposedException(nameof(Lease));resource.CopyTo(image,Stamp.Region.Width,Stamp.Region.Height);return Stopwatch.GetTimestamp();}
        public void Dispose(){if(done)return;lock(owner.gate){if(owner.reading!=slot)throw new InvalidOperationException("GPU_LEASE_OWNERSHIP");owner.reading=-1;done=true;}}
    }
    void ReleaseResources() {
        foreach(var r in registered)r.Dispose();registered=Array.Empty<RegisteredTexture>();
        foreach(var t in textures)t.Dispose();textures=Array.Empty<ID3D11Texture2D>();
    }
    public void Dispose(){lock(gate){if(disposed)return;if(reading!=-1)throw new InvalidOperationException("DISPOSE_WITH_ACTIVE_GPU_READER");disposed=true;ReleaseResources();}}
}
