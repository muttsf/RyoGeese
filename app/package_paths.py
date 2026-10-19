"""Package files are read-only; mutable files belong to the current user."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parent
READER_ROOT=ROOT/'reader'
DOTNET=ROOT/'runtime/dotnet/dotnet.exe'
CACHE_ROOT=Path(os.environ['LOCALAPPDATA'])/'RyoGeese/cache'
def package_file(relative):
    name=Path(relative)
    if name.is_absolute() or name.drive:raise ValueError('PACKAGE_ABSOLUTE_PATH')
    path=(ROOT/name).resolve()
    if ROOT not in path.parents:raise ValueError('PACKAGE_PATH_OUTSIDE')
    return path
