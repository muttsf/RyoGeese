"""Borderless dark recommendation display. No capture or decision policy."""
import tkinter as tk
from tkinter import font as tkfont
from app_support import SKILLS
from display_driver import DisplayDriver
from spell_icons import SpellIcons

BG='#0d0a14';FG='#f5efff';MUTED='#b6a9c8';LINE='#443350';INSET='#241a32';PURPLE='#ddc6f5';SOFT='#3b294e'
PRIMARY='#7548a5';PRIMARY_HOVER='#8a59bd';PRIMARY_EDGE='#b189d4'
OPACITY=.90
class RecommendationWindow:
    def __init__(self,root,state,worker,topmost=True,preview=False,on_locate=None,on_config=None,on_keys=None,on_close=None,specialization_name='暗牧'):
        self.root=root;self.state=state;self.worker=worker
        self.mode='standard';self.normal_geometry='600x280+120+120';self.drag=None
        self.on_close=on_close
        self.location_complete=False
        self.preview=preview
        self.icons=SpellIcons(root)
        self.skill_font=tkfont.Font(root,family='Microsoft YaHei UI',size=-34,weight='bold')
        self.key_font=tkfont.Font(root,family='Segoe UI',size=-38,weight='bold')
        self.mini_font=tkfont.Font(root,family='Segoe UI',size=38)
        self.last_mini_text=None
        root.title(specialization_name+'推荐'+(' · 离线外观预览' if preview else ''))
        root.geometry(self.normal_geometry);root.minsize(560,270)
        root.overrideredirect(True);root.attributes('-alpha',OPACITY)
        root.configure(bg=BG);root.attributes('-topmost',topmost)
        self.normal=tk.Frame(root,bg=BG,padx=20,pady=14,highlightbackground=LINE,highlightthickness=1)
        self.normal.pack(fill='both',expand=True)
        self.normal.columnconfigure(0,weight=1);self.normal.rowconfigure(1,weight=1)
        header=tk.Frame(self.normal,bg=BG);header.grid(row=0,column=0,sticky='ew');header.columnconfigure(0,weight=1)
        self.spec_label=tk.Label(header,text=specialization_name,font=('Microsoft YaHei UI',11,'bold'),bg=BG,fg=FG,padx=0)
        self.spec_label.grid(row=0,column=0,sticky='w')
        self.burst_status=tk.StringVar(value='爆发自动')
        self.burst_label=tk.Label(header,textvariable=self.burst_status,font=('Microsoft YaHei UI',10),bg=BG,fg=PURPLE)
        self.burst_label.grid(row=0,column=1,padx=(10,14))
        self.mode_button=tk.Button(header,text='极简',command=lambda:self.set_mode('mini'),font=('Microsoft YaHei UI',10),
            bg=INSET,fg=FG,activebackground=SOFT,activeforeground=FG,relief='flat',bd=0,highlightthickness=1,
            highlightbackground=LINE,padx=12,pady=4,cursor='hand2')
        self.mode_button.grid(row=0,column=2)
        main=tk.Frame(self.normal,bg=BG,pady=18);main.grid(row=1,column=0,sticky='nsew')
        main.columnconfigure(1,weight=1)
        self.icon=tk.Label(main,image=self.icons.get(None,96),width=96,height=96,bg=INSET,bd=0,
            highlightbackground='#73518f',highlightthickness=1)
        self.icon.grid(row=0,column=0,padx=(0,20),sticky='nw')
        current=tk.Frame(main,bg=BG);current.grid(row=0,column=1,sticky='nsew')
        current.columnconfigure(0,weight=1);current.rowconfigure(1,weight=1);current.rowconfigure(2,weight=1)
        self.loading=tk.Label(current,text='载入中',font=('Microsoft YaHei UI',14),bg=BG,fg=MUTED,padx=0,bd=0)
        self.skill=tk.Label(current,text='',font=self.skill_font,bg=BG,fg=FG,anchor='w',padx=0,pady=0,bd=0)
        self.skill.grid(row=1,column=0,sticky='nw')
        self.key=tk.Label(current,text='',font=self.key_font,bg=BG,fg=FG,padx=0,pady=1,anchor='w',bd=0,
            highlightthickness=0,wraplength=300,justify='left')
        self.key.grid(row=2,column=0,sticky='sw')
        self.close_frame=tk.Frame(main,bg='#8c67ad',padx=1,pady=1)
        self.close_frame.grid(row=0,column=2,sticky='ne',padx=(12,0),pady=(22,0))
        self.close_button=tk.Button(self.close_frame,text='退出',command=self.close,font=('Microsoft YaHei UI',-20),bg=INSET,fg=PURPLE,
            activebackground=SOFT,activeforeground=FG,relief='flat',bd=0,highlightthickness=0,
            padx=22,pady=10,cursor='hand2')
        self.close_button.pack()
        footer=tk.Frame(self.normal,bg=BG);footer.grid(row=2,column=0,sticky='ew',pady=(2,0))
        footer.columnconfigure(0,weight=1,uniform='footer_edge')
        footer.columnconfigure(1,weight=0)
        footer.columnconfigure(2,weight=1,uniform='footer_edge')
        self.burst_button=tk.Button(footer,text='暂缓爆发',command=self.toggle_burst,font=('Microsoft YaHei UI',-24,'bold'),
            bg=PRIMARY,fg='#ffffff',activebackground=PRIMARY_HOVER,activeforeground='#ffffff',relief='flat',bd=0,
            highlightbackground=PRIMARY_EDGE,highlightthickness=1,padx=40,pady=11,cursor='hand2')
        self.burst_button.grid(row=0,column=1)
        self.locate_button=tk.Button(footer,text='重新定位',command=on_locate,font=('Microsoft YaHei UI',10),
            bg=INSET,fg=FG,activebackground=SOFT,activeforeground=FG,relief='flat',bd=0,
            highlightbackground=LINE,highlightthickness=1,padx=10,pady=6,cursor='hand2')
        self.locate_button.grid(row=0,column=2,sticky='e')
        # Session writes diagnostic status here; it is intentionally not a label.
        self.runtime_status=tk.StringVar(value='')
        for widget in (header,self.spec_label,main,self.icon,current,self.skill,self.key):
            widget.bind('<ButtonPress-1>',self._drag_start)
            widget.bind('<B1-Motion>',self._drag_move)
        self.mini=tk.Frame(root,bg=BG)
        self.mini_key=tk.Label(self.mini,text='',font=self.mini_font,bg=BG,fg=FG)
        self.mini_key.pack(fill='both',expand=True)
        self.mini_key.bind('<Double-Button-1>',lambda event:self.set_mode('standard'))
        self.mini_key.bind('<ButtonPress-1>',self._drag_start)
        self.mini_key.bind('<B1-Motion>',self._drag_move)
        root.bind('<Escape>',lambda event:self.set_mode('standard') if self.mode=='mini' else None)
        root.bind('<Alt-F4>',lambda event:self.close())
        self.menu=tk.Menu(root,tearoff=0)
        self.menu.add_command(label='返回标准',command=lambda:self.set_mode('standard'))
        self.menu.add_command(label='停止并关闭',command=self.close)
        self.mini_key.bind('<Button-3>',lambda e:self.menu.tk_popup(e.x_root,e.y_root))
        self.driver=DisplayDriver(root,state,worker,self.render,interval_ms=10)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.render(state.view())

    def _drag_start(self,event):
        self.drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())

    def _drag_move(self,event):
        if self.drag:self.root.geometry(f'+{event.x_root-self.drag[0]}+{event.y_root-self.drag[1]}')

    def set_mode(self,mode):
        if mode not in ('standard','mini'):raise ValueError('INVALID_DISPLAY_MODE')
        if mode==self.mode:return
        if mode=='mini':
            self.normal_geometry=self.root.geometry()
            x,y=self.root.winfo_x(),self.root.winfo_y()
            self.normal.pack_forget();self.root.overrideredirect(True)
            self.root.minsize(72,72);self.root.geometry(f'104x88+{x}+{y}')
            self.mini.pack(fill='both',expand=True)
        else:
            self.mini.pack_forget();self.root.overrideredirect(True)
            self.root.minsize(560,270);self.root.geometry(self.normal_geometry)
            self.normal.pack(fill='both',expand=True)
        self.mode=mode
        self.render(self.state.view())

    def toggle_burst(self):
        self.state.request_mode('hold' if self.state.mode=='auto' else 'auto')
        self.render(self.state.view())

    def set_location_complete(self,complete):
        self.location_complete=bool(complete)
        self.render(self.state.view())

    def render(self,view):
        self.last_rendered_view=view
        if view.details_json is None and not view.stopped:
            self.loading.configure(text='完成' if self.location_complete else '载入中')
            self.loading.grid(row=0,column=0,sticky='w',pady=(0,4))
        else:self.loading.grid_remove()
        if view.requested_mode=='hold':
            status='正在暂缓…' if view.pending_control else '爆发已暂缓'
        else:
            status='正在恢复自动…' if view.pending_control and view.applied_mode=='hold' else '爆发自动'
        if self.burst_status.get()!=status:self.burst_status.set(status)
        self._text(self.burst_button,'恢复爆发' if view.requested_mode=='hold' else '暂缓爆发')
        self.burst_label.configure(fg='#efb8f0' if view.requested_mode=='hold' else PURPLE)
        self._text(self.skill,view.skill_name or '')
        self._text(self.key,view.key or '')
        icon=self.icons.get(view.skill,96)
        if str(self.icon.cget('image'))!=str(icon):self.icon.configure(image=icon)
        text='' if view.skill is None else view.key
        self._text(self.mini_key,text)
        face=self.mini_font
        if text!=self.last_mini_text:
            size=38;face.configure(size=size)
            while size>10 and (face.measure(text)>96 or face.metrics('linespace')>72):
                size-=1;face.configure(size=size)
            self.last_mini_text=text
        if self.mode=='mini':
            width=max(104,face.measure(text)+16);height=max(88,face.metrics('linespace')+16)
            if self.root.winfo_width()!=width or self.root.winfo_height()!=height:self.root.geometry(f'{width}x{height}')
        else:
            self.root.minsize(max(560,self.normal.winfo_reqwidth()),max(270,self.normal.winfo_reqheight()))

    @staticmethod
    def _text(widget,text):
        if widget.cget('text')!=text:widget.configure(text=text)

    def start(self):self.driver.start()
    def close(self):
        if self.on_close is not None:return self.on_close()
        try:self.driver.stop('WINDOW_CLOSED')
        finally:self.root.destroy()

