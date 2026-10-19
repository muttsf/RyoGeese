using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

namespace GpuDash;

// Control/data pointers only. The live path never creates a host image buffer.
internal static unsafe class Cuda
{
    internal static string Packages => Path.Combine(PackagePaths.Root,"runtime","gpu");
    [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern nint AddDllDirectory(string path);
    [DllImport("kernel32", SetLastError=true)] static extern bool SetDefaultDllDirectories(uint flags);
    static readonly List<nint> Libraries = new();
    internal static void InitializeLoader()
    {
        if (!SetDefaultDllDirectories(0x1000)) throw new System.ComponentModel.Win32Exception();
        foreach (string path in Directory.GetDirectories(Path.Combine(Packages,"nvidia")))
        {
            var bin=Path.Combine(path,"bin");
            if(Directory.Exists(bin) && AddDllDirectory(bin)==0) throw new System.ComponentModel.Win32Exception();
        }
        AddDllDirectory(Path.Combine(Packages,"onnxruntime","capi"));
        NativeLibrary.SetDllImportResolver(typeof(Cuda).Assembly, Resolve);
        NativeLibrary.SetDllImportResolver(typeof(Microsoft.ML.OnnxRuntime.InferenceSession).Assembly, Resolve);
    }
    internal static void LoadModelLibraries() {
        // Only recognition needs these libraries; capture/crop does not load them.
        foreach(var name in new[]{"cublas64_12.dll","cublasLt64_12.dll","cudnn64_9.dll"})
        {
            var path=Directory.EnumerateFiles(Path.Combine(Packages,"nvidia"),name,SearchOption.AllDirectories).Single();
            Libraries.Add(NativeLibrary.Load(path));
        }
    }
    static nint Resolve(string name,Assembly assembly,DllImportSearchPath? flags)
    {
        string? path=name switch {
            "cudart" => Path.Combine(Packages,"nvidia","cuda_runtime","bin","cudart64_12.dll"),
            "nvrtc" => Path.Combine(Packages,"nvidia","cuda_nvrtc","bin","nvrtc64_120_0.dll"),
            "onnxruntime" => Path.Combine(Packages,"onnxruntime","capi","onnxruntime.dll"),
            _ => null};
        return path is null ? 0 : NativeLibrary.Load(path);
    }
    [DllImport("cudart")] internal static extern int cudaSetDevice(int device);
    [DllImport("cudart")] internal static extern int cudaD3D11GetDevice(out int device,nint adapter);
    [DllImport("cudart")] internal static extern int cudaMalloc(out nint pointer,nuint size);
    [DllImport("cudart")] internal static extern int cudaFree(nint pointer);
    [DllImport("cudart")] internal static extern int cudaMemset(nint pointer,int value,nuint size);
    [DllImport("cudart")] internal static extern int cudaMemcpy(nint dst,nint src,nuint size,int kind);
    [DllImport("cudart")] internal static extern int cudaMemcpy2DFromArray(nint dst,nuint pitch,nint src,nuint x,nuint y,nuint width,nuint height,int kind);
    [DllImport("cudart")] internal static extern int cudaDeviceSynchronize();
    [DllImport("cudart")] internal static extern int cudaMemGetInfo(out nuint free,out nuint total);
    [DllImport("cudart")] internal static extern int cudaGraphicsD3D11RegisterResource(out nint resource,nint d3d,uint flags);
    [DllImport("cudart")] internal static extern int cudaGraphicsUnregisterResource(nint resource);
    [DllImport("cudart")] internal static extern int cudaGraphicsMapResources(int count,ref nint resource,nint stream);
    [DllImport("cudart")] internal static extern int cudaGraphicsUnmapResources(int count,ref nint resource,nint stream);
    [DllImport("cudart")] internal static extern int cudaGraphicsSubResourceGetMappedArray(out nint array,nint resource,uint index,uint level);
    [DllImport("cudart")] static extern nint cudaGetErrorString(int code);
    internal static void Check(int code) { if(code!=0) throw new InvalidOperationException("CUDA:"+code+":"+Marshal.PtrToStringAnsi(cudaGetErrorString(code))); }
    [DllImport("nvcuda")] internal static extern int cuModuleLoadData(out nint module,nint data);
    [DllImport("nvcuda")] internal static extern int cuModuleUnload(nint module);
    [DllImport("nvcuda", CharSet=CharSet.Ansi)] internal static extern int cuModuleGetFunction(out nint function,nint module,string name);
    [DllImport("nvcuda")] internal static extern int cuLaunchKernel(nint func,uint gx,uint gy,uint gz,uint bx,uint by,uint bz,uint shared,nint stream,nint args,nint extra);
    [DllImport("nvrtc", CharSet=CharSet.Ansi)] static extern int nvrtcCreateProgram(out nint program,string source,string name,int count,nint headers,nint names);
    [DllImport("nvrtc")] static extern int nvrtcCompileProgram(nint program,int count,nint options);
    [DllImport("nvrtc")] static extern int nvrtcGetProgramLogSize(nint program,out nuint size);
    [DllImport("nvrtc")] static extern int nvrtcGetProgramLog(nint program,nint log);
    [DllImport("nvrtc")] static extern int nvrtcGetPTXSize(nint program,out nuint size);
    [DllImport("nvrtc")] static extern int nvrtcGetPTX(nint program,nint data);
    [DllImport("nvrtc")] static extern int nvrtcDestroyProgram(ref nint program);
    internal static nint Compile(string source,string? saveFile=null)
    {
        if(nvrtcCreateProgram(out nint p,source,"dash.cu",0,0,0)!=0) throw new InvalidOperationException("NVRTC_CREATE");
        var opts=new[]{"--gpu-architecture=compute_86","--std=c++14","--fmad=false"};
        var pointers=opts.Select(Marshal.StringToCoTaskMemUTF8).ToArray();
        try {
            fixed(nint* pp=pointers) {
                int result=nvrtcCompileProgram(p,opts.Length,(nint)pp);
                nvrtcGetProgramLogSize(p,out nuint size);
                byte[] log=new byte[checked((int)size)];
                fixed(byte* lp=log) nvrtcGetProgramLog(p,(nint)lp);
                if(result!=0) throw new InvalidOperationException("NVRTC_COMPILE:"+Encoding.UTF8.GetString(log));
            }
            if(nvrtcGetPTXSize(p,out nuint bytes)!=0) throw new InvalidOperationException("NVRTC_SIZE");
            byte[] ptx=new byte[checked((int)bytes)];
            fixed(byte* pt=ptx) {
                if(nvrtcGetPTX(p,(nint)pt)!=0) throw new InvalidOperationException("NVRTC_PTX");
                if(saveFile!=null)File.WriteAllBytes(saveFile,ptx);
                int result=cuModuleLoadData(out nint module,(nint)pt);
                if(result!=0) throw new InvalidOperationException("CUDA_MODULE:"+result);
                return module;
            }
        } finally { foreach(nint ptr in pointers) Marshal.FreeCoTaskMem(ptr); nvrtcDestroyProgram(ref p); }
    }
    internal static nint LoadCompiled(string file) {
        byte[] data=File.ReadAllBytes(file);
        fixed(byte* p=data){int c=cuModuleLoadData(out nint module,(nint)p);if(c!=0)throw new InvalidOperationException("CUDA_COMPILED_MODULE:"+c);return module;}
    }
    internal static void Launch(nint f,int count,params ulong[] values)
    {
        var pointers=new nint[values.Length];
        fixed(ulong* p=values) {
            for(int i=0;i<values.Length;i++) pointers[i]=(nint)(p+i);
            fixed(nint* pp=pointers) {
                int result=cuLaunchKernel(f,(uint)((count+255)/256),1,1,256,1,1,0,0,(nint)pp,0);
                if(result!=0) throw new InvalidOperationException("CUDA_LAUNCH:"+result);
            }
        }
    }
    internal static ulong Ptr(nint p)=>(ulong)p;
    internal static ulong F(float value)=>(uint)BitConverter.SingleToInt32Bits(value);
}

internal sealed unsafe class DeviceBuffer:IDisposable
{
    internal nint Pointer {get;private set;}
    internal nuint Bytes {get;}
    readonly bool metadataRead;
    internal DeviceBuffer(long bytes,bool metadataRead=false) { if(bytes<=0 || bytes>512L*1024*1024) throw new ArgumentOutOfRangeException(nameof(bytes)); this.metadataRead=metadataRead;Bytes=(nuint)bytes; Cuda.Check(Cuda.cudaMalloc(out nint p,Bytes));Pointer=p; }
    internal void Zero()=>Cuda.Check(Cuda.cudaMemset(Pointer,0,Bytes));
    internal void Upload<T>(T[] values) where T:unmanaged { if((nuint)(values.Length*sizeof(T))>Bytes) throw new ArgumentException("GPU_UPLOAD_SIZE"); fixed(T* p=values) Cuda.Check(Cuda.cudaMemcpy(Pointer,(nint)p,(nuint)(values.Length*sizeof(T)),1)); }
    // Only bounded scalar metadata can cross D2H. A caller cannot download image pixels.
    internal T[] Metadata<T>(int count) where T:unmanaged {
        if(!metadataRead || count<0 || count*sizeof(T)>32768 || (nuint)(count*sizeof(T))>Bytes) throw new ArgumentException("METADATA_BOUND_OR_IMAGE_DOWNLOAD_FORBIDDEN");
        T[] result=new T[count];fixed(T* p=result) Cuda.Check(Cuda.cudaMemcpy((nint)p,Pointer,(nuint)(count*sizeof(T)),2));return result;
    }
    public void Dispose() { if(Pointer!=0) { nint p=Pointer;Pointer=0;Cuda.Check(Cuda.cudaFree(p)); } }
}

internal sealed class KernelModule:IDisposable
{
    readonly nint module;
    readonly Dictionary<string,nint> funcs=new();
    internal KernelModule(string file,bool compile=false) {
        string binary=Path.ChangeExtension(file,"ptx"),digest=binary+".source.sha256";
        string hash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant();
        if(compile){module=Cuda.Compile(File.ReadAllText(file),binary);File.WriteAllText(digest,hash);}
        else {
            if(!File.Exists(binary)||!File.Exists(digest)||File.ReadAllText(digest)!=hash)throw new InvalidOperationException("COMPILED_KERNEL_MISSING_OR_SOURCE_CHANGED");
            module=Cuda.LoadCompiled(binary);
        }
    }
    internal void Run(string name,int count,params ulong[] args) {
        if(!funcs.TryGetValue(name,out nint f)) { int c=Cuda.cuModuleGetFunction(out f,module,name);if(c!=0)throw new InvalidOperationException("CUDA_FUNCTION:"+name+":"+c);funcs[name]=f; }
        Cuda.Launch(f,count,args);
    }
    public void Dispose()=>Cuda.cuModuleUnload(module);
}
