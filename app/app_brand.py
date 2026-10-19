"""Editable branding only; no recommendation policy."""
from pathlib import Path
from tkinter import messagebox

def about(root):
    from release_info import read_release
    release=read_release()
    messagebox.showinfo('RyoGeese',
        f'RyoGeese {release.version}\n\n本软件由手电加鞭制作，完全开源免费且在github：{release.download_url}，喜欢的话请点个星~',
        parent=root)


def apply_icon(root):
    try:
        from tkinter import PhotoImage
        assets=Path(__file__).resolve().parent/'assets'
        root._ryogeese_icon=PhotoImage(master=root,file=str(assets/'RyoGeese.png'))
        root.iconphoto(True,root._ryogeese_icon)
        root.iconbitmap(default=str(assets/'RyoGeese.ico'))
        root.iconbitmap(str(assets/'RyoGeese.ico'))
        return True
    except Exception:return False
