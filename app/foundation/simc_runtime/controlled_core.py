# History/control base only. No priority implementation; TalentCore owns selection.
"""Frozen v1 recommendation order with only two user-permission conjuncts.
Generated from the protected frozen source; AST normalization is verified by
run_checks_and_replay.py. No cooldown/observation is rewritten by holding.
"""
from frozen_v1 import PluginModel, KEYS, CD_KEYS

class ControlledCore(PluginModel):
 def __init__(self,constants):
  super().__init__(constants)
  self.burst_modes={'voidform':'auto','power_infusion':'auto'}

 def set_burst_mode(self,skill,mode):
  if type(skill) is not str or skill not in self.burst_modes:
   raise ValueError('UNSUPPORTED_BURST_CONTROL')
  if type(mode) is not str or mode not in ('auto','hold'):
   raise ValueError('UNSUPPORTED_BURST_MODE')
  changed=self.burst_modes[skill]!=mode
  self.burst_modes[skill]=mode
  return changed

