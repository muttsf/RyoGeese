"""One frozen priority core, explicit gear-mechanism configuration.

Normal item/stat changes do not create another rotation or clear observation
history. Fresh plugin displays remain authoritative. No hypothetical cast
generates resource, charges or volley supply. This is an offline candidate.
"""
import copy
from frozen_v1 import PluginModel

TIER_MODES={
    'none':{'two_piece':False,'four_piece':False,'period_s':15.0,'range_s':[15.0,15.0]},
    'two_piece':{'two_piece':True,'four_piece':False,'period_s':12.0,'range_s':[12.0,12.0]},
    'four_piece':{'two_piece':True,'four_piece':True,'period_s':12.0,'range_s':[12.0,12.0]},
    'unknown_no_four_piece':{'two_piece':None,'four_piece':False,'period_s':15.0,'range_s':[12.0,15.0]},
}

class ProfileModel(PluginModel):
    def __init__(self,constants,tier_mode='unknown_no_four_piece'):
        # Do not mutate the protected config or priority source. The historical
        # core constant name is bound to the selected complete-period parameter.
        super().__init__(constants)
        self.tier_mode=None
        self.ordinary_equipment_updates=0
        self.set_tier_mode(tier_mode)

    def set_tier_mode(self,mode):
        if type(mode) is not str or mode not in TIER_MODES:
            raise ValueError('UNSUPPORTED_TIER_MODE')
        self.tier_mode=mode
        self.c['tentacle_mid2_2pc_base_recharge_s']=TIER_MODES[mode]['period_s']
        # No reset of observed timers/charges, no procurement of buff supply.

    def mark_ordinary_equipment_change(self):
        """Optional bookkeeping only. No item IDs, stats or new dynamic fields."""
        self.ordinary_equipment_updates+=1

    def recommend(self,time_ms,observation):
        # Priority/number validation/history estimation are exactly the frozen
        # v1 implementation; this wrapper adds explanatory configuration only.
        result=super().recommend(time_ms,observation)
        if result.get('skill') is None:
            return result
        spec=TIER_MODES[self.tier_mode]
        remaining=result['estimated']['timer_seconds']['A2_rch']
        charge=observation['A2_chg']
        full=0.0 if charge==2 else remaining+(spec['period_s'] if charge==0 else 0)
        full_range=[0.0,0.0] if charge==2 else [remaining+x for x in spec['range_s']] if charge==0 else [remaining,remaining]
        result['profile']={
            'tier_mode':self.tier_mode,'mid2_two_piece':spec['two_piece'],'mid2_four_piece':spec['four_piece'],
            'tentacle_complete_period_prior_s':spec['period_s'],
            'tentacle_complete_period_range_due_to_set_s':copy.deepcopy(spec['range_s']),
            'tentacle_full_recharge_estimate_s':full,
            'tentacle_full_recharge_range_due_to_set_s':full_range,
            'is_observed_full_recharge':False,
            'unknown_two_piece_policy':'explicit15s prior plus12..15s range; recommendations allowed as estimates',
            'ordinary_equipment_updates':self.ordinary_equipment_updates,
            'priority_core':'BYTE_IDENTICAL_FROZEN_V1',
            'current_cd_charge_resource_aura_source':'existing plugin observations',
            'haste_planning_window':'existing A1 history plus PI estimate, not current GCD',
            'four_piece_supply_policy':'trust observed A7; never fabricate extra supply from tier or recommendation',
            'damage_model':'not implemented; crit/mastery/weapon/trinket changes not scored',
            'talent_scope':'fixed current Voidweaver tree only; other trees not automatically certified',
        }
        return result

def core_result(result):
    """For preservation checks only; never used to select a skill."""
    return {k:v for k,v in result.items() if k!='profile'}
