# History/control base only. No priority implementation; TalentCore owns selection.
"""Only plugin-range observations + their timestamp history enter this model.

The internal states are estimates, not observations or live castability claims.
No native labels, simulator runtime, current cast/channel/GCD, or execution ACK.
"""

KEYS={'A1_cd','A2_rch','A3_cd','A4_cd','A5_cd','A6_cd','A2_chg','A7_supply','B1','B2','B3','C1_hp_pct','C2_current','C2_max','D1','D2','D3'}
CD_KEYS=('A1_cd','A2_rch','A3_cd','A4_cd','A5_cd','A6_cd')

class PluginModel:
 def __init__(self,constants):
  self.c=dict(constants);self.timers={};self.previous=None
  self.base_gcd_est=1.2;self.ts_inflight_until=-1
  self.ready_window=.25 # explicitly estimated planning window, not observed GCD

 def _timer(self,key,n,t,round_up=True,present=True):
  if not present or (round_up and n==0):lo=hi=0.
  elif round_up:lo=max(0.,n-1.);hi=float(n)
  else:lo=float(n);hi=n+1.
  old=self.timers.get(key)
  if old is not None and t>=old[0]:
   dt=t-old[0];pred_lo=max(0,old[1]-dt);pred_hi=max(0,old[2]-dt)
   x,y=max(lo,pred_lo),min(hi,pred_hi)
   # A reset/extension or unresolved endpoint conflict resets to visible band.
   if x<=y and not (hi>0 and y==0):lo,hi=x,y
  self.timers[key]=(t,lo,hi)
  return (lo+hi)/2
