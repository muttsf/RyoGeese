using System.Runtime.InteropServices;
using System.Text;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX.Direct3D11;
using WinRT;
using Vortice.Direct3D11;
using Vortice.DXGI;

namespace GpuDash;

internal static unsafe class WindowsInterop
{
    [DllImport("combase",CharSet=CharSet.Unicode)] static extern int WindowsCreateString(string value,uint length,out nint str);
    [DllImport("combase")] static extern int WindowsDeleteString(nint str);
    [DllImport("combase")] static extern int RoGetActivationFactory(nint name,ref Guid iid,out nint factory);
    [DllImport("combase")] internal static extern int RoInitialize(uint kind);
    [DllImport("combase")] internal static extern void RoUninitialize();
    [DllImport("d3d11")] static extern int CreateDirect3D11DeviceFromDXGIDevice(nint device,out nint wrapped);
    [DllImport("d3d11")] static extern int CreateDirect3D11SurfaceFromDXGISurface(nint surface,out nint wrapped);
    [DllImport("user32")] static extern bool EnumWindows(EnumWindow callback,nint param);
    delegate bool EnumWindow(nint window,nint param);
    [DllImport("user32",CharSet=CharSet.Unicode)] static extern int GetWindowText(nint window,StringBuilder text,int max);
    [DllImport("user32")] static extern uint GetWindowThreadProcessId(nint window,out uint pid);
    [DllImport("user32")] internal static extern bool IsWindow(nint window);
    [DllImport("user32")] internal static extern bool IsWindowVisible(nint window);
    [DllImport("user32")] internal static extern bool IsIconic(nint window);
    internal static uint WindowProcessId(nint window) { GetWindowThreadProcessId(window,out uint pid);return pid; }
    internal static nint ExactGameWindow(bool allowMinimized=false) {
        var matches=new List<nint>();
        EnumWindows((hwnd,_)=>{
            var text=new StringBuilder(256);GetWindowText(hwnd,text,text.Capacity);
            if(text.ToString()!="魔兽世界"||!IsWindowVisible(hwnd))return true;
            GetWindowThreadProcessId(hwnd,out uint pid);
            try {using var p=System.Diagnostics.Process.GetProcessById((int)pid);if(p.ProcessName.Equals("Wow",StringComparison.OrdinalIgnoreCase))matches.Add(hwnd);}catch(ArgumentException){}
            return true;
        },0);
        if(matches.Count!=1)throw new InvalidOperationException("WINDOW_NOT_UNIQUE_EXACT_MATCH:"+matches.Count);
        if(!allowMinimized&&IsIconic(matches[0]))throw new InvalidOperationException("GAME_WINDOW_MINIMIZED");
        return matches[0];
    }
    internal static GraphicsCaptureItem Item(nint hwnd) {
        string name="Windows.Graphics.Capture.GraphicsCaptureItem";
        Marshal.ThrowExceptionForHR(WindowsCreateString(name,(uint)name.Length,out nint hs));
        nint factory=0,item=0;
        try {
            Guid interop=new("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"),iid=new("79C3F95B-31F7-4EC2-A464-632EF5D30760");
            Marshal.ThrowExceptionForHR(RoGetActivationFactory(hs,ref interop,out factory));
            var create=(delegate* unmanaged[Stdcall]<nint,nint,Guid*,nint*,int>)(*(nint**)factory)[3];
            Marshal.ThrowExceptionForHR(create(factory,hwnd,&iid,&item));
            return MarshalInterface<GraphicsCaptureItem>.FromAbi(item);
        } finally {if(item!=0)Marshal.Release(item);if(factory!=0)Marshal.Release(factory);WindowsDeleteString(hs);}
    }
    internal static IDirect3DDevice Device(ID3D11Device device) {
        using var dxgi=device.QueryInterface<IDXGIDevice>();
        Marshal.ThrowExceptionForHR(CreateDirect3D11DeviceFromDXGIDevice(dxgi.NativePointer,out nint wrapped));
        try{return MarshalInterface<IDirect3DDevice>.FromAbi(wrapped);}finally{Marshal.Release(wrapped);}
    }
    internal static IDirect3DSurface Surface(ID3D11Texture2D texture) {
        using var dxgi=texture.QueryInterface<IDXGISurface>();
        Marshal.ThrowExceptionForHR(CreateDirect3D11SurfaceFromDXGISurface(dxgi.NativePointer,out nint wrapped));
        try{return MarshalInterface<IDirect3DSurface>.FromAbi(wrapped);}finally{Marshal.Release(wrapped);}
    }
    internal static ID3D11Texture2D Texture(IDirect3DSurface surface) {
        nint wrapped=MarshalInterface<IDirect3DSurface>.FromManaged(surface),access=0;
        try {
            Guid iid=new("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1"),tid=new("6f15aaf2-d208-4e89-9ab4-489535d34f9c");
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(wrapped,ref iid,out access));
            nint texture=0;var get=(delegate* unmanaged[Stdcall]<nint,Guid*,nint*,int>)(*(nint**)access)[3];
            Marshal.ThrowExceptionForHR(get(access,&tid,&texture));return new ID3D11Texture2D(texture);
        } finally {if(access!=0)Marshal.Release(access);Marshal.Release(wrapped);}
    }
}
