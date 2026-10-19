"""Static template registry; routing never executes SIMC directives."""
from dataclasses import dataclass
from app_support import IMPORTER,SKILLS

@dataclass(frozen=True)
class Template:
    id: str='priest.shadow.voidweaver.single'
    label: str='暗影牧师 · 虚空编织者 · BOSS单体'
    short_label: str='暗牧'
    skills: tuple=tuple(SKILLS)
    actor: str='priest'
    specialization: str='shadow'
    plugin_profile: str='shadow'
    layout: str='L16'
    active_resources: tuple=('C2',)
    reserved_resources: tuple=('C3',)

SHADOW=Template()

# Deliberately no skills, reader, or rotation implementation for planned specs.
PLANNED_TEMPLATES = {
    ('warlock','demonology'): '恶魔术：待支持，不能使用暗牧循环',
}

def select_template(text):
    actors=[];specs=[]
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line:continue
        key,value=(p.strip() for p in line.split('=',1))
        if key in IMPORTER.ACTORS:actors.append(key)
        if key=='spec':specs.append(value)
    if len(actors)==len(specs)==1 and (actors[0],specs[0]) in PLANNED_TEMPLATES:
        raise ValueError(PLANNED_TEMPLATES[(actors[0],specs[0])])
    if actors!=['priest'] or specs!=['shadow']:
        raise ValueError('目前仅适配暗牧；请粘贴含职业和spec的单角色完整SIMC导出。')
    return SHADOW
