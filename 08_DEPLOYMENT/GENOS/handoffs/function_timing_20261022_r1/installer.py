"""Exact-byte diagnostic patch; no engine rehash, data changes or automatic push."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def digest(raw):return hashlib.sha256(raw).hexdigest()
def plain(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('SYMLINK_PATH')
    return path

def put(path,raw):
    path=plain(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def write(path,value):put(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
def sha(path):return digest(plain(path).read_bytes()) if plain(path).is_file() else None

def code_gate(root):
    """Verify current selected engine/workflow pins, without rewriting any."""
    pipeline=json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    pins={'00_SYSTEM/PIPELINE.json':sha(root/'00_SYSTEM/PIPELINE.json')}
    entries=[(e,False) for e in pipeline['engines'].values()]+[(e,True) for e in pipeline.get('workflows',{}).get('registered',[])]
    for entry,is_workflow in entries:
        name=entry['manifest']
        if sha(root/name)!=entry['sha256']:raise ValueError('MANIFEST_HASH: '+name)
        pins[name]=entry['sha256']
        value=json.loads((root/name).read_text())
        if is_workflow and value.get('version')!=entry.get('version'):raise ValueError('WORKFLOW_VERSION')
        for file,expected in value.get('files',{}).items():
            if is_workflow:file='02_BACKEND/workflow/'+file
            if file in pins and pins[file]!=expected:raise ValueError('PIN_CONFLICT: '+file)
            pins[file]=expected
    for name,expected in pins.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('INVALID_PIN_PATH')
        if sha(root/name)!=expected:raise ValueError('CODE_HASH: '+name)
    return pins


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['check','apply','gate','rollback'])
    parser.add_argument('--root',default=str(Path.home()/'DEV'))
    parser.add_argument('--state',required=True)
    parser.add_argument('--committed',action='store_true')
    parser.add_argument('--generation')
    args=parser.parse_args()
    package=Path(__file__).resolve().parent
    spec=json.loads((package/'PATCH.json').read_text())
    for name,expected in spec['assets'].items():
        if sha(package/name)!=expected:raise ValueError('PACKAGE_HASH: '+name)
    root=plain(Path(args.root).expanduser()).resolve(strict=True)
    actual=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True).strip()
    if Path(actual).resolve()!=root:raise ValueError('EXISTING_DEV_CHECKOUT_REQUIRED')
    state=plain(args.state);state.mkdir(parents=True,exist_ok=True)
    with (state/'LOCK').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt=state/'INSTALL_STATE.json'
        binding={'root':str(root),'device':root.stat().st_dev,'inode':root.stat().st_ino,'package_sha256':sha(package/'PATCH.json')}
        statefile=state/'ROOT_BINDING.json'
        if statefile.exists() and json.loads(statefile.read_text())!=binding:raise ValueError('ROOT_OR_PACKAGE_CHANGED')
        if not statefile.exists():write(statefile,binding)
        prior=json.loads(receipt.read_text()) if receipt.exists() else None
        if args.mode=='rollback':
            if prior is None:raise ValueError('NO_INSTALL_RECEIPT')
            for name,record in prior['files'].items():
                if sha(root/name) not in (record['before_sha256'],record['after_sha256']):raise ValueError('USER_CHANGE_PRESERVED: '+name)
            for name,record in reversed(list(prior['files'].items())):
                if record['before'] is None:
                    if (root/name).exists():(root/name).unlink()
                else:put(root/name,base64.b64decode(record['before'],validate=True))
            prior['status']='ROLLED_BACK';write(receipt,prior)
            print('ROLLBACK_COMPLETE; deploy previous committed revision separately')
            return
        for name,record in spec['files'].items():
            current=sha(root/name)
            allowed=[record['after_sha256']] if args.mode=='gate' else record['before_sha256']+[record['after_sha256']]
            if current not in allowed:raise ValueError('UNKNOWN_CODE_PRESERVED: '+name+' actual='+str(current))
        pins=code_gate(root)
        if args.mode=='apply':
            if prior is None or prior['status']=='ROLLED_BACK':
                files={}
                for name,record in spec['files'].items():
                    current=sha(root/name)
                    if current==record['after_sha256']:raise ValueError('INSTALLED_WITHOUT_RECEIPT: '+name)
                    raw=(root/name).read_bytes() if current is not None else None
                    files[name]={'before':base64.b64encode(raw).decode() if raw is not None else None,
                        'before_sha256':current,'after_sha256':record['after_sha256']}
                prior={'binding':binding,'status':'APPLYING','files':files,'unchanged_pins':pins}
                write(receipt,prior)
            # Preserve an interrupted apply receipt and resume only these exact bytes.
            for name,record in prior['files'].items():
                if sha(root/name) not in (record['before_sha256'],record['after_sha256']):raise ValueError('APPLY_RESUME_CONFLICT')
            for name in prior['files']:
                raw=(package/spec['files'][name]['payload']).read_bytes()
                put(root/name,raw)
            code_gate(root)
            prior['status']='APPLIED';write(receipt,prior)
        current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        if args.committed:
            names=list(pins)+list(spec['files'])
            tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0'))
            if not set(names)<=tracked:raise ValueError('UNTRACKED_DEPLOY_CODE')
            subprocess.run(['git','diff','--quiet','HEAD','--',*names],cwd=root,check=True)
        if args.mode=='gate' and args.committed:
            command=[sys.executable,str(package/'genos_release_gate.py'),'--code-zip',str(package/'CODE.zip'),'--deploy-root',str(root)]
            if args.generation:command+=['--generation',args.generation]
            else:command+=['--code-only']
            subprocess.run(command,check=True)
        generation={'status':'NOT_VERIFIED','reason':'explicit field generation/revision not supplied'}
        if args.generation:
            selected=plain(Path(args.generation).expanduser()).resolve(strict=True)
            # Metadata identity only; this never claims source/index E2E verification.
            generation={'status':'E2E_AND_ASSETS_VERIFIED' if args.mode=='gate' and args.committed else 'MANIFEST_IDENTITY_ONLY','path':str(selected),'manifest_sha256':sha(selected/'manifest.json')}
            if generation['manifest_sha256'] is None:raise ValueError('GENERATION_MANIFEST_MISSING')
        result={'mode':args.mode,'python':sys.executable,'version':sys.version.split()[0],
            'root':str(root),'head':current_head,'committed_checked':args.committed,
            'code':{n:sha(root/n) for n in spec['files']},'engine_dependency_files_verified':len(pins),
            'generation':generation,'serving_revision':'NOT_VERIFIED','field_workflow_request':'NOT_RUN'}
        write(state/(args.mode+'-'+uuid.uuid4().hex+'.json'),result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        print(args.mode.upper()+'_COMPLETE')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('FAILED: '+type(exc).__name__+': '+str(exc),file=sys.stderr)
        sys.exit(1)
