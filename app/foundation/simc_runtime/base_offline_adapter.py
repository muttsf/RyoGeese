"""Saved Dash states -> unchanged frozen v1. Standard library, offline only.

No capture, OCR, native runtime, execution ACK, wall-clock freshness or UI.
Observation history commits only after full validation and a successful model call.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CD_MAP = {'A1_cd':'A1.display', 'A2_rch':'A2.recharge_display',
          'A3_cd':'A3.display', 'A4_cd':'A4.display', 'A5_cd':'A5.display', 'A6_cd':'A6.display'}
NUM_MAP = {'A2_chg':'A2.charges', 'C1_hp_pct':'C1.hp_percent',
           'C2_current':'C2.current', 'C2_max':'C2.maximum'}
AURAS = ('B1','B2','B3','D1','D2','D3')
FIELDS = set(CD_MAP.values()) | set(NUM_MAP.values()) | {'A7.uses','A7.ready','C1.target_context'} | {a+'.'+s for a in AURAS for s in ('presence','seconds')}

def number(v):
    return type(v) in (int, float) and math.isfinite(v) and v >= 0

def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


class OfflineAdapter:
    def __init__(self, model):
        self.model = model
        self.context = None
        self.last_source_ns = None
        self.last_sequence = None
        self.accepted = set()
        self.terminal = False

    def process(self, row, now_ns=None):
        state = row.get('state', {})
        packet = row.get('originalPacket') or {}
        out = {'status':'NO_RECOMMENDATION', 'skill':None, 'reasons':[],
               'stateVersion':state.get('state_version'), 'model':'FROZEN_V1',
               'forecast':False, 'liveCastability':'UNKNOWN', 'actualCastConfirmed':False}
        if packet.get('kind') != 'CAL_FACTS':
            if packet.get('kind') == 'STOP' or row.get('kind') == 'END':
                self.terminal = True
            out['reasons'] = ['CONTROL_OR_INVALIDATION_RECORD']
            out['originalKind'] = packet.get('kind') or row.get('kind')
            out['diagnostics'] = state.get('diagnostics', [])
            out['recordReason'] = row.get('reason')
            return out
        def fail(reason, field=None):
            out['reasons'].append(reason + (':'+field if field else ''))
        if self.terminal:
            fail('AFTER_STOP')
            return out
        proof = row.get('frameEvidence') or {}
        if row.get('stateAccepted') is not True or row.get('inheritedAccepted') is not True or row.get('proofError') is not None:
            fail('SOURCE_NOT_ACCEPTED')
        if state.get('capture_status') != 'ok' or state.get('geometry_status') != 'ok':
            fail('CAPTURE_OR_GEOMETRY_FAILED')
        context = (packet.get('sessionId'), packet.get('clockId'))
        if not all(type(x) is str and x for x in context) or context != (state.get('session_id'), proof.get('clockId')):
            fail('SESSION_OR_CLOCK_CONFLICT')
        if self.context is not None and context != self.context:
            fail('CROSS_SESSION_OR_CLOCK')
        if packet.get('wireVersion') != 'dash-consumer-wire/1' or packet.get('addonVersion') != '1.45-S1' or packet.get('freshnessLimitMs') != 250:
            fail('UNSUPPORTED_WIRE_PROFILE_OR_TTL')
        if not str(state.get('layout_version','')).startswith('Dash-L16:') or state.get('profile_version') != 'Dash-1.45-S1-visible-facts/1':
            fail('UNSUPPORTED_STATE_PROFILE')
        if packet.get('timestampMeaning') != 'WGC_COMPOSITOR_QPC_100NS_NOT_GAME_RENDER_TIME' or proof.get('mode') != 'live-qpc':
            fail('UNSUPPORTED_SOURCE_TIME')
        src = packet.get('sourceCaptureTimestamp')
        seq = packet.get('sequence')
        if type(src) is not int or src < 0 or type(seq) is not int or seq < 1:
            fail('INVALID_SOURCE_OR_FRAME')
            return out
        source_ns = src*100
        if now_ns is None:
            if not number(state.get('as_of')):
                fail('INVALID_REPLAY_TIME')
                return out
            now_ns = round(state['as_of']*1e9)
        if type(now_ns) is not int:
            fail('INVALID_REPLAY_TIME')
            return out
        result_ns, emitted_ns = packet.get('resultQpcNs'), packet.get('emittedQpcNs')
        if not all(type(x) is int for x in (result_ns, emitted_ns)) or not source_ns <= result_ns <= emitted_ns <= now_ns:
            fail('TIME_ORDER_CONFLICT')
        if not source_ns <= now_ns < source_ns+250_000_000:
            fail('SOURCE_EXPIRED_OR_FUTURE')
        elif type(emitted_ns) is int and now_ns-emitted_ns >= 250_000_000:
            fail('RECEIVE_EXPIRED')
        if self.last_source_ns is not None and (source_ns < self.last_source_ns or seq <= self.last_sequence):
            fail('OUT_OF_ORDER_OR_DUPLICATE')
        if (context, seq) in self.accepted:
            fail('DUPLICATE_FRAME')
        if proof.get('sequence') != seq or proof.get('sourceCaptureTimestamp') != src:
            fail('FRAME_PROOF_CONFLICT')
        try:
            if proof.get('originalPacketSHA256') != digest(packet) or proof.get('originalFactsSHA256') != digest(packet.get('facts')):
                fail('PACKET_HASH_CONFLICT')
        except (ValueError, TypeError):
            fail('NON_JSON_OR_NONFINITE_PACKET')
        facts = state.get('fields', [])
        if type(facts) is not list or any(type(f) is not dict for f in facts):
            fail('INVALID_FIELDS')
            return out
        by = {f.get('name','').removeprefix('dash.'):f for f in facts}
        if len(by) != len(facts) or set(by) != FIELDS:
            fail('MISSING_DUPLICATE_OR_FOREIGN_FIELDS')
            return out
        original = {f.get('name'):f for f in packet.get('facts', [])}
        if len(original) != len(packet.get('facts', [])) or set(original) != FIELDS:
            fail('ORIGINAL_FIELD_SET_CONFLICT')
            return out
        observed = {}
        for name, f in by.items():
            observed[name] = {k:f.get(k) for k in ('status','value','reason')}
            if any(f.get(k) != original[name].get(k) for k in ('status','value','reason')):
                fail('STATE_PACKET_CONFLICT', name)
            evidence = f.get('evidence', [])
            if len(evidence) != 1:
                fail('MISSING_OR_AMBIGUOUS_EVIDENCE', name)
                continue
            e = evidence[0]
            if e.get('session_id') != context[0] or e.get('frame_id') != seq or e.get('image_sha256') != proof.get('imageSHA256') or e.get('source_ref') != proof.get('sourceRef'):
                fail('CROSS_PACKAGE_EVIDENCE', name)
            if e.get('layout_version') != state.get('layout_version') or e.get('profile_version') != state.get('profile_version') or e.get('roi') != proof.get('fieldROIs',{}).get(name):
                fail('LAYOUT_OR_ROI_CONFLICT', name)
            if not number(e.get('observed_at')) or abs(e['observed_at']-src/1e7)>1e-6 or e.get('source') != 'dash-screen:live-qpc':
                fail('OBSERVATION_TIME_CONFLICT', name)
            if f.get('status') == 'known':
                if not number(e.get('expires_at')) or abs(e['expires_at']-src/1e7-.25)>1e-6 or now_ns >= round(e['expires_at']*1e9):
                    fail('FIELD_EXPIRED_OR_TTL_CONFLICT', name)
            elif f.get('value') is not None:
                fail('NONKNOWN_RETAINED_VALUE', name)
        out['observedFacts'] = observed
        out['provenance'] = {'sessionId':context[0], 'clockId':context[1], 'frameId':seq,
            'inputId':proof.get('inputId'), 'imageSHA256':proof.get('imageSHA256'),
            'sourceRef':proof.get('sourceRef'), 'sourceQpcNs':source_ns,
            'sourceTimeMeaning':packet.get('timestampMeaning'), 'resultQpcNs':result_ns,
            'replayEvaluationQpcNs':now_ns, 'journalRecordedQpcNs':row.get('qpcNs'),
            'validUntilQpcNs':source_ns+250_000_000, 'ageMs':(now_ns-source_ns)/1e6,
            'targetIdentity':state.get('target_identity'), 'targetEpochLabel':state.get('target_epoch'),
            'targetContinuity':'UNKNOWN', 'gameRenderTimeKnown':False}
        inputs, normalization, assumptions = {}, {}, []
        def known(name):
            f = by[name]
            if f.get('status') != 'known':
                fail('INPUT_UNAVAILABLE_'+str(f.get('reason')), name)
                return None
            return f.get('value')
        for key, name in CD_MAP.items():
            v = known(name)
            if v == 'OK':
                inputs[key] = 0
                normalization[key] = 'OK -> own cooldown zero only'
            elif number(v):
                inputs[key] = v
            elif v is not None:
                fail('NONNUMERIC_CD_NA_HOLD_OR_FAILURE', name)
        for key, name in NUM_MAP.items():
            v = known(name)
            if number(v):
                inputs[key] = v
            elif v is not None:
                fail('INVALID_VISIBLE_NUMBER', name)
        uses, ready = known('A7.uses'), known('A7.ready')
        if uses == '\u2014' and ready == '\u2014':
            inputs['A7_supply'] = 0
            assumptions.append({'key':'A7_supply','value':0,'kind':'ESTIMATED_BOOLEAN_SUPPLY_PROXY',
                'condition':'both fresh known em dash: not volley replacement mode',
                'notObserved':'exact executable count zero or both underlying buff stacks'})
        elif number(uses) and ready == 'OK' and type(uses) is int and uses > 0:
            inputs['A7_supply'] = uses
            assumptions.append({'key':'A7_supply','value':uses,'kind':'ESTIMATED_SUPPLY_PROXY',
                'condition':'fresh positive visible count plus confirmed replacement OK',
                'notObserved':'two hidden buff stacks or complete castability'})
        else:
            fail('A7_INCOMPLETE_OR_CONFLICTING_MODE_COUNT')
        for aura in AURAS:
            p, s = by[aura+'.presence'], by[aura+'.seconds']
            presence = known(aura+'.presence')
            if type(presence) is not bool:
                fail('UNKNOWN_OR_INVALID_PRESENCE', aura)
            elif presence is False:
                if p.get('reason') == 'NORMAL_COMPLETE_BLANK' and s.get('status') == 'unknown' and s.get('value') is None and s.get('reason') == 'NOT_APPLICABLE_ABSENT':
                    inputs[aura] = {'present':False,'seconds':0}
                    normalization[aura] = 'confirmed absence + N/A -> structural seconds sentinel zero (no countdown observed)'
                else:
                    fail('ABSENCE_SECONDS_CONFLICT', aura)
            else:
                seconds = known(aura+'.seconds')
                if number(seconds):
                    inputs[aura] = {'present':True,'seconds':seconds}
                else:
                    fail('PRESENT_SECONDS_UNAVAILABLE', aura)
        ctx = by['C1.target_context']
        if ctx.get('status') == 'known' and ctx.get('value') == 'no_target':
            fail('EXPLICIT_NO_TARGET')
        elif ctx.get('status') != 'unknown' or ctx.get('reason') != 'TARGET_IDENTITY_NOT_PROVIDED':
            fail('UNSUPPORTED_TARGET_CONTEXT')
        if 'C1_hp_pct' in inputs and inputs['C1_hp_pct'] > 100:
            fail('HP_OUT_OF_RANGE')
        if 'A2_chg' in inputs and (type(inputs['A2_chg']) is not int or inputs['A2_chg'] > 2):
            fail('CHARGES_OUT_OF_RANGE')
        if all(k in inputs for k in ('C2_current','C2_max')) and (inputs['C2_max']<=0 or inputs['C2_current']>inputs['C2_max']):
            fail('RESOURCE_CONFLICT')
        out.update(modelInputs=inputs, normalization=normalization, adapterEstimates=assumptions)
        if out['reasons']:
            return out
        # Unknown target identity: do not fuse HP/DOT across frames. Player CD,
        # recharge and BUFF history are still plugin observations of one player.
        candidate = copy.deepcopy(self.model)
        for a in ('B1','B2','B3'):
            candidate.timers.pop(a, None)
        suggestion = candidate.recommend(source_ns/1e6, inputs)
        if suggestion.get('skill') is None:
            fail('MODEL_REJECTED_'+suggestion['reason'])
            return out
        self.model = candidate
        self.context, self.last_source_ns, self.last_sequence = context, source_ns, seq
        self.accepted.add((context, seq))
        out.update(status='OFFLINE_CONDITIONAL_ESTIMATED_RECOMMENDATION', skill=suggestion['skill'],
            recommendation=suggestion, modelEstimateAtQpcNs=source_ns,
            conditions=['fixed Voidweaver MID2 four-piece single-target profile assumed; saved player configuration unconfirmed',
                        'current displayed target values used only within this frame; attackability/aliveness/range unknown',
                        'target lifetime forecasting disabled; fixed sustained BOSS single target policy',
                        'no active interrupt instruction; no action acknowledgment; skill emission does not advance resources'],
            qualification='ESTIMATED_PRIORITY_ONLY_NOT_CONFIRMED_EXECUTABLE')
        return out
