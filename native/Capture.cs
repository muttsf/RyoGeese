using System.Diagnostics;
using Windows.Graphics;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;

namespace GpuDash;

internal sealed class Capture:IDisposable
{
    readonly TextureBridge bridge;
    readonly IDirect3DDevice device;
    readonly GraphicsCaptureItem item;
    readonly Direct3D11CaptureFramePool pool;
    readonly GraphicsCaptureSession session;
    readonly object gate=new();
    int pendingWidth,pendingHeight,width,height;
    bool closed,disposed;
    string? error;
    internal readonly nint Window;
    internal readonly FrameBank Bank;
    internal long Arrivals,Admitted;
    internal Capture(TextureBridge bridge,nint window) {
        this.bridge=bridge;Window=window;
        if(!GraphicsCaptureSession.IsSupported())throw new InvalidOperationException("WGC_NOT_SUPPORTED");
        item=WindowsInterop.Item(window);width=item.Size.Width;height=item.Size.Height;FrameBank.ValidateSize(width,height);
        device=WindowsInterop.Device(bridge.Device);Bank=new FrameBank(bridge);pool=null!;session=null!;
        try {
            Bank.Reset(width,height);
            pool=Direct3D11CaptureFramePool.CreateFreeThreaded(device,DirectXPixelFormat.B8G8R8A8UIntNormalized,2,item.Size);
            session=pool.CreateCaptureSession(item);session.IsCursorCaptureEnabled=false;
            pool.FrameArrived+=Arrived;item.Closed+=Closed;
            // This constructor is called only after a fresh one-use human-ready marker was consumed.
            session.StartCapture();
        }catch{disposed=true;session?.Dispose();pool?.Dispose();Bank.Dispose();device.Dispose();throw;}
    }
    void Closed(GraphicsCaptureItem _,object __){lock(gate)closed=true;}
    void Arrived(Direct3D11CaptureFramePool sender,object _) {
        lock(gate) {
            if(disposed)return;
            try {
                using var frame=sender.TryGetNextFrame();if(frame is null)return;
                Arrivals=checked(Arrivals+1);long received=Stopwatch.GetTimestamp();
                int w=frame.ContentSize.Width,h=frame.ContentSize.Height;
                if(w!=width||h!=height){pendingWidth=w;pendingHeight=h;return;}
                if(WindowsInterop.IsIconic(Window))return;
                using var texture=WindowsInterop.Texture(frame.Surface);
                if(Bank.Copy(texture,w,h,received,frame.SystemRelativeTime.Ticks))Admitted=checked(Admitted+1);
            } catch(Exception ex){error=ex.GetType().Name+":"+ex.Message;}
        }
    }
    internal bool ApplyResize() {
        lock(gate) {
            if(pendingWidth==0&&pendingHeight==0)return false;
            int w=pendingWidth,h=pendingHeight;FrameBank.ValidateSize(w,h);
            Bank.Reset(w,h);pool.Recreate(device,DirectXPixelFormat.B8G8R8A8UIntNormalized,2,new SizeInt32{Width=w,Height=h});
            width=w;height=h;pendingWidth=pendingHeight=0;return true;
        }
    }
    internal void SetRegion(Region? region){lock(gate)Bank.Reset(width,height,region);}
    internal string? Failure {
        get {lock(gate)return error??(closed||!WindowsInterop.IsWindow(Window)?"GAME_WINDOW_CLOSED":null);}
    }
    public void Dispose() {
        lock(gate){if(disposed)return;disposed=true;}
        pool.FrameArrived-=Arrived;item.Closed-=Closed;
        session.Dispose();pool.Dispose();Bank.Dispose();device.Dispose();
    }
}
