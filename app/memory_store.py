"""One bounded atomic record shared by SIMC and keys, stable across candidates."""
import copy,hashlib,json,os,tempfile
from pathlib import Path
from keybindings import validate
from templates import SHADOW,select_template

class MemoryStore:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory is not None else Path(os.environ['LOCALAPPDATA'])/'AiHekili'/'startup'
        self.path=self.directory/'current.json'

    def _read(self):
        if not self.path.exists():return dict(schema='startup-memory/1',template=SHADOW.id,profile=None,keys=None)
        if self.path.stat().st_size>1048576:raise ValueError('保存记录过大，请保留原文件后重新导入。')
        data=json.loads(self.path.read_text('utf-8-sig'))
        if type(data) is not dict or not {'schema','template','profile','keys'}.issubset(data):
            raise ValueError('保存记录结构损坏，请重新核对SIMC；原记录保留。')
        if data.get('schema')!='startup-memory/1' or data.get('template')!=SHADOW.id:raise ValueError('保存记录的模板不受支持。')
        p=data.get('profile')
        if p is not None:
            text=p['sourceText']
            if type(text) is not str or len(text.encode('utf-8'))>262144 or hashlib.sha256(text.encode('utf-8')).hexdigest()!=p['sourceSHA256']:
                raise ValueError('上次SIMC校验失败；原记录保留。')
            select_template(text)
        if data.get('keys') is not None:validate(data['keys'])
        return data

    def _write(self,data):
        raw=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        if len(raw)>1048576:raise ValueError('保存记录过大。')
        self.directory.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='current.',suffix='.tmp',dir=self.directory)
        temp=Path(name)
        try:
            with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            temp.replace(self.path)
        finally:
            if temp.exists():temp.unlink()

    def load(self):return copy.deepcopy(self._read()['profile'])
    def save(self,bundle):
        self._write(self._updated_profile(bundle))
    def save_setup(self,bundle,keys):
        keys=validate(keys)
        data=self._updated_profile(bundle);data['keys']=keys;self._write(data)
        return keys
    def _updated_profile(self,bundle):
        from app_support import IMPORTER
        try:data=self._read()
        except (ValueError,KeyError,TypeError):
            raw=self.path.read_bytes()
            if len(raw)>1048576:raise ValueError('旧记录过大，未覆盖原文件。')
            backup=self.path.with_name('current.corrupt.json')
            if backup.exists() and backup.read_bytes()!=raw:raise ValueError('已有另一份损坏备份，请先保留备份后再恢复。')
            if not backup.exists():
                with backup.open('xb') as f:f.write(raw)
            data=dict(schema='startup-memory/1',template=SHADOW.id,profile=None,keys=None)
        select_template(bundle['sourceText'])
        rebuilt=IMPORTER.Importer().build_bundle(bundle['preview'],bundle['sourceText'],data['profile'])
        if rebuilt!=bundle:raise ValueError('配置内容与重新核对结果不一致。')
        data['profile']=copy.deepcopy(bundle);return data
    def load_keys(self):
        from app_support import SKILLS
        return self._read()['keys'] or {k:'' for k in SKILLS}
    def save_keys(self,keys):
        keys=validate(keys);data=self._read();data['keys']=keys;self._write(data);return keys

class KeyMemory:
    def __init__(self,memory):self.memory=memory
    def load(self):return self.memory.load_keys()
    def save(self,keys):return self.memory.save_keys(keys)
