"""Optional local PNG files. No downloading, game access, or rotation state."""
import json
import os
from pathlib import Path
import struct

MAX_BYTES=512*1024
MAX_SIDE=512
PNG=b'\x89PNG\r\n\x1a\n'

def png_dimensions(data):
    if type(data) is not bytes or len(data)>MAX_BYTES or len(data)<33:
        raise ValueError('请选择不超过512KB的PNG图片。')
    if data[:8]!=PNG or data[8:16]!=b'\x00\x00\x00\x0dIHDR':
        raise ValueError('图片不是有效的PNG格式。')
    width,height=struct.unpack('>II',data[16:24])
    if not (1<=width<=MAX_SIDE and 1<=height<=MAX_SIDE):
        raise ValueError('图片宽高需在1至512像素之间，建议使用方形图标。')
    return width,height

def read_png(path):
    path=Path(path)
    if not path.is_file():raise ValueError('请选择PNG图片文件。')
    with path.open('rb') as file:data=file.read(MAX_BYTES+1)
    png_dimensions(data)
    return data

class IconStore:
    def __init__(self,template_id,directory=None):
        rules=json.loads(Path(__file__).with_name('icon_rules.json').read_text('utf-8'))
        if rules.get('schema')!='ryogeese-icon-rules/1' or template_id not in rules['templates']:
            raise ValueError('当前职业没有图标导入规则。')
        self.entries=rules['templates'][template_id]['skills']
        self.folder=(Path(directory) if directory is not None else Path(os.environ['LOCALAPPDATA'])/'RyoGeese/icons')/template_id

    def filename(self,skill):
        if skill not in self.entries:raise ValueError('未知技能，未修改图标。')
        number=self.entries[skill]['spellId']
        if type(number) is not int or number<=0:raise ValueError('技能图标规则无效。')
        return str(number)+'.png'

    def _path(self,skill):
        path=self.folder/self.filename(skill)
        for item in (path,*path.parents):
            try:info=item.lstat()
            except FileNotFoundError:continue
            if item.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
                raise OSError('图标保存位置不可用（目录链接）。')
        return path

    def load(self,skill):
        path=self._path(skill)
        if not path.exists():return None
        return read_png(path)

