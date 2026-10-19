using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using static Vortice.Direct3D11.D3D11;
using static Vortice.DXGI.DXGI;

namespace GpuDash;

internal sealed class TextureBridge:IDisposable
{
    internal readonly ID3D11Device Device;
    internal readonly ID3D11DeviceContext Context;
    internal readonly int CudaDevice;
    internal readonly string AdapterName;
    internal TextureBridge() {
        using var factory=CreateDXGIFactory1<IDXGIFactory1>();
        IDXGIAdapter1? adapter=null;
        for(uint i=0;factory.EnumAdapters1(i,out var a).Success;i++) {
            if(a.Description1.VendorId==0x10de) {adapter=a;break;} a.Dispose();
        }
        if(adapter is null)throw new InvalidOperationException("NVIDIA_ADAPTER_NOT_FOUND");
        using(adapter) {
            AdapterName=adapter.Description1.Description;
            Cuda.Check(Cuda.cudaD3D11GetDevice(out CudaDevice,adapter.NativePointer));
            Cuda.Check(Cuda.cudaSetDevice(CudaDevice));
            D3D11CreateDevice(adapter,DriverType.Unknown,DeviceCreationFlags.BgraSupport,
                new[]{FeatureLevel.Level_11_1,FeatureLevel.Level_11_0},out Device,out _,out Context).CheckError();
            using var multithread=Context.QueryInterface<ID3D11Multithread>();
            multithread.SetMultithreadProtected(true);
        }
    }
    internal ID3D11Texture2D Texture(int width,int height)=>Device.CreateTexture2D(new Texture2DDescription {
        Width=(uint)width,Height=(uint)height,MipLevels=1,ArraySize=1,Format=Format.B8G8R8A8_UNorm,
        SampleDescription=new SampleDescription(1,0),Usage=ResourceUsage.Default,
        BindFlags=BindFlags.RenderTarget | BindFlags.ShaderResource,CPUAccessFlags=CpuAccessFlags.None });
    // Register once for a reusable owned texture. WGC surfaces are borrowed and never registered.
    internal RegisteredTexture Register(ID3D11Texture2D texture)=>new(texture);
    public void Dispose() {Context.Dispose();Device.Dispose();}
}
internal sealed class RegisteredTexture:IDisposable
{
    readonly ID3D11Texture2D texture;
    nint resource;
    internal RegisteredTexture(ID3D11Texture2D texture) {this.texture=texture;Cuda.Check(Cuda.cudaGraphicsD3D11RegisterResource(out resource,texture.NativePointer,0));}
    internal void CopyTo(DeviceBuffer pixels,int width,int height) {
        if(width<=0 || height<=0 || pixels.Bytes<(nuint)(width*height*4L))throw new ArgumentException("GPU_TEXTURE_BOUNDS");
        Cuda.Check(Cuda.cudaGraphicsMapResources(1,ref resource,0));
        try {
            Cuda.Check(Cuda.cudaGraphicsSubResourceGetMappedArray(out nint array,resource,0,0));
            Cuda.Check(Cuda.cudaMemcpy2DFromArray(pixels.Pointer,(nuint)(width*4),array,0,0,(nuint)(width*4),(nuint)height,3));
        } finally {Cuda.Check(Cuda.cudaGraphicsUnmapResources(1,ref resource,0));}
    }
    public void Dispose() {if(resource!=0) {nint r=resource;resource=0;Cuda.Check(Cuda.cudaGraphicsUnregisterResource(r));} }
}
