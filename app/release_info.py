"""Shared release identity for the About dialog and installer generation."""
from dataclasses import dataclass
import json
from pathlib import Path
import re

@dataclass(frozen=True)
class Release:
    version: str
    file_version: str
    repository_url: str

    @property
    def download_url(self):
        return self.repository_url + '/releases'

    @property
    def tag(self):
        return 'v' + self.version

    @property
    def installer_filename(self):
        return 'RyoGeese-' + self.version + '-x64-Setup.exe'

def read_release(path=None):
    source=Path(path) if path is not None else Path(__file__).with_name('release.json')
    data=json.loads(source.read_text(encoding='utf-8-sig'))
    version=data.get('version')
    if type(version) is not str or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:alpha|beta|rc)\.[1-9]\d*)?',version):
        raise ValueError('INVALID_RELEASE_VERSION')
    numbers=[int(part) for part in version.split('-',1)[0].split('.')]
    build=data.get('build_number')
    if type(build) is not int or not 0<=build<=65535 or any(n>65535 for n in numbers):
        raise ValueError('INVALID_WINDOWS_FILE_VERSION')
    url=data.get('repository_url')
    if type(url) is not str or not re.fullmatch(r'https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_.-]+',url):
        raise ValueError('INVALID_RELEASE_REPOSITORY_URL')
    return Release(version,'.'.join(str(n) for n in (*numbers,build)),url)
