"""Existing saved-display field mapping, verbatim; no old replay/IO entrypoint."""
import re

CD={'A1_cd':'A1.display','A2_rch':'A2.recharge_display','A3_cd':'A3.display',
    'A4_cd':'A4.display','A5_cd':'A5.display','A6_cd':'A6.display'}

NUM={'A2_chg':'A2.charges','C1_hp_pct':'C1.hp_percent','C2_current':'C2.current','C2_max':'C2.maximum'}

AURAS=('B1','B2','B3','D1','D2','D3')

FIELDS=set(CD.values())|set(NUM.values())|{'A7.uses','A7.ready','C1.target_context'}|{a+'.'+b for a in AURAS for b in ('presence','seconds')}

KEYS=set(CD)|set(NUM)|set(AURAS)|{'A7_supply'}

def decode(snapshot):
    """Only saved row strings/tags enter mapping; retain original rows separately."""
    missing=[];inputs={};normalized={};estimated=[]
    if snapshot.get('stopRequested') or snapshot.get('mode')!='LIVE':
        return inputs,['STOP_OR_NOT_LIVE_RECORDED_VIEW'],normalized,estimated
    rows=snapshot.get('rows',[])
    if type(rows) is not list or any(type(f) is not dict for f in rows):
        return inputs,['INVALID_ROWS'],normalized,estimated
    by={f.get('name'):f for f in rows}
    if len(by)!=len(rows) or set(by)!=FIELDS:
        return inputs,['MISSING_DUPLICATE_OR_FOREIGN_FIELD'],normalized,estimated
    def known(name):
        f=by[name];v=f.get('values',[])
        if f.get('tags')!=['known'] or len(v)!=3 or v[2]!='当前有效':
            missing.append('UNAVAILABLE:'+name+':'+str(v[2] if len(v)==3 else f.get('tags')))
            return None
        return v[1]
    def integer(v):
        return int(v) if type(v) is str and re.fullmatch(r'[0-9]+',v) else None
    for k,name in CD.items():
        v=known(name);n=integer(v)
        if v=='OK':inputs[k]=0;normalized[k]='OK_TO_OWN_CD_ZERO'
        elif n is not None:inputs[k]=n
        elif v is not None:missing.append('NA_HOLD_OR_NONNUMERIC:'+name)
    for k,name in NUM.items():
        v=known(name);n=integer(v)
        if n is not None:inputs[k]=n
        elif v is not None:missing.append('NONNUMERIC:'+name)
    uses,ready=known('A7.uses'),known('A7.ready');n=integer(uses)
    if uses=='—' and ready=='—':
        inputs['A7_supply']=0
        estimated.append({'key':'A7_supply','value':0,'kind':'NON_VOLLEY_MODE_BOOLEAN_PROXY_NOT_EXACT_COUNT_OBSERVED'})
    elif n is not None and n>0 and ready=='OK':
        inputs['A7_supply']=n
        estimated.append({'key':'A7_supply','value':n,'kind':'VISIBLE_COUNT_AND_RDY_SUPPLY_PROXY_NOT_HIDDEN_BUFF_STACKS'})
    else:missing.append('A7_MODE_COUNT_UNAVAILABLE_OR_CONFLICT')
    for a in AURAS:
        p=known(a+'.presence');f=by[a+'.seconds'];v=f.get('values',[])
        if p=='无':
            if f.get('tags')==['unknown'] and len(v)==3 and v[1]=='—' and v[2]=='此行无效果，秒数不适用':
                inputs[a]={'present':False,'seconds':0};normalized[a]='ABSENT_PLUS_NA_STRUCTURAL_SECONDS_SENTINEL'
            else:missing.append('ABSENCE_SECONDS_CONFLICT:'+a)
        elif p=='有':
            n=integer(known(a+'.seconds'))
            if n is not None:inputs[a]={'present':True,'seconds':n}
            else:missing.append('PRESENT_SECONDS_UNAVAILABLE:'+a)
        else:missing.append('PRESENCE_UNAVAILABLE:'+a)
    ctx=by['C1.target_context'];v=ctx.get('values',[])
    if ctx.get('tags')==['known'] and len(v)==3 and v[1]=='未选中目标（NT）':missing.append('EXPLICIT_NO_TARGET')
    elif ctx.get('tags')!=['unknown'] or len(v)!=3 or v[1]!='未确认':missing.append('TARGET_CONTEXT_CONFLICT')
    if 'C1_hp_pct' in inputs and inputs['C1_hp_pct']>100:missing.append('HP_RANGE')
    if 'A2_chg' in inputs and inputs['A2_chg']>2:missing.append('CHARGE_RANGE')
    if 'C2_current' in inputs and 'C2_max' in inputs and (inputs['C2_current']>inputs['C2_max'] or inputs['C2_max']<=0):missing.append('RESOURCE_CONFLICT')
    return inputs,missing,normalized,estimated

