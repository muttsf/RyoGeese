"""Only UUID-local pinned dependencies; no legacy assistant entry point."""
import hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
FOUNDATION=ROOT/'foundation'
def verify_local():
    lock=json.loads((ROOT/'01-本候选来源锁.json').read_text('utf-8'))
    for item in lock['copies']:
        p=(ROOT/ item['copy']['path']).resolve()
        if ROOT not in p.resolve().parents:raise ValueError('DEPENDENCY_OUTSIDE_CANDIDATE')
        b=p.read_bytes()
        if len(b)!=item['copy']['bytes'] or hashlib.sha256(b).hexdigest()!=item['copy']['sha256']:
            raise ValueError('DEPENDENCY_CHANGED:'+p.name)
verify_local()
sys.path.insert(0,str(FOUNDATION))
from runtime_access import load_runtime
IMPORTER,PROMPT=load_runtime()
SKILLS=PROMPT.SKILLS

