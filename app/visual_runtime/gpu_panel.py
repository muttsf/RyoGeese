"""Scalar-only GPU test panel. A fresh human click/chat marker starts capture."""
import sys
sys.dont_write_bytecode=True
import os,json,subprocess,threading,time,uuid,hashlib,collections
from pathlib import Path
from datetime import datetime,timezone
import tkinter as tk
from tkinter import ttk
from owned_process import OwnedJob,qpc,FREQUENCY,panel_memory
from cpu_policies import memory_status,start_assessment,OwnedMemoryGuard
from display_state import FIELDS,Metrics
from fact_stream import FactStream
from journal import Journal,ErrorEvents,atomic_json

ROOT=Path(__file__).resolve().parent
from package_paths import READER_ROOT,DOTNET,CACHE_ROOT,package_file
WORKER=READER_ROOT/'bin/GpuDash.dll'
DEFAULTS=json.loads((ROOT/'live_defaults.json').read_text('utf-8'))

def verify_runtime(progress=None,cancel=None):
    lock=json.loads((ROOT/'runtime_lock.json').read_text('utf-8'))
    for index,p in enumerate(lock['files']):
        if cancel is not None and cancel.is_set():raise InterruptedError('START_CHECK_CANCELLED')
        path=package_file(p['path']);digest=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):
                if cancel is not None and cancel.is_set():raise InterruptedError('START_CHECK_CANCELLED')
                digest.update(block)
        if path.stat().st_size!=p['bytes'] or digest.hexdigest()!=p['SHA256']:raise ValueError('GPU_RUNTIME_CHANGED:'+str(path))
        if progress is not None:progress(index+1,len(lock['files']),path.name)

class RuntimeCheck:
    """Only hashes files. The background thread cannot touch Tk or start capture."""
    def __init__(self):
        self.cancel=threading.Event();self.done=threading.Event();self.progress=(0,0,'');self.error=None
        threading.Thread(target=self.run,daemon=True,name='GPU-runtime-hash').start()
    def run(self):
        try:verify_runtime(self.update,self.cancel)
        except Exception as ex:self.error=str(ex)
        finally:self.done.set()
    def update(self,n,total,name):self.progress=(n,total,name)

class Panel:
    def __init__(self,master,detailed_logs=True,event_sink=None,run_parent=None):
        self.master=master;master.title('Dash GPU视觉读取');master.geometry('630x740')
        self.detailed_logs=detailed_logs;self.event_sink=event_sink
        self.run_parent=Path(run_parent) if run_parent is not None else Path(os.environ['LOCALAPPDATA'])/'RyoGeese/reader_tmp'
        self.state=FactStream();self.metrics=Metrics();self.proc=None;self.job=None;self.run=None;self.journal=None
        self.stopping=None;self.eof=False;self.receiver_error=None;self.worker_stopped=None;self.started_at=None;self.last_message=time.monotonic();self.finished=False
        self.preflight=None;self.pending_start=None
        self.progress_delay_logged=False
        self.memory_samples=collections.deque(maxlen=600);self.guard=OwnedMemoryGuard();self.last_memory=0;self.last_drawn_seq=None;self.last_state_token=None;self.closing=False
        self.banner=tk.StringVar(value='准备中；点击开始即确认游戏和Dash当前完整可见。不会发送游戏输入。')
        ttk.Label(master,textvariable=self.banner,wraplength=610).pack(padx=10,pady=10)
        controls=ttk.Frame(master);controls.pack(fill='x',padx=10)
        self.interval=tk.IntVar(value=DEFAULTS['intervalMs']);self.duration=tk.IntVar(value=DEFAULTS['seconds'])
        ttk.Label(controls,text='周期ms').pack(side='left');ttk.Spinbox(controls,from_=100,to=2000,increment=100,textvariable=self.interval,width=6).pack(side='left')
        ttk.Label(controls,text='时长秒').pack(side='left');ttk.Spinbox(controls,from_=5,to=3600,increment=30,textvariable=self.duration,width=6).pack(side='left')
        self.start_button=ttk.Button(controls,text='游戏已就绪，开始',command=self.start);self.start_button.pack(side='left',padx=5)
        ttk.Button(controls,text='重新定位',command=self.relocate).pack(side='left');ttk.Button(controls,text='停止',command=self.stop).pack(side='left')
        self.memory_text=tk.StringVar(value='整机内存只提示；没有固定空闲MB启动门槛。')
        ttk.Label(master,textvariable=self.memory_text,wraplength=610).pack(padx=10,pady=8)
        frame=ttk.Frame(master);frame.pack(fill='both',expand=True,padx=10)
        self.labels={}
        for row,name in enumerate(FIELDS):
            ttk.Label(frame,text=name,width=26).grid(row=row,column=0,sticky='w')
            label=ttk.Label(frame,text='UNKNOWN',width=17);label.grid(row=row,column=1,sticky='w');self.labels[name]=label
        ttk.Label(master,text='仅读插件内部事实；本次测视觉速度/内存，尚未接技能推荐。',wraplength=610).pack(pady=6)
        master.protocol('WM_DELETE_WINDOW',self.close);master.after(100,self.pulse)
    def start(self,chat_ready=None):
        if self.preflight is not None or (self.proc is not None and not self.finished):return
        try:
            interval=int(self.interval.get());seconds=int(self.duration.get())
            if interval!=500 or not (seconds==0 or 5<=seconds<=3600):raise ValueError('当前固定每500毫秒读取一次')
            # Bind readiness at the human action, never renew it after slow hashing.
            ready=dict(candidateRoot=str(ROOT),humanReady=True,readyUTC=datetime.now(timezone.utc).isoformat(),intervalMs=interval,seconds=seconds,source='HUMAN_CURRENT_READY_BUTTON_CLICK')
            if chat_ready:
                bound=json.loads(Path(chat_ready).read_text('utf-8'))
                if bound.get('humanReady') is not True:raise ValueError('CHAT_READY_NOT_HUMAN')
                ready.update(readyUTC=bound['readyUTC'],source='HUMAN_CURRENT_CHAT_READY',humanMessage=bound['humanMessage'])
            self.proc=None;self.run=None;self.pending_start=(interval,seconds,ready)
            self.preflight=RuntimeCheck();self.start_button.configure(state='disabled');self.banner.set('正在后台核验运行文件；可停止或关闭。尚未加载模型或采集。')
        except Exception as ex:self.banner.set('启动检查失败：'+str(ex));self.start_button.configure(state='normal')
    def launch(self,interval,seconds,ready):
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(ready['readyUTC'])).total_seconds()
            if not 0<=age<=180:raise ValueError('READY_NOT_CURRENT')
            # Plain system-memory query is advisory even at 0MB; a query failure is also recorded.
            try:advisory=start_assessment(memory_status())
            except Exception as ex:advisory=dict(allowed=True,systemMemoryHardGate=False,error=str(ex))
            run=self.run_parent/uuid.uuid4().hex;run.mkdir(parents=True,exist_ok=False)
            atomic_json(run/'ready.json',ready)
            if self.detailed_logs:atomic_json(run/'startup_memory_advisory.json',advisory)
            self.state=FactStream();self.metrics=Metrics();self.guard=OwnedMemoryGuard();self.memory_samples.clear()
            self.run=run;self.journal=Journal(run/'events.jsonl') if self.detailed_logs else ErrorEvents(self.event_sink);self.eof=False;self.receiver_error=None;self.worker_stopped=None;self.stopping=None;self.finished=False;self.last_drawn_seq=None;self.last_state_token=None
            env=os.environ.copy();env['DOTNET_CLI_HOME']=str(CACHE_ROOT/'dotnet-home');env['DOTNET_CLI_TELEMETRY_OPTOUT']='1'
            env['TEMP']=env['TMP']=str(CACHE_ROOT/'temp');Path(env['TEMP']).mkdir(parents=True,exist_ok=True)
            env['CUDA_CACHE_PATH']=str(CACHE_ROOT/'cuda-cache');env.pop('DASH_OFFLINE_ORT_TRACE',None)
            self.started_at=self.last_message=time.monotonic();self.last_memory=0
            self.proc=subprocess.Popen([str(DOTNET),str(WORKER),'--live',str(run/'ready.json'),str(interval),str(seconds)],cwd=str(ROOT),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW)
            self.job=OwnedJob(self.proc)
            self.start_button.configure(state='disabled');self.banner.set('初始化GPU；系统内存压力只记录，不阻止启动。')
            self.journal.write(dict(kind='owned_process_created',pid=self.proc.pid,jobKillOnClose=True))
            threading.Thread(target=self.receive,args=(self.proc,self.state,self.metrics,self.journal),daemon=True,name='GPU-state-receiver').start();threading.Thread(target=self.read_errors,args=(self.proc,self.journal),daemon=True,name='GPU-errors').start()
        except Exception as ex:
            self.eof=True;self.receiver_error='START_ERROR:'+str(ex);self.state.clear('START_ERROR',terminal=True);self.banner.set('启动失败：'+str(ex));self.start_button.configure(state='normal')
            if self.event_sink:self.event_sink('reader_launch_failed',error=self.receiver_error)
            if self.proc is not None and self.proc.poll() is None:self.proc.kill()
    def receive(self,process,state,metrics,journal):
        try:
            for line in iter(lambda:process.stdout.readline(65537),''):
                if len(line)>65536:raise ValueError('STDOUT_LINE_BOUND')
                p=json.loads(line)
                if self.proc is process and p.get('kind')=='stopped':self.worker_stopped=p
                journal.write(p);metrics.add(p);state.accept(p)
                if self.proc is process:
                    self.last_message=time.monotonic()
                    self.progress_delay_logged=False
        except Exception as ex:
            if self.proc is process:self.receiver_error=str(ex)
            state.clear('RECEIVER_ERROR',terminal=True)
        finally:
            if self.proc is process:self.eof=True
            state.finish('EOF')
    def read_errors(self,process,journal):
        try:
            for line in iter(lambda:process.stderr.readline(8193),''):journal.write(dict(kind='stderr',text=line[:8192]))
        except Exception as ex:
            if self.proc is process:self.receiver_error='STDERR:'+str(ex)
    def send(self,command):
        if self.proc is not None and self.proc.poll() is None:
            try:self.proc.stdin.write(json.dumps(command)+'\n');self.proc.stdin.flush()
            except (BrokenPipeError,OSError):pass
    def stop(self,reason='USER_STOP'):
        if self.preflight is not None:self.preflight.cancel.set()
        self.state.clear(reason,terminal=True)
        for label in self.labels.values():label.configure(text='UNKNOWN')
        if self.proc is not None and self.proc.poll() is None:
            if self.stopping is None:self.stopping=time.monotonic();self.send(dict(command='stop'))
        if self.run is not None and self.detailed_logs:
            try:atomic_json(self.run/'latest_state.json',dict(packet=None,reason=reason,scope='plugin_only',sourceAgeVerified=False))
            except OSError as ex:self.receiver_error='STATE_WRITE_ERROR:'+str(ex)
        self.banner.set('停止中，旧状态已清空。')
    def relocate(self):
        if self.proc is None or self.proc.poll() is not None:return
        revision=self.state.relocate();self.send(dict(command='relocate',revision=revision));self.banner.set('重新定位；旧状态已清空。')
    def pulse(self):
        try:self.update_panel()
        except Exception as ex:
            # A broken disk/UI callback must not leave an unsupervised worker.
            self.receiver_error='PANEL_ERROR:'+str(ex);self.state.clear('PANEL_ERROR',terminal=True)
            if self.event_sink:self.event_sink('reader_panel_error',error=self.receiver_error)
            try:
                for label in self.labels.values():label.configure(text='UNKNOWN')
                self.banner.set('面板异常，已结束采集并清空状态：'+str(ex));self.start_button.configure(state='disabled')
            finally:
                try:
                    if self.job is not None:self.job.close();self.job=None
                finally:
                    if self.proc is not None and self.proc.poll() is None:self.proc.kill()
                    self.finished=True;self.eof=True
            if self.run is not None and self.detailed_logs:
                try:atomic_json(self.run/'panel_failure.json',dict(reason=self.receiver_error,workerKilled=True))
                except OSError:pass
            if self.closing:self.master.destroy()
    def check_progress(self,now):
        if self.metrics.ticks==0 and self.stopping is None and now-self.started_at>=DEFAULTS['startupTimeoutSeconds']:
            self.journal.write(dict(kind='WARMUP_TIMEOUT',elapsedSeconds=now-self.started_at,
                                    limitSeconds=DEFAULTS['startupTimeoutSeconds'],action='STOP_OWNED_READER'))
            self.stop('WARMUP_TIMEOUT')
        elif self.metrics.ticks>0 and now-self.last_message>DEFAULTS['progressTimeoutSeconds'] and not self.progress_delay_logged:
            self.progress_delay_logged=True
            self.journal.write(dict(kind='PROGRESS_DELAY_OBSERVED',seconds=now-self.last_message,action='LOG_ONLY_NO_DROP'))
        if self.stopping is not None and now-self.stopping>DEFAULTS['stopGraceSeconds'] and self.job is not None:
            self.journal.write(dict(kind='owned_forced_stop',reason='STOP_GRACE_EXPIRED'));self.job.close();self.job=None
    def update_panel(self):
        now=time.monotonic()
        if self.preflight is not None:
            check=self.preflight
            if check.done.is_set():
                args=self.pending_start;self.preflight=None;self.pending_start=None
                if check.cancel.is_set() or self.closing:self.banner.set('启动核验已取消；没有开始采集。');self.start_button.configure(state='normal')
                elif check.error:self.banner.set('运行文件核验失败：'+check.error);self.start_button.configure(state='normal')
                else:self.launch(*args)
            elif not check.cancel.is_set():
                n,total,name=check.progress;self.banner.set('后台核验运行文件 %d/%d：%s；尚未采集。'%(n,total,name))
        if self.proc is not None:
            if self.proc.poll() is not None and not self.finished and (self.eof or self.receiver_error is not None):self.finish()
            elif self.proc.poll() is None:
                elapsed=now-self.started_at
                if self.receiver_error:self.stop('RECEIVER_ERROR')
                if now-self.last_memory>=1 and self.job is not None:
                    self.last_memory=now
                    try:
                        mem=self.job.memory();system=memory_status();sample=dict(elapsedSeconds=elapsed,reader=mem,panel=panel_memory(),system=system);self.memory_samples.append(sample);self.journal.write(dict(kind='resource',**sample))
                        self.memory_text.set('读取器驻留 %.0fMB / 提交 %.0fMB；整机占用%d%%（仅提示）'%(mem['privateResidentMiB'],mem['privateMiB'],system['loadPercent']))
                        reason=self.guard.observe(elapsed,mem['privateMiB'],mem['privateResidentMiB'])
                        if reason:self.stop(reason)
                    except OSError as ex:self.journal.write(dict(kind='resource_query_error',text=str(ex)))
                self.check_progress(now)
        packet,reason=self.state.view()
        if packet is None:
            for label in self.labels.values():label.configure(text='UNKNOWN')
        elif self.last_drawn_seq!=packet['seq']:
            self.last_drawn_seq=packet['seq'];self.metrics.shown(packet)
            values={f['name']:f for f in packet['facts']}
            for name,label in self.labels.items():
                f=values[name];label.configure(text=str(f['value']) if f['status']=='known' else 'UNKNOWN')
            self.banner.set('读取中：第%d轮，GPU识别%.1fms；采样周期%dms。'%(packet['round'],packet['readMs'],self.interval.get()))
        token=None if packet is None else packet['seq']
        if self.run is not None and token!=self.last_state_token and self.detailed_logs:
            self.last_state_token=token
            atomic_json(self.run/'latest_state.json',dict(schema='dash-gpu-state/1',scope='plugin_only',sourceAgeVerified=False,targetIdentity=None,targetEpoch=None,packet=packet,reason=reason))
        if self.closing and (self.proc is None or self.finished):self.master.destroy();return
        self.master.after(100,self.pulse)
    def finish(self):
        self.state.finish('STOPPED');self.finished=True
        for label in self.labels.values():label.configure(text='UNKNOWN')
        if self.job is not None:self.job.close();self.job=None
        report=dict(state='LIVE_TEST_FINISHED_NOT_FORMAL_ACCEPTANCE',exitCode=self.proc.returncode,elapsedSeconds=time.monotonic()-self.started_at,metrics=self.metrics.report(),resources=list(self.memory_samples),workerStopped=self.worker_stopped,receiverError=self.receiver_error,all25Cleared=all(label.cget('text')=='UNKNOWN' for label in self.labels.values()),formalFrozen=False,independentVAL=0)
        if self.detailed_logs:atomic_json(self.run/'summary.json',report)
        else:self.journal.write(dict(kind='finished',exitCode=self.proc.returncode,error=self.receiver_error,elapsedSeconds=report['elapsedSeconds']))
        self.start_button.configure(state='normal');self.banner.set('运行结束，25项已清空。')
    def close(self):
        self.closing=True;self.stop('PANEL_CLOSED');self.master.withdraw()
        if self.proc is None or self.finished:self.master.destroy()

if __name__=='__main__':
    app=tk.Tk();panel=Panel(app)
    if len(sys.argv)==3 and sys.argv[1]=='--chat-ready':app.after(200,lambda:panel.start(sys.argv[2]))
    app.mainloop()
