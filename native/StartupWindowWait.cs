using System.Diagnostics;

namespace GpuDash;

// Startup-only readiness. Does not affect live facts, decisions or display.
internal sealed class StartupWindowWait
{
    internal const int TimeoutSeconds=120;
    readonly long started;
    internal StartupWindowWait(long startedAt) { started=startedAt; }
    internal string? Observe(long now,bool exists,bool visible,bool minimized) {
        if(now-started>=TimeoutSeconds*Stopwatch.Frequency)return "GAME_WINDOW_NOT_READY_TIMEOUT";
        if(!exists)return "GAME_WINDOW_CLOSED_DURING_STARTUP";
        return visible&&!minimized?null:"WAITING_FOR_GAME_WINDOW";
    }
}
