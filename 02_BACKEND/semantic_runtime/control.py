"""Publish immutable releases and apply an explicitly user-directed cutover."""
import argparse
from datetime import datetime,timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from .contracts import sha,write
from .storage import publish


def prepare(root,code_root,generation,release_id,authorization,validation):
    root=Path(root).resolve();code_root=Path(code_root).resolve();generation=Path(generation).resolve()
    if not release_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in release_id):raise ValueError('invalid release ID')
    dest=root/'08_DEPLOYMENT/RELEASES'/release_id
    if dest.exists():raise ValueError('release already exists')
    active=root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    data=json.loads((generation/'manifest.json').read_text())
    if sha(generation/'store.sqlite')!=data['store_sha256']:raise ValueError('data hash mismatch')
    auth=json.loads(Path(authorization).read_text())
    if auth.get('quality_gate_override') is not True:raise ValueError('explicit user-directed quality waiver required')
    report=json.loads(Path(validation).read_text())
    if not report.get('structural_checks_passed'):raise ValueError('structural example checks must pass')
    dest.mkdir(parents=True)
    shutil.copytree(code_root/'02_BACKEND/semantic_runtime',dest/'code/02_BACKEND/semantic_runtime',ignore=shutil.ignore_patterns('__pycache__','moleg_links.py'))
    shutil.copytree(code_root/'02_BACKEND/ENGINES/term_runtime',dest/'code/02_BACKEND/ENGINES/term_runtime')
    (dest/'code/06_TOOLS').mkdir(parents=True)
    shutil.copyfile(code_root/'service.py',dest/'code/service.py')
    shutil.copyfile(code_root/'06_TOOLS/serve.sh',dest/'code/06_TOOLS/serve.sh')
    (dest/'code/00_SYSTEM').mkdir(parents=True)
    shutil.copyfile(code_root/'00_SYSTEM/PIPELINE.json',dest/'code/00_SYSTEM/PIPELINE.json')
    config=json.loads((dest/'code/00_SYSTEM/PIPELINE.json').read_text())
    for relative in {c['schema_path'] for c in config['contracts'].values()}:
        target=dest/'code'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(code_root/relative,target)
    term=next(x for x in config['profiles']['legal-rag']['nodes'] if x['id']=='retrieve')['parameters'].get('term_agent',{})
    if term.get('enabled'):
        binding=data.get('navigation') or term['index']
        base=generation if data.get('navigation') else code_root
        asset=(base/binding['path']).resolve();asset.relative_to(base)
        if sha(asset/'manifest.json')!=binding['manifest_sha256']:raise ValueError('navigation manifest drift')
        from .term_index import TermIndex
        from .storage import Store
        checked=Store(generation)
        try:TermIndex(asset,checked)
        finally:checked.close()
        if not data.get('navigation'):shutil.copytree(asset,dest/'code'/binding['path'])
    # Preserve the exact pre-cutover launchers and active pointer for explicit rollback.
    (dest/'rollback').mkdir()
    for name,path in [('service.py',root/'service.py'),('serve.sh',root/'06_TOOLS/serve.sh'),('PIPELINE.json',root/'00_SYSTEM/PIPELINE.json')]:
        shutil.copy2(path,dest/'rollback'/name)
    previous_pipeline=auth.get('rollback_pipeline')
    if previous_pipeline:
        original=(root/previous_pipeline['path']).resolve();original.relative_to(root)
        if sha(original)!=previous_pipeline['sha256']:raise ValueError('rollback pipeline hash mismatch')
        shutil.copy2(original,dest/'rollback/PIPELINE.json')
    shutil.copyfile(active,dest/'rollback/ACTIVE_RELEASE.json')
    shutil.copyfile(authorization,dest/'authorization.json');shutil.copyfile(validation,dest/'validation.json')
    manifest={'schema_version':'semantic-runtime-release-v2','release_id':release_id,
              'code_root':str((dest/'code').relative_to(root)),
              'files':{str(p.relative_to(dest/'code')):sha(p) for p in sorted((dest/'code').rglob('*')) if p.is_file()},
              'data_path':str(generation.relative_to(root)),'data_manifest_sha256':sha(generation/'manifest.json'),
              'previous_active_sha256':sha(active),'authorization_sha256':sha(dest/'authorization.json'),
              'validation_sha256':sha(dest/'validation.json'),'quality_certified':False,
              'deployment_basis':'USER_DIRECTED_CUTOVER','legacy_fallback':False,
              'created_at':datetime.now(timezone.utc).isoformat()}
    write(dest/'release.json',manifest)
    return dest/'release.json'


def activate(root,manifest_path,confirm=False):
    if not confirm:raise ValueError('--confirm-main is required')
    root=Path(root).resolve();manifest_path=Path(manifest_path).resolve();manifest=json.loads(manifest_path.read_text())
    if manifest['schema_version']!='semantic-runtime-release-v2':raise ValueError('unsupported release')
    code=root/manifest['code_root']
    for relative,expected in manifest['files'].items():
        if sha(code/relative)!=expected:raise ValueError('release code drift: '+relative)
    if sha(root/manifest['data_path']/'manifest.json')!=manifest['data_manifest_sha256']:raise ValueError('release data drift')
    from .storage import Store
    checked=Store(root/manifest['data_path']);checked.close()
    if sha(manifest_path.parent/'authorization.json')!=manifest['authorization_sha256']:raise ValueError('authorization drift')
    if sha(manifest_path.parent/'validation.json')!=manifest['validation_sha256']:raise ValueError('validation drift')
    active=root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';receipts=root/'01_DATA/ACTIVE/local/receipts';receipts.mkdir(exist_ok=True)
    with (active.parent/'.semantic-cutover.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if sha(active)!=manifest['previous_active_sha256']:raise ValueError('stale activation plan')
        old=json.loads(active.read_text());generation=int(old.get('generation',0))+1
        pointer={'schema_version':'semantic-runtime-active-v2','release_id':manifest['release_id'],'generation':generation,
                 'manifest_path':str(manifest_path.relative_to(root)),'release_manifest_sha256':sha(manifest_path),
                 'activated_at':datetime.now(timezone.utc).isoformat(),'deployment_basis':'USER_DIRECTED_CUTOVER',
                 'quality_certified':False,'legacy_fallback':False,'previous_active_sha256':sha(active)}
        receipt={'action':'USER_DIRECTED_CUTOVER','before':old,'after':pointer,'manifest_sha256':sha(manifest_path),
                 'quality_gate_override':True,'note':'User explicitly requested latest downstream despite unmet performance thresholds.'}
        write(receipts/('semantic-apply-'+uuid.uuid4().hex+'.json'),receipt)
        temporary=active.with_name('.ACTIVE_RELEASE.'+uuid.uuid4().hex+'.tmp');write(temporary,pointer);os.replace(temporary,active)
        return pointer


def rollback(root,confirm=False):
    if not confirm:raise ValueError('--confirm-main is required')
    root=Path(root).resolve();active=root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    with (active.parent/'.semantic-cutover.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=json.loads(active.read_text())
        if current.get('schema_version')!='semantic-runtime-active-v2':raise ValueError('no semantic release to roll back')
        manifest_path=root/current['manifest_path']
        if sha(manifest_path)!=current['release_manifest_sha256']:raise ValueError('release drift')
        manifest=json.loads(manifest_path.read_text());backup=manifest_path.parent/'rollback'
        if sha(backup/'ACTIVE_RELEASE.json')!=manifest['previous_active_sha256']:raise ValueError('rollback pointer drift')
        previous=json.loads((backup/'ACTIVE_RELEASE.json').read_text());previous['generation']=int(current['generation'])+1
        previous['activated_at']=datetime.now(timezone.utc).isoformat()
        write(active.parent/'receipts'/('semantic-rollback-'+uuid.uuid4().hex+'.json'),{'action':'EXPLICIT_ROLLBACK','before':current,'after':previous})
        for source,target in [('service.py',root/'service.py'),('serve.sh',root/'06_TOOLS/serve.sh'),('PIPELINE.json',root/'00_SYSTEM/PIPELINE.json')]:
            temp=target.with_name('.'+target.name+'.'+uuid.uuid4().hex);shutil.copy2(backup/source,temp);os.replace(temp,target)
        temp=active.with_name('.ACTIVE_RELEASE.'+uuid.uuid4().hex);write(temp,previous);os.replace(temp,active)
        return previous


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path.cwd());sub=p.add_subparsers(dest='command',required=True)
    load=sub.add_parser('load');load.add_argument('--source-store',type=Path,required=True);load.add_argument('--output',type=Path,required=True);load.add_argument('--data-status',choices=['DRAFT','APPROVED','EXAMPLE'],default='DRAFT');load.add_argument('--export-allowed',action='store_true')
    pre=sub.add_parser('prepare');pre.add_argument('--code-root',type=Path,required=True);pre.add_argument('--generation',type=Path,required=True);pre.add_argument('--release-id',required=True);pre.add_argument('--authorization',type=Path,required=True);pre.add_argument('--validation',type=Path,required=True)
    nav=sub.add_parser('build-term-index');nav.add_argument('--generation',type=Path,required=True);nav.add_argument('--legal',type=Path,required=True);nav.add_argument('--dictionary',type=Path,required=True);nav.add_argument('--output',type=Path,required=True)
    apply=sub.add_parser('apply');apply.add_argument('--manifest',type=Path,required=True);apply.add_argument('--confirm-main',action='store_true')
    back=sub.add_parser('rollback');back.add_argument('--confirm-main',action='store_true')
    sub.add_parser('status');args=p.parse_args()
    if args.command=='load':result=publish(args.root,args.source_store,args.output,data_status=args.data_status,export_allowed=args.export_allowed)
    elif args.command=='build-term-index':
        from .storage import Store
        from .term_index import compile_index
        source=Store(args.generation)
        try:result=compile_index(source,args.legal,args.dictionary,args.output)
        finally:source.close()
    elif args.command=='prepare':result=str(prepare(args.root,args.code_root,args.generation,args.release_id,args.authorization,args.validation))
    elif args.command=='apply':result=activate(args.root,args.manifest,args.confirm_main)
    elif args.command=='rollback':result=rollback(args.root,args.confirm_main)
    else:result=json.loads((args.root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
