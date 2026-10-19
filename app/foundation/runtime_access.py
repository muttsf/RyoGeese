"""Load the UUID-local unchanged offline importer; reject foreign modules."""
from pathlib import Path
import hashlib
import importlib
import json
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT/'simc_runtime'
MODULES = ('simc_import','strict_talents','talent_model','configured_adapter',
           'base_offline_adapter','display_fields','profile_model','talent_core',
           'controlled_core','frozen_v1','prompt_view')

def load_runtime():
    lock = json.loads((ROOT/'01-来源保护与隔离副本.json').read_text('utf-8'))
    for entry in lock['copies']:
        path = (ROOT.parent / entry['copy']['path']).resolve()
        if RUNTIME not in path.parents: continue
        data = path.read_bytes()
        if len(data)!=entry['copy']['bytes'] or hashlib.sha256(data).hexdigest()!=entry['copy']['sha256']:
            raise ValueError('RUNTIME_FILE_CHANGED:'+path.name)
    for name in MODULES:
        if name in sys.modules and Path(sys.modules[name].__file__).resolve().parent != RUNTIME:
            raise ValueError('FOREIGN_MODULE:'+name)
    if str(RUNTIME) not in sys.path: sys.path.insert(0,str(RUNTIME))
    importer = importlib.import_module('simc_import')
    prompt = importlib.import_module('prompt_view')
    for name in MODULES:
        if name in sys.modules and Path(sys.modules[name].__file__).resolve().parent != RUNTIME:
            raise ValueError('FOREIGN_MODULE:'+name)
    return importer, prompt

