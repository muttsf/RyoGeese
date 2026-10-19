"""Desktop entry. Opening settings never starts capture."""
import sys
sys.dont_write_bytecode=True
import tkinter as tk
from tkinter import messagebox
import ctypes
import traceback
from ctypes import wintypes


class SingleInstance:
    """Keep repeated double-clicks from creating multiple GPU readers."""
    def __init__(self,name='Local\\AiHekiliDesktop'):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype=wintypes.HANDLE
        self.kernel.ReleaseMutex.argtypes=[wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.kernel.CreateMutexW(None,True,name)
        error=ctypes.get_last_error()
        if not self.handle:raise ctypes.WinError(error)
        self.acquired=error!=183
        if not self.acquired:self.kernel.CloseHandle(self.handle);self.handle=None

    def close(self):
        if self.handle:
            self.kernel.ReleaseMutex(self.handle)
            self.kernel.CloseHandle(self.handle)
            self.handle=None


def run_app(build_app):
    root=None
    instance=None
    diagnostics=None
    normal=False
    try:
        root=tk.Tk()
        root.withdraw()
        instance=SingleInstance()
        if not instance.acquired:
            messagebox.showinfo('RyoGeese已打开','请切回已经打开的RyoGeese窗口。',parent=root)
            root.destroy()
            return
        from diagnostics import Diagnostics
        diagnostics=Diagnostics()
        root.diagnostics=diagnostics
        def callback_error(typ,exc,tb):
            diagnostics.exception('tk_callback_exception',typ,exc,tb)
            if sys.stderr is not None:
                try:
                    traceback.print_exception(typ,exc,tb,file=sys.stderr)
                    sys.stderr.flush()
                except (OSError,ValueError):pass
        root.report_callback_exception=callback_error
        app=build_app(root)
        diagnostics.event('desktop_ready')
        root.deiconify()
        root.mainloop()
        normal=True
    except Exception as exc:
        if diagnostics:diagnostics.exception('startup_or_mainloop_exception',type(exc),exc,exc.__traceback__)
        messagebox.showerror('RyoGeese未能打开','程序文件或运行环境需要检查：\n'+str(exc),parent=root)
        if root is not None and root.winfo_exists():root.destroy()
    finally:
        if diagnostics:diagnostics.close(normal=normal)
        if instance:instance.close()


def main():
    def build(root):
        from desktop_app import DesktopApp
        return DesktopApp(root)
    run_app(build)


if __name__=='__main__':main()
