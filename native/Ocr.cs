using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using System.Diagnostics;
using System.Text.Json;

namespace GpuDash;

internal record ReadToken(string Text,double Confidence,string Method);
internal sealed unsafe class Ocr:IDisposable
{
    readonly InferenceSession session;
    readonly OrtMemoryInfo info;
    readonly KernelModule kernels;
    readonly string inputName,outputName;
    readonly string[] vocabulary;
    readonly bool tracing;
    readonly DeviceBuffer input=new(24*3*48*1024*4),specs=new(24*5*4),ids=new(24*64*4,true),scores=new(24*4,true),lengths=new(24*4,true);
    internal Ocr(JsonElement assets,KernelModule kernels,int device,string profileRoot) {
        Cuda.LoadModelLibraries();
        this.kernels=kernels;vocabulary=assets.GetProperty("vocabulary").EnumerateArray().Select(x=>x.GetString()!).ToArray();
        inputName=assets.GetProperty("inputName").GetString()!;outputName=assets.GetProperty("outputName").GetString()!;
        info=new OrtMemoryInfo("Cuda",OrtAllocatorType.DeviceAllocator,device,OrtMemType.Default);
        using var opts=new SessionOptions{IntraOpNumThreads=1,InterOpNumThreads=1,GraphOptimizationLevel=GraphOptimizationLevel.ORT_ENABLE_ALL,LogSeverityLevel=OrtLoggingLevel.ORT_LOGGING_LEVEL_ERROR};
        opts.AddSessionConfigEntry("session.intra_op.allow_spinning","0");opts.AddSessionConfigEntry("session.inter_op.allow_spinning","0");
        // ONNX's small shape/control nodes run on CPU. Image operators must stay on CUDA;
        // offline profiling below audits node type and transferred byte counts explicitly.
        tracing=Environment.GetEnvironmentVariable("DASH_OFFLINE_ORT_TRACE")=="1";
        if(tracing){opts.ProfileOutputPathPrefix=Path.Combine(profileRoot,"ort_gpu");opts.EnableProfiling=true;}
        // This is an on-demand GPU arena cap, not reserved CPU RAM. Leave room
        // for changing batch shapes and reuse coalescible arena chunks.
        using var cuda=new OrtCUDAProviderOptions();cuda.UpdateOptions(new Dictionary<string,string>{{"device_id",device.ToString()},{"gpu_mem_limit","2147483648"},{"arena_extend_strategy","kNextPowerOfTwo"},{"cudnn_conv_algo_search","HEURISTIC"},{"cudnn_conv_use_max_workspace","0"},{"use_tf32","0"}});
        opts.AppendExecutionProvider_CUDA(cuda);
        var model=assets.GetProperty("model");
        string file=PackagePaths.FileIn(PackagePaths.Reader,model.GetProperty("path").GetString()!);
        var hash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant();
        if(hash!=model.GetProperty("SHA256").GetString())throw new InvalidOperationException("MODEL_BYTES_CHANGED");
        session=new InferenceSession(file,opts);
    }
    // Warm CUDA/cuDNN before the capture clock starts. This synthetic GPU tensor
    // is never decoded or published as a game fact.
    internal double Warm() {
        var start=Stopwatch.GetTimestamp();input.Zero();
        using var tensor=OrtValue.CreateTensorValueWithData(info,TensorElementType.Float,new long[]{1,3,48,96},input.Pointer,3L*48*96*4);
        using var binding=session.CreateIoBinding();binding.BindInput(inputName,tensor);binding.BindOutputToDevice(outputName,info);
        using var run=new RunOptions();session.RunWithBinding(run,binding);binding.SynchronizeBoundOutputs();
        return Stopwatch.GetElapsedTime(start).TotalMilliseconds;
    }
    internal Dictionary<int,ReadToken> Read(DeviceBuffer images,int[] metadata,List<(int cell,int mode)> requested) {
        var results=new Dictionary<int,ReadToken>();
        double Ratio((int cell,int mode) x) {int o=x.cell*12+(x.mode==0?5:x.mode==1?7:9);return (double)metadata[o]/metadata[o+1];}
        var ordered=requested.OrderBy(Ratio).ToArray();
        for(int start=0;start<ordered.Length;start+=24) {
            var batch=ordered.Skip(start).Take(24).ToArray();
            int width=(int)(48*Math.Max(2,batch.Max(Ratio)));
            if(width<=0||width>1024)throw new InvalidOperationException("OCR_WIDTH_BOUND");
            var values=new List<int>();
            foreach(var item in batch) {
                int o=item.cell*12+(item.mode==0?5:item.mode==1?7:9),w=metadata[o],h=metadata[o+1];
                if(w<=0||h<=0)throw new InvalidOperationException("OCR_EMPTY_SHAPE");
                values.AddRange(new[]{item.cell,item.mode,w,h,Math.Min(width,(int)Math.Ceiling(48.0*w/h))});
            }
            specs.Upload(values.ToArray());
            kernels.Run("normalize",batch.Length*3*48*width,Cuda.Ptr(images.Pointer),Cuda.Ptr(specs.Pointer),(ulong)batch.Length,(ulong)width,Cuda.Ptr(input.Pointer));
            Cuda.Check(Cuda.cudaDeviceSynchronize());
            using var tensor=OrtValue.CreateTensorValueWithData(info,TensorElementType.Float,new long[]{batch.Length,3,48,width},input.Pointer,batch.Length*3L*48*width*4);
            using var binding=session.CreateIoBinding();binding.BindInput(inputName,tensor);binding.BindOutputToDevice(outputName,info);
            using var run=new RunOptions();
            try{session.RunWithBinding(run,binding);binding.SynchronizeBoundOutputs();}
            catch(OnnxRuntimeException ex){throw new InvalidOperationException($"OCR_GPU_RUN_FAILED:batch={batch.Length};width={width};"+ex.Message,ex);}
            using var output=binding.GetOutputValues();
            var pred=output.Single();var shape=pred.GetTensorTypeAndShape().Shape;
            if(shape.Length!=3||shape[0]!=batch.Length||shape[2]!=vocabulary.Length)throw new InvalidOperationException("OCR_OUTPUT_SHAPE");
            // This fixed statement takes the address of GPU memory; it does not dereference or copy the pixels/predictions.
            fixed(float* pointer=pred.GetTensorMutableDataAsSpan<float>())
                kernels.Run("ctc",batch.Length,(ulong)pointer,(ulong)batch.Length,(ulong)shape[1],(ulong)shape[2],Cuda.Ptr(ids.Pointer),Cuda.Ptr(scores.Pointer),Cuda.Ptr(lengths.Pointer));
            var tokenIds=ids.Metadata<int>(batch.Length*64);var confidence=scores.Metadata<float>(batch.Length);var count=lengths.Metadata<int>(batch.Length);
            for(int b=0;b<batch.Length;b++) {
                if(count[b]<0||count[b]>64)throw new InvalidOperationException("CTC_TOKEN_BOUND");
                string text=string.Concat(tokenIds.Skip(b*64).Take(count[b]).Select(i=>vocabulary[i]));
                results[batch[b].cell]=new(text,confidence[b],"GPU_ONNX_CTC");
            }
        }
        return results;
    }
    public void Dispose() {
        if(tracing)session.EndProfiling();session.Dispose();info.Dispose();input.Dispose();specs.Dispose();ids.Dispose();scores.Dispose();lengths.Dispose();
    }
}
