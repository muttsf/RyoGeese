using System.Text.Json;
using System.Diagnostics;

namespace GpuDash;
internal sealed class SessionControl:IDisposable
{
    internal readonly ManualResetEventSlim Stop=new(false);
    long revision;
    int recommendationsRequested;
    internal long Revision=>Interlocked.Read(ref revision);
    internal bool RecommendationsRequested=>Volatile.Read(ref recommendationsRequested)!=0;
    internal SessionControl() {
        new Thread(()=>{
            try {
                for(string? line;(line=Console.ReadLine())!=null;) {
                    if(line.Length>4096){Stop.Set();return;}
                    using var doc=JsonDocument.Parse(line);string cmd=doc.RootElement.GetProperty("command").GetString()!;
                    if(cmd=="stop"){Stop.Set();return;}
                    if(cmd=="begin_recommendations")Interlocked.Exchange(ref recommendationsRequested,1);
                    if(cmd=="relocate") {
                        long next=doc.RootElement.GetProperty("revision").GetInt64();
                        if(next>Revision)Interlocked.Exchange(ref revision,next);
                    }
                }
            } catch { } finally {Stop.Set();}
        }){IsBackground=true,Name="bounded-control"}.Start();
    }
    // The background read may still finish during shutdown; keep its managed event valid.
    public void Dispose()=>Stop.Set();
}
// Time belongs to the capture supervisor, never the recommendation or display.
internal sealed class RunBudget
{
    internal const int SetupWaitSeconds=600;
    readonly long captureStarted;readonly int seconds;
    internal long RecommendationStarted {get;private set;}
    internal RunBudget(long captureStarted,int seconds){this.captureStarted=captureStarted;this.seconds=seconds;}
    internal string? Observe(long now,bool requested) {
        if(requested&&RecommendationStarted==0)RecommendationStarted=now;
        if(RecommendationStarted!=0&&seconds==0)return null;
        long origin=RecommendationStarted==0?captureStarted:RecommendationStarted;
        double limit=RecommendationStarted==0?SetupWaitSeconds:seconds;
        if((double)(now-origin)/Stopwatch.Frequency<limit)return null;
        return RecommendationStarted==0?"SETUP_WAIT_TIMEOUT":"DURATION_COMPLETE";
    }
}
internal static class SessionAssets
{
    internal static JsonDocument Load(string root) {
        var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"assets_v2.json")));
        try {
            foreach(var pin in doc.RootElement.GetProperty("upstreamPins").EnumerateArray()) {
                var bytes=File.ReadAllBytes(PackagePaths.FileIn(root,pin.GetProperty("path").GetString()!));
                string hash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
                if(hash!=pin.GetProperty("SHA256").GetString())throw new InvalidOperationException("UPSTREAM_ASSET_CHANGED");
            }
            return doc;
        }catch{doc.Dispose();throw;}
    }
    internal static void ConsumeReady(string file,string root,int interval,int seconds) {
        if(interval!=500||(seconds!=0&&seconds<5)||seconds>3600)throw new ArgumentOutOfRangeException("LIVE_CONFIG_BOUNDS");
        using var ready=JsonDocument.Parse(File.ReadAllText(file));var r=ready.RootElement;
        if(r.GetProperty("candidateRoot").GetString()!=root||r.GetProperty("intervalMs").GetInt32()!=interval||r.GetProperty("seconds").GetInt32()!=seconds||r.GetProperty("humanReady").GetBoolean()!=true)
            throw new InvalidOperationException("READY_BINDING_MISMATCH");
        var age=DateTimeOffset.UtcNow-DateTimeOffset.Parse(r.GetProperty("readyUTC").GetString()!,System.Globalization.CultureInfo.InvariantCulture);
        if(age<TimeSpan.Zero||age>TimeSpan.FromMinutes(3))throw new InvalidOperationException("READY_NOT_CURRENT");
        // CreateNew consumes exactly once, including a later startup failure; no automatic retry.
        using var marker=new FileStream(file+".consumed",FileMode.CreateNew,FileAccess.Write,FileShare.Read);
        using var writer=new StreamWriter(marker);writer.Write(DateTimeOffset.UtcNow.ToString("O"));
    }
}
