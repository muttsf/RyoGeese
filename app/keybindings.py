import json
from pathlib import Path
from app_support import ROOT,SKILLS

ORDER=('mind_blast','void_blast','void_torrent','mind_flay','tentacle_slam',
       'shadow_word_madness','vampiric_touch','shadow_word_pain','shadow_word_death',
       'voidform','void_volley','power_infusion')

# The decision lane keeps distinct spells. The setup screen represents buttons.
ALIASES={'void_blast':'mind_blast','void_volley':'voidform'}
BUTTONS=tuple(k for k in ORDER if k not in ALIASES)
BUTTON_LABELS=dict(SKILLS,mind_blast='心灵震爆／虚空冲击',voidform='虚空形态／虚空齐射')

def expand_buttons(values):
    if type(values) is not dict or set(values)!=set(BUTTONS):
        raise ValueError('按键设置格式不完整，请重新打开技能按键。')
    return validate({k:values[ALIASES.get(k,k)] for k in ORDER})

def collapse_buttons(values):
    """Read old records without choosing between conflicting user bindings."""
    keys=validate(values)
    buttons={k:keys[k] for k in BUTTONS}
    conflicts=[]
    for alias,base in ALIASES.items():
        a,b=keys[alias],keys[base]
        if a and b and a.casefold()!=b.casefold():
            buttons[base]=''
            conflicts.append(BUTTON_LABELS[base])
        else:buttons[base]=b or a
    return buttons,conflicts

def validate(values):
    if type(values) is not dict or set(values)!=set(SKILLS):
        raise ValueError('技能按键模板不完整或有未知技能。')
    out={}
    for skill,key in values.items():
        if type(key) is not str:raise ValueError('按键必须为文字。')
        key=key.strip()
        if len(key)>24 or any(ord(c)<32 or ord(c)==127 for c in key):
            raise ValueError('按键最多24个字符，不能含换行或控制字符。')
        out[skill]=key
    return out

class KeyStore:
    def __init__(self,directory=None):
        self.directory=(Path(directory) if directory else ROOT/'user_data').resolve()
        if ROOT not in self.directory.parents:raise ValueError('配置路径必须在本候选内。')
        self.path=self.directory/'keybindings.json'

    def load(self):
        if not self.path.exists():return {k:'' for k in SKILLS}
        if self.path.stat().st_size>16384:raise ValueError('按键文件过大。')
        data=json.loads(self.path.read_text('utf-8-sig'))
        if data.get('schema')!='shadow_priest_keybindings/1':raise ValueError('按键文件格式不支持。')
        return validate(data['keys'])

    def save(self,values):
        keys=validate(values)
        self.directory.mkdir(exist_ok=True,parents=True)
        temp=self.directory/'keybindings.tmp'
        try:
            with temp.open('w',encoding='utf-8') as f:
                json.dump(dict(schema='shadow_priest_keybindings/1',keys=keys),f,ensure_ascii=False,indent=2)
            temp.replace(self.path)
        finally:
            if temp.is_file():temp.unlink()
        return keys

