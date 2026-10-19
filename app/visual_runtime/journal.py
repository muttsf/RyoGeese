"""Bounded diagnostic files; image bytes are never accepted."""
from pathlib import Path
import json,threading,os,time

def _replace_with_retry(source,target):
    """Return prior replace failures (0..3); 0 is first-attempt success.

    Three planned sleeps total 70ms, not a wall-clock upper bound.
    """
    # Some Windows readers temporarily deny delete/rename. Keep the atomic
    # replacement and tolerate at most three short waits; persistent/other I/O
    # errors still reach the existing owned-worker stop guard.
    for attempt in range(4):
        try:
            os.replace(source,target)
            return attempt
        except PermissionError as ex:
            if getattr(ex,'winerror',None) not in (5,32,33) or attempt==3:raise
            time.sleep((.01,.02,.04)[attempt])


class Journal:
    def __init__(self,path):self.path=Path(path);self.lock=threading.Lock();self.limit=16*1024*1024
    def write(self,value):
        data=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
        if len(data)>65536:raise ValueError('JOURNAL_PACKET_TOO_LARGE')
        with self.lock:
            if self.path.exists() and self.path.stat().st_size+len(data)>self.limit:_replace_with_retry(self.path,self.path.with_suffix('.previous.jsonl'))
            with self.path.open('ab') as f:f.write(data)

class ErrorEvents:
    """Ordinary packets stay in memory; only errors enter the public error logger."""
    def __init__(self,sink):self.sink=sink
    def write(self,value):
        if self.sink is None:return
        kind=str(value.get('kind','unknown'))
        try:
            if kind=='stopped' and value.get('reason') not in (None,'USER_STOP_OR_PARENT_EOF','DURATION_COMPLETE'):
                self.sink('reader_error',packet=value)
            else:self.sink('reader_'+kind,**{k:v for k,v in value.items() if k!='kind'})
        except Exception:pass

def atomic_json(path,value):
    path=Path(path);data=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
    if len(data)>512*1024:raise ValueError('STATE_FILE_SIZE_BOUND')
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(data)
    return _replace_with_retry(temp,path)
