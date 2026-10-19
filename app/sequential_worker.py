"""One FIFO evaluator, bounded waiting/results, and explicit control resets only."""
from collections import deque
from dataclasses import dataclass, replace
import threading
from pipeline_types import Work, Outcome

@dataclass(frozen=True)
class Failure:
    work: Work
    reason: str

class SequentialWorker:
    def __init__(self,evaluator,after_publish=None,capacity=32,prepare_work=None):
        if type(capacity) is not int or capacity<1:raise ValueError('INVALID_FIFO_CAPACITY')
        self.evaluator=evaluator;self.after_publish=after_publish;self.capacity=capacity;self.prepare_work=prepare_work
        self.condition=threading.Condition();self.pending=deque();self.completed=deque()
        self.closed=False;self.in_flight=None;self.fence=None;self.epoch=0
        self.submitted=self.evaluated=self.max_pending=self.discarded_on_reset=0
        self.discarded_on_close=self.after_publish_errors=0
        self.thread=threading.Thread(target=self._run,name='offline-recommendation',daemon=True)
        self.thread.start()

    def has_capacity(self):
        with self.condition:return not self.closed and len(self.pending)<self.capacity

    def submit(self,work):
        if not isinstance(work,Work):raise TypeError('IMMUTABLE_WORK_REQUIRED')
        with self.condition:
            if self.closed or len(self.pending)>=self.capacity:return False
            if self.fence is None:self.fence=work.fence
            if work.fence!=self.fence:raise ValueError('EXPLICIT_RESET_REQUIRED_FOR_FENCE_CHANGE')
            self.pending.append(work);self.submitted+=1
            self.max_pending=max(self.max_pending,len(self.pending));self.condition.notify_all()
            return True

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.pending)
                if self.closed:return
                work=self.pending.popleft();epoch=self.epoch;self.in_flight=work
                self.condition.notify_all()
            try:
                if self.prepare_work is not None:
                    prepared=self.prepare_work(work)
                    if not isinstance(prepared,Work) or replace(prepared,mode=work.mode,control_version=work.control_version)!=work:
                        raise ValueError('PREPARE_WORK_IDENTITY')
                    work=prepared
                result=self.evaluator(work)
                if not isinstance(result,Outcome) or result.work!=work:raise ValueError('EVALUATOR_RESULT_IDENTITY')
            except Exception as exc:
                result=Failure(work,type(exc).__name__+':'+str(exc)[:160])
            with self.condition:
                self.evaluated+=1
                self.condition.wait_for(lambda:self.closed or epoch!=self.epoch or len(self.completed)<self.capacity)
                published=not self.closed and epoch==self.epoch and work.fence==self.fence
                if published:self.completed.append(result)
                elif self.closed:self.discarded_on_close+=1
                else:self.discarded_on_reset+=1
                self.condition.notify_all()
            if published and isinstance(result,Outcome) and self.after_publish is not None:
                try:self.after_publish(work,result)
                except Exception:
                    with self.condition:self.after_publish_errors+=1
            with self.condition:self.in_flight=None;self.condition.notify_all()

    def take(self):
        with self.condition:
            result=self.completed.popleft() if self.completed else None
            self.condition.notify_all();return result

    def reset(self,fence):
        if type(fence) is not int or fence<0:raise ValueError('INVALID_RESET_FENCE')
        with self.condition:
            count=len(self.pending)+len(self.completed)
            self.discarded_on_reset+=count;self.pending.clear();self.completed.clear()
            self.fence=fence;self.epoch+=1;self.condition.notify_all()
            return count

    def stats(self):
        with self.condition:
            return dict(pending=len(self.pending),completed=len(self.completed),inFlight=int(self.in_flight is not None),
                capacity=self.capacity,submitted=self.submitted,evaluated=self.evaluated,maxPending=self.max_pending,
                discardedOnReset=self.discarded_on_reset,discardedOnClose=self.discarded_on_close,
                afterPublishErrors=self.after_publish_errors,closed=self.closed,alive=self.thread.is_alive())

    def close(self,timeout=0):
        with self.condition:
            if not self.closed:
                self.discarded_on_close+=len(self.pending)+len(self.completed)
                self.pending.clear();self.completed.clear();self.closed=True;self.condition.notify_all()
        if self.thread is not threading.current_thread():self.thread.join(timeout=max(0,float(timeout)))
        return not self.thread.is_alive()
