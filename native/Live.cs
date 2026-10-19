using System.Diagnostics;
using System.Text.Json;

namespace GpuDash;
internal static class Live
{
    internal static int Run(string root,string ready,int interval,int seconds) {
        SessionAssets.ConsumeReady(ready,root,interval,seconds);
        Console.InputEncoding=System.Text.Encoding.UTF8;Console.OutputEncoding=System.Text.Encoding.UTF8;
        using var control=new SessionControl();string session=Guid.NewGuid().ToString("N");long seq=0,revision=0;
        string stopReason="DURATION_COMPLETE";bool captureStopped=false;int exitCode=0;long started=Stopwatch.GetTimestamp();
        int hr=WindowsInterop.RoInitialize(1);System.Runtime.InteropServices.Marshal.ThrowExceptionForHR(hr);
        Capture? capture=null;DeviceBuffer? image=null;TextureBridge? bridge=null;KernelModule? kernels=null;Reader? reader=null;
        long NextSeq()=>seq=checked(seq+1);
        void Clear(string reason) => Emit(new{kind="clear",session,seq=NextSeq(),revision=control.Revision,reason,qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
        try {
            Emit(new{kind="initializing",session,qpcTicks=started,qpcFrequency=Stopwatch.Frequency,systemMemoryHardGate=false});
            using var assets=SessionAssets.Load(root);Cuda.InitializeLoader();
            var samples=new FailureSamples(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(ready))!,"failure_samples"),assets.RootElement);
            bridge=new TextureBridge();kernels=new KernelModule(Path.Combine(root,"gpu","dash.cu"));
            reader=new Reader(assets.RootElement,kernels,bridge.CudaDevice,Path.Combine(root,"证据"));
            Emit(new{kind="initializing",session,phase="GPU_MODEL_WARMING",qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
            double warmMs=reader.Warm();
            Emit(new{kind="initializing",session,phase="GPU_MODEL_READY",warmMs,qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
            if(control.Stop.IsSet)throw new OperationCanceledException("USER_STOP_DURING_INITIALIZATION");
            nint gameWindow=WindowsInterop.ExactGameWindow(allowMinimized:true);
            uint gamePid=WindowsInterop.WindowProcessId(gameWindow);
            Emit(new{kind="initializing",session,phase="GAME_WINDOW_SELECTED",window=(long)gameWindow,gamePid,
                visible=WindowsInterop.IsWindowVisible(gameWindow),minimized=WindowsInterop.IsIconic(gameWindow),
                qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
            var startupWindow=new StartupWindowWait(started);bool waitingReported=false;
            while(true) {
                if(control.Stop.IsSet)throw new OperationCanceledException("USER_STOP_DURING_WINDOW_WAIT");
                bool exists=WindowsInterop.IsWindow(gameWindow)&&WindowsInterop.WindowProcessId(gameWindow)==gamePid;
                bool visible=exists&&WindowsInterop.IsWindowVisible(gameWindow),minimized=exists&&WindowsInterop.IsIconic(gameWindow);
                string? windowState=startupWindow.Observe(Stopwatch.GetTimestamp(),exists,visible,minimized);
                if(windowState is null)break;
                if(windowState!="WAITING_FOR_GAME_WINDOW")throw new InvalidOperationException(windowState);
                if(!waitingReported) {
                    waitingReported=true;
                    Emit(new{kind="initializing",session,phase=windowState,window=(long)gameWindow,gamePid,visible,minimized,
                        startupTimeoutSeconds=StartupWindowWait.TimeoutSeconds,qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
                }
                control.Stop.Wait(100);
            }
            Emit(new{kind="initializing",session,phase="GAME_WINDOW_READY",window=(long)gameWindow,gamePid,
                waitedForRestore=waitingReported,qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
            capture=new Capture(bridge,gameWindow);started=Stopwatch.GetTimestamp();
            Emit(new{kind="capture_started",session,qpcTicks=started,qpcFrequency=Stopwatch.Frequency,pid=Environment.ProcessId,window=(long)capture.Window,intervalMs=interval,seconds,adapter=bridge.AdapterName,ageFilterEnabled=false,overrunPolicy="FINISH_CURRENT_THEN_NEXT",durationStarts="BEGIN_RECOMMENDATIONS",setupWaitSeconds=RunBudget.SetupWaitSeconds});
            var budget=new RunBudget(started,seconds);
            Geometry? globalGeometry=null;long ordinal=0,next=started,round=0,overruns=0;double lastMemoryAt=-10;object? mem=null;
            while(!control.Stop.IsSet) {
                long now=Stopwatch.GetTimestamp();
                bool pending=budget.RecommendationStarted==0;
                string? expired=budget.Observe(now,control.RecommendationsRequested);
                if(pending&&budget.RecommendationStarted!=0)Emit(new{kind="recommendations_started",session,qpcTicks=now,qpcFrequency=Stopwatch.Frequency,seconds});
                if(expired!=null){stopReason=expired;break;}
                if(now<next){control.Stop.Wait(TimeSpan.FromSeconds((double)(next-now)/Stopwatch.Frequency));continue;}
                long planned=next;next=checked(now+(long)(interval/1000.0*Stopwatch.Frequency));round=checked(round+1);
                Emit(new{kind="tick",session,round,revision=control.Revision,qpcTicks=now,qpcFrequency=Stopwatch.Frequency,plannedTicks=planned,skippedSlots=0,overrunRounds=overruns});
                if(capture.Failure is string fatal)throw new InvalidOperationException(fatal);
                bool resized=capture.ApplyResize();
                if(control.Revision!=revision||resized) {
                    if(!resized)capture.SetRegion(null);globalGeometry=null;ordinal=0;revision=control.Revision;Clear("RELOCATING");
                }
                if(WindowsInterop.IsIconic(capture.Window)){Clear("GAME_WINDOW_MINIMIZED");FinishRound();continue;}
                Region? pendingCrop=null;ReadResult? result=null;FrameStamp? stamp=null;long copyComplete=0;
                using(var lease=capture.Bank.Take(ordinal)) {
                    if(lease is null){Clear("NO_NEW_FRAME");FinishRound();continue;}
                    stamp=lease.Stamp;ordinal=stamp.Ordinal;
                    
                    long bytes=4L*stamp.Region.Width*stamp.Region.Height;
                    if(image is null||image.Bytes!=(nuint)bytes){image?.Dispose();image=new DeviceBuffer(bytes);}
                    copyComplete=lease.CopyTo(image);
                    if(globalGeometry is null) {
                        try {
                            globalGeometry=Locator.Find(kernels,image,stamp.Region.Width,stamp.Region.Height);
                            int x=Math.Max(0,(int)Math.Floor(globalGeometry.Left)-4),y=Math.Max(0,(int)Math.Floor(globalGeometry.Top)-4);
                            int right=Math.Min(stamp.WindowWidth,(int)Math.Ceiling(globalGeometry.Left+578*globalGeometry.Scale)+4),bottom=Math.Min(stamp.WindowHeight,(int)Math.Ceiling(globalGeometry.Top+306*globalGeometry.Scale)+4);
                            pendingCrop=new(x,y,right-x,bottom-y);
                        }catch(InvalidOperationException ex) when(ex.Message.StartsWith("NO_UNIQUE_MARKERS")||ex.Message.StartsWith("LOCATOR_CANDIDATE_OVERFLOW")) {
                            Clear("LOCATE_FAILED:"+ex.Message);FinishRound();continue;
                        }
                    }
                    var local=globalGeometry with{Left=globalGeometry.Left-stamp.Region.X,Top=globalGeometry.Top-stamp.Region.Y};
                    result=reader.Read(image,stamp.Region.Width,stamp.Region.Height,local);
                    samples.Save(kernels,image,stamp.Region.Width,stamp.Region.Height,result,round);
                }
                long done=Stopwatch.GetTimestamp();double age=Stopwatch.GetElapsedTime(stamp!.ReceivedTicks,done).TotalMilliseconds;
                if(control.Revision!=revision)Clear("RELOCATE_FENCE");
                
                else {
                    if(Stopwatch.GetElapsedTime(started).TotalSeconds-lastMemoryAt>=1){try{mem=Memory.Snapshot("live");}catch(Exception ex){mem=new{error=ex.Message};}lastMemoryAt=Stopwatch.GetElapsedTime(started).TotalSeconds;}
                    Emit(new{kind="facts",session,seq=NextSeq(),revision,round,sourceOrdinal=stamp.Ordinal,generation=stamp.Generation,sourceAgeVerified=false,
                        nativeFrameTicks=stamp.NativeTicks,receivedTicks=stamp.ReceivedTicks,copyQueuedTicks=stamp.CopyQueuedTicks,copyCompleteTicks=copyComplete,qpcTicks=done,qpcFrequency=Stopwatch.Frequency,
                        plannedTicks=planned,wakeTicks=now,receivedAgeMs=age,readMs=result!.milliseconds,latenessMs=Stopwatch.GetElapsedTime(planned,now).TotalMilliseconds,
                        skippedSlots=0,overrunRounds=overruns,captureArrivals=capture.Arrivals,gpuCopies=capture.Admitted,region=stamp.Region,geometry=globalGeometry,facts=result.facts,retries=result.retries,memory=mem,
                        purpose="VISUAL_FACTS_TEST_NO_RECOMMENDATION_NO_GAME_INPUT"});
                }
                if(pendingCrop!=null&&control.Revision==revision)capture.SetRegion(pendingCrop);
                FinishRound();
                void FinishRound(){long tick=Stopwatch.GetTimestamp();if(next<tick){overruns++;next=tick;}}
            }
            if(control.Stop.IsSet)stopReason="USER_STOP_OR_PARENT_EOF";
            // Release capture registrations while the owning device/context are still alive.
            image?.Dispose();image=null;capture.Dispose();capture=null;captureStopped=true;
        } catch(OperationCanceledException ex) when(control.Stop.IsSet) {
            stopReason=ex.Message;
        } catch(Exception ex) {
            exitCode=2;stopReason=ex.GetType().Name+":"+ex.Message;Emit(new{kind="error",session,reason=stopReason,qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
        } finally {
            try{image?.Dispose();}catch(Exception ex){exitCode=3;stopReason+=";IMAGE_CLEANUP:"+ex.Message;}
            try{if(capture is not null){capture.Dispose();captureStopped=true;}}catch(Exception ex){exitCode=3;stopReason+=";CAPTURE_CLEANUP:"+ex.Message;}
            foreach(var resource in new IDisposable?[]{reader,kernels,bridge})try{resource?.Dispose();}catch(Exception ex){exitCode=3;stopReason+=";GPU_CLEANUP:"+ex.Message;}
            Clear(stopReason);Emit(new{kind="stopped",session,reason=stopReason,captureStopped,qpcTicks=Stopwatch.GetTimestamp(),qpcFrequency=Stopwatch.Frequency});
            WindowsInterop.RoUninitialize();
        }
        return exitCode;
    }
    internal static void Emit(object packet)=>Console.WriteLine(JsonSerializer.Serialize(packet));
}
