"""Post-stop timing statistics. Threshold counts are observations, never gates."""
import json,math

def stats(values):
    values=sorted(values)
    if not values:return dict(n=0,mean=None,p95=None,maximum=None,over500=0,over2000=0)
    return dict(n=len(values),mean=sum(values)/len(values),p95=values[math.ceil(len(values)*.95)-1],
                maximum=values[-1],over500=sum(x>500 for x in values),over2000=sum(x>2000 for x in values))

def summarize(rows):
    pairs=dict(roundToDisplay=('roundStartedQpcNs','renderedQpcNs'),
        receivedToDisplay=('receivedQpcNs','renderedQpcNs'),
        compositorToDisplay=('nativeQpcNs','renderedQpcNs'),
        receivedToRecognized=('receivedQpcNs','recognizedQpcNs'),
        recognizedToAdmitted=('recognizedQpcNs','admittedQpcNs'),
        decisionQueue=('admittedQpcNs','evaluationBeginQpcNs'),
        decision=('evaluationBeginQpcNs','evaluationEndQpcNs'),
        decisionToDisplay=('evaluationEndQpcNs','renderedQpcNs'))
    return {name:stats([(r[end]-r[start])/1e6 for r in rows
                       if r.get(start,0)>0 and r.get(end,0)>=r[start]])
            for name,(start,end) in pairs.items()}

def save_timing(run,rows,samples,dropped,native_run,frequency):
    raw=dict(schema=1,clock='SAME_HOST_QPC_NANOSECONDS',captureIntervalMs=500,
             automaticDisplayExpiry=False,droppedTimingRows=dropped,rows=rows)
    (run/'pipeline_timings.json').write_text(json.dumps(raw,ensure_ascii=False,separators=(',',':')),'utf-8')
    recognition=[];compositor_leads=[];overruns=None;capture_interval=None
    events=None if native_run is None else native_run/'events.jsonl'
    if events is not None and events.is_file():
        with events.open(encoding='utf-8') as stream:
            for line in stream:
                p=json.loads(line)
                if p.get('kind')=='capture_started':capture_interval=p.get('intervalMs')
                if p.get('kind')=='facts':
                    value=p.get('readMs')
                    if type(value) in (int,float) and math.isfinite(value) and value>=0:recognition.append(value)
                    native=p.get('nativeFrameTicks');done=p.get('qpcTicks');freq=p.get('qpcFrequency')
                    if all(type(value) is int and value>0 for value in (native,done,freq)):
                        lead=(native*100-done*1_000_000_000//freq)/1e6
                        if lead>0:compositor_leads.append(lead)
                    overruns=p.get('overrunRounds',overruns)
    raw_available=events is not None and events.is_file()
    rotated=raw_available and events.with_name('events.previous.jsonl').is_file()
    report=dict(status='COMPUTED_STOPPED_RUN_SAMPLES',actualAccuracyVerified=False,sourceAgeVerified=False,
        statusMeaning='Statistics of recorded samples only; not whole-run success or live accuracy.',
        pipelineCoverage='BOUNDED_SAMPLES_TRUNCATED' if dropped else 'RECORDED_DELIVERIES_ONLY',
        nativeCoverage='TAIL_ONLY_ROTATED' if rotated else 'STOPPED_EVENTS_FILE' if raw_available else 'UNKNOWN',
        nativeUnavailableReason=None if raw_available else 'Missing supervised stopped-run evidence or forced shutdown.',
        automaticDisplayExpiry=False,captureIntervalMs=capture_interval,overrunRounds=overruns,
        compositorClockDiagnostic=dict(compositorAfterRecognitionCount=len(compositor_leads),
            maximumLeadMs=max(compositor_leads,default=None),inputAdmissionAffected=False,originalTimestampsPreserved=True),
        statistics=dict(visibleSampleCount=sum(bool(r['skill']) for r in samples),
                        pipelineStages=summarize(rows),gpuRecognition=stats(recognition)),
        limits=['Widget configuration timing, not pixel presentation or game state age.',
                'Missing round-start timestamps remain unmeasured.',
                'Latency thresholds do not discard, cancel, reorder or clear advice.'])
    (run/'timing_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    return report
