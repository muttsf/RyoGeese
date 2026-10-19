"""One latest scalar-state slot. No image, source-clock repair or recommendation."""
import threading
from owned_process import qpc,FREQUENCY

FIELDS=('A1.display','A2.charges','A2.recharge_display','A3.display','A4.display','A5.display','A6.display','A7.uses','A7.ready','B1.presence','B1.seconds','B2.presence','B2.seconds','B3.presence','B3.seconds','C1.hp_percent','C1.target_context','C2.current','C2.maximum','D1.presence','D1.seconds','D2.presence','D2.seconds','D3.presence','D3.seconds')

class LatestState:
    def __init__(self,ttl_ms=1000):
        self.lock=threading.Lock();self.packet=None;self.seq=0;self.session=None;self.revision=0;self.reason='NOT_STARTED';self.terminal=False;self.ttl=ttl_ms/1000
    def clear(self,reason,terminal=False):
        with self.lock:self.packet=None;self.reason=reason;self.terminal|=terminal
    def relocate(self):
        with self.lock:self.revision+=1;self.packet=None;self.reason='RELOCATING';return self.revision
    def accept(self,p):
        with self.lock:
            if self.terminal:return
            if p.get('kind') not in ('facts','clear','error','stopped'):return
            if self.session is None:self.session=p['session']
            if p.get('session')!=self.session:raise ValueError('STATE_SESSION_CHANGED')
            if p.get('revision',self.revision)<self.revision:return
            if p.get('seq',0) and p['seq']<=self.seq:return
            if p['kind']!='facts':
                self.packet=None;self.reason=p.get('reason','STOPPED');self.terminal=p['kind'] in ('error','stopped');self.seq=max(self.seq,p.get('seq',0));return
            if p.get('seq',0)<=self.seq:return
            self.seq=p['seq']
            if p.get('qpcFrequency')!=FREQUENCY:raise ValueError('QPC_FREQUENCY_MISMATCH')
            if {f['name'] for f in p['facts']}!=set(FIELDS) or len(p['facts'])!=25:raise ValueError('INCOMPLETE_25_FIELD_SNAPSHOT')
            if any(f['status'] not in ('known','unknown') or (f['status']=='unknown' and f['value'] is not None) for f in p['facts']):raise ValueError('INVALID_UNKNOWN_VALUE')
            age=(qpc()-p['receivedTicks'])/FREQUENCY
            if age<0 or age>self.ttl:self.packet=None;self.reason='RESULT_EXPIRED';return
            self.packet=p;self.reason='READING'
    def view(self):
        with self.lock:
            if self.packet is not None and (qpc()-self.packet['receivedTicks'])/FREQUENCY>self.ttl:self.packet=None;self.reason='RESULT_EXPIRED'
            return self.packet,self.reason

class Histogram:
    def __init__(self):self.bins=[0]*10001;self.count=0;self.total=0.;self.maximum=0.
    def add(self,value):
        self.bins[min(10000,max(0,round(value)))]+=1;self.count+=1;self.total+=value;self.maximum=max(self.maximum,value)
    def percentile(self,p):
        if not self.count:return None
        target=max(1,__import__('math').ceil(self.count*p));seen=0
        for i,n in enumerate(self.bins):
            seen+=n
            if seen>=target:return i
    def report(self):return dict(count=self.count,mean=None if not self.count else self.total/self.count,p50=self.percentile(.5),p95=self.percentile(.95),maximum=self.maximum)

class Metrics:
    def __init__(self):
        self.lock=threading.Lock();self.last_tick=None;self.last_fact=None;self.ticks=0;self.facts=0;self.clears=0;self.skipped=0;self.reasons={};self.read=Histogram();self.cadence=Histogram();self.fact_cadence=Histogram();self.age=Histogram();self.ui_age=Histogram()
    def add(self,p):
        with self.lock:
            kind=p.get('kind')
            if kind=='tick':
                self.ticks+=1;tick=p['qpcTicks'];freq=p['qpcFrequency']
                if self.last_tick is not None:self.cadence.add((tick-self.last_tick)/freq*1000)
                self.last_tick=tick;self.skipped=max(self.skipped,p.get('skippedSlots',0))
            elif kind=='facts':
                self.facts+=1;tick=p['qpcTicks'];freq=p['qpcFrequency']
                if self.last_fact is not None:self.fact_cadence.add((tick-self.last_fact)/freq*1000)
                self.last_fact=tick;self.read.add(p['readMs']);self.age.add(p['receivedAgeMs'])
            elif kind=='clear':
                self.clears+=1;reason=p.get('reason','UNKNOWN')[:160]
                if len(self.reasons)<32 or reason in self.reasons:self.reasons[reason]=self.reasons.get(reason,0)+1
    def shown(self,packet):
        with self.lock:self.ui_age.add((qpc()-packet['receivedTicks'])/FREQUENCY*1000)
    def report(self):
        with self.lock:return dict(tickAttempts=self.ticks,factPackets=self.facts,clears=self.clears,skippedSlots=self.skipped,reasons=self.reasons.copy(),sampleIntervalsMs=self.cadence.report(),factIntervalsMs=self.fact_cadence.report(),recognitionMs=self.read.report(),receivedToOutputMs=self.age.report(),receivedToUIObservedMs=self.ui_age.report(),sourceAgeVerified=False,decisionRecommendationMeasured=False)
