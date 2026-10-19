"""Startup configuration state without a layout. Historical offline scope only."""
from pathlib import Path
from dataclasses import dataclass
import copy
import hashlib
import json
from runtime_access import load_runtime

@dataclass(frozen=True)
class AppliedProfile:
    identity: str
    revision: int
    bundle_json: str
    purpose: str = 'HISTORICAL_OFFLINE_ONLY'

class ProfileSession:
    def __init__(self, on_change=None, on_applied=None, purpose='offline', store_directory=None):
        if purpose != 'offline': raise ValueError('CURRENT_1215_EXPORT_NOT_VERIFIED')
        module,_ = load_runtime()
        self.importer = module.Importer()
        self.store = module.ProfileStore(store_directory)
        self.on_change = on_change
        self.on_applied = on_applied
        self.text = ''
        self.tier = None
        self.preview = None
        self.active = None
        self.revision = 0
        self.status = 'WAITING_IMPORT'
        self.previous = None
        self.saved_but_not_started = False

    def edit(self, text, tier_override=None):
        if type(text) is not str: raise ValueError('TEXT_REQUIRED')
        self.text = text
        self.tier = tier_override
        self.preview = None
        self.active = None
        self.revision += 1
        self.status = 'WAITING_RECHECK'
        self.saved_but_not_started = False
        if self.on_change: self.on_change(None)

    def load_previous(self):
        saved = self.store.load()
        if saved is None: return False
        self.previous = saved
        self.edit(saved['sourceText'],
                  saved['gearProfile']['tier_mode'] if saved['preview']['tier']['source']=='USER_CONFIRMED' else None)
        return True

    def check(self):
        self.preview = None
        self.active = None
        if self.on_change: self.on_change(None)
        try:
            self.preview = self.importer.parse(self.text,self.tier)
        except Exception:
            self.status = 'REJECTED'
            raise
        self.status = 'CHECKED' if self.preview['ready'] else 'WAITING_SET_CONFIRMATION'
        return copy.deepcopy(self.preview)

    def apply(self):
        self.active = None
        if self.on_change: self.on_change(None)
        if self.preview is None:
            self.status = 'RECHECK_REQUIRED'
            raise ValueError('RECHECK_REQUIRED')
        try:
            bundle = self.importer.build_bundle(self.preview,self.text,self.previous)
            self.store.save(bundle)
        except Exception:
            self.status = 'APPLY_FAILED'
            raise
        data = json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        applied = AppliedProfile(hashlib.sha256(data.encode('utf-8')).hexdigest(),
                                 self.revision,data)
        self.previous = copy.deepcopy(bundle)
        try:
            if self.on_applied: self.on_applied(applied)
        except Exception:
            self.saved_but_not_started = True
            self.status = 'SAVED_BUT_START_CALLBACK_FAILED'
            if self.on_change: self.on_change(None)
            raise
        self.active = applied
        self.status = 'APPLIED_OFFLINE'
        return applied

