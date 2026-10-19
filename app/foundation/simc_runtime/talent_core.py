"""Fixed sustained BOSS single target; no target lifetime prediction.
Skill order, observation validation and cooldown/aura history remain unchanged.
Unobserved Mind Devourer react never becomes an observed proc or a zero fee.
"""
import math
from frozen_v1 import KEYS, CD_KEYS
from controlled_core import ControlledCore

class TalentCore(ControlledCore):
 def recommend(self,time_ms,observation):
  # Hard whitelist and type checks make the input boundary reviewable.
  if type(time_ms) not in (int,float) or not math.isfinite(time_ms):return {'skill':None,'reason':'INVALID_TIME'}
  if set(observation)!=KEYS:return {'skill':None,'reason':'INCOMPLETE_OR_FOREIGN_INPUT_KEYS'}
  o=observation;t=time_ms/1000
  for k in CD_KEYS+('A2_chg','A7_supply','C1_hp_pct','C2_current','C2_max'):
   if type(o[k]) not in (int,float) or not math.isfinite(o[k]) or o[k]<0:return {'skill':None,'reason':'UNKNOWN_OR_INVALID_VISIBLE_NUMBER','field':k}
  if o['C2_current']>o['C2_max'] or o['C1_hp_pct']>100 or o['A2_chg']>2:return {'skill':None,'reason':'CONFLICTING_VISIBLE_STATE'}
  for k in ('B1','B2','B3','D1','D2','D3'):
   if type(o[k]) is not dict or set(o[k])!={'present','seconds'} or type(o[k]['present']) is not bool or type(o[k]['seconds']) not in (int,float) or not math.isfinite(o[k]['seconds']) or o[k]['seconds']<0:return {'skill':None,'reason':'UNKNOWN_OR_INVALID_VISIBLE_AURA','field':k}
  if self.previous and t<self.previous[0]:return {'skill':None,'reason':'OUT_OF_ORDER_OBSERVATION'}
  est={k:self._timer(k,o[k],t) for k in CD_KEYS}
  for k in ('B1','B2','B3','D1','D2','D3'):
   est[k]=self._timer(k,o[k]['seconds'],t,k.startswith('D'),o[k]['present'])
  pi=o['D3']['present'];form=o['D2']['present'];rift=o['D1']['present']
  if self.previous:
   old_t,old=self.previous;dt=t-old_t
   if o['A1_cd']>old['A1_cd']+1 and old['A1_cd']<=1:
    period=est['A1_cd']+min(dt,1.5)/2
    base=1.5*period/self.c['shared_MB_VB_base_recharge_s']*(1.2 if pi else 1)
    self.base_gcd_est=min(1.5,max(.75,.5*self.base_gcd_est+.5*base))
   if o['A2_chg']<old['A2_chg']:self.ts_inflight_until=t+.4
  gcd=max(.75,min(1.5,self.base_gcd_est/(1.2 if pi else 1)))
  self.previous=(t,{k:(dict(v) if type(v) is dict else v) for k,v in o.items()})
  p,v,mad=(o[k]['present'] for k in ('B1','B2','B3'))
  dots_up=p and v;vv=o['A7_supply']>0;resource=o['C2_current'];deficit=o['C2_max']-resource
  # Pandemic: 30% of base VT 21s / SW:P 16s. Not target lifetime.
  refresh_v=not v or est['B2']<=6.3;refresh_p=not p or est['B1']<=4.8
  ts_ready=o['A2_chg']>0 or est['A2_rch']<=self.ready_window
  full_recharge=0 if o['A2_chg']==2 else est['A2_rch']+(self.c['tentacle_mid2_2pc_base_recharge_s'] if o['A2_chg']==0 else 0)
  in_flight=t<self.ts_inflight_until
  ready=lambda k:est[k]<=self.ready_window
  estimates={'target_lifetime_s':None,'target_lifetime_origin':'DISABLED_FIXED_BOSS_SINGLE_TARGET','gcd_max_s_model':gcd,'gcd_is_observed':False,'no_future_adds_plan':True,'no_target_shield_assumed':True,'D1_rift_bridge':'ESTIMATED_PROXY','A7_supply_bridge':'ESTIMATED_PROXY','tentacle_in_flight_estimate':in_flight,'timer_seconds':est}
  def choose(skill,line,reason):return {'skill':skill,'sourceLine':line,'reason':reason,'estimated':estimates,'quality':'PLUGIN_INPUT_ESTIMATED_MODEL_NOT_NATIVE_READY'}
  # Original class-skill priority, including PI and Voidform. Consumables,
  # external buffs, items, races and self-healing are outside this output scope.
  # Ignore end-of-fight shortcuts; use ordinary sustained-combat conditions.
  if dots_up:
   if self.burst_modes['power_infusion']=='auto' and form and not pi and ready('A5_cd'):return choose('power_infusion',47,'形态期间灌注可用')
   if self.burst_modes['voidform']=='auto' and ready('A6_cd') and not form and not vv and (p or not v):return choose('voidform',50,'爆发入口成立，形态供应限制满足')
  # Devour Matter target shield is unobserved: no-shield is an estimate.
  if not v:
   if ts_ready:return choose('tentacle_slam',62,'先用触须补触')
   return choose('vampiric_touch',63,'目标缺触，先补触')
  madness_condition=(not mad or est['B3']<=gcd or (deficit<=35 and (est['A6_cd']>25 or deficit<=5)) or (rift and (est['A6_cd']>=75 or not self.talents['ancient_madness'])) or form)
  if resource>=self.c['madness_ordinary_cost'] and madness_condition:return choose('shadow_word_madness',64,'狂乱与DOT/形态窗口满足癫的估算条件')
  if ts_ready and ((refresh_v and not in_flight) or full_recharge<=gcd*2):return choose('tentacle_slam',65,'触续补窗口或触须即将满层')
  if ready('A3_cd') and dots_up:return choose('void_torrent',67,'双DOT在位，洪流可用')
  if self.talents['invoked_nightmare'] and refresh_p and (v or in_flight):return choose('shadow_word_pain',69,'痛进入续补窗口')
  if vv and o['A6_cd']==0:return choose('void_volley',70,'高位齐射：基础形态冷却结束')
  if ready('A1_cd'):
   if rift:return choose('void_blast',71,'裂隙估计在位，共享冷却可用')
   if not self.talents['thought_harvester'] or est['A3_cd']>=gcd*2 or not dots_up:return choose('mind_blast',72,'普通震爆共享冷却可用')
  # Current fixed Voidweaver has no MFI talent supply.
  if ts_ready and (self.talents['void_apparitions']>0 or self.talents['maddening_tentacles']):return choose('tentacle_slam',75,'触须作为高收益填充')
  if refresh_v and (est['A2_rch']>=est['B2'] or not ts_ready):return choose('vampiric_touch',77,'触续补且触须不能及时接手')
  if refresh_v:return choose('vampiric_touch',81,'低位补触')
  if o['C1_hp_pct']<(20+15*self.talents['deathspeaker']) and ready('A4_cd'):return choose('shadow_word_death',83,'目标进入灭的斩杀范围')
  if vv:return choose('void_volley',85,'当前天赋不保留共鸣齐射')
  return choose('mind_flay',86,'普通鞭笞填充，不发主动打断提示')
