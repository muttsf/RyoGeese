"""Desktop ownership and setup flow; the reviewed recommendation lane is reused."""
import hashlib
import json
import os
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

from app_support import ROOT, IMPORTER
from keybindings import collapse_buttons
from memory_store import MemoryStore
from templates import select_template
from profile_session import AppliedProfile
from main_window import MainWindow
from startup import Session, clear_stage
from recommendation_window import RecommendationWindow
from shutdown import request_close
from location_feedback import location_ready


def prepared_backend(root):
    # Only a user click reaches here. Import does not load GPU or capture.
    from visual_backend import VisualBackend
    backend=VisualBackend(root)
    backend.panel.interval.set(500)
    backend.panel.duration.set(0)
    return backend


def reader_end_message(reason,error,banner,worker_reason=''):
    detail=' '.join(str(value or '') for value in (reason,error,banner,worker_reason))
    if 'WARMUP_TIMEOUT' in detail:
        return '载入等待已超过120秒，本轮读取已停止。请让游戏和Dash保持显示后重新定位。'
    if 'GAME_WINDOW_NOT_READY_TIMEOUT' in detail or 'GAME_WINDOW_MINIMIZED' in detail:
        return '暂时无法取得游戏画面。请把游戏恢复到屏幕上，再点击定位插件。'
    if 'GAME_WINDOW_CLOSED_DURING_STARTUP' in detail:
        return '载入期间游戏窗口已关闭，请重新打开游戏后定位。'
    if 'WINDOW_NOT_UNIQUE_EXACT_MATCH:0' in detail:
        return '没有找到可读取的魔兽世界窗口，请让游戏画面显示后定位。'
    return '本次读取已结束：'+(error or worker_reason or reason or banner)


class PreparedBackend:
    """Transfer an already user-started reader to the recommendation session."""
    def __init__(self,backend):self.backend=backend
    def start(self):
        begin=getattr(self.backend,'begin_recommendations',None)
        if begin:begin()
    def view(self):return self.backend.view()
    def relocate(self):return self.backend.relocate()
    def close(self):return self.backend.close()
    def abort(self):return self.backend.abort()
    def closed(self):return self.backend.closed()
    @property
    def panel(self):return getattr(self.backend,'panel',None)


class DesktopSession(Session):
    def __init__(self,owner,profile,keys,backend):
        self.owner=owner
        self.monitor=None
        child=tk.Toplevel(owner.root)
        self.child=child
        flow=SimpleNamespace(root=child,preview=False,short_validation=True,cleanup_root=owner.root,
                             debug_logs=owner.debug_logs,log_files=owner.log_files,
                             on_shutdown_error=owner.shutdown_error,
                             session_root=owner.session_root,
                             backend_factory=lambda root:PreparedBackend(backend))
        try:
            super().__init__(flow,profile,keys)
            self.cancel_button.configure(command=self.close)
            self.cancel_button.pack_forget()
            if owner.debug_logs:
                from session_monitor import TrialMonitor
                self.monitor=TrialMonitor(self,entry_point='DESKTOP_SETUP')
        except Exception:
            if getattr(self,'after',None) is not None:
                self.root.after_cancel(self.after)
            if hasattr(self,'state'):self.state.stop('CONSTRUCTION_FAILED')
            if hasattr(self,'worker'):self.worker.close(0)
            if hasattr(self,'current_log'):self.current_log.close()
            child.destroy()
            raise
        child.bind('<Destroy>',self._destroyed,add='+')

    def _destroyed(self,event):
        if event.widget is self.child and not self.closed:
            # TkDriver may already have removed its Toplevel. The owner survives.
            self.owner.root.after_idle(self.close)

    def render_failed(self):
        # Return from the child timer before disposing its Tcl commands.
        self.child.withdraw()
        self.owner.root.after_idle(self.close)

    def show_window(self):
        clear_stage(self.root)
        self.window=RecommendationWindow(self.root,self.state,self.worker,
            on_locate=self.relocate,on_config=self.close,on_keys=None,on_close=self.close)
        self.window.driver.after_render=self.after_display
        self.window.driver.on_error=self.render_failed
        self.window.start()

    def close(self,on_done=None):
        if self.closed:return super().close()
        if self.monitor:self.monitor.stop()
        def completed():
            report=None
            try:
                if self.monitor:report=self.monitor.save()
                if self.current_log.error:self.owner.record('recommendation_log_error',error=self.current_log.error,dropped=self.current_log.dropped)
            except Exception as exc:
                report='读取已停止，验证摘要保存失败：'+str(exc)
            finally:
                if self.child.winfo_exists():self.child.destroy()
                self.owner.session_ended(self,report)
                if on_done:on_done()
        super().close(completed)


class DesktopApp:
    def __init__(self,root,memory=None,backend_factory=None,session_root=None,log_files=None,sound_player=None,debug_logs=False):
        self.root=root
        self.diagnostics=getattr(root,'diagnostics',None)
        from log_files import default_logs
        self.log_files=log_files or (self.diagnostics.logs if self.diagnostics else default_logs())
        self.sound_player=sound_player;self.debug_logs=debug_logs
        root.ryogeese_debug_logs=debug_logs
        self.memory=memory or MemoryStore()
        self.factory=backend_factory or prepared_backend
        self.session_root=Path(session_root) if session_root else self.memory.directory/'sessions'
        self.importer=IMPORTER.Importer()
        self.previous=None
        self.preview=None
        self.backend=None
        self.session=None
        self.minimum_revision=0
        self.located=False
        self.closing=False
        self.stopping=False
        self.after=None
        self.stop_after=None
        self.stop_errors=()
        self.policy=json.loads((ROOT/'runtime_metadata.json').read_text('utf-8'))
        self.ui=MainWindow(root,self)
        from app_brand import apply_icon
        if not apply_icon(root):self.record('icon_load_failed')
        self.load_previous()
        self.after=root.after(100,self.poll)

    def load_previous(self):
        self.profile_edited()
        self.previous=None
        try:
            self.previous=self.memory.load()
            keys=self.memory.load_keys()
            if self.previous:
                self.ui.set_text(self.previous['sourceText'])
            buttons,conflicts=collapse_buttons(keys)
            for skill,value in buttons.items():self.ui.key_vars[skill].set(value)
            self.ui.status.set('已载入上次记录。' if self.previous else '尚未开始。')
            if conflicts:self.ui.status.set('上次两种形态的按键不同，请重新填写共用按键：'+'、'.join(conflicts)+'。原记录保留。')
        except Exception as exc:
            self.previous=None
            self.ui.status.set('上次记录未载入；原文件保留，请重新导入：'+str(exc))
        self.update_controls()

    def profile_edited(self):
        if not hasattr(self,'ui'):return
        self.preview=None
        self.ui.confirmed.set(False)
        self.ui.show_result('粘贴当前角色的 /simc 导出，再点击“核对SIMC”。\n修改后需要重新核对；套装会自动识别。')
        self.update_controls()

    def keys_edited(self):
        if not hasattr(self,'ui'):return
        self.ui.confirmed.set(False)
        self.update_controls()

    def check_profile(self):
        self.preview=None
        self.ui.confirmed.set(False)
        try:
            text=self.ui.get_text()
            template=select_template(text)
            p=self.importer.parse(text)
            self.preview=p
            tier=IMPORTER.tier_description(p['tier'])
            rows=[template.label,'角色：'+p['character'],
                  '游戏资料：'+(p['versionProvided'] or '导出未提供build'),
                  '套装：'+tier,'已读取 '+str(len(p['equipment']))+' 个已穿装备槽位（不含背包）。']
            if p['warnings']:rows += ['']+['• '+w for w in p['warnings']]
            self.ui.show_result('\n'.join(rows))
            self.ui.status.set('SIMC已核对。' if p['ready'] else '套装资料尚未识别完整；请保留这份SIMC供修正，暂不开始推荐。')
        except Exception as exc:
            self.preview=None
            self.ui.show_result('尚未采用这份配置\n\n'+str(exc))
            self.ui.status.set('核对未通过，原保存记录保留。')
        self.update_controls()

    def update_controls(self):
        if not hasattr(self,'ui'):return
        try:self.ui.get_keys();valid_keys=True
        except ValueError:valid_keys=False
        checked=bool(self.preview and self.preview['ready'])
        busy=self.session is not None or self.stopping or self.closing
        allowed=self.policy.get('readingEnabled') is True
        self.ui.apply_step_locks(checked,self.located,valid_keys,busy)
        ready=checked and valid_keys and self.ui.keys_visited and self.ui.confirmed.get() and self.located and allowed and not busy
        self.ui.start_button.configure(state='normal' if ready else 'disabled')
        self.ui.locate_button.configure(state='disabled' if busy or not checked or not allowed else 'normal',
                                        text='重新定位' if self.backend is not None else '定位插件')

    def locate(self):
        if self.closing or self.stopping or self.session is not None:return
        if self.policy.get('readingEnabled') is not True:
            self.ui.status.set('当前版本尚未开放读取，请查看使用说明。')
            return
        self.located=False
        self.update_controls()
        try:
            self.record('locate_requested',newReader=self.backend is None)
            if self.backend is None:
                self.minimum_revision=0
                self.backend=self.factory(self.root)
                self.backend.start()
            else:
                revision=self.backend.relocate()
                self.minimum_revision=revision if type(revision) is int else self.minimum_revision+1
            self.ui.locator_status.set('载入中')
        except Exception as exc:
            self.ui.locator_status.set('载入失败')
            self.ui.status.set('定位未完成：'+str(exc))
            self.stop()
        self.update_controls()

    def poll(self):
        self.after=None
        if self.closing:return
        if self.backend is not None and self.session is None and not self.stopping:
            try:
                packet,reason,terminal,error,banner=self.backend.view()
                was_located=self.located
                self.located=not terminal and location_ready(packet,self.minimum_revision)
                if terminal:
                    self.ui.locator_status.set('已停止')
                    self.ui.status.set(reader_end_message(reason,error,banner,(getattr(getattr(self.backend,'panel',None),'worker_stopped',None) or {}).get('reason','')))
                    self.stop()
                elif self.located:
                    if not was_located:self.record('locate_completed',revision=packet['revision'],
                        generation=packet.get('generation'),ordinal=packet.get('sourceOrdinal'))
                    self.ui.locator_status.set('完成')
                else:self.ui.locator_status.set('载入中')
            except Exception as exc:
                self.ui.locator_status.set('载入失败')
                self.ui.status.set('读取暂不可用：'+str(exc))
                self.stop()
        self.update_controls()
        self.after=self.root.after(100,self.poll)

    def start(self):
        if self.closing or self.stopping or self.session is not None:return False
        constructing=False
        try:
            if self.policy.get('readingEnabled') is not True:raise ValueError('当前版本未开放读取。')
            if self.backend is None:raise ValueError('请先点击定位插件。')
            packet,reason,terminal,error,banner=self.backend.view()
            if terminal or not location_ready(packet,self.minimum_revision):
                self.located=False
                raise ValueError('当前定位已失效，请等待新画面或重新定位。')
            if not self.ui.confirmed.get():raise ValueError('请确认当前SIMC、插件模板和按键。')
            if not self.ui.keys_visited:raise ValueError('请先打开第三步技能按键设置。')
            if not self.preview or not self.preview['ready']:raise ValueError('请先核对SIMC。')
            text=self.ui.get_text()
            select_template(text)
            keys=self.ui.get_keys()
            # Use the same surviving-record basis as MemoryStore's recovery.
            try:previous=self.memory.load()
            except (ValueError,KeyError,TypeError):previous=None
            bundle=self.importer.build_bundle(self.preview,text,previous)
            # One atomic record: profile and keys are committed together.
            self.memory.save_setup(bundle,keys)
            if self.memory.load_keys()!=keys or self.memory.load()!=bundle:
                raise ValueError('保存后的记录核对失败，尚未开始推荐；请保留日志。')
            self.record('setup_saved_verified',recordPath=str(self.memory.path),sourceSHA256=bundle['sourceSHA256'],buttonCount=10)
            self.previous=bundle
            payload=json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
            profile=AppliedProfile(hashlib.sha256(payload.encode()).hexdigest(),1,payload)
            constructing=True
            self.session=DesktopSession(self,profile,keys,self.backend)
            self.record('recommendation_session_started',session=self.session.state.session,run=str(self.session.run))
            if not self.debug_logs:
                from start_sound import play_start_sound
                play_start_sound(self.record,player=self.sound_player)
            self.root.withdraw()
            self.update_controls()
            return True
        except Exception as exc:
            if constructing:self.stop()
            self.ui.status.set('未能开始：'+str(exc))
            self.update_controls()
            return False

    def session_ended(self,session,report):
        self.record('recommendation_session_ended',session=session.state.session,run=str(session.run),
                    reportSaved=isinstance(report,dict))
        if self.session is session:self.session=None
        self.backend=None
        self.located=False
        self.minimum_revision=0
        if not self.closing:self.root.deiconify()
        self.ui.confirmed.set(False)
        self.ui.locator_status.set('已停止')
        stopped=(report.get('workerStopped') or {}) if isinstance(report,dict) else {}
        ending='30分钟测试已完成，已返回设置。' if stopped.get('reason')=='DURATION_COMPLETE' else '本次读取已停止。'
        self.ui.status.set(ending+'SIMC和按键已保留，可通过“打开日志”查看本轮记录。')
        if isinstance(report,str):self.ui.status.set(report)
        self.update_controls()
        if self.closing:self.root.destroy()

    def stop(self):
        self.record('stop_requested',hasSession=self.session is not None,hasReader=self.backend is not None)
        self.located=False
        self.ui.locator_status.set('已停止')
        if self.session is not None:
            self.session.close()
            return
        if self.backend is None:return
        self.stopping=True
        backend=self.backend
        self.stop_errors=request_close(backend)
        if self.stop_errors:self.shutdown_error('；'.join(self.stop_errors))
        self.update_controls()
        def finished():
            self.stop_after=None
            try:ready=backend.closed()
            except Exception as exc:
                self.stop_errors=('读取退出状态：'+type(exc).__name__,)
                self.shutdown_error(self.stop_errors[0]);return
            if not ready:self.stop_after=self.root.after(50,finished);return
            if self.backend is backend:self.backend=None
            self.stopping=False
            self.stop_errors=()
            self.minimum_revision=0
            self.update_controls()
            if self.closing:self.root.destroy()
        if self.stop_after is None:finished()

    def shutdown_error(self,message):
        self.record('shutdown_error',message=message)
        self.closing=False
        self.root.deiconify()
        if self.after is None:self.after=self.root.after(100,self.poll)
        self.ui.status.set('读取停止异常，请再次关闭窗口重试：'+message)
        self.update_controls()

    def close(self):
        self.record('window_close_requested')
        if self.closing:
            self.stop();return
        self.closing=True
        if self.after is not None:self.root.after_cancel(self.after);self.after=None
        if self.session is not None or self.backend is not None:self.stop()
        else:self.root.destroy()

    def open_manual(self):
        from app_brand import about
        about(self.root)

    def record(self,kind,**data):
        if self.diagnostics:self.diagnostics.event(kind,**data)

    def open_logs(self):
        path=self.log_files.directory
        try:path.mkdir(parents=True,exist_ok=True);os.startfile(path)
        except OSError as exc:self.ui.status.set('日志位置：'+str(path)+'；未能打开：'+str(exc))
