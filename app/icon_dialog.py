"""One file selection for all classes. No per-skill editing UI."""
import tkinter as tk
from tkinter import filedialog,messagebox
from icon_pack import IconPack
from spell_icons import make_icon

def choose_icon_pack(ui):
    path=filedialog.askopenfilename(parent=ui.root,title='选择图标包',filetypes=[('ZIP图标包','*.zip')])
    if not path:return
    ui.status.set('载入中');ui.root.update_idletasks()
    try:
        count=IconPack().install(path,lambda data:make_icon(ui.root,data,36))
        ui.status.set('完成')
        messagebox.showinfo('图标包',f'导入完成，共{count}个图标。下次打开推荐窗生效。',parent=ui.root)
    except (OSError,ValueError,tk.TclError) as exc:
        ui.status.set('导入失败，原图标包保留。')
        messagebox.showerror('图标包未导入',str(exc),parent=ui.root)
