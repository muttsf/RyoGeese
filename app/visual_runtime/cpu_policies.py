"""System memory is advisory. Guards concern the owned reader, not other apps."""
import ctypes
from ctypes import wintypes as w

class PhysicalMemory(ctypes.Structure):
    _fields_=[('length',w.DWORD),('loadPercent',w.DWORD)]+[(x,ctypes.c_ulonglong) for x in ('totalPhysical','availablePhysical','totalPageFile','availablePageFile','totalVirtual','availableVirtual','availableExtendedVirtual')]

def memory_status():
    item=PhysicalMemory();item.length=ctypes.sizeof(item)
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GlobalMemoryStatusEx.argtypes=[ctypes.POINTER(PhysicalMemory)];api.GlobalMemoryStatusEx.restype=w.BOOL
    if not api.GlobalMemoryStatusEx(ctypes.byref(item)):raise ctypes.WinError(ctypes.get_last_error())
    return dict(availablePhysicalMiB=item.availablePhysical/1048576,availableCommitMiB=item.availablePageFile/1048576,loadPercent=item.loadPercent)

def start_assessment(status):
    # No amount of free physical memory is a startup prerequisite.
    return dict(allowed=True,systemMemoryHardGate=False,status=status,
        warning='SYSTEM_MEMORY_PRESSURE_ADVISORY' if status.get('loadPercent',0)>=90 else None)

class OwnedMemoryGuard:
    def __init__(self):self.consecutive=0
    def observe(self,elapsed,private_mib,resident_mib):
        # Generous process-local ceilings catch runaway use, not ordinary 95% machine load.
        reason='OWNED_READER_MEMORY_RUNAWAY' if private_mib>6144 or resident_mib>3072 else None
        # Legitimate GPU-arena growth can increase process commit without the
        # same resident RAM growth. Do not mistake a +512MiB change for a leak.
        self.consecutive=self.consecutive+1 if reason else 0
        return reason if self.consecutive>=3 else None
