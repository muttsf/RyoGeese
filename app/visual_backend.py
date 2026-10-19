"""Reuse pinned v12 supervision. Construction/import never starts capture."""
import importlib.util,sys,os,tkinter as tk
from pathlib import Path
from app_support import ROOT

from package_paths import READER_ROOT,DOTNET
GPU_ROOT=READER_ROOT
NATIVE=ROOT/'visual_runtime'
for name in ('owned_process','display_state','journal','cpu_policies','fact_stream'):
    if name in sys.modules and Path(sys.modules[name].__file__).resolve().parent!=NATIVE:
        raise ValueError('FOREIGN_VISUAL_MODULE:'+name)
sys.path.insert(0,str(NATIVE))
spec=importlib.util.spec_from_file_location('candidate_gpu_panel',NATIVE/'gpu_panel.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
native.WORKER=GPU_ROOT/'bin/GpuDash.dll'
native.DOTNET=DOTNET

class VisualBackend:
    def __init__(self,root):
        self.diagnostics=getattr(root._root(),'diagnostics',None)
        diagnostics=self.diagnostics
        owner=self;self.streaming=False
        self.hidden=tk.Toplevel(root);self.hidden.withdraw()
        class Panel(native.Panel):
            def launch(self,interval,seconds,ready):
                # Bind this session to the packaged reader and its own assets.
                ready=dict(ready,candidateRoot=str(GPU_ROOT))
                super().launch(interval,seconds,ready)
                if owner.streaming:owner.begin_recommendations()
                if diagnostics:
                    if self.proc is not None:diagnostics.set_reader(self.proc,self.run)
                    else:diagnostics.event('reader_launch_failed',reason=self.receiver_error)
        self.debug_logs=getattr(root._root(),'ryogeese_debug_logs',False)
        self.temp_root=Path(os.environ['LOCALAPPDATA'])/'RyoGeese/reader_tmp'
        self.panel=Panel(self.hidden,detailed_logs=self.debug_logs,
            event_sink=None if diagnostics is None else diagnostics.event,
            run_parent=None if self.debug_logs else self.temp_root)
        self.hidden.withdraw();self.requested=False;self.temp_cleaned=False
        self.aborting=False;self.abort_reason=None
        self.exit_logged=False

    def start(self):
        if self.requested:raise ValueError('NO_AUTOMATIC_RETRY')
        if not native.WORKER.is_file() or not native.DOTNET.is_file():
            raise ValueError('视觉读取运行文件缺失，请核对本机运行环境。')
        if self.diagnostics:self.diagnostics.event('reader_preflight_requested')
        self.requested=True;self.panel.start()

    def view(self):
        if self.streaming:p,reason,ended=self.panel.state.take_view()
        else:p,reason=self.panel.state.view();ended=self.panel.state.terminal or self.panel.finished
        failed=self.panel.receiver_error
        if self.requested and self.panel.proc is None and self.panel.preflight is None:
            failed=failed or self.panel.banner.get()
        terminal=ended or bool(failed)
        return p,reason,terminal,failed,self.panel.banner.get()

    def begin_recommendations(self):
        self.panel.state.begin();self.streaming=True
        self.panel.send(dict(command='begin_recommendations'))

    def relocate(self):
        self.panel.relocate()
        return self.panel.state.revision
    def close(self):
        self.panel.state.clear('USER_STOP',terminal=True)
        if self.hidden.winfo_exists():self.panel.close()
        else:self.abort('VISUAL_WINDOW_DESTROYED')
    def abort(self,reason='NORMAL_CLOSE_FAILED'):
        # Only held Popen/job handles are used. Never reopen or kill by PID/name.
        self.aborting=True;self.abort_reason=reason
        if self.diagnostics:self.diagnostics.event('reader_forced_shutdown',reason=reason)
        panel=self.panel;panel.closing=True
        if panel.preflight is not None:panel.preflight.cancel.set()
        panel.state.clear(reason,terminal=True)
        try:
            if panel.job is not None:panel.job.close();panel.job=None
        finally:
            if panel.proc is not None and panel.proc.poll() is None:panel.proc.kill()
            try:self.hidden.withdraw()
            except tk.TclError:pass
    def closed(self):
        panel=self.panel
        if panel.preflight is not None and not panel.preflight.done.is_set():return False
        code=None if panel.proc is None else panel.proc.poll()
        ready=panel.proc is None or (code is not None and (panel.finished or self.aborting))
        if ready and panel.proc is not None and self.diagnostics and not self.exit_logged:
            self.exit_logged=True
            self.diagnostics.event('reader_process_exit',exitCode=code,nativeRun=None if panel.run is None else str(panel.run),
                                   supervisorFinished=panel.finished,forcedAbort=self.aborting)
        if ready and not self.debug_logs and panel.run is not None and not self.temp_cleaned:
            self.temp_cleaned=True
            try:
                run=panel.run
                if run.resolve().parent!=self.temp_root.resolve() or run.lstat().st_file_attributes&0x400:
                    raise OSError('UNEXPECTED_READER_TEMP_PATH')
                for name in ('ready.json','ready.json.consumed'):
                    path=run/name
                    if path.exists():
                        if path.lstat().st_file_attributes&0x400:raise OSError('REPARSE_READER_TEMP_FILE')
                        path.unlink()
                # Diagnostic/unknown files are retained; remove only an empty directory.
                if not any(run.iterdir()):run.rmdir()
            except OSError as exc:
                if self.diagnostics:self.diagnostics.event('reader_temp_cleanup_failed',error=type(exc).__name__)
        return ready

def qpc():return native.qpc()
FREQUENCY=native.FREQUENCY
def qpc_ns():return qpc()*1_000_000_000//FREQUENCY
