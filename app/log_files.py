"""Two-category, best-effort log storage. Budgets never gate the application."""
import json,os,re,stat,threading,uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path

FILE_BYTES=5*1024*1024
COUNTS={'报错':8,'推荐':32}
CHINA=timezone(timedelta(hours=8))
NAME=re.compile(r'^(报错|推荐)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d{6}_[0-9a-f]{8}_\d{4}(?:_fatal)?\.txt$')
LOCK=threading.RLock()
ACTIVE=set()

def local_time():return datetime.now(CHINA).isoformat(timespec='milliseconds')
def _reparse(path):
    return bool(path.lstat().st_file_attributes&0x400) if hasattr(path.lstat(),'st_file_attributes') else path.is_symlink()

class LogFiles:
    def __init__(self,directory=None,file_bytes=FILE_BYTES,counts=None):
        self.directory=Path(directory) if directory is not None else Path(os.environ['LOCALAPPDATA'])/'RyoGeese/logs'
        self.file_bytes=file_bytes;self.counts=dict(COUNTS if counts is None else counts)
        self.run=uuid.uuid4().hex[:8];self.number=0;self.streams={};self.error=None
        self.cleanup_failures=0;self.write_failures=0;self.closed=False

    def _failure(self,exc,cleanup=False):
        if cleanup:self.cleanup_failures+=1
        else:
            self.error=type(exc).__name__+':'+str(exc)[:160];self.write_failures+=1

    def _ensure(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        if _reparse(self.directory):raise OSError('日志目录是链接，未写入或清理该目录。')

    def _new(self,category,fatal=False):
        self._ensure();self.number+=1
        stamp=datetime.now(CHINA).strftime('%Y-%m-%d_%H-%M-%S_%f')
        path=self.directory/f'{category}_{stamp}_{self.run}_{self.number:04d}{"_fatal" if fatal else ""}.txt'
        stream=path.open('xb',buffering=0);ACTIVE.add(path)
        self._prune(category)
        return path,stream

    def _prune(self,category):
        # A locked/unremovable old file is a soft cleanup failure, never a startup gate.
        try:
            if not self.directory.exists():return
            if _reparse(self.directory):raise OSError('日志目录是链接，未清理该目录。')
            files=[]
            for path in self.directory.iterdir():
                match=NAME.fullmatch(path.name)
                if not match or match[1]!=category or _reparse(path):continue
                info=path.stat()
                if stat.S_ISREG(info.st_mode):files.append((info.st_mtime_ns,path))
            excess=max(0,len(files)-self.counts[category])
            for _,path in sorted(files):
                if not excess:break
                if path in ACTIVE:continue
                try:path.unlink();excess-=1
                except FileNotFoundError:excess-=1
                except OSError as exc:self._failure(exc,cleanup=True)
        except OSError as exc:self._failure(exc,cleanup=True)

    def _close_category(self,category):
        previous=self.streams.pop(category,None)
        if previous:
            path,stream,_,_=previous
            try:stream.close()
            finally:ACTIVE.discard(path)

    def write(self,category,record,header=None):
        try:
            raw=(json.dumps(record,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
            head=b'' if header is None else (json.dumps(header,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
            if category not in self.counts or len(raw)>65536 or len(head)>16384:raise ValueError('LOG_ENTRY_BOUND')
            with LOCK:
                if self.closed:return False
                current=self.streams.get(category)
                if current is None or current[3]!=head or current[2]+len(raw)>self.file_bytes:
                    self._close_category(category)
                    path,stream=self._new(category)
                    current=[path,stream,0,head];self.streams[category]=current
                    if head:
                        if stream.write(head)!=len(head):raise OSError('LOG_HEADER_SHORT_WRITE')
                        current[2]+=len(head)
                if current[1].write(raw)!=len(raw):raise OSError('LOG_SHORT_WRITE')
                current[2]+=len(raw)
                self.error=None
            return True
        except Exception as exc:
            with LOCK:
                self._failure(exc)
                try:self._close_category(category)
                except OSError:pass
            return False

    def open_fatal(self):
        try:
            with LOCK:
                if self.closed:return None
                return self._new('报错',fatal=True)
        except OSError as exc:self._failure(exc);return None

    def close_fatal(self,item):
        if item is None:return
        with LOCK:
            path,stream=item
            try:
                stream.close()
                if not _reparse(self.directory) and not _reparse(path) and path.stat().st_size==0:path.unlink()
            except OSError as exc:self._failure(exc)
            finally:ACTIVE.discard(path)

    def close(self):
        with LOCK:
            self.closed=True
            for category in list(self.streams):
                try:self._close_category(category)
                except OSError as exc:self._failure(exc)
            for category in self.counts:self._prune(category)

    def status(self):
        return dict(directory=str(self.directory),fileBytes=self.file_bytes,counts=dict(self.counts),
                    error=self.error,cleanupFailures=self.cleanup_failures,writeFailures=self.write_failures)

_default=None
def default_logs():
    global _default
    with LOCK:
        if _default is None:_default=LogFiles()
        return _default
