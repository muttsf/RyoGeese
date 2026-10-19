"""One optional, atomically replaced ZIP. Spell IDs are shared across classes."""
import os,re,stat,struct,tempfile,zipfile,zlib
from pathlib import Path

MAX_PACK=128*1024*1024
MAX_FILES=8192
MAX_TOTAL=256*1024*1024
NAME=re.compile(r'(?:icons/)?([1-9][0-9]{0,9})\.png',re.I)
ZIP_ERRORS=(zipfile.BadZipFile,NotImplementedError,RuntimeError,zlib.error,EOFError)

def regular_location(path):
    for item in (path,*path.parents):
        try:info=item.lstat()
        except FileNotFoundError:continue
        if item.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
            raise OSError('图标保存位置不可用（目录链接）。')
    return path

def _bounded_directory(path):
    size=path.stat().st_size
    if size>MAX_PACK or size<22:raise ValueError('请选择不超过128MB的ZIP图标包。')
    with path.open('rb') as f:
        f.seek(max(0,size-65557));tail=f.read()
    offset=tail.rfind(b'PK\x05\x06')
    if offset<0 or offset+22>len(tail):raise ValueError('图标包不是有效的ZIP文件。')
    _,disk,start,on_disk,count,amount,position,comment=struct.unpack_from('<4s4H2LH',tail,offset)
    if offset+22+comment!=len(tail) or disk or start or count!=on_disk or count>MAX_FILES or amount>4*1024*1024 or position+amount>size-22:
        raise ValueError('图标包过大或格式不支持，请使用普通ZIP。')
    return count

def entries(archive,expected):
    items=archive.infolist()
    if len(items)!=expected:raise ValueError('图标包目录不完整。')
    result={};total=0
    for item in items:
        name=item.orig_filename
        if '\\' in name or name.startswith('/') or any(v in ('.','..') for v in name.split('/')) or '\x00' in name:
            raise ValueError('图标包包含无效路径。')
        if stat.S_ISLNK(item.external_attr>>16) or item.flag_bits&1:
            raise ValueError('图标包不能包含链接或密码。')
        if item.is_dir():continue
        match=NAME.fullmatch(name)
        if not match:
            if name in ('README.txt','README.md','说明.txt') and item.file_size<=16384:continue
            raise ValueError('图标请按技能编号命名，例如8092.png。')
        number=int(match[1])
        if number>4294967295 or number in result:raise ValueError('图标包包含无效或重复的技能编号。')
        if not 33<=item.file_size<=512*1024 or item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
            raise ValueError('单张图标需为不超过512KB的PNG。')
        total+=item.file_size
        if total>MAX_TOTAL:raise ValueError('图标包解压后总大小不能超过256MB。')
        result[number]=item
    if not result:raise ValueError('图标包中没有按技能编号命名的PNG。')
    return result

def _read_icons(archive,icons):
    from icon_store import MAX_BYTES,png_dimensions
    total=0
    for number,item in icons.items():
        with archive.open(item) as source:data=source.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES or len(data)!=item.file_size:
            raise ValueError('图标大小超出限制或与ZIP记录不符。')
        total+=len(data)
        if total>MAX_TOTAL:raise ValueError('图标包解压后总大小不能超过256MB。')
        png_dimensions(data)
        yield number,data

class IconPack:
    def __init__(self,directory=None):
        self.folder=Path(directory) if directory is not None else Path(os.environ['LOCALAPPDATA'])/'RyoGeese/icons'
        self.path=self.folder/'icon_pack.zip'

    def install(self,source,validate_image):
        regular_location(self.path);self.folder.mkdir(parents=True,exist_ok=True)
        descriptor,name=tempfile.mkstemp(prefix='pack.',suffix='.tmp',dir=self.folder)
        temporary=Path(name)
        try:
            with os.fdopen(descriptor,'wb') as output,Path(source).open('rb') as input:
                total=0
                while True:
                    block=input.read(1024*1024)
                    if not block:break
                    total+=len(block)
                    if total>MAX_PACK:raise ValueError('图标包不能超过128MB。')
                    output.write(block)
                output.flush();os.fsync(output.fileno())
            count=_bounded_directory(temporary)
            with zipfile.ZipFile(temporary) as archive:
                icons=entries(archive,count)
                for number,data in _read_icons(archive,icons):validate_image(data)
            regular_location(self.path);temporary.replace(self.path)
            return len(icons)
        except ZIP_ERRORS as exc:
            raise ValueError('图标包损坏或格式不支持。') from exc
        finally:
            if temporary.exists():temporary.unlink()

    def load_many(self,numbers):
        path=regular_location(self.path)
        if not path.exists():return None
        try:
            count=_bounded_directory(path)
            with zipfile.ZipFile(path) as archive:
                icons=entries(archive,count)
                wanted={number:icons[number] for number in set(numbers) if number in icons}
                return dict(_read_icons(archive,wanted))
        except ZIP_ERRORS as exc:
            raise ValueError('本地图标包不可用。') from exc
