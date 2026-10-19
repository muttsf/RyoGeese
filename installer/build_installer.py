"""Generate exact install/uninstall lists and compile with an explicit NSIS tool."""
import argparse,json,subprocess,sys
from pathlib import Path,PurePosixPath
from prepare_payload import digest,relative_name,regular_file,save
from publish_guard import check_public_payload,check_release_texts

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from release_info import read_release

def legacy_files():
    rules=json.loads((ROOT/'app/icon_rules.json').read_text('utf-8'))
    skills=rules['templates']['priest.shadow.voidweaver.single']['skills']
    return ['assets/man.wav','assets/take-it-boy.wav','icons/icons.json',
            *['icons/'+name+'_96.png' for name in skills]]

def includes(payload,output):
    payload=Path(payload).resolve();output=Path(output)
    if output.exists():raise ValueError('INCLUDE_OUTPUT_MUST_BE_NEW')
    privacy=check_public_payload(payload)
    check_release_texts(payload)
    manifest=json.loads((payload/'payload_manifest.json').read_text('utf-8'))
    files=[];seen=set()
    for row in manifest['files']:
        name=row['path'];relative_name(name)
        if name.casefold() in seen:raise ValueError('DUPLICATE_FILE')
        seen.add(name.casefold());path=regular_file(payload,name)
        if path.stat().st_size!=row['bytes'] or digest(path)!=row['sha256']:raise ValueError('PAYLOAD_CHANGED:'+name)
        files.append(name)
    files.append('payload_manifest.json')
    actual={p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()}
    if actual!=set(files):raise ValueError('UNMANAGED_PAYLOAD_FILE')
    if '图标导入规则.txt' not in files:raise ValueError('ICON_GUIDE_MISSING')
    for name in files:relative_name(name)
    old=set(legacy_files())-set(files)
    folders=set()
    for name in set(files)|old:
        for parent in PurePosixPath(name).parents:
            if str(parent)!='.':folders.add(parent.as_posix())
    output.mkdir(parents=True)
    install=[];last=None
    for name in sorted(files):
        folder=str(PurePosixPath(name).parent)
        if folder!=last:
            suffix='' if folder=='.' else '\\'+folder.replace('/','\\')
            install.append('SetOutPath "$INSTDIR'+suffix+'"');last=folder
        install.append('File "${PAYLOAD_ROOT}\\'+name.replace('/','\\')+'"')
    uninstall=['Delete "$INSTDIR\\'+name.replace('/','\\')+'"' for name in sorted(files)]
    cleanup=['Delete "$INSTDIR\\'+name.replace('/','\\')+'"' for name in sorted(old)]
    checks=[]
    for folder in ['',*sorted(folders)]:
        suffix='' if not folder else '\\'+folder.replace('/','\\')
        checks+=['System::Call \'kernel32::GetFileAttributesW(w "$INSTDIR'+suffix+'") i.r0\'',
                 '${If} $0 != -1','  IntOp $0 $0 & 0x400','  ${If} $0 != 0',
                 '    Goto ${fail_label}','  ${EndIf}','${EndIf}']
    remove=['RMDir "$INSTDIR\\'+folder.replace('/','\\')+'"' for folder in
            sorted(folders,key=lambda value:(-len(PurePosixPath(value).parts),value))]
    for name,lines in [('install_files',install),('uninstall_files',uninstall),('upgrade_cleanup',cleanup),
                       ('check_directories',checks),('remove_empty_directories',remove)]:
        (output/(name+'.nsh')).write_text('\n'.join(lines)+'\n','utf-8-sig')
    release=read_release(payload/'release.json')
    values={'RG_RELEASE_VERSION':release.version,'RG_FILE_VERSION':release.file_version,
            'RG_RELEASE_TAG':release.tag,'RG_REPOSITORY_URL':release.repository_url,
            'RG_DOWNLOAD_URL':release.download_url,'RG_INSTALLER_FILENAME':release.installer_filename}
    (output/'release.nsh').write_text('; Generated from release.json\n'+''.join(
        '!define '+key+' "'+value+'"\n' for key,value in values.items()),'utf-8-sig')
    save(output/'input_manifest.json',{'files':files,'knownLegacyRemoved':sorted(old),
         'directories':sorted(folders),'recursiveRemoval':False,'manifestSHA256':digest(payload/'payload_manifest.json'),
         'publicationPrivacy':privacy})
    return release

def build(payload,output,compiler,template=None,defines=None):
    output=Path(output).absolute()
    if output.exists():raise ValueError('BUILD_OUTPUT_MUST_BE_NEW')
    if Path(payload).resolve() in output.resolve().parents:raise ValueError('BUILD_OUTPUT_INSIDE_PAYLOAD')
    for path in (Path(payload).absolute(),output):
        if any(c in str(path) for c in ('$','"','\r','\n')):raise ValueError('UNSAFE_NSIS_ROOT_PATH')
    if output.resolve()!=output:raise ValueError('BUILD_OUTPUT_DIRECTORY_LINK')
    release=includes(payload,output/'generated')
    target=output/release.installer_filename
    args=[str(Path(compiler).resolve()),'/NOCONFIG','/INPUTCHARSET','UTF8','/OUTPUTCHARSET','UTF8','/V3',
          '/DPAYLOAD_ROOT='+str(Path(payload).resolve()),'/DOUTPUT_FILE='+str(target),
          '/DINCLUDE_ROOT='+str(output/'generated'),'/DVERSION_INCLUDE='+str(output/'generated/release.nsh')]
    args.extend('/D'+key+'='+value for key,value in (defines or {}).items())
    args.append(str(template or ROOT/'installer/RyoGeese.nsi'))
    with (output/'build.log').open('xb') as log:
        result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
    if result.returncode:raise RuntimeError('NSIS_BUILD_FAILED: '+str(output/'build.log'))
    if target.stat().st_size>=2*1024**3:raise ValueError('INSTALLER_SIZE_LIMIT')
    result={'file':target.name,'bytes':target.stat().st_size,'sha256':digest(target),'version':release.version,
            'manifestSHA256':digest(Path(payload)/'payload_manifest.json'),'reviewRequiredBeforePublication':True}
    save(output/'build_result.json',result)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--makensis',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.payload,args.output,args.makensis),ensure_ascii=False))
