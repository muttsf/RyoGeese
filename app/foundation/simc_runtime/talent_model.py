"""Small static talent profile over the established gear and burst model."""
import copy
from profile_model import ProfileModel
from talent_core import TalentCore

COMMIT='3dcabb94dd32f786786c67541dfd10db9f39e43b'
BUILD='12.1.5.70391'
BASE_TALENTS={
    'invoked_nightmare':True,'misery':False,'ancient_madness':True,
    'improved_voidform':False,'devour_matter':True,'distorted_reality':True,
    'mind_devourer':False,'thought_harvester':False,'void_apparitions':4,
    'maddening_tentacles':True,'deathspeaker':False}
PRIORITY_SCOPE='FROZEN_V1_ORDER_FIXED_BOSS_WITHOUT_LIFETIME_FORECAST'

def validate_profile(profile):
    if type(profile) is not dict or set(profile)!={'schema','hero','commit','build','talents'}:
        raise ValueError('INCOMPLETE_OR_FOREIGN_TALENT_PROFILE')
    if profile['schema']!='shadow_priest_common_voidweaver_talents/1' or profile['hero']!='voidweaver' or profile['commit']!=COMMIT or profile['build']!=BUILD:
        raise ValueError('UNSUPPORTED_TALENT_PROFILE_SCOPE')
    talents=profile['talents']
    if type(talents) is not dict or set(talents)!=set(BASE_TALENTS):
        raise ValueError('INCOMPLETE_OR_FOREIGN_TALENT_KEYS')
    for key,value in talents.items():
        if key=='void_apparitions':
            if type(value) is not int or not 0<=value<=4:raise ValueError('INVALID_VOID_APPARITIONS_RANK')
        elif type(value) is not bool:raise ValueError('UNKNOWN_OR_INVALID_TALENT:'+key)
    if talents['invoked_nightmare']==talents['misery']:
        raise ValueError('DOT_CHOICE_MUST_SELECT_EXACTLY_ONE')
    return copy.deepcopy(profile)

def base_profile():
    return dict(schema='shadow_priest_common_voidweaver_talents/1',hero='voidweaver',
        commit=COMMIT,build=BUILD,talents=copy.deepcopy(BASE_TALENTS))

class TalentModel(ProfileModel,TalentCore):
    def __init__(self,constants,tier_mode='unknown_no_four_piece',talent_profile=None):
        self.talent_profile=validate_profile(base_profile() if talent_profile is None else talent_profile)
        self.talents=copy.deepcopy(self.talent_profile['talents'])
        super().__init__(constants,tier_mode)
        self._bind_talent_parameters()

    def _bind_talent_parameters(self):
        self.c['madness_ordinary_cost']=50+5*self.talents['distorted_reality']
        self.c['mind_devourer_selected']=self.talents['mind_devourer']

    def set_talent_profile(self,profile):
        checked=validate_profile(profile)
        changed=checked!=self.talent_profile
        self.talent_profile=checked;self.talents=copy.deepcopy(checked['talents'])
        self._bind_talent_parameters()
        # Fresh observed CD/resource/charges/buffs remain authoritative. Changing
        # static talents never fabricates a cast, grant, proc, aura or a new time.
        return changed

    def set_talents(self,**updates):
        candidate=copy.deepcopy(self.talent_profile)
        candidate['talents'].update(updates)
        return self.set_talent_profile(candidate)

    def describe_talents(self):
        gaps=[]
        if self.talents['mind_devourer']:
            gaps.append({'field':'buff.mind_devourer.react','status':'UNKNOWN',
                'effect':'free madness opportunity and MB suppression not resolved',
                'policy':'ordinary-paid fallback remains; no zero cost or proc inferred'})
        if self.talents['devour_matter']:
            gaps.append({'field':'target.has_absorb','status':'UNKNOWN',
                'effect':'high priority shield-dependent Death not resolved',
                'policy':'same explicit no-shield planning estimate as prior core'})
        return {'schema':self.talent_profile['schema'],'selected':copy.deepcopy(self.talents),
            'use':'CURRENT_CONFIRMED_BASE' if self.talents==BASE_TALENTS else 'EXPLICIT_STATIC_TALENT_SCENARIO',
            'ordinaryMadnessCost':self.c['madness_ordinary_cost'],
            'DeathExecuteThresholdPercent':20+15*self.talents['deathspeaker'],
            'runtimeGaps':gaps,'talentTriggerObserved':False,
            'legalFullTreeValidation':False,'heroScope':'VOIDWEAVER_WITH_EXISTING_MAJOR_SKILLS',
            'bossSingleTargetPolicy':'assumption, not observed target classification; current slot values used',
            'passiveChanges':'observed resource/CD/buff/supply used; no damage/haste/extension precredit',
            'otherHeroSkills':'Archon Resonant Energy and Mind Flay Insanity not supported',
            'inputKeysRemain17':True}

    def recommend(self,time_ms,observation):
        result=super().recommend(time_ms,observation)
        if result.get('skill') is None:return result
        description=self.describe_talents()
        result['profile']['priority_core']=PRIORITY_SCOPE
        result['profile']['talent_scope']='current Voidweaver major skills plus listed static common-talent variants'
        result['talentConfiguration']=description
        result['burstControl']={'modes':copy.deepcopy(self.burst_modes),
            'meaning':'recommendation permission only; release reevaluates the next admitted observation',
            'manualCastClearsHold':False,'forcePairOrOrder':False,'actualExecution':False}
        if self.talents['mind_devourer']:
            result['quality']='PLUGIN_INPUT_ESTIMATED_ORDINARY_PATH_WITH_UNKNOWN_FREE_PROC'
        return result
