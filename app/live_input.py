"""Pinned scalar bridge. Original timestamps are recorded, not used as a timeout.

nativeFrameTicks is SystemRelativeTime.Ticks (100ns), not raw QPC ticks.
This is compositor-frame age, never the age of a game state update.
"""
from app_support import IMPORTER
import display_fields as fields

def map_facts(packet):
    facts=packet.get('facts')
    if type(facts) is not list or len(facts)!=25:raise ValueError('INCOMPLETE_25_FIELDS')
    by={f.get('name'):f for f in facts if type(f) is dict}
    if len(by)!=25 or set(by)!=fields.FIELDS:raise ValueError('DUPLICATE_OR_FOREIGN_FIELDS')
    for f in facts:
        if f.get('status') not in ('known','unknown') or (f['status']=='unknown' and f.get('value') is not None):raise ValueError('INVALID_FIELD_STATUS')
    def known(name):
        f=by[name]
        if f['status']!='known':raise ValueError('UNKNOWN:'+name)
        return f['value']
    def number(name):
        value=known(name)
        if type(value) is not int or value<0:raise ValueError('INVALID_NUMBER:'+name)
        return value
    o={}
    for key,name in fields.CD.items():
        value=known(name)
        if value=='OK':o[key]=0
        else:o[key]=number(name)
    for key,name in fields.NUM.items():o[key]=number(name)
    use,ready=known('A7.uses'),known('A7.ready')
    if use=='—' and ready=='—':o['A7_supply']=0
    elif type(use) is int and use>0 and ready=='OK':o['A7_supply']=use
    else:raise ValueError('A7_CONFLICT')
    for aura in fields.AURAS:
        present=known(aura+'.presence');seconds=by[aura+'.seconds']
        if type(present) is not bool:raise ValueError('INVALID_PRESENCE')
        if present:o[aura]=dict(present=True,seconds=number(aura+'.seconds'))
        elif seconds['status']=='unknown' and seconds.get('reason')=='NOT_APPLICABLE_ABSENT':o[aura]=dict(present=False,seconds=0)
        else:raise ValueError('ABSENCE_SECONDS_CONFLICT')
    ctx=by['C1.target_context']
    if ctx['status']=='known':raise ValueError('EXPLICIT_NO_TARGET_OR_FOREIGN_CONTEXT')
    if ctx.get('reason')!='TARGET_IDENTITY_NOT_PROVIDED':raise ValueError('UNKNOWN_TARGET_CONTEXT')
    if o['C1_hp_pct']>100 or o['A2_chg']>2 or not 0<=o['C2_current']<=o['C2_max'] or o['C2_max']<=0:
        raise ValueError('CONFLICTING_RANGE')
    return o

def frame_times(packet,now_ns,now_qpc,frequency):
    for key in ('nativeFrameTicks','receivedTicks','qpcTicks','qpcFrequency','seq','revision','generation','sourceOrdinal'):
        if type(packet.get(key)) is not int or packet[key]<0:raise ValueError('INVALID_STAMP:'+key)
    if any(type(v) is not int or v<=0 for v in (now_ns,now_qpc,frequency,packet['nativeFrameTicks'])):raise ValueError('INVALID_CLOCK')
    if packet['qpcFrequency']!=frequency or frequency<=0:raise ValueError('QPC_FREQUENCY_MISMATCH')
    if not packet['receivedTicks']<=packet['qpcTicks']<=now_qpc:raise ValueError('FUTURE_OR_REVERSED_QPC')
    # Preserve the original compositor timestamp and explicit unit conversion.
    # Its relation to arrival/completion is diagnostic, never an admission gate.
    # Do not clamp or substitute it; the actual QPC lane above remains checked.
    return (packet['receivedTicks']*1_000_000_000//frequency,
            packet['nativeFrameTicks']*100,
            packet['qpcTicks']*1_000_000_000//frequency)
