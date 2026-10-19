"""Current recommendation session; configuration belongs to DesktopApp."""
import collections,json,tkinter as tk
from tkinter import ttk
from app_support import ROOT,SKILLS
from recommendation_window import RecommendationWindow
from presentation_state import PresentationState
from pipeline_types import Stamp
from sequential_worker import SequentialWorker
from session_evaluator import SessionEvaluator
from recommendation_log import CurrentLog
from live_input import map_facts,frame_times
from shutdown import request_close
from location_feedback import location_ready

def clear_stage(root):
    root.overrideredirect(False)
    for child in root.winfo_children():
        if not isinstance(child,tk.Toplevel):child.destroy()

class Session:
    def __init__(self,flow,profile,keys):
        self.flow=flow;self.root=flow.root;self.profile=profile;self.keys=keys
        self.window=None;self.closed=False;self.after=None;self.sequence=0;self.last_source=None;self.native_session=None;self.required_revision=0
        self.close_after=None;self.close_callback=None;self.close_complete=False;self.cleanup_errors=[]
        self.location_pending=True
        from visual_backend import qpc_ns
        self.state=PresentationState(SKILLS,keymap=keys)
        self.state.start('QPC_NS_FIFO_NO_DISPLAY_TTL');self.state.set_profile(profile.identity)
        self.timings=collections.deque(maxlen=4096);self.timing_dropped=0;self.input_issues=collections.Counter()
        parent=getattr(flow,'session_root',ROOT/('demo_sessions' if flow.preview else 'short_sessions' if getattr(flow,'short_validation',False) else 'sessions'))
        run=parent/self.state.session
        debug_logs=getattr(flow,'debug_logs',True)
        if debug_logs:run.mkdir(parents=True)
        self.run=run
        bundle=json.loads(profile.bundle_json)
        self.current_log=CurrentLog(run/'recommendations.jsonl',compact=not debug_logs,
            logs=getattr(flow,'log_files',None),configuration={k:bundle[k] for k in ('talentProfile','gearProfile')},
            context=dict(profile=profile.identity,session=self.state.session))
        self.evaluator=SessionEvaluator(profile,self.current_log,controls=self.state.controls)
        self.worker=SequentialWorker(self.evaluator,after_publish=self.evaluator.after_publish,prepare_work=self.evaluator.prepare_work)
        if flow.backend_factory is None:
            from visual_backend import VisualBackend
            factory=VisualBackend
        else:factory=flow.backend_factory
        try:self.backend=factory(self.root)
        except Exception:
            self.worker.close(0);self.current_log.close();raise
        clear_stage(self.root);self.root.title('启动预热');self.root.geometry('650x230');self.root.minsize(580,210)
        self.warm_frame=ttk.Frame(self.root,padding=24);self.warm_frame.pack(fill='both',expand=True)
        ttk.Label(self.warm_frame,text='正在准备推荐',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w')
        self.message=tk.StringVar(value='核验运行文件，然后预热GPU并定位Dash；尚无推荐。')
        ttk.Label(self.warm_frame,textvariable=self.message,wraplength=590).pack(anchor='w',pady=18)
        text='停止本次短验' if getattr(flow,'short_validation',False) else '取消并返回按键'
        self.cancel_button=ttk.Button(self.warm_frame,text=text,command=lambda:self.close(lambda:flow.keys(profile)))
        self.cancel_button.pack(anchor='e')
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        try:
            self.backend.start()
            begin=getattr(self.backend,'begin_recommendations',None)
            if begin:begin()
        except Exception as ex:self.message.set('启动失败：'+str(ex));self.state.stop('START_FAILED');return
        self.after=self.root.after(10,self.pulse)
    def show_window(self):
        clear_stage(self.root)
        self.window=RecommendationWindow(self.root,self.state,self.worker,preview=self.flow.preview,
            on_locate=self.relocate,on_config=lambda:self.close(self.flow.profile),
            on_keys=lambda:self.close(lambda:self.flow.keys(self.profile)),on_close=self.close)
        self.window.driver.after_render=self.after_display
        self.window.start()
    def pulse(self):
        self.after=None
        if self.closed:return
        try:
            # Do not consume the stream's next item until its receiving stage has room.
            packet,reason,terminal,error,banner=self.backend.view() if self.worker.has_capacity() else (None,'DECISION_QUEUE_BUSY',False,None,'')
            if terminal:
                panel=getattr(self.backend,'panel',None)
                stopped=getattr(panel,'worker_stopped',None) or {}
                normal=(reason=='DURATION_COMPLETE' or stopped.get('reason')=='DURATION_COMPLETE') and not error
                counts=self.worker.stats()
                draining=normal and (counts['pending'] or counts['completed'] or counts['inFlight'])
                if normal and not draining:
                    self.current_log.close()
                    draining=self.current_log.thread.is_alive()
                if not draining:self.state.stop(error or reason or 'VISUAL_STOP')
                if self.window:
                    self.window.runtime_status.set('正在完成本轮剩余推荐' if draining else '本轮读取已结束')
                    self.window.locate_button.configure(state='disabled')
                else:self.message.set('启动未完成：'+(error or banner or reason))
            elif packet is None:
                self.state.note_waiting(reason or 'WAITING_VISUAL_INPUT')
                if self.window:self.window.runtime_status.set('处理中' if reason=='DECISION_QUEUE_BUSY' else '等待下一次更新')
                else:self.message.set(banner)
            else:
                if self.window is None:self.show_window()
                self.admit(packet)
            if self.window:
                view=self.state.view()
                if view!=self.window.last_rendered_view:self.window.render(view)
        except Exception as ex:
            diagnostics=getattr(self.root._root(),'diagnostics',None)
            if diagnostics:diagnostics.exception('recommendation_session_error',type(ex),ex,ex.__traceback__)
            self.state.stop('SESSION_ERROR:'+type(ex).__name__)
            try:
                if self.root.winfo_exists():self.root.withdraw()
            except tk.TclError:pass  # the child can already have been destroyed
            getattr(self.flow,'cleanup_root',self.root).after_idle(self.close)
            return
        self.after=self.root.after(10,self.pulse)
    def admit(self,p):
        if type(p.get('revision')) is not int or p['revision']<self.required_revision:return
        source=(p.get('session'),p.get('revision'),p.get('generation'),p.get('sourceOrdinal'))
        if self.native_session is None:self.native_session=p.get('session')
        if type(self.native_session) is not str or p.get('session')!=self.native_session:raise ValueError('VISUAL_SESSION_CHANGED')
        if source==self.last_source:return
        self.last_source=source
        if self.location_pending and location_ready(p,self.required_revision):
            self.location_pending=False
            self.window.set_location_complete(True)
            diagnostics=getattr(self.root._root(),'diagnostics',None)
            if diagnostics:diagnostics.event('recommendation_location_completed',revision=p['revision'],generation=p.get('generation'),ordinal=p.get('sourceOrdinal'))
        try:
            from visual_backend import qpc,FREQUENCY
            tick=qpc();admitted=tick*1_000_000_000//FREQUENCY
            received,native,recognized=frame_times(p,admitted,tick,FREQUENCY)
            o=map_facts(p)
        except ValueError as ex:
            self.input_issues[str(ex)[:100]]+=1
            self.state.note_waiting(str(ex))
            self.window.runtime_status.set('等待有效识别；保留上次推荐');return
        self.sequence+=1
        started=p.get('wakeTicks',0)
        started_ns=started*1_000_000_000//FREQUENCY if type(started) is int and started>0 else 0
        stamp=Stamp(self.state.session,self.state.clock,p['revision'],p['generation'],self.sequence,p['sourceOrdinal'],received,native,recognized,admitted,started_ns)
        work=self.state.offer(stamp,o)
        if work and not self.worker.submit(work):raise RuntimeError('UNEXPECTED_DECISION_BACKPRESSURE')
        if work:self.window.runtime_status.set('读取中 · 每500毫秒一轮')
    def after_display(self,outcome,rendered_ns):
        work=outcome.work;stamp=work.stamp;detail=json.loads(outcome.details_json)
        timing=detail['timing']
        row=dict(job=work.job,sequence=stamp.sequence,revision=stamp.revision,generation=stamp.generation,ordinal=stamp.ordinal,
                 roundStartedQpcNs=stamp.round_started_ns,receivedQpcNs=stamp.received_ns,nativeQpcNs=stamp.native_ns,
                 recognizedQpcNs=stamp.recognized_ns,admittedQpcNs=stamp.admitted_ns,
                 evaluationBeginQpcNs=timing['evaluationBeginQpcNs'],evaluationEndQpcNs=timing['evaluationEndQpcNs'],
                 renderedQpcNs=rendered_ns,skill=outcome.skill)
        if len(self.timings)==self.timings.maxlen:self.timing_dropped+=1
        self.timings.append(row)
        self.current_log.record_display(outcome,rendered_ns)
        if self.current_log.error and getattr(self,'_reported_log_error',None)!=self.current_log.error:
            self._reported_log_error=self.current_log.error
            diagnostics=getattr(self.root._root(),'diagnostics',None)
            if diagnostics:diagnostics.event('recommendation_log_error',error=self.current_log.error,dropped=self.current_log.dropped)
        if rendered_ns-stamp.received_ns>=2_000_000_000:
            diagnostics=getattr(self.root._root(),'diagnostics',None)
            if diagnostics:diagnostics.event('pipeline_delay_observed',milliseconds=(rendered_ns-stamp.received_ns)/1e6,
                                             sequence=stamp.sequence,action='RECORDED_ONLY_NO_DROP')
    def relocate(self):
        self.state.invalidate('RELOCATING')
        self.worker.reset(self.state.fence)
        self.location_pending=True
        if self.window:
            self.window.set_location_complete(False)
            self.window.runtime_status.set('重新定位中；等待新画面')
        revision=self.backend.relocate()
        self.required_revision=revision if type(revision) is int else self.required_revision+1
    def close(self,on_done=None):
        if self.close_complete:return
        scheduler=getattr(self.flow,'cleanup_root',self.root)
        if not self.closed:
            self.closed=True;self.close_callback=on_done
            self.state.stop('SESSION_CLOSED')
            try:
                if self.after is not None:self.root.after_cancel(self.after);self.after=None
                if self.window:self.window.driver.stop('SESSION_CLOSED')
            except Exception as exc:
                self.cleanup_errors.append('关闭推荐窗：'+type(exc).__name__)
                try:self.root.withdraw()
                except tk.TclError:pass
            finally:
                self.worker.close(0)
                self.current_log.close()
        self.cleanup_errors.extend(request_close(self.backend))
        self.cleanup_errors=self.cleanup_errors[-8:]
        if self.cleanup_errors:
            notify=getattr(self.flow,'on_shutdown_error',None)
            if notify:notify('；'.join(self.cleanup_errors))
        if self.close_after is None:self._wait_closed(scheduler)

    def _wait_closed(self,scheduler):
        self.close_after=None
        try:ready=self.backend.closed()
        except Exception as exc:
            self.cleanup_errors.append('读取退出状态：'+type(exc).__name__)
            notify=getattr(self.flow,'on_shutdown_error',None)
            if notify:notify('；'.join(self.cleanup_errors[-8:]))
            return  # No false exit claim; an explicit Stop can retry.
        ready=ready and not self.worker.stats()['alive'] and not self.current_log.thread.is_alive()
        if not ready:
            self.close_after=scheduler.after(50,lambda:self._wait_closed(scheduler));return
        self.close_complete=True
        if self.close_callback:self.close_callback()
        elif self.root.winfo_exists():self.root.destroy()
