"""Error-only background reporting. Storage availability is never a runtime gate."""
import faulthandler,queue,sys,threading,traceback
from log_files import LogFiles,default_logs,local_time

PRIVATE_KEYS={'simc','sourcetext','bundle_json','keymap','keybindings','keys','talents'}
def _safe(value,depth=0):
    if depth>4:return '[DEPTH_LIMIT]'
    if type(value) is dict:return {str(k)[:80]:_safe(v,depth+1) for k,v in list(value.items())[:32] if str(k).lower() not in PRIVATE_KEYS}
    if type(value) in (list,tuple):return [_safe(v,depth+1) for v in value[:32]]
    if value is None or type(value) in (bool,int):return value
    if type(value) is float:return value if abs(value)<float('inf') else None
    return str(value)[:8192]

class Diagnostics:
    def __init__(self,directory=None,probe=None,install_hooks=True,interval=1,logs=None):
        self.logs=logs or (LogFiles(directory) if directory is not None else default_logs())
        self.directory=self.run=self.logs.directory
        self.error=None;self.dropped=0;self._probe=probe;self._reader=None
        self._queue=queue.Queue(maxsize=256);self._stop=threading.Event();self._fatal=None;self._owns_fatal=False
        self._old_sys=self._old_thread=self._sys_hook=self._thread_hook=None
        if install_hooks:self._install_hooks()
        self._thread=threading.Thread(target=self._loop,name='error-log',daemon=True);self._thread.start()

    @property
    def healthy(self):return self._thread.is_alive() and self.error is None and self.logs.error is None

    def event(self,kind,**data):
        name=str(kind)[:80];low=name.lower()
        report=any(word in low for word in ('error','fail','exception','timeout','forced','fault'))
        report=report or name.endswith('stderr') or name=='pipeline_delay_observed' or bool(data.get('error')) or data.get('exitCode') not in (None,0)
        if not report:return True
        if self._stop.is_set():return False
        try:self._queue.put_nowait(dict(时间=local_time(),kind=name,data=_safe(data)));return True
        except queue.Full:self.dropped+=1;self.error='报错日志队列已满；推荐继续。';return False

    def exception(self,kind,exc_type,exc,tb):
        try:text=''.join(traceback.format_exception(exc_type,exc,tb,limit=12))[-8192:]
        except Exception:text='TRACEBACK_FORMAT_FAILED'
        return self.event(kind,exceptionType=getattr(exc_type,'__name__','Exception'),traceback=text)

    def set_reader(self,process,run):self._reader=process
    def _loop(self):
        while not self._stop.is_set() or not self._queue.empty():
            try:item=self._queue.get(timeout=.1)
            except queue.Empty:continue
            try:
                if self._probe is None:
                    from resource_probe import ResourceProbe
                    self._probe=ResourceProbe()
                item['资源快照']=_safe(self._probe.sample(process=self._reader))
            except Exception as exc:item['资源快照']='不可用：'+type(exc).__name__
            self.error=None if self.logs.write('报错',item) else self.logs.error

    def _install_hooks(self):
        self._old_sys,self._old_thread=sys.excepthook,threading.excepthook
        def main_hook(kind,exc,tb):
            self.exception('UNHANDLED_MAIN_EXCEPTION',kind,exc,tb)
            self._old_sys(kind,exc,tb)
        def thread_hook(args):
            self.exception('UNHANDLED_THREAD_EXCEPTION',args.exc_type,args.exc_value,args.exc_traceback)
            self._old_thread(args)
        self._sys_hook,self._thread_hook=main_hook,thread_hook
        sys.excepthook,threading.excepthook=main_hook,thread_hook
        if not faulthandler.is_enabled():
            self._fatal=self.logs.open_fatal()
            if self._fatal:
                try:faulthandler.enable(file=self._fatal[1],all_threads=True);self._owns_fatal=True
                except Exception as exc:self.error=type(exc).__name__;self.logs.close_fatal(self._fatal);self._fatal=None

    def close(self,normal=True):
        self._stop.set()
        if self._thread is not threading.current_thread():self._thread.join(1)
        if self._sys_hook is not None and sys.excepthook is self._sys_hook:sys.excepthook=self._old_sys
        if self._thread_hook is not None and threading.excepthook is self._thread_hook:threading.excepthook=self._old_thread
        if self._owns_fatal:faulthandler.disable();self._owns_fatal=False
        self.logs.close_fatal(self._fatal);self._fatal=None
        self.logs.close()
        return not self._thread.is_alive()
