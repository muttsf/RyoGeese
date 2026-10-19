"""Build a tiny windowed entry, not a software installer."""
import argparse,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from release_info import read_release

def build(compiler,output):
    root=ROOT;output=Path(output)
    if output.exists():raise ValueError('LAUNCHER_OUTPUT_MUST_BE_NEW')
    release=read_release(root/'app/release.json')
    with tempfile.TemporaryDirectory(prefix='ryogeese-launcher-') as temporary:
        version=Path(temporary)/'Version.cs'
        version.write_text('using System.Reflection;\n'+''.join(
            '[assembly: '+key+'("'+value+'")]\n' for key,value in (
                ('AssemblyVersion',release.file_version),('AssemblyFileVersion',release.file_version),
                ('AssemblyInformationalVersion',release.version))),'utf-8')
        args=[str(compiler),'/nologo','/codepage:65001','/target:winexe','/platform:anycpu','/optimize+','/debug-',
              '/win32icon:'+str(root/'app/assets/RyoGeese.ico'),'/out:'+str(output),str(root/'installer/Launcher.cs'),str(version)]
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
    if result.returncode:raise RuntimeError(result.stdout.decode('utf-8',errors='replace'))
    return result.stdout.decode('utf-8',errors='replace')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(build(a.compiler,a.output))
