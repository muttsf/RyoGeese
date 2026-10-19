"""Compact equal setup cards; dialogs edit data, DesktopApp retains the rules."""
import tkinter as tk
from tkinter import ttk
from keybindings import BUTTONS,expand_buttons
from setup_dialogs import SimcDialog,KeyMappingDialog
from templates import select_template

BG='#f4f4f4';CARD='#ffffff';FG='#171717';MUTED='#666666';LINE='#d0d0d0'
LOCKED_BG='#e3e3e3';LOCKED_FG='#999999'


class MainWindow:
    def __init__(self,root,owner,confirmation_sound=None):
        self.root=root;self.owner=owner;self.confirmation_sound=confirmation_sound
        self.source_text='';self.result_text='';self.simc_dialog=None;self.keys_dialog=None
        self.keys_visited=False;self.step_locks=None
        root.title('RyoGeese');root.overrideredirect(False);root.resizable(True,True)
        root.geometry('960x780');root.minsize(820,720);root.configure(bg=BG)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TFrame',background=CARD);style.configure('Page.TFrame',background=BG)
        style.configure('TLabel',background=CARD,foreground=FG,font=('Microsoft YaHei UI',10))
        style.configure('Page.TLabel',background=BG)
        style.configure('TButton',font=('Microsoft YaHei UI',11),padding=(18,8),background=CARD,foreground=FG,
                        bordercolor='#999999',lightcolor=CARD,darkcolor=CARD,focuscolor=FG)
        style.map('TButton',background=[('disabled','#eeeeee'),('active','#e8e8e8')],foreground=[('disabled','#999999')])
        style.configure('Primary.TButton',background='#222222',foreground='white',bordercolor='#222222',lightcolor='#222222',darkcolor='#222222')
        style.map('Primary.TButton',background=[('disabled','#dddddd'),('active','#444444')],foreground=[('disabled','#999999')])
        style.configure('TCheckbutton',background=CARD,foreground=FG,font=('Microsoft YaHei UI',10),indicatorbackground=CARD,indicatorforeground=FG,focuscolor=FG)
        style.map('TCheckbutton',background=[('active',CARD)])
        style.configure('TEntry',fieldbackground=CARD,foreground=FG,bordercolor=LINE,lightcolor=CARD,darkcolor=CARD,insertcolor=FG)
        style.map('TEntry',bordercolor=[('focus','#777777')],lightcolor=[('focus','#777777')],darkcolor=[('focus','#777777')])
        style.configure('TScrollbar',background='#dddddd',troughcolor=BG,bordercolor=BG,lightcolor='#dddddd',darkcolor='#dddddd',arrowcolor=FG)
        style.configure('Locked.TFrame',background=LOCKED_BG)
        style.configure('Locked.TLabel',background=LOCKED_BG,foreground=LOCKED_FG)
        style.configure('Locked.TButton',background='#d8d8d8',foreground=LOCKED_FG,bordercolor='#c5c5c5',lightcolor='#d8d8d8',darkcolor='#d8d8d8')
        style.map('Locked.TButton',background=[('disabled','#d8d8d8'),('active','#d8d8d8')],foreground=[('disabled',LOCKED_FG)])
        style.configure('Locked.TCheckbutton',background=LOCKED_BG,foreground=LOCKED_FG,indicatorbackground=LOCKED_BG)
        style.map('Locked.TCheckbutton',background=[('disabled',LOCKED_BG),('active',LOCKED_BG)],foreground=[('disabled',LOCKED_FG)])
        self.outer=ttk.Frame(root,style='Page.TFrame',padding=20);self.outer.pack(fill='both',expand=True)
        self.outer.columnconfigure(0,weight=1);self.outer.rowconfigure(1,weight=1)
        header=ttk.Frame(self.outer,style='Page.TFrame');header.grid(row=0,column=0,sticky='ew',pady=(0,18));header.columnconfigure(0,weight=1)
        ttk.Label(header,text='RyoGeese',style='Page.TLabel',font=('Segoe UI',25,'bold')).grid(row=0,column=0,sticky='w')
        self.icons_button=ttk.Button(header,text='导入图标包',command=self.open_icons);self.icons_button.grid(row=0,column=1,padx=(8,8))
        self.manual_button=ttk.Button(header,text='使用说明',command=owner.open_manual);self.manual_button.grid(row=0,column=2,padx=(0,8))
        self.logs_button=ttk.Button(header,text='打开日志',command=owner.open_logs);self.logs_button.grid(row=0,column=3)
        cards=ttk.Frame(self.outer,style='Page.TFrame');cards.grid(row=1,column=0,sticky='nsew');cards.columnconfigure(0,weight=1)
        self.step_cards=[]
        titles=('1  导入 SIMC','2  定位插件','3  技能定位','4  开始')
        bodies=[]
        for row,title in enumerate(titles):
            cards.rowconfigure(row,weight=1,uniform='steps')
            card=tk.Frame(cards,bg=CARD,highlightbackground=LINE,highlightthickness=1,padx=18,pady=14)
            card.grid(row=row,column=0,sticky='nsew',pady=(0,12));card.grid_propagate(False);card.columnconfigure(0,weight=1)
            ttk.Label(card,text=title,font=('Microsoft YaHei UI',13,'bold')).grid(row=0,column=0,sticky='w')
            body=ttk.Frame(card);body.grid(row=1,column=0,sticky='ew',pady=(12,0));body.columnconfigure(0,weight=1)
            self.step_cards.append(card);bodies.append(body)
        self.simc_status=tk.StringVar(value='未导入')
        ttk.Label(bodies[0],textvariable=self.simc_status,foreground=MUTED).grid(row=0,column=0,sticky='w')
        self.import_button=ttk.Button(bodies[0],text='导入SIMC',command=self.open_simc)
        self.import_button.grid(row=0,column=1,sticky='e')
        self.locator_status=tk.StringVar(value='未载入')
        self.locator_label=ttk.Label(bodies[1],textvariable=self.locator_status,foreground=MUTED);self.locator_label.grid(row=0,column=0,sticky='w')
        self.locate_button=ttk.Button(bodies[1],text='定位插件',command=owner.locate);self.locate_button.grid(row=0,column=1,sticky='e')
        self.key_status=tk.StringVar(value='未设置')
        ttk.Label(bodies[2],textvariable=self.key_status,foreground=MUTED).grid(row=0,column=0,sticky='w')
        self.keys_button=ttk.Button(bodies[2],text='设置技能按键',command=self.open_keys);self.keys_button.grid(row=0,column=1,sticky='e')
        self.key_vars={skill:tk.StringVar() for skill in BUTTONS}
        for value in self.key_vars.values():value.trace_add('write',self._keys_changed)
        self.confirmed=tk.BooleanVar(value=False)
        self.confirm_box=ttk.Checkbutton(bodies[3],text='确认配置，准备开始',variable=self.confirmed,command=self._confirmation_changed)
        self.confirm_box.grid(row=0,column=0,sticky='w')
        self.start_button=ttk.Button(bodies[3],text='开始推荐',style='Primary.TButton',command=owner.start,state='disabled');self.start_button.grid(row=0,column=2,sticky='e')
        self.status=tk.StringVar(value='')
        self.status_label=ttk.Label(self.outer,textvariable=self.status,style='Page.TLabel',foreground=MUTED,wraplength=880)
        self.status_label.grid(row=2,column=0,sticky='ew',pady=(2,0))
        self.apply_step_locks(False,False,False,False)
        root.protocol('WM_DELETE_WINDOW',owner.close)

    def get_text(self):return self.source_text

    def set_text(self,text):
        self.keys_visited=False
        self.source_text=text;self.owner.profile_edited();self._source_status()

    def show_result(self,text):
        self.result_text=text;self._source_status()

    def _source_status(self):
        checked=bool(getattr(self.owner,'preview',None) and self.owner.preview['ready'])
        self.simc_status.set('已载入：'+select_template(self.source_text).short_label if checked else '待核对' if self.source_text else '未导入')

    def import_simc(self,text):
        if len(text.encode('utf-8'))>262144:raise ValueError('内容过大，请只导入一个角色的SIMC。')
        self.set_text(text);self.owner.check_profile()
        return bool(getattr(self.owner,'preview',None) and self.owner.preview['ready'])

    def get_keys(self):return expand_buttons({skill:value.get() for skill,value in self.key_vars.items()})

    def _keys_changed(self,*args):
        self.keys_visited=False
        count=sum(bool(value.get().strip()) for value in self.key_vars.values())
        self.key_status.set(f'已填写 {count}/{len(BUTTONS)}' if count else '未设置')
        self.owner.keys_edited()

    def open_simc(self):
        if 'disabled' in self.import_button.state():return None
        if self.simc_dialog is None:self.simc_dialog=SimcDialog(self)
        else:self.simc_dialog.window.lift()
        return self.simc_dialog

    def open_icons(self):
        if 'disabled' in self.icons_button.state():return None
        from icon_dialog import choose_icon_pack
        return choose_icon_pack(self)

    def open_keys(self):
        if 'disabled' in self.keys_button.state():return None
        if self.keys_dialog is None:self.keys_dialog=KeyMappingDialog(self)
        else:self.keys_dialog.window.lift()
        self.keys_visited=True
        self.owner.update_controls()
        return self.keys_dialog

    def apply_step_locks(self,checked,located,valid_keys,busy):
        if not (checked and located):self.keys_visited=False
        keys_ready=checked and located and valid_keys and self.keys_visited
        if not keys_ready and self.confirmed.get():self.confirmed.set(False)
        locks=(False,not checked,not (checked and located),not keys_ready)
        if locks!=self.step_locks:
            self.step_locks=locks
            for card,locked in zip(self.step_cards,locks):self._shade_card(card,locked)
        self.import_button.state(['disabled'] if busy else ['!disabled'])
        self.icons_button.state(['disabled'] if busy else ['!disabled'])
        self.keys_button.state(['disabled'] if busy or locks[2] else ['!disabled'])
        self.confirm_box.state(['disabled'] if busy or locks[3] else ['!disabled'])

    def _shade_card(self,card,locked):
        card.configure(bg=LOCKED_BG if locked else CARD)
        remaining=list(card.winfo_children())
        while remaining:
            widget=remaining.pop();remaining.extend(widget.winfo_children())
            if isinstance(widget,ttk.Frame):widget.configure(style='Locked.TFrame' if locked else 'TFrame')
            elif isinstance(widget,ttk.Label):
                widget.configure(style='Locked.TLabel' if locked else 'TLabel',foreground=LOCKED_FG if locked else FG if widget.master is card else MUTED)
            elif isinstance(widget,ttk.Checkbutton):widget.configure(style='Locked.TCheckbutton' if locked else 'TCheckbutton')
            elif isinstance(widget,ttk.Button):
                widget.configure(style='Locked.TButton' if locked else 'Primary.TButton' if widget is self.start_button else 'TButton')
            if locked and isinstance(widget,(ttk.Button,ttk.Checkbutton)):widget.state(['disabled'])

    def _confirmation_changed(self):
        self.owner.update_controls()
        if self.confirmed.get() and self.confirmation_sound is not None:
            try:self.confirmation_sound()
            except Exception as exc:
                record=getattr(self.owner,'record',None)
                if record:record('confirmation_sound_failed',error=type(exc).__name__)

