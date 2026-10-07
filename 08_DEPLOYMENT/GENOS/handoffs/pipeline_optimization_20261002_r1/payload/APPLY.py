"""Hash-gated GENOS working-checkout patch, durable backup and rollback."""
import argparse
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def atomic_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as f:
        temporary=Path(f.name);f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
    if target.exists():shutil.copymode(target,temporary)
    os.replace(temporary,target)

def engine_plan(dev,apply=False):
    environment={**os.environ,'PYTHONPATH':str(dev/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(dev)}
    command=[sys.executable,'-m','semantic_runtime.control','rehash-engines']+(['--apply'] if apply else [])
    result=subprocess.run(command,cwd=dev,env=environment,text=True,capture_output=True)
    if result.returncode not in (0,1):raise ValueError('Engine rehash failed: '+result.stderr[-1600:])
    report=json.loads(result.stdout)
    if apply and result.returncode:raise ValueError('Engine rehash apply did not pass')
    return report

def rollback(backup):
    receipt=json.loads((backup/'before.json').read_text());dev=Path(receipt['dev'])
    for path,expected in receipt['before'].items():
        source=backup/'files'/path
        if sha(source)!=expected:raise ValueError('Backup drift: '+path)
    for path in receipt['before']:atomic_copy(backup/'files'/path,dev/path)
    write(backup/'rollback.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'restored':list(receipt['before']),'dev':str(dev)})
    print('ROLLBACK COMPLETE',backup,flush=True)

def apply(dev,check=False):
    dev=dev.resolve();manifest=json.loads((HERE/'CODE_MANIFEST.json').read_text());rows=manifest['files'];code=[r for r in rows if r['role']=='code']
    before={}
    for row in rows:
        source=(HERE/row['path']).resolve();source.relative_to(HERE)
        if sha(source)!=row['sha256']:raise ValueError('Package drift: '+row['path'])
        if source.suffix=='.py':ast.parse(source.read_text(),filename=str(source))
    for row in code:
        target=dev/row['path'];target.resolve().relative_to(dev)
        if target.is_symlink() or not target.is_file():raise ValueError('Checkout file missing/symlink: '+row['path'])
        actual=sha(target)
        if actual not in row['allowed_predecessors']+[row['sha256']]:
            raise ValueError('FILE_DRIFT: '+row['path']+'; no files applied. Use the actual checkout diff to prepare a matching patch.')
        before[row['path']]=actual
    if check:
        print(json.dumps({'preflight':'PASS','code_files':len(code),'dev':str(dev),'python':sys.executable,'version':sys.version},ensure_ascii=False),flush=True);return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=dev/'.genos-pipeline-optimization-backups'/stamp;backup.mkdir(parents=True,exist_ok=False)
    metadata=[dev/'00_SYSTEM/PIPELINE.json',*sorted((dev/'02_BACKEND/ENGINES').rglob('*.json'))]
    for path in metadata:
        if path.is_file():before[str(path.relative_to(dev))]=sha(path)
    for path,expected in before.items():
        dst=backup/'files'/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dev/path,dst)
        if sha(dst)!=expected:raise ValueError('Backup mismatch: '+path)
    write(backup/'before.json',{'dev':str(dev),'before':before,'python':sys.executable,'version':sys.version,'package_manifest_sha256':sha(HERE/'CODE_MANIFEST.json')})
    try:
        for row in code:
            if sha(dev/row['path'])!=before[row['path']]:raise ValueError('Concurrent checkout drift: '+row['path'])
            atomic_copy(HERE/row['path'],dev/row['path'])
        plan=engine_plan(dev);write(backup/'engine-plan.json',plan)
        if set(plan.get('changed_code',[]))-{r['path'] for r in code}:raise ValueError('Unrelated engine code drift; patch rolled back')
        if plan.get('unlisted_runtime_files'):raise ValueError('Unknown unlisted runtime files; patch rolled back')
        write(backup/'engine-apply.json',engine_plan(dev,True))
        for row in code:
            if sha(dev/row['path'])!=row['sha256']:raise ValueError('Applied code hash mismatch: '+row['path'])
        write(backup/'applied.json',{'dev':str(dev),'files':{row['path']:row['sha256'] for row in code},'main_promoted':False,'generation_activated':False,'git_pushed':False,'serving_deployed':False})
    except BaseException:
        rollback(backup);raise
    print('CODE APPLIED; backup/receipt:',backup,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dev',type=Path,default=Path.home()/'DEV');parser.add_argument('--check',action='store_true');parser.add_argument('--rollback',type=Path);args=parser.parse_args()
    if args.rollback:rollback(args.rollback.resolve())
    else:apply(args.dev,args.check)
