"""A held Popen handle and a kill-on-close job; no reopening PIDs or other apps."""
import ctypes
from ctypes import wintypes as w

k=ctypes.WinDLL('kernel32',use_last_error=True);ps=ctypes.WinDLL('psapi',use_last_error=True)
class Basic(ctypes.Structure):
    _fields_=[('processTime',ctypes.c_int64),('jobTime',ctypes.c_int64),('flags',w.DWORD),('minWS',ctypes.c_size_t),('maxWS',ctypes.c_size_t),('processLimit',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
class IO(ctypes.Structure):_fields_=[(x,ctypes.c_uint64) for x in ('readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes')]
class Extended(ctypes.Structure):_fields_=[('basic',Basic),('io',IO)]+[(x,ctypes.c_size_t) for x in ('processMemory','jobMemory','peakProcess','peakJob')]
class Counters(ctypes.Structure):
    _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(x,ctypes.c_size_t) for x in ('peakWS','workingSet','peakPaged','paged','peakNonpaged','nonpaged','pagefile','peakPagefile','private','privateWS')]+[('sharedCommit',ctypes.c_uint64)]
k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];k.CreateJobObjectW.restype=w.HANDLE
k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];k.SetInformationJobObject.restype=w.BOOL
k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];k.AssignProcessToJobObject.restype=w.BOOL
k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
ps.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(Counters),w.DWORD];ps.GetProcessMemoryInfo.restype=w.BOOL
k.QueryPerformanceCounter.argtypes=[ctypes.POINTER(ctypes.c_int64)];k.QueryPerformanceCounter.restype=w.BOOL
k.QueryPerformanceFrequency.argtypes=[ctypes.POINTER(ctypes.c_int64)];k.QueryPerformanceFrequency.restype=w.BOOL
k.GetCurrentProcess.restype=w.HANDLE
_frequency=ctypes.c_int64();k.QueryPerformanceFrequency(ctypes.byref(_frequency));FREQUENCY=_frequency.value
def qpc():
    value=ctypes.c_int64()
    if not k.QueryPerformanceCounter(ctypes.byref(value)):raise ctypes.WinError(ctypes.get_last_error())
    return value.value

def memory_for_handle(handle):
    item=Counters();item.cb=ctypes.sizeof(item)
    if not ps.GetProcessMemoryInfo(handle,ctypes.byref(item),item.cb):raise ctypes.WinError(ctypes.get_last_error())
    return dict(privateMiB=item.private/1048576,privateResidentMiB=item.privateWS/1048576,workingSetMiB=item.workingSet/1048576)

def panel_memory():return memory_for_handle(k.GetCurrentProcess())

class OwnedJob:
    def __init__(self,process):
        self.process=process;self.handle=k.CreateJobObjectW(None,None)
        try:
            if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
            limits=Extended();limits.basic.flags=0x2000
            if not k.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):raise ctypes.WinError(ctypes.get_last_error())
            if not k.AssignProcessToJobObject(self.handle,int(process._handle)):raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            process.kill()
            if self.handle:k.CloseHandle(self.handle);self.handle=None
            raise
    def memory(self):
        return memory_for_handle(int(self.process._handle))
    def close(self):
        if self.handle:k.CloseHandle(self.handle);self.handle=None
