"""Bounded diagnostic queue; slow/failed logging never waits in the decision lane."""
import collections,json,threading
from log_files import default_logs,local_time

class CurrentLog:
    def __init__(self,path,compact=False,logs=None,configuration=None,context=None):
        self.compact=compact;self.logs=logs or default_logs();self.configuration=configuration or {}
        self.context=context or {}
        self.journal=None
        if not compact:
            from visual_backend import native
            self.journal=native.Journal(path)
        self.condition=threading.Condition();self.pending=collections.deque();self.capacity=256
        self.closed=False;self.error=None;self.written=0;self.dropped=0
        self.thread=threading.Thread(target=self._run,daemon=True,name='current-result-log');self.thread.start()

    def submit(self,work,outcome):
        from visual_backend import qpc_ns
        return self._offer(work,outcome,qpc_ns(),False)

    def record_display(self,outcome,rendered_ns):
        if not self.compact:return False
        return self._offer(outcome.work,outcome,rendered_ns,True)

    def _offer(self,work,outcome,observed,displayed):
        with self.condition:
            if self.closed:return False
            if len(self.pending)>=self.capacity:
                self.dropped+=1;self.error='LOG_QUEUE_FULL_RECOMMENDATIONS_CONTINUE';return False
            self.pending.append((work,outcome,observed,displayed));self.condition.notify_all();return True

    def _run(self):
        from app_support import ROOT,SKILLS
        if self.compact:
            try:version=json.loads((ROOT/'runtime_metadata.json').read_text('utf-8'))['version']
            except Exception as exc:
                version='UNKNOWN';self.error='LOG_VERSION:'+type(exc).__name__
            header_base=dict(kind='CONFIGURATION',schema='RyoGeese-recommendation/1',version=version,**self.configuration)
            # This writer also keeps the setup when no recommendation arrives.
            # All file I/O stays off the UI and decision threads.
            if self.context:
                try:
                    if not self.logs.write('推荐',dict(kind='SESSION_STARTED',时间=local_time()),dict(header_base,**self.context)):
                        self.error=self.logs.error;self.dropped+=1
                except Exception as exc:self.error=type(exc).__name__+':'+str(exc)[:160];self.dropped+=1
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or bool(self.pending))
                if not self.pending:return
                work,outcome,observed,displayed=self.pending.popleft()
            try:
                details=json.loads(outcome.details_json);current=details['recommendation'];observation=json.loads(work.observation_json)
                row=dict(kind='RECOMMENDATION_REPLAY',profile=work.profile_identity,
                    profileVersion=work.profile_version,controlVersion=work.control_version,mode=work.mode,
                    source=dict(session=work.stamp.session,revision=work.stamp.revision,generation=work.stamp.generation,
                                ordinal=work.stamp.ordinal,sequence=work.stamp.sequence,job=work.job),
                    observation=observation,current=current,
                    timing=dict(details['timing'],afterPublishObservedQpcNs=observed,receivedQpcNs=work.stamp.received_ns,
                                nativeQpcNs=work.stamp.native_ns,recognizedQpcNs=work.stamp.recognized_ns,admittedQpcNs=work.stamp.admitted_ns),
                    actualCastConfirmed=False)
                row['timing']['roundStartedQpcNs']=work.stamp.round_started_ns
                if displayed:
                    row=dict(kind='DISPLAY',profile=work.profile_identity,source=row['source'],skill=outcome.skill,
                        mode=work.mode,timing=dict(roundStartedQpcNs=work.stamp.round_started_ns,
                            receivedQpcNs=work.stamp.received_ns,renderedQpcNs=observed))
                if self.compact:
                    if not displayed:row['current']={k:v for k,v in current.items() if k not in ('profile','talentConfiguration','burstControl')}
                    row=dict(时间=local_time(),技能=SKILLS.get(current.get('skill'),''),爆发='暂缓' if work.mode=='hold' else '自动',
                             狂乱=observation.get('C2_current'),**row)
                    header=dict(header_base,profile=work.profile_identity,session=work.stamp.session)
                    if not self.logs.write('推荐',row,header):self.error=self.logs.error;self.dropped+=1;continue
                else:self.journal.write(row)
                self.written+=1
            except Exception as exc:self.error=type(exc).__name__+':'+str(exc)[:160];self.dropped+=1

    def close(self):
        with self.condition:self.closed=True;self.condition.notify_all()

    def status(self):
        with self.condition:return dict(closed=self.closed,threadAlive=self.thread.is_alive(),pending=len(self.pending),
            capacity=self.capacity,written=self.written,dropped=self.dropped,error=self.error)
