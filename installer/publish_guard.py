"""Refuse saved player data before assembly/compilation. Never deletes user data."""
import json,re
from pathlib import Path

PRIVATE_FOLDERS={'user_data','userdata','logs','sessions','__pycache__'}
PRIVATE_FILES={'current.json','current_profile.json','keybindings.json','startup-memory.json'}
PRIVATE_SCHEMAS={'startup-memory/1','shadow_priest_startup_profile/1','shadow_priest_keybindings/1'}
REFERENCES={'foundation/simc_runtime/current_profile.json':'shadow_priest_mechanism_profile/1'}
TEXT_TYPES={'.txt','.md','.py','.json','.simc'}
ACTOR=re.compile(r'^\s*(?:priest|warlock|hunter|mage|rogue|warrior|paladin|shaman|druid|monk|demon_hunter|death_knight|evoker)\s*=',re.M)
TALENTS=re.compile(r'^\s*talents\s*=',re.M)

def _contains_saved_state(value):
    if isinstance(value,dict):
        schema=value.get('schema')
        if isinstance(schema,str) and schema in PRIVATE_SCHEMAS:return True
        source=value.get('sourceText')
        if isinstance(source,str) and source.strip():return True
        return any(_contains_saved_state(v) for v in value.values())
    if isinstance(value,list):return any(_contains_saved_state(v) for v in value)
    return False

def check_public_payload(root):
    root=Path(root);count=0
    for path in root.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(root).as_posix();parts=relative.casefold().split('/')
        if (PRIVATE_FOLDERS.intersection(parts[:-1]) or
            (parts[-1] in PRIVATE_FILES and relative not in REFERENCES) or
            path.suffix.casefold() in ('.simc','.log','.dmp') or
            parts[-1].startswith(('报错_','推荐_'))):
            raise ValueError('PRIVATE_PLAYER_FILE:'+relative)
        if path.suffix.casefold() not in TEXT_TYPES:continue
        count+=1
        text=path.read_text('utf-8-sig')
        if ACTOR.search(text) and TALENTS.search(text):raise ValueError('PRIVATE_SIMC_EXPORT:'+relative)
        if path.suffix.casefold()=='.json':
            value=json.loads(text)
            if _contains_saved_state(value):raise ValueError('PRIVATE_SAVED_PROFILE:'+relative)
            if relative in REFERENCES and (not isinstance(value,dict) or value.get('schema')!=REFERENCES[relative]):
                raise ValueError('PRIVATE_REFERENCE_REPLACED:'+relative)
    return {'textFilesChecked':count,'savedPlayerRecords':0}

def check_release_texts(root):
    root=Path(root);release=json.loads((root/'release.json').read_text('utf-8-sig'))
    version=release['version'];url=release['repository_url'];source=(root/'SOURCE.txt').read_text('utf-8-sig')
    for name in ('SOURCE.txt','发布候选说明.txt','THIRD_PARTY_NOTICES.txt'):
        if version not in (root/name).read_text('utf-8-sig').splitlines()[0]:
            raise ValueError('RELEASE_TEXT_VERSION_MISMATCH:'+name)
    for target in (url+'/releases/tag/v'+version,url+'/tree/v'+version):
        if target not in source:raise ValueError('CORRESPONDING_SOURCE_TAG_MISMATCH')
