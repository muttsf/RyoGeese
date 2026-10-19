"""Bounded session diagnostics; no alternate setup or capture entry point."""
import collections,json,tkinter as tk
from visual_backend import qpc,FREQUENCY

class TrialMonitor:
    """Retain changed skill/source states; never records player input or keys."""
    def __init__(self,session,entry_point='LEGACY_SHORT_VALIDATION'):
        self.session=session;self.root=session.root;self.samples=collections.deque(maxlen=6000)
        self.entry_point=entry_point
        self.dropped=0;self.after=self.root.after(0,self.poll);self.stopped=False
    def poll(self):
        self.after=None
        if self.stopped:return
        s=self.session;window=s.window
        if window is not None:
            view=window.last_rendered_view;outcome=s.state.result
            work=outcome.work if outcome is not None else None
            row=dict(qpc=qpc(),automaticDisplayExpiry=False,skill=window.skill.cget('text'),
                mode=window.mode,reason=view.reason,requestedMode=view.requested_mode,appliedMode=view.applied_mode,
                requiredRevision=s.required_revision,
                source=None if work is None else dict(revision=work.stamp.revision,generation=work.stamp.generation,ordinal=work.stamp.ordinal))
            if not self.samples or any(row[k]!=self.samples[-1][k] for k in row if k!='qpc'):
                if len(self.samples)==self.samples.maxlen:self.dropped+=1
                self.samples.append(row)
        if s.state.terminal and s.backend.closed():s.close();return
        self.after=self.root.after(25,self.poll)
    def stop(self):
        self.stopped=True
        if self.after is not None:
            try:self.root.after_cancel(self.after)
            except tk.TclError:pass
            self.after=None
    def save(self):
        s=self.session;panel=getattr(s.backend,'panel',None)
        visible=[r for r in self.samples if r['skill']]
        stale_revision=[r for r in visible if r['source'] is not None and r['source']['revision']<r['requiredRevision']]
        reader=getattr(s.backend,'backend',s.backend)
        summary_ready=bool(panel is not None and panel.finished and panel.run is not None and (panel.run/'summary.json').is_file())
        report=dict(status='STOPPED_SESSION_REQUIRES_AUTHOR_AND_USER_REVIEW',entryPoint=self.entry_point,
            backendKind=type(reader).__name__,qpcFrequency=FREQUENCY,
            uiSampling='DISPLAY_OR_SOURCE_CHANGES',sampleCount=len(self.samples),droppedSamples=self.dropped,visibleWidgetSamples=len(visible),
            blankWidgetSamples=len(self.samples)-len(visible),visibleSamplesWithoutMatchedSource=sum(r['source'] is None for r in visible),
            automaticDisplayExpiry=False,staleRevisionSamples=len(stale_revision),captureIntervalMs=500,
            nativeRun=None if panel is None or panel.run is None else str(panel.run),
            workerStopped=None if panel is None else panel.worker_stopped,processExited=s.backend.closed(),
            supervisorSummaryFinished=None if panel is None else panel.finished,
            supervisorSummaryPresent=summary_ready,
            forcedAbort=getattr(reader,'aborting',False),cleanupErrors=list(s.cleanup_errors),
            actualCastsConfirmed=False,firstSkillAccuracyMeasured=False,sourceAgeVerified=False,liveEnabled=False,
            limits=['Widget polling is not rendered-pixel timing or a hard real-time bound.',
                    'Native time is compositor time, not the game/plugin update time.',
                    'Ordinary waiting or unknown input retains the last delivered decision; explicit Stop/relocate clears it.',
                    '500ms and 2s are diagnostic thresholds only, never age-based dropping rules.',
                    'Recommendations and replay logs are not confirmation of a cast.'],
            formalFrozen=False,independentVAL=0)
        diagnostics=getattr(s.root._root(),'diagnostics',None)
        report['diagnosticsRun']=str(diagnostics.run) if diagnostics else None
        report['currentLog']=s.current_log.status()
        report['workerCounts']=s.worker.stats()
        report['inputIssues']=dict(s.input_issues)
        report['fifoCounts']=None if panel is None or not hasattr(panel,'state') else panel.state.stats()
        samples_path=s.run/'ui_timing_samples.json'
        samples_path.write_text(json.dumps(dict(schema=3,sampling='DISPLAY_OR_SOURCE_CHANGES',entryPoint=self.entry_point,qpcFrequency=FREQUENCY,
            nativeSession=s.native_session,droppedSamples=self.dropped,samples=list(self.samples)),
            ensure_ascii=False,separators=(',',':')),'utf-8')
        from pipeline_report import save_timing
        timing=save_timing(s.run,list(s.timings),self.samples,s.timing_dropped,
                           panel.run if summary_ready and not getattr(reader,'aborting',False) else None,FREQUENCY)
        report['timingReviewStatus']=timing['status']
        name='session_result.json' if self.entry_point=='DESKTOP_SETUP' else 'short_validation_result.json'
        (s.run/name).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        return report

