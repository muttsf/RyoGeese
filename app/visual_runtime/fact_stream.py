"""Ordered visual facts with bounded backpressure; no age/expiry policy."""
from collections import deque
import copy
import math
import threading
from display_state import FIELDS,FREQUENCY

class FactStream:
    def __init__(self,capacity=64):
        if type(capacity) is not int or capacity<1:raise ValueError('INVALID_FACT_CAPACITY')
        self.capacity=capacity;self.condition=threading.Condition();self.queue=deque()
        self.packet=None;self.reason='NOT_STARTED';self.session=None;self.seq=0;self.revision=0
        self.streaming=False;self.done=False;self.epoch=0
        self.accepted=self.consumed=self.max_pending=self.waits=self.discarded_on_reset=0

    @property
    def terminal(self):
        with self.condition:return self.done and not self.queue

    @property
    def has_pending(self):
        with self.condition:return bool(self.queue)

    def begin(self):
        with self.condition:
            if self.streaming:return False
            self.streaming=True;self.queue.clear()
            if self.packet is not None:self.queue.append((self.packet,'READING'))
            self.max_pending=max(self.max_pending,len(self.queue));self.condition.notify_all()
            return True

    @staticmethod
    def _validate(p):
        if type(p) is not dict:raise ValueError('FACT_PACKET_OBJECT_REQUIRED')
        kind=p.get('kind')
        if kind not in ('facts','clear','error','stopped'):return None
        if type(p.get('session')) is not str or not p['session']:raise ValueError('FACT_SESSION_REQUIRED')
        for name in ('seq','revision'):
            if name in p and (type(p[name]) is not int or p[name]<0):raise ValueError('INVALID_FACT_SEQUENCE')
        if kind=='facts':
            if type(p.get('seq')) is not int or p['seq']<1:raise ValueError('FACT_SEQUENCE_REQUIRED')
            if type(p.get('qpcFrequency')) is not int or p['qpcFrequency']!=FREQUENCY:raise ValueError('QPC_FREQUENCY_MISMATCH')
            for name in ('qpcTicks','receivedTicks','nativeFrameTicks','generation','sourceOrdinal'):
                if type(p.get(name)) is not int or p[name]<0:raise ValueError('INVALID_FACT_CLOCK_OR_SOURCE')
            if p['sourceOrdinal']<1 or p['receivedTicks']>p['qpcTicks']:raise ValueError('INVALID_FACT_CLOCK_OR_SOURCE')
            # Compositor timestamps are retained metadata. A lead relative to
            # our completion timestamp must not terminate the receiving lane.
            fields=p.get('facts')
            if type(fields) is not list or len(fields)!=25 or any(type(f) is not dict for f in fields):raise ValueError('INCOMPLETE_25_FIELD_SNAPSHOT')
            if {f.get('name') for f in fields}!=set(FIELDS):raise ValueError('INCOMPLETE_25_FIELD_SNAPSHOT')
            for field in fields:
                value=field.get('value')
                if field.get('status') not in ('known','unknown') or (field['status']=='unknown' and value is not None):raise ValueError('INVALID_UNKNOWN_VALUE')
                if type(value) not in (str,int,float,bool,type(None)) or (type(value) is float and not math.isfinite(value)):raise ValueError('INVALID_FACT_VALUE')
        return kind

    def accept(self,p):
        kind=self._validate(p)
        if kind is None:return False
        snapshot=copy.deepcopy(p)
        with self.condition:
            if self.done:return False
            if self.session is not None and p['session']!=self.session:raise ValueError('STATE_SESSION_CHANGED')
            revision=p.get('revision',self.revision);seq=p.get('seq',0);epoch=self.epoch
            if revision<self.revision or (seq and seq<=self.seq):return False
            if self.streaming:
                waited=False
                while len(self.queue)>=self.capacity and not self.done and epoch==self.epoch:
                    if not waited:self.waits+=1;waited=True
                    self.condition.wait()
                if self.done or epoch!=self.epoch or revision<self.revision:return False
                if self.session is not None and p['session']!=self.session:raise ValueError('STATE_SESSION_CHANGED')
                if seq and seq<=self.seq:return False
            self.session=p['session'];self.seq=max(self.seq,seq)
            packet=snapshot if kind=='facts' else None
            reason='READING' if kind=='facts' else str(p.get('reason','STOPPED'))[:240]
            self.packet=packet;self.reason=reason;self.accepted+=1
            if self.streaming:
                self.queue.append((packet,reason));self.max_pending=max(self.max_pending,len(self.queue))
            if kind in ('error','stopped'):self.done=True
            self.condition.notify_all();return True

    def view(self):
        with self.condition:
            if not self.streaming:return self.packet,self.reason
            if self.queue:return self.queue[0]
            return None,self.reason if self.done else 'WAITING_FACTS'

    def take_view(self):
        with self.condition:
            if self.queue:
                packet,reason=self.queue.popleft();self.consumed+=1;self.condition.notify_all()
                return packet,reason,False if packet is not None else self.done and not self.queue
            return None,self.reason if self.done else 'WAITING_FACTS',self.done

    def finish(self,reason='EOF'):
        with self.condition:
            self.done=True;self.reason=str(reason)[:240];self.condition.notify_all()

    def clear(self,reason,terminal=False):
        with self.condition:
            self.discarded_on_reset+=len(self.queue);self.queue.clear();self.epoch+=1
            self.packet=None;self.reason=str(reason)[:240];self.done|=terminal
            self.condition.notify_all()

    def relocate(self):
        with self.condition:
            self.discarded_on_reset+=len(self.queue);self.queue.clear();self.epoch+=1
            self.revision+=1;self.packet=None;self.reason='RELOCATING';self.done=False
            self.condition.notify_all();return self.revision

    def stats(self):
        with self.condition:
            return dict(pending=len(self.queue),capacity=self.capacity,maxPending=self.max_pending,
                accepted=self.accepted,consumed=self.consumed,backpressureWaits=self.waits,
                discardedOnReset=self.discarded_on_reset,streaming=self.streaming,done=self.done,revision=self.revision)
