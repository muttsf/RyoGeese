"""Presentation model: retain the last delivered decision until explicitly changed."""
import json,threading,uuid
from pipeline_types import Work,Outcome,View

class BurstControl:
    def __init__(self):self.lock=threading.Lock();self.value=('auto',0)
    def set(self,mode,version):
        with self.lock:self.value=(mode,version)
    def snapshot(self):
        with self.lock:return self.value

class PresentationState:
    def __init__(self,skills,keymap=None):
        self.skills=dict(skills);self.keymap=dict(keymap or {})
        self.owner=threading.get_ident();self.session=None;self.clock=None
        self.profile=None;self.profile_version=0;self.control_version=0
        self.mode='auto';self.applied_mode=None;self.fence=0;self.job=0
        self.controls=BurstControl()
        self.result=None;self.active_work=None;self.terminal=True;self.reason='NOT_STARTED'

    def _owner(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('UI_THREAD_REQUIRED')

    def start(self,clock):
        self._owner();self.session=uuid.uuid4().hex;self.clock=clock
        self.terminal=False;self.result=None;self.reason='WAITING_DECISION'
        return self.session

    def set_profile(self,identity):
        self._owner();self.profile=identity;self.profile_version+=1
        self.invalidate('PROFILE_CHANGED')

    def request_mode(self,mode):
        self._owner()
        if mode not in ('auto','hold'):raise ValueError('INVALID_BURST_MODE')
        if self.terminal or mode==self.mode:return False
        self.mode=mode;self.control_version+=1
        self.controls.set(mode,self.control_version)
        return True

    def note_waiting(self,reason):
        self._owner();self.waiting_reason=str(reason)[:160]

    def offer(self,stamp,observation):
        self._owner()
        if self.terminal or self.profile is None:return None
        payload=json.dumps(observation,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        if len(payload.encode('utf-8'))>65536:raise ValueError('OVERSIZED_OBSERVATION')
        self.job+=1
        work=Work(stamp,self.profile,self.profile_version,self.control_version,self.fence,self.job,self.mode,payload)
        self.active_work=work
        return work

    def accept(self,outcome):
        self._owner()
        if self.terminal:return False
        if not isinstance(outcome,Outcome):raise TypeError('DECISION_MESSAGE_REQUIRED')
        if outcome.skill is not None and outcome.skill not in self.skills:raise ValueError('UNKNOWN_SKILL')
        # Delivery order belongs to the FIFO; this consumer has no age/job ranking.
        self.result=outcome;self.applied_mode=outcome.applied_mode;self.reason=outcome.reason
        return True

    def invalidate(self,reason):
        """Explicit relocation/configuration boundary, never normal frame arrival."""
        self._owner();self.fence+=1;self.result=None;self.active_work=None;self.reason=reason

    def stop(self,reason='STOP'):
        self.invalidate(reason);self.terminal=True

    def view(self):
        self._owner();result=self.result;skill=result.skill if result is not None else None
        return View(skill,self.skills[skill] if skill else None,
            (self.keymap.get(skill) or '鼠标点击') if skill else None,self.reason,self.mode,self.applied_mode,
            self.applied_mode!=self.mode,self.terminal,result.details_json if result else None)
