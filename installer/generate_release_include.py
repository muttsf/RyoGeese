"""Generate NSIS release definitions from the application's release.json."""
import argparse
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from release_info import read_release

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--metadata',type=Path,default=Path(__file__).resolve().parents[1]/'app/release.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    release=read_release(args.metadata)
    values={'RG_RELEASE_VERSION':release.version,'RG_FILE_VERSION':release.file_version,
            'RG_RELEASE_TAG':release.tag,'RG_REPOSITORY_URL':release.repository_url,
            'RG_DOWNLOAD_URL':release.download_url,'RG_INSTALLER_FILENAME':release.installer_filename}
    text='; Generated from release.json. Do not edit.\n'
    text+=''.join('!define '+key+' "'+value+'"\n' for key,value in values.items())
    with args.output.open('x',encoding='utf-8-sig',newline='\n') as f:f.write(text)

if __name__=='__main__':main()
