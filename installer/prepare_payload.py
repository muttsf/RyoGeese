"""Assemble reviewed sources with exact, externally supplied runtime dependencies."""
import argparse,hashlib,json,shutil,uuid
from pathlib import Path,PurePosixPath
from publish_guard import check_public_payload,check_release_texts

REPOSITORY=Path(__file__).resolve().parents[1]

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def relative_name(value):
    if not isinstance(value,str) or not value or any(c in value for c in ('\\',':','$','"','\r','\n')):
        raise ValueError('UNSAFE_FILE_NAME')
    path=PurePosixPath(value)
    if path.is_absolute() or value!=path.as_posix() or any(part in ('..','.') or part.endswith((' ','.')) for part in value.split('/')) or '//' in value:
        raise ValueError('UNSAFE_FILE_NAME')
    return path

def regular_file(root,name):
    root=Path(root).resolve();path=root/str(relative_name(name))
    if root not in path.resolve().parents:raise ValueError('PATH_OUTSIDE_INPUT')
    for current in (path,*path.parents):
        if current.exists() and (current.is_symlink() or getattr(current.lstat(),'st_file_attributes',0)&0x400):
            raise ValueError('INPUT_DIRECTORY_LINK')
        if current==root:break
    if not path.is_file():raise ValueError('MISSING_INPUT:'+name)
    return path

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')

def prepare(dependencies,output,build_id=None):
    source=REPOSITORY/'app';output=Path(output).absolute()
    if output.exists():raise ValueError('OUTPUT_MUST_BE_NEW')
    check_public_payload(source)
    check_release_texts(source)
    for item in (source.resolve(),Path(dependencies).resolve()):
        if output==item or item in output.parents:raise ValueError('OUTPUT_INSIDE_INPUT')
    if output.resolve()!=output:raise ValueError('OUTPUT_DIRECTORY_LINK')
    for item in output.parents:
        if item.exists() and (item.is_symlink() or getattr(item.lstat(),'st_file_attributes',0)&0x400):
            raise ValueError('OUTPUT_DIRECTORY_LINK')
    for name in ('reader/gpu/dash.cu','reader/gpu/dash.ptx','reader/gpu/dash.ptx.source.sha256',
                 '图标导入规则.txt','icon_rules.json','notices/INSTALL_TERMS.txt'):
        regular_file(source,name)
    stamp=(source/'reader/gpu/dash.ptx.source.sha256').read_text('utf-8').strip()
    if stamp!=digest(source/'reader/gpu/dash.cu'):raise ValueError('KERNEL_SOURCE_STAMP_MISMATCH')
    pins=json.loads((REPOSITORY/'DEPENDENCIES.json').read_text('utf-8'))
    if pins.get('schema')!='ryogeese-dependencies/1':raise ValueError('DEPENDENCY_SCHEMA')
    names=set()
    # Check all dependency paths and hashes before creating the output tree.
    for pin in pins['files']:
        name=pin['path'];relative_name(name)
        if name.casefold() in names:raise ValueError('DUPLICATE_DEPENDENCY_PATH')
        names.add(name.casefold())
        if not (name.startswith('runtime/') or name.startswith('reader/bin/')):raise ValueError('DEPENDENCY_SCOPE')
        path=regular_file(dependencies,name)
        if path.stat().st_size!=pin['bytes'] or digest(path)!=pin['sha256']:raise ValueError('DEPENDENCY_CHANGED:'+name)
    output.mkdir(parents=True)
    for path in sorted(source.rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(source).as_posix();path=regular_file(source,name)
        if name.casefold() in names:raise ValueError('SOURCE_DEPENDENCY_COLLISION')
        relative_name(name)
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    for pin in pins['files']:
        target=output/pin['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(regular_file(dependencies,pin['path']),target)
        if digest(target)!=pin['sha256']:raise ValueError('DEPENDENCY_COPY_CHANGED:'+pin['path'])
    release=json.loads((source/'release.json').read_text('utf-8'))
    metadata=json.loads((source/'runtime_metadata.json').read_text('utf-8'))
    metadata['version']='RYOGEESE-'+(build_id or uuid.uuid4().hex)
    save(output/'runtime_metadata.json',metadata)
    def pin(path):return {'path':path.relative_to(output).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}
    foundation=[path for path in sorted((output/'foundation/simc_runtime').rglob('*')) if path.is_file()]
    save(output/'foundation/01-来源保护与隔离副本.json',{'copies':[{'copy':pin(path)} for path in foundation]})
    runtime=[]
    for folder in ('runtime','reader'):
        for path in sorted((output/folder).rglob('*')):
            if path.is_file():
                entry=pin(path);entry['SHA256']=entry.pop('sha256');runtime.append(entry)
    save(output/'visual_runtime/runtime_lock.json',{'schema':'ryogeese-package-runtime/1','candidateRoot':'.','files':runtime,
         'externalPrerequisites':['Windows WGC and system APIs','NVIDIA display driver','Microsoft Visual C++ x64 runtime']})
    sources=[path for path in sorted(output.rglob('*')) if path.is_file() and
             path.relative_to(output).parts[0] not in {'runtime','reader'} and
             path.name not in {'01-本候选来源锁.json','payload_manifest.json'}]
    save(output/'01-本候选来源锁.json',{'copies':[{'copy':pin(path)} for path in sources]})
    files=[pin(path) for path in sorted(output.rglob('*')) if path.is_file() and path.name!='payload_manifest.json']
    save(output/'payload_manifest.json',{'version':metadata['version'],'releaseVersion':release['version'],
         'state':'REBUILT_CANDIDATE_REQUIRES_RELEASE_REVIEW','pluginBundled':False,'files':files})
    return {'output':str(output),'files':len(files)+1,'dependencyFiles':len(pins['files']),
            'manifestSHA256':digest(output/'payload_manifest.json')}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dependency-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--build-id')
    args=parser.parse_args()
    print(json.dumps(prepare(args.dependency_root,args.output,args.build_id),ensure_ascii=False))
