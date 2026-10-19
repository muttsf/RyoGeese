"""Load optional user icons once per window; missing/bad files stay blank."""
import base64
import tkinter as tk
from icon_store import IconStore
from icon_pack import IconPack
from templates import SHADOW

def make_icon(root,data,size=96,image_factory=None):
    factory=image_factory or tk.PhotoImage
    image=factory(master=root,data=base64.b64encode(data).decode('ascii'),format='png')
    width,height=image.width(),image.height()
    # Crop non-square input first, keeping any later zoom bounded by the frame.
    if width!=height:
        side=min(width,height);left=(width-side)//2;top=(height-side)//2
        square=factory(master=root,width=side,height=side)
        square.tk.call(str(square),'copy',str(image),'-from',left,top,left+side,top+side)
        image=square
    factor=max(1,image.width()//size)
    if factor>1:image=image.subsample(factor)
    # The fixed-size Label centers and clips overflow instead of leaving padding.
    zoom=max(1,(size+image.width()-1)//image.width())
    if zoom>1:image=image.zoom(zoom)
    return image

class SpellIcons:
    def __init__(self,root,store=None,image_factory=None,pack=None,template_id=SHADOW.id):
        factory=image_factory or tk.PhotoImage
        self.images={}
        self.empty={96:factory(master=root,width=96,height=96)}
        store=store if store is not None else IconStore(template_id)
        try:
            packed=(pack if pack is not None else IconPack()).load_many(v['spellId'] for v in store.entries.values())
        except (OSError,ValueError):packed={}
        for skill in store.entries:
            try:
                data=store.load(skill) if packed is None else packed.get(store.entries[skill]['spellId'])
                if data is not None:self.images[skill,96]=make_icon(root,data,96,factory)
            except (OSError,ValueError,tk.TclError):
                pass

    def get(self,skill,size):
        return self.images.get((skill,size),self.empty[size])
