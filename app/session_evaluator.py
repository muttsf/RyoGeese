"""Current recommendation only; priority rules and history remain in the adapter."""
import json
from dataclasses import replace

class SessionEvaluator:
    def __init__(self,profile,journal=None,clock_ns=None,controls=None):
        from app_support import IMPORTER
        from visual_backend import qpc_ns
        self.profile=profile;self.journal=journal;self.importer=IMPORTER.Importer()
        self.clock_ns=clock_ns or qpc_ns
        self.controls=controls
        self.bundle=json.loads(profile.bundle_json);self.adapter=self.importer.make_adapter(self.bundle)
        self.origin=None;self.context=None
        self.last_received=None
    def prepare_work(self,work):
        if self.controls is None:return work
        mode,version=self.controls.snapshot()
        return replace(work,mode=mode,control_version=version)
    def __call__(self,work):
        from pipeline_types import Outcome
        begin=self.clock_ns()
        if work.profile_identity!=self.profile.identity:raise ValueError('PROFILE_IDENTITY_MISMATCH')
        context=(work.stamp.session,work.stamp.revision,work.stamp.generation)
        gap=self.last_received is not None and work.stamp.received_ns-self.last_received>=1_000_000_000
        if context!=self.context or gap:
            self.adapter=self.importer.make_adapter(self.bundle);self.context=context
        self.last_received=work.stamp.received_ns
        if self.origin is None:self.origin=work.stamp.received_ns
        for skill in ('voidform','power_infusion'):self.adapter.set_burst_mode(skill,work.mode)
        t=(work.stamp.received_ns-self.origin)/1_000_000;o=json.loads(work.observation_json)
        result=self.adapter.model.recommend(t,o)
        end=self.clock_ns()
        details=dict(recommendation=result,configuration=self.adapter._configuration(),actualCastConfirmed=False,
            sourceAgeVerified=False,inputEvidence='VISUAL_SCALARS_ADMITTED_BY_SESSION',
            sourceTimeMeaning='WGC_COMPOSITOR_QPC_100NS_NOT_GAME_RENDER_TIME',nativeCastability='UNKNOWN',
            timing=dict(evaluationBeginQpcNs=begin,evaluationEndQpcNs=end))
        return Outcome(work,result.get('skill'),result.get('reason','NO_SKILL'),work.mode,json.dumps(details,ensure_ascii=False,allow_nan=False))
    def after_publish(self,work,outcome):
        if self.journal is not None:self.journal.submit(work,outcome)
