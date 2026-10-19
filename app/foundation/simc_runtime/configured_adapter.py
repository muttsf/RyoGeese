"""Offline source admission + existing mapping + one configured frozen core.

State journals retain original source timing and admission. Saved display text
uses independent snapshots and never manufactures missing source provenance.
The two transports cannot share one observation history.
"""
import copy
from base_offline_adapter import OfflineAdapter, digest
from display_fields import decode, KEYS
from profile_model import TIER_MODES
from talent_model import TalentModel as ProfileModel, PRIORITY_SCOPE
from prompt_view import render_prompt

class ConfiguredOfflineAdapter(OfflineAdapter):
    def __init__(self,constants,profile,talent_profile=None):
        if type(profile) is not dict or profile.get('schema')!='shadow_priest_mechanism_profile/1' or profile.get('hero')!='voidweaver' or profile.get('tier_mode') not in TIER_MODES:
            raise ValueError('UNSUPPORTED_PROFILE')
        self.settings=copy.deepcopy(profile)
        super().__init__(ProfileModel(constants,profile['tier_mode'],talent_profile))
        self.transport=None
        self.display_last_qpc=-1
        self.display_last_candidate=None
        self.display_terminal=False
        self.configuration_use='CURRENT_PROFILE_ESTIMATE'

    def set_tier_mode(self,mode):
        self.model.set_tier_mode(mode)
        self.configuration_use='CURRENT_PROFILE_ESTIMATE' if mode==self.settings['tier_mode'] else 'EXPLICIT_MECHANISM_SCENARIO'

    def set_talent_profile(self,profile):
        changed=self.model.set_talent_profile(profile)
        if changed:self.display_last_candidate=None
        return changed

    def set_talents(self,**updates):
        changed=self.model.set_talents(**updates)
        if changed:self.display_last_candidate=None
        return changed

    def set_burst_mode(self,skill,mode):
        changed=self.model.set_burst_mode(skill,mode)
        # A new saved display record can reevaluate identical facts after a user
        # policy change. Never reset source timing, stop state or model history.
        if changed:self.display_last_candidate=None
        return changed

    def mark_ordinary_equipment_change(self):
        self.model.mark_ordinary_equipment_change()

    def _configuration(self):
        return {'selectedTierMode':self.model.tier_mode,'use':self.configuration_use,
            'actualCurrentFourPiece':self.settings['actual_four_piece'],
            'actualCurrentTwoPiece':self.settings['actual_two_piece'],
            'newItemExportRequired':False,'priorityCore':PRIORITY_SCOPE,'burstModes':copy.deepcopy(self.model.burst_modes),'talentConfiguration':self.model.describe_talents()}

    def _reject(self,reason):
        return {'status':'NO_RECOMMENDATION','skill':None,'reasons':[reason],
            'model':'FROZEN_V1_WITH_GEAR_BURST_AND_COMMON_TALENTS','configuration':self._configuration(),
            'forecast':False,'liveCastability':'UNKNOWN','actualCastConfirmed':False}

    def process(self,row,now_ns=None):
        if self.transport not in (None,'SOURCE_JOURNAL'):
            result=self._reject('MIXED_TRANSPORT_HISTORY_REJECTED');result['prompt']=render_prompt(result);return result
        self.transport='SOURCE_JOURNAL'
        # The entire old process() body, including freshness, mapping and commit,
        # is reused unmodified. Only the model dependency adds declared talent conditions to gear and burst controls.
        result=super().process(row,now_ns)
        result['model']='FROZEN_V1_WITH_GEAR_BURST_AND_COMMON_TALENTS'
        result['configuration']=self._configuration()
        result['pipelineInput']='SAVED_SOURCE_JOURNAL'
        result['historyPolicy']='player history only; unknown target HP/DOT history cleared by existing adapter'
        if result.get('conditions'):
            result['conditions'][0]='Voidweaver major skills plus declared common talent choices; static scenarios separate from actual equipped talents'
        result['prompt']=render_prompt(result)
        return result

    def process_display(self,snapshot,snapshot_line,display_context):
        result=self._process_display(snapshot,snapshot_line,display_context)
        result['prompt']=render_prompt(result)
        return result

    def _process_display(self,snapshot,snapshot_line,display_context):
        if self.transport not in (None,'SAVED_DISPLAY'):
            return self._reject('MIXED_TRANSPORT_HISTORY_REJECTED')
        self.transport='SAVED_DISPLAY'
        out=self._reject('UNKNOWN_STALE_OR_CLEARED_VIEW')
        out.update(pipelineInput='SAVED_DISPLAY_TEXT',snapshotLine=snapshot_line,
            originalSavedRows=copy.deepcopy(snapshot.get('rows',[])),savedDisplayQpcNs=snapshot.get('qpcNs'),
            sessionId=display_context['sessionId'],clockId=display_context['clockId'],
            sourceCaptureQpcNs=None,sourceFrameId=None,sourceExpiresAt=None,sourceAgeMs=None,
            sourceFreshness='UNKNOWN',targetIdentity=None,targetContinuity='UNKNOWN',
            historyPolicy='independent snapshot; no source/target observation history update',modelTimeMs=None)
        if self.display_terminal:
            out['reasons']=['AFTER_DISPLAY_STOP'];return out
        if snapshot.get('stopRequested') is True:
            self.display_terminal=True
            out['reasons']=['DISPLAY_STOPPED'];return out
        qpc=snapshot.get('qpcNs')
        if type(qpc) is not int or qpc<=self.display_last_qpc:
            out['reasons']=['DISPLAY_TIME_ORDER_CONFLICT'];return out
        self.display_last_qpc=qpc
        # Existing decoder validates the whole25 key set before model use.
        o,missing,normalization,estimates=decode(snapshot)
        by={f.get('name'):f for f in snapshot.get('rows',[]) if type(f) is dict}
        if by.get('A1.display',{}).get('tags')!=['known']:
            return out
        signature=digest(snapshot['rows'])
        if signature==self.display_last_candidate:
            out['reasons']=['IDENTICAL_RENDERED_STATE_NOT_NEW_SOURCE_PROOF'];return out
        self.display_last_candidate=signature
        out.update(modelInputs=o,reasons=missing,normalization=normalization,adapterEstimates=estimates)
        if missing:return out
        if set(o)!=KEYS:
            out['reasons']=['MAPPED_KEYS_NOT17'];return out
        independent=ProfileModel(self.model.c,self.model.tier_mode,self.model.talent_profile)
        independent.burst_modes=copy.deepcopy(self.model.burst_modes)
        independent.ordinary_equipment_updates=self.model.ordinary_equipment_updates
        result=independent.recommend(0,o)
        if result.get('skill') is None:
            out['reasons']=['MODEL_REJECTED:'+result['reason']];return out
        out.update(status='INDEPENDENT_SAVED_DISPLAY_ESTIMATED_RECOMMENDATION',skill=result['skill'],
            recommendation=result,modelTimeMs=0,
            modelTimeMeaning='abstract independent snapshot; not source capture or current wall time')
        return out
