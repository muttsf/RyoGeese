"""Read-only Windows CPU/RAM counters from held handles; no sampling on import."""
import ctypes as C
from ctypes import wintypes as W
import os
import time

MIB=1024*1024

def unknown(reason):return dict(status='UNKNOWN',reason=str(reason)[:240])

class MemoryCounters(C.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(n,C.c_size_t) for n in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]

class Performance(C.Structure):
    _fields_=[('cb',W.DWORD)]+[(n,C.c_size_t) for n in
        ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
         'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
        ('HandleCount',W.DWORD),('ProcessCount',W.DWORD),('ThreadCount',W.DWORD)]

def _ticks(ft):return (ft.dwHighDateTime<<32)|ft.dwLowDateTime
def _checked(result):
    if not result:raise C.WinError(C.get_last_error())

class ResourceProbe:
    def __init__(self):
        self.previous={};self.reader=None;self.error=None
        try:
            self.kernel=C.WinDLL('kernel32',use_last_error=True)
            self.psapi=C.WinDLL('psapi',use_last_error=True)
            ft=C.POINTER(W.FILETIME)
            declarations=((self.kernel,'GetCurrentProcess',[],W.HANDLE),
                (self.kernel,'GetActiveProcessorCount',[W.WORD],W.DWORD),
                (self.kernel,'GetSystemTimes',[ft,ft,ft],W.BOOL),
                (self.kernel,'GetProcessTimes',[W.HANDLE,ft,ft,ft,ft],W.BOOL),
                (self.psapi,'GetProcessMemoryInfo',[W.HANDLE,C.POINTER(MemoryCounters),W.DWORD],W.BOOL),
                (self.psapi,'GetPerformanceInfo',[C.POINTER(Performance),W.DWORD],W.BOOL))
            for dll,name,args,result in declarations:
                function=getattr(dll,name);function.argtypes=args;function.restype=result
            self.processors=int(self.kernel.GetActiveProcessorCount(0xffff))
            if not self.processors:raise C.WinError(C.get_last_error())
        except Exception as exc:self.error=type(exc).__name__+':'+str(exc)

    def _system_cpu(self):
        if self.processors>64:return dict(unknown('PROCESSOR_GROUPS_OVER_64_UNSUPPORTED'),percent=None)
        idle,kernel,user=(W.FILETIME() for _ in range(3))
        _checked(self.kernel.GetSystemTimes(C.byref(idle),C.byref(kernel),C.byref(user)))
        current=(_ticks(idle),_ticks(kernel)+_ticks(user));previous=self.previous.get('system')
        self.previous['system']=current
        if previous is None:return dict(unknown('FIRST_SAMPLE_BASELINE'),percent=None)
        di,dt=current[0]-previous[0],current[1]-previous[1]
        if dt<=0 or not 0<=di<=dt:return dict(unknown('INVALID_CPU_INTERVAL'),percent=None)
        return dict(status='KNOWN',percent=100*(dt-di)/dt,scope='SYSTEM_ALL_LOGICAL_PROCESSORS')

    def _memory(self):
        value=Performance();value.cb=C.sizeof(value)
        _checked(self.psapi.GetPerformanceInfo(C.byref(value),value.cb))
        if not value.PageSize or value.CommitLimit<value.CommitTotal:raise ValueError('INVALID_MEMORY_COUNTERS')
        scale=value.PageSize/MIB
        return dict(status='KNOWN',physicalTotalMiB=value.PhysicalTotal*scale,
            physicalAvailableMiB=value.PhysicalAvailable*scale,commitTotalMiB=value.CommitTotal*scale,
            commitLimitMiB=value.CommitLimit*scale,commitAvailableMiB=(value.CommitLimit-value.CommitTotal)*scale)

    def _process(self,handle,key,pid):
        memory=MemoryCounters();memory.cb=C.sizeof(memory)
        _checked(self.psapi.GetProcessMemoryInfo(handle,C.byref(memory),memory.cb))
        created,exited,kernel,user=(W.FILETIME() for _ in range(4))
        _checked(self.kernel.GetProcessTimes(handle,C.byref(created),C.byref(exited),C.byref(kernel),C.byref(user)))
        now=time.perf_counter_ns();ticks=_ticks(kernel)+_ticks(user);previous=self.previous.get(key)
        self.previous[key]=(now,ticks);cpu=None;reason='FIRST_SAMPLE_BASELINE'
        if self.processors>64:reason='PROCESSOR_GROUPS_OVER_64_UNSUPPORTED'
        elif previous is not None:
            dt,used=now-previous[0],ticks-previous[1]
            if dt>0 and used>=0:
                value=used*10000/(dt*self.processors)
                if 0<=value<=100:cpu=value;reason=None
                else:reason='INVALID_CPU_INTERVAL'
            else:reason='INVALID_CPU_INTERVAL'
        return dict(status='KNOWN',pid=pid,cpuPercent=cpu,cpuStatus='KNOWN' if cpu is not None else 'UNKNOWN',
            cpuReason=reason,cpuScope='PROCESS_NORMALIZED_TO_SYSTEM',privateCommitMiB=memory.PrivateUsage/MIB,
            workingSetMiB=memory.WorkingSetSize/MIB)

    def sample(self,process=None):
        started=time.perf_counter_ns()
        result=dict(logicalProcessors=getattr(self,'processors',None),scope='READ_ONLY_WIN32_HELD_PROCESS_HANDLES')
        for name,read in (('systemCPU',self._system_cpu),('systemMemory',self._memory),
                          ('mainProcess',lambda:self._process(self.kernel.GetCurrentProcess(),'main',os.getpid()))):
            try:result[name]=unknown(self.error) if self.error else read()
            except Exception as exc:result[name]=unknown(type(exc).__name__+':'+str(exc))
        if process is not self.reader:self.previous.pop('reader',None);self.reader=process
        try:
            if process is None:result['readerProcess']=unknown('NO_OWNED_READER')
            else:
                code=process.poll()
                if code is not None:result['readerProcess']=dict(status='EXITED',pid=process.pid,exitCode=code)
                elif self.error:result['readerProcess']=unknown(self.error)
                else:result['readerProcess']=self._process(int(process._handle),'reader',process.pid)
        except Exception as exc:result['readerProcess']=unknown(type(exc).__name__+':'+str(exc))
        result['sampleDurationMs']=(time.perf_counter_ns()-started)/1e6
        return result
