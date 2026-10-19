using System.Runtime.InteropServices;

namespace GpuDash;
internal static class Memory
{
    [StructLayout(LayoutKind.Sequential)] struct Counters {
        public uint cb,faults;
        public nuint peakWorkingSet,workingSet,peakPaged,paged,peakNonPaged,nonPaged,pagefile,peakPagefile,privateCommit,privateWorkingSet;
        public ulong sharedCommit;
    }
    [DllImport("kernel32")] static extern nint GetCurrentProcess();
    [DllImport("psapi",SetLastError=true)] static extern bool GetProcessMemoryInfo(nint process,ref Counters counters,uint size);
    internal static object Snapshot(string phase) {
        Counters c=new(){cb=(uint)Marshal.SizeOf<Counters>()};
        if(!GetProcessMemoryInfo(GetCurrentProcess(),ref c,c.cb))throw new System.ComponentModel.Win32Exception();
        Cuda.Check(Cuda.cudaMemGetInfo(out nuint free,out nuint total));
        return new{phase,workingSetBytes=(ulong)c.workingSet,privateWorkingSetBytes=(ulong)c.privateWorkingSet,privateCommitBytes=(ulong)c.privateCommit,sharedCommitBytes=c.sharedCommit,gpuFreeBytes=(ulong)free,gpuTotalBytes=(ulong)total};
    }
}
