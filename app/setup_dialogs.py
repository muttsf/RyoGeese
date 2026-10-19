"""Modal draft editors. No disk persistence, reader, or recommendation logic."""
import tkinter as tk
from tkinter import ttk
from keybindings import BUTTONS,BUTTON_LABELS,expand_buttons

class DraftDialog:
    def __init__(self,ui,title,width,height,attribute):
        self.ui=ui;self.attribute=attribute;self.window=tk.Toplevel(ui.root)
        self.window.title(title);self.window.transient(ui.root);self.window.configure(bg='white')
        x=ui.root.winfo_x()+max(0,(ui.root.winfo_width()-width)//2)
        y=ui.root.winfo_y()+max(0,(ui.root.winfo_height()-height)//2)
        self.window.geometry(f'{width}x{height}+{x}+{y}');self.window.minsize(width-80,height-60)
        self.window.protocol('WM_DELETE_WINDOW',self.close);self.window.bind('<Escape>',lambda event:self.close())
        self.body=ttk.Frame(self.window,padding=18);self.body.pack(fill='both',expand=True)
        self.body.columnconfigure(0,weight=1);self.body.rowconfigure(0,weight=1)
        self.error=tk.StringVar(value='')
        ttk.Label(self.body,textvariable=self.error,wraplength=width-50,justify='left').grid(row=1,column=0,sticky='ew',pady=(8,0))
        self.actions=ttk.Frame(self.body);self.actions.grid(row=2,column=0,sticky='ew',pady=(12,0));self.actions.columnconfigure(0,weight=1)

    def ready(self):
        self.window.update_idletasks();self.window.grab_set()

    def close(self):
        self.window.grab_release();self.window.destroy();setattr(self.ui,self.attribute,None)

class SimcDialog(DraftDialog):
    def __init__(self,ui):
        super().__init__(ui,'导入 SIMC',760,520,'simc_dialog')
        editor=ttk.Frame(self.body);editor.grid(row=0,column=0,sticky='nsew')
        editor.columnconfigure(0,weight=1);editor.rowconfigure(0,weight=1)
        self.text=tk.Text(editor,wrap='none',font=('Consolas',11),bg='white',fg='#171717',insertbackground='#171717',undo=True,bd=1,relief='solid',padx=8,pady=8)
        self.text.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(editor,orient='vertical',command=self.text.yview);vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(editor,orient='horizontal',command=self.text.xview);horizontal.grid(row=1,column=0,sticky='ew')
        self.text.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.text.insert('1.0',ui.get_text())
        left=ttk.Frame(self.actions);left.grid(row=0,column=0,sticky='w')
        self.paste_button=ttk.Button(left,text='粘贴',command=self.paste);self.paste_button.pack(side='left')
        self.previous_button=ttk.Button(left,text='载入上次',command=self.previous);self.previous_button.pack(side='left',padx=(8,0))
        self.cancel_button=ttk.Button(self.actions,text='取消',command=self.close);self.cancel_button.grid(row=0,column=1,padx=(8,8))
        self.import_button=ttk.Button(self.actions,text='导入',style='Primary.TButton',command=self.commit);self.import_button.grid(row=0,column=2)
        self.ready();self.text.focus_set()

    def paste(self):
        try:
            text=self.window.clipboard_get()
            if not text.strip():raise ValueError('剪贴板为空。')
            if len(text.encode('utf-8'))>262144:raise ValueError('内容过大，请只粘贴一个角色的SIMC。')
            self.text.delete('1.0','end');self.text.insert('1.0',text);self.error.set('')
        except (tk.TclError,ValueError) as exc:self.error.set(str(exc))

    def previous(self):
        try:
            previous=self.ui.owner.memory.load()
            if not previous:raise ValueError('没有保存的SIMC记录。')
            self.text.delete('1.0','end');self.text.insert('1.0',previous['sourceText']);self.error.set('')
        except (OSError,ValueError,KeyError,TypeError) as exc:self.error.set('载入上次失败：'+str(exc))

    def commit(self):
        try:
            if self.ui.import_simc(self.text.get('1.0','end-1c')):self.close()
            else:self.error.set(self.ui.result_text)
        except ValueError as exc:self.error.set(str(exc))

class KeyMappingDialog(DraftDialog):
    def __init__(self,ui):
        super().__init__(ui,'技能按键',780,460,'keys_dialog')
        fields=ttk.Frame(self.body);fields.grid(row=0,column=0,sticky='nsew')
        fields.columnconfigure(0,weight=1);fields.columnconfigure(1,weight=1)
        self.variables={};self.inputs={}
        for index,skill in enumerate(BUTTONS):
            group=ttk.Frame(fields,padding=(0,5,16,5));group.grid(row=index//2,column=index%2,sticky='ew');group.columnconfigure(0,weight=1)
            ttk.Label(group,text=BUTTON_LABELS[skill],wraplength=210).grid(row=0,column=0,sticky='w',padx=(0,10))
            value=tk.StringVar(value=ui.key_vars[skill].get());entry=ttk.Entry(group,textvariable=value,width=8,font=('Segoe UI',11))
            entry.grid(row=0,column=1,sticky='e',ipady=3);self.variables[skill]=value;self.inputs[skill]=entry
        self.cancel_button=ttk.Button(self.actions,text='取消',command=self.close);self.cancel_button.grid(row=0,column=1,padx=(8,8))
        self.confirm_button=ttk.Button(self.actions,text='确认',style='Primary.TButton',command=self.commit);self.confirm_button.grid(row=0,column=2)
        self.ready()

    def commit(self):
        try:
            if self.ui.step_locks[2]:raise ValueError('请返回主页面完成插件定位。')
            values=expand_buttons({skill:value.get() for skill,value in self.variables.items()})
            for skill in BUTTONS:self.ui.key_vars[skill].set(values[skill])
            self.ui.keys_visited=True;self.ui.owner.update_controls()
            self.close()
        except ValueError as exc:self.error.set(str(exc))
