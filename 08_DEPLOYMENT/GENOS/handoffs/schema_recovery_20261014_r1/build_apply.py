"""Apply the validated build component only to its exact dependency/preimage set."""
import argparse,hashlib,json,os,stat,subprocess,sys,uuid
from pathlib import Path
import apply_patch as io

O=Path(__file__).resolve().parent
VERSION='GENOS_SCHEMA_BUILD_20261014_R1'

def read(path):return path.read_bytes() if path.is_file() else None
def digest(raw):return io.sha(raw) if raw is not None else None

def check(root,spec,*,after=False):
    changes={r['path']:r for r in spec['files']};bad=[]
    for name,expected in spec['dependencies'].items():
        actual=digest(read(io.path_at(root,name)));row=changes.get(name)
        allowed=[expected] if after or row is None else [row['before'],row['after']]
        if actual not in allowed:bad.append({'path':name,'actual':actual,'expected':allowed})
    for row in changes.values():
        raw=io.path_at(O/'build-payload',row['path']).read_bytes()
        if digest(raw)!=row['after']:raise ValueError('Payload changed: '+row['path'])
        compile(raw,row['path'],'exec')
    cm=root/'CODE_MANIFEST.json'
    if cm.exists():
        # Build-only files are absent from the query inventory. Do not invalidate
        # a different full-code inventory or silently rewrite its serving pins.
        manifest=json.loads(cm.read_bytes());io.inventory(root,manifest)
        for row in manifest['files']:
            if row['path'] in changes and row['sha256']!=changes[row['path']]['after']:
                bad.append({'path':row['path'],'reason':'Full-code inventory requires separately pinned release rebase'})
    if bad:raise ValueError('BUILD_REBASE_REQUIRED; no files changed: '+json.dumps(bad,ensure_ascii=False))
    return changes

def verify(root,spec):
    check(root,spec,after=True)
    code="""import sys
from pathlib import Path
r=Path(sys.argv[1]);sys.path.insert(0,str(r/'02_BACKEND'))
from lawrag.core.structure import recipe_runtime,recipe_output
from lawrag.pipeline import reference_resolution
from semantic_runtime.legal_agent import output_contract
for m in (recipe_runtime,recipe_output,reference_resolution,output_contract):
 assert Path(m.__file__).resolve().is_relative_to(r),m.__file__
assert recipe_runtime.VERSION=='genos-recipe-v38-output-contract-recovery'
print('INSTALLED_BUILD_V38 PASS; actual imports; model calls=0')
"""
    subprocess.run([sys.executable,'-c',code,str(root)],cwd=root,check=True,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)})

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path.home()/'DEV')
    p.add_argument('action',choices=['check','apply','verify','undo']);p.add_argument('backup',nargs='?',type=Path)
    args=p.parse_args();root=args.root.resolve(strict=True)
    spec=json.loads((O/'BUILD_SOURCE_BINDING.json').read_bytes())
    with io.locked(root):
        if args.action=='undo':
            if args.backup is None:raise ValueError('Exact BACKUP path required')
            backup=args.backup.resolve(strict=True);receipt=json.loads((backup/'receipt.json').read_bytes())
            if receipt['version']!=VERSION or receipt['root']!=str(root):raise ValueError('Backup binding differs')
            for row in receipt['files']:
                if digest(read(io.path_at(root,row['path']))) not in (row['before'],row['after']):raise ValueError('Current code changed; undo refused: '+row['path'])
                if digest(read(io.path_at(backup,row['path'])))!=row['before']:raise ValueError('Backup changed: '+row['path'])
            for row in receipt['files']:
                io.atomic(io.path_at(root,row['path']),io.path_at(backup,row['path']).read_bytes(),row['mode'])
            receipt['state']='RESTORED';io.atomic(backup/'receipt.json',io.encoded(receipt))
            print('BUILD_RESTORED');return
        changes=check(root,spec,after=args.action=='verify')
        if args.action=='check':print('BUILD_CHECK PASS; exact dependency and preimage set');return
        if args.action=='verify':verify(root,spec);return
        pending=[row for row in changes.values() if digest(read(io.path_at(root,row['path'])))!=row['after']]
        if not pending:verify(root,spec);print('BUILD_ALREADY_APPLIED');return
        backup=io.path_at(root,'TRANSFER/schema-build-r1/backup-'+uuid.uuid4().hex);backup.mkdir(parents=True)
        receipt={'version':VERSION,'root':str(root),'state':'PREPARED','files':[]}
        for row in pending:
            target=io.path_at(root,row['path']);raw=target.read_bytes();mode=stat.S_IMODE(target.stat().st_mode)
            io.atomic(io.path_at(backup,row['path']),raw,mode);receipt['files'].append({**row,'mode':mode})
        io.atomic(backup/'receipt.json',io.encoded(receipt));print('BACKUP='+str(backup),flush=True)
        for row in receipt['files']:io.atomic(io.path_at(root,row['path']),io.path_at(O/'build-payload',row['path']).read_bytes(),row['mode'])
        verify(root,spec);receipt['state']='VERIFIED';io.atomic(backup/'receipt.json',io.encoded(receipt))
        print('BUILD_APPLIED; restart build process; field model execution pending')

if __name__=='__main__':
    try:main()
    except Exception as exc:print(str(exc),file=sys.stderr);raise SystemExit(1)
