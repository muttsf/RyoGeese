"""Stopped-run diagnostics only. WGC age is not game-state age or pixel timing."""
import hashlib
import io
import json
from pathlib import Path

MAX_BYTES, MAX_LINES, MAX_SAMPLES = 32 * 1024 * 1024, 20000, 10000


def _require(condition, reason):
    if not condition:raise ValueError(reason)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _decode(text):
    return json.loads(text, object_pairs_hook=_pairs,
                      parse_constant=lambda value: _require(False, 'NONFINITE_JSON'))


def _read(path, remaining):
    with Path(path).open('rb') as stream:raw = stream.read(remaining + 1)
    _require(len(raw) <= remaining, 'INPUT_SIZE_LIMIT')
    return raw.decode('utf-8-sig'), hashlib.sha256(raw).hexdigest(), len(raw)


def _key(value, ordinal):
    _require(type(value) is dict, 'MISSING_SOURCE_KEY')
    result = tuple(value.get(k) for k in ('revision', 'generation', ordinal))
    _require(all(_integer(v) for v in result) and result[2] > 0, 'INVALID_SOURCE_KEY')
    return result


def _distribution(values):
    if not values:return dict(status='UNKNOWN', reason='NO_MATCHED_VISIBLE_SAMPLES')
    ordered = sorted(values)
    return dict(status='COMPUTED', unit='ms', count=len(values),
                minimum=ordered[0]/1e6, maximum=ordered[-1]/1e6,
                mean=sum(values)/len(values)/1e6,
                p50=ordered[(len(values)*50+99)//100-1]/1e6,
                p95=ordered[(len(values)*95+99)//100-1]/1e6)


def review_short(events_path, ui_path, output_path, *, qpc_frequency=None,
                 native_session=None, same_host=False):
    """Caller binds same-host QPC provenance; writes a fresh output file once.

    UI root: {samples: [...], qpcFrequency: int, nativeSession: str}.
    Frequency/session may instead be bound by explicit keyword arguments.
    Any malformed, missing, ambiguous or truncated input makes statistics UNKNOWN.
    """
    output, events_path = Path(output_path), Path(events_path)
    previous = events_path.with_suffix('.previous.jsonl')
    _require(output.resolve() not in (events_path.resolve(), previous.resolve(), Path(ui_path).resolve()),
             'OUTPUT_COLLIDES_WITH_INPUT')
    report = dict(status='UNKNOWN', sourceAgeVerified=False, actualAccuracyVerified=False,
                  sameHostDeclared=same_host is True, statistics=None,
                  limits=['WGC compositor time is not game/plugin update time.',
                          'Widget samples are not actual rendered-pixel timing.',
                          'Blank spans describe sampled observations only.'])
    try:
        _require(same_host is True, 'SAME_HOST_QPC_NOT_BOUND')
        lines, native_files, remaining = [], [], MAX_BYTES
        for path in ([previous] if previous.is_file() else []) + [events_path]:
            text, digest, size = _read(path, remaining)
            remaining -= size
            for line in io.StringIO(text):
                lines.append(line)
                _require(len(lines) <= MAX_LINES, 'EVENT_LINE_LIMIT')
            native_files.append(dict(name=path.name, sha256=digest, bytes=size))
        ui_text, ui_hash, _ = _read(ui_path, remaining)
        report['inputSHA256'] = dict(nativeFiles=native_files, ui=ui_hash)
        _require(len(lines) <= MAX_LINES, 'EVENT_LINE_LIMIT')
        ui = _decode(ui_text)
        if type(ui) is list:ui = dict(samples=ui)
        _require(type(ui) is dict and type(ui.get('samples')) is list, 'UI_ROOT_REQUIRED')
        samples = ui['samples']
        _require(0 < len(samples) <= MAX_SAMPLES, 'EMPTY_OR_OVERSIZE_UI')
        _require(type(ui.get('droppedSamples', 0)) is int and ui.get('droppedSamples', 0) == 0, 'DROPPED_UI_SAMPLES')
        frequency = qpc_frequency if qpc_frequency is not None else ui.get('qpcFrequency')
        session = native_session if native_session is not None else ui.get('nativeSession')
        _require(_integer(frequency, 1), 'CLOCK_FREQUENCY_MISSING')
        _require(type(session) is str and bool(session), 'NATIVE_SESSION_MISSING')
        _require(_integer(ui.get('qpcFrequency', frequency), 1) and ui.get('qpcFrequency', frequency) == frequency, 'UI_FREQUENCY_CONFLICT')
        _require(ui.get('nativeSession', session) == session, 'UI_SESSION_CONFLICT')
        facts, delays, early, late = {}, [], 0, 0
        for line in lines:
            if not line.strip():continue
            row = _decode(line)
            _require(type(row) is dict, 'INVALID_EVENT')
            _require(row.get('session', session) == session, 'CROSS_NATIVE_SESSION')
            if row.get('kind') != 'facts':continue
            _require(row.get('session') == session, 'FACT_SESSION_MISSING')
            key = _key(row, 'sourceOrdinal')
            _require(key not in facts, 'DUPLICATE_SOURCE_KEY')
            n, r, d, f = (row.get(k) for k in ('nativeFrameTicks', 'receivedTicks', 'qpcTicks', 'qpcFrequency'))
            _require(all(_integer(v, 1) for v in (n, r, d, f)) and f == frequency, 'INVALID_NATIVE_CLOCK')
            _require(r <= d and n*frequency <= d*10_000_000, 'INVALID_NATIVE_ORDER')
            facts[key] = (n, r, d)
            early += n*frequency <= r*10_000_000
            late += n*frequency > r*10_000_000
            delays.append((d-r)*1_000_000_000//frequency)
        _require(bool(facts), 'NO_NATIVE_FACTS')
        source_ages, received_ages, blanks, last, start = [], [], [], -1, None
        for index, row in enumerate(samples):
            _require(type(row) is dict and type(row.get('skill')) is str, 'INVALID_UI_SAMPLE')
            tick = row.get('qpc')
            _require(_integer(tick, 1) and tick > last, 'INVALID_UI_CLOCK_ORDER')
            last = tick
            _require(row.get('nativeSession', session) == session, 'CROSS_UI_SESSION')
            source = row.get('source')
            if source is not None:
                _require(source.get('session', session) == session, 'CROSS_UI_SOURCE_SESSION')
                key = _key(source, 'ordinal')
                _require(key in facts, 'UI_SOURCE_NOT_FOUND')
                _require(tick >= facts[key][2], 'UI_PRECEDES_EMITTED_SOURCE')
            if row['skill']:
                _require(source is not None and _integer(row.get('expiresQpcNs')), 'VISIBLE_SOURCE_MISSING')
                n, r, d = facts[key]
                _require(tick >= d, 'UI_PRECEDES_EMITTED_SOURCE')
                source_ages.append(tick*1_000_000_000//frequency-n*100)
                received_ages.append((tick-r)*1_000_000_000//frequency)
            if not row['skill'] and start is None:start = index
            if start is not None and (row['skill'] or index == len(samples)-1):
                end = index-1 if row['skill'] else index
                a, b = samples[start]['qpc'], samples[end]['qpc']
                blanks.append(dict(firstBlankSampleQpc=a, lastBlankSampleQpc=b,
                                   observedSpanMs=(b-a)*1000/frequency, sampleCount=end-start+1,
                                   nextVisibleSampleQpc=tick if row['skill'] else None))
                start = None
        report.update(status='COMPUTED_STOPPED_RUN_SAMPLES', nativeSession=session, qpcFrequency=frequency,
                      statistics=dict(nativeFactCount=len(facts), uiSampleCount=len(samples),
                      visibleSampleCount=len(source_ages), blankSampleCount=sum(not r['skill'] for r in samples),
                      nativeOrdering=dict(nativeAtOrBeforeReceived=early, receivedBeforeNativeAtOrBeforeEmitted=late),
                      nativeToReceived=_distribution([r*1_000_000_000//frequency-n*100 for n,r,d in facts.values()]),
                      nativeToEmitted=_distribution([d*1_000_000_000//frequency-n*100 for n,r,d in facts.values()]),
                      receivedToEmitted=_distribution(delays), visibleWgcAge=_distribution(source_ages),
                      visibleReceivedAge=_distribution(received_ages), blankObservedSpans=blanks))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, UnicodeError) as exc:
        report['reason'] = type(exc).__name__ + ':' + str(exc)[:160]
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return report
