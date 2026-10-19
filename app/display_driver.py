"""Consume delivered FIFO decisions on Tk; no freshness or ordering policy."""
from pipeline_types import Outcome
from sequential_worker import Failure

class DisplayDriver:
    def __init__(self,root,state,worker,on_view,interval_ms=10,on_error=None):
        self.root=root;self.state=state;self.worker=worker;self.on_view=on_view
        self.interval_ms=interval_ms;self.on_error=on_error;self.after_id=None
        self.after_render=None;self.running=False;self.last_view=None;self.worker_stopped=None

    def _publish(self):
        view=self.state.view()
        if view!=self.last_view:self.on_view(view);self.last_view=view

    def start(self):
        self.state._owner()
        if not self.running:self.running=True;self.after_id=self.root.after(0,self._step)

    def _step(self):
        self.after_id=None
        if not self.running:return
        try:
            notice=self.worker.take()
            if isinstance(notice,Outcome):
                if self.state.accept(notice):
                    self._publish()
                    if self.after_render:
                        from visual_backend import qpc_ns
                        self.after_render(notice,qpc_ns())
            elif isinstance(notice,Failure):
                self.state.stop('DECISION_ERROR:'+notice.reason)
                self._publish()
                if self.on_error:self.on_error()
            self._publish()
            if self.state.terminal:
                self.running=False;self.worker_stopped=self.worker.close(0)
            else:self.after_id=self.root.after(self.interval_ms,self._step)
        except Exception:
            self.state.stop('DISPLAY_ERROR');self.running=False
            self.worker_stopped=self.worker.close(0)
            if self.on_error:self.on_error()
            else:self.root.destroy()
            raise

    def stop(self,reason='STOP'):
        self.running=False
        if self.after_id is not None:self.root.after_cancel(self.after_id);self.after_id=None
        self.state.stop(reason)
        try:self._publish()
        finally:self.worker_stopped=self.worker.close(0)
        return self.worker_stopped
