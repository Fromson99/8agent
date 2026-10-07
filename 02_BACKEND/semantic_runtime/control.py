"""Publish immutable releases and apply an explicitly user-directed cutover."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from .contracts import sha,write
from .storage import publish


def copy_learning_bundle(binding, code_root, target_root, generation, terms, documents):
    """Pin the explicitly selected review bundle into a prepared release, without activation."""
    from .navigation_learning import load_learning_bundle
    load_learning_bundle(binding, code_root, generation, terms, documents)
    source=(Path(code_root)/binding['path']).resolve()
    target=(Path(target_root)/binding['path']).resolve()
    target.relative_to(Path(target_root).resolve())
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:
        stream.write(source.read_bytes())
    if sha(target)!=binding['sha256']:raise ValueError('learning bundle changed during release copy')


# Build-time modules that serving never imports; releases leave them out, so manifests must too.
BUILD_ONLY=('moleg_links.py',)
def prepare(root,code_root,generation,release_id,authorization,validation,integration_preview=None):
    root=Path(root).resolve();code_root=Path(code_root).resolve();generation=Path(generation).resolve()
    if not release_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in release_id):raise ValueError('invalid release ID')
    dest=root/'08_DEPLOYMENT/RELEASES'/release_id
    if dest.exists():raise ValueError('release already exists')
    active=root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    active_pointer=json.loads(active.read_text())
    active_binding={'pointer':active_pointer,'pointer_sha256':sha(active)}
    data=json.loads((generation/'manifest.json').read_text())
    if sha(generation/'store.sqlite')!=data['store_sha256']:raise ValueError('data hash mismatch')
    auth=json.loads(Path(authorization).read_text())
    report=json.loads(Path(validation).read_text())
    qualification=None
    if auth.get('qualification') is not None:
        from .release_qualification import verify
        qualification=verify(root,auth,report)
    elif integration_preview is not None and auth.get('purpose')=='integration_preview':
        pass  # Read-only preview is removed before returning; cannot activate.
    elif auth.get('quality_gate_override') is not True:
        raise ValueError('qualified source or explicit user-directed quality waiver required')
    if not report.get('structural_checks_passed'):raise ValueError('structural example checks must pass')
    dest.mkdir(parents=True)
    shutil.copytree(code_root/'02_BACKEND/semantic_runtime',dest/'code/02_BACKEND/semantic_runtime',ignore=shutil.ignore_patterns('__pycache__',*BUILD_ONLY))
    shutil.copytree(code_root/'02_BACKEND/ENGINES/term_runtime',dest/'code/02_BACKEND/ENGINES/term_runtime')
    # Engine manifests may pin shared modules outside semantic_runtime (legal_coordinate.py).
    # Copy them with their package markers so the release imports and verifies its own bytes.
    pinned=set()
    selected_config=json.loads((code_root/'00_SYSTEM/PIPELINE.json').read_text())
    for entry in selected_config['engines'].values():
        engine=(code_root/entry['manifest']).resolve();engine.relative_to(code_root)
        if sha(engine)!=entry['sha256']:raise ValueError('engine manifest drift')
        target=(dest/'code'/entry['manifest']).resolve();target.relative_to((dest/'code').resolve())
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(engine,target)
        pinned.update(json.loads(engine.read_text()).get('files',{}))
    for relative in sorted(pinned):
        path=Path(relative)
        operator_tools={'06_TOOLS/run_tool.py','06_TOOLS/ACTIVE_TOOLS.json',
                        '06_TOOLS/COMMANDS/legal_agent_trace.py','06_TOOLS/COMMANDS/legal_agent_contracts.py'}
        if path.is_absolute() or '..' in path.parts or (path.parts[0] not in ('02_BACKEND','00_SYSTEM') and relative not in operator_tools):
            raise ValueError('pinned engine file outside code/config/operator tools: '+relative)
        for marker in [p/'__init__.py' for p in path.parents if len(p.parts)>1]:
            if (code_root/marker).is_file() and not (dest/'code'/marker).exists():
                (dest/'code'/marker).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code_root/marker,dest/'code'/marker)
        (dest/'code'/path).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code_root/path,dest/'code'/path)
    (dest/'code/06_TOOLS').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(code_root/'service.py',dest/'code/service.py')
    for relative in ('main.py','service/service.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','08_DEPLOYMENT/GENOS/stream_app.py','08_DEPLOYMENT/GENOS/start_sse.py'):
        target=dest/'code'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(code_root/relative,target)
    shutil.copyfile(code_root/'06_TOOLS/serve.sh',dest/'code/06_TOOLS/serve.sh')
    (dest/'code/00_SYSTEM').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(code_root/'00_SYSTEM/PIPELINE.json',dest/'code/00_SYSTEM/PIPELINE.json')
    config=json.loads((dest/'code/00_SYSTEM/PIPELINE.json').read_text())
    if (code_root/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').is_file():
        for relative in ('00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',
                         '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'):
            target=dest/'code'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(code_root/relative,target)
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
        try:
            index=TermIndex(asset,checked)
            learning=term.get('learning',{}).get('bundle')
            if learning is not None:
                if term.get('implementation')!='navigation-loop-v1':raise ValueError('learning requires navigation-loop-v1')
                copy_learning_bundle(learning,code_root,dest/'code',generation,
                                     {t['id']:t for t in index.terms},
                                     {r[0] for r in checked.db.execute('SELECT document_id FROM document')})
        finally:checked.close()
        if term.get('implementation') in ('navigation-loop-v1', 'definition-scope-harness-v1', 'document-navigation-v1','legal-agent-v1','legal-agent-tools-v2','legal-agent-tools-v3', 'legal-agent-tools-v4', 'legal-agent-tools-v5'):
            from .navigation_agent import glossary_assets
            glossary=glossary_assets(generation,term)
            glossary.close()
        if term.get('implementation')=='definition-scope-harness-v1':
            from .task_policy import load_bound_definition
            load_bound_definition(generation, term['task_policy'])
        if not data.get('navigation'):shutil.copytree(asset,dest/'code'/binding['path'])
        from .folder_navigation import load_origin_projection
        for projection in term.get('origin_projections',[]):
            if projection.get('generation_id')!=data['generation_id']:continue
            checked=Store(generation)
            try:load_origin_projection(code_root,term,checked)
            finally:checked.close()
            target=(dest/'code'/projection['path']).resolve();target.relative_to((dest/'code').resolve())
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code_root/projection['path'],target)
        for projection in term.get('alias_projections',[]):
            # Read from the code root at serving time like the origin projection; pinned by sha256.
            if projection.get('generation_id')!=data['generation_id']:continue
            if sha(code_root/projection['path'])!=projection['sha256']:raise ValueError('alias projection hash mismatch')
            target=(dest/'code'/projection['path']).resolve();target.relative_to((dest/'code').resolve())
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code_root/projection['path'],target)
    # Preserve the exact pre-cutover launchers and active pointer for explicit rollback.
    (dest/'rollback').mkdir()
    for name,path in [('service.py',root/'service.py'),('serve.sh',root/'06_TOOLS/serve.sh'),('PIPELINE.json',root/'00_SYSTEM/PIPELINE.json')]:
        shutil.copy2(path,dest/'rollback'/name)
    previous_pipeline=auth.get('rollback_pipeline')
    if previous_pipeline:
        original=(root/previous_pipeline['path']).resolve();original.relative_to(root)
        if sha(original)!=previous_pipeline['sha256']:raise ValueError('rollback pipeline hash mismatch')
        shutil.copy2(original,dest/'rollback/PIPELINE.json')
    staged_files={str(p.relative_to(dest/'code')):sha(p)
                  for p in sorted((dest/'code').rglob('*')) if p.is_file()}
    # Publishing must satisfy every configured engine hash contract, including
    # dependencies historically labelled build-only but still pinned at runtime.
    for entry in config['engines'].values():
        engine=json.loads((dest/'code'/entry['manifest']).read_text())
        for relative,expected in engine.get('files',{}).items():
            if staged_files.get(relative)!=expected:
                raise ValueError('serving engine dependency missing or changed: '+relative)
    integration=None
    if integration_preview is not None:
        from .release_integration import draft
        try:
            if int(active_pointer.get('generation',0)) <= 0:
                raise ValueError('integration preview requires an active MAIN release')
            preview=Path(integration_preview).resolve()
            if preview.is_relative_to(dest):
                raise ValueError('integration preview must be outside prepared release')
            value=draft(root,active_pointer,staged_files)
            if sha(active)!=active_binding['pointer_sha256']:
                raise ValueError('active MAIN changed during integration preview')
            write(preview,value)
        finally:
            shutil.rmtree(dest)
        return preview
    if int(active_pointer.get('generation',0)) > 0:
        from .release_integration import check as check_integration
        try:
            integration=check_integration(root,active_binding,staged_files,report.get('integration'))
        except (ValueError, OSError, KeyError, TypeError):
            shutil.rmtree(dest)
            raise
    shutil.copyfile(active,dest/'rollback/ACTIVE_RELEASE.json')
    shutil.copyfile(authorization,dest/'authorization.json');shutil.copyfile(validation,dest/'validation.json')
    manifest={'schema_version':'semantic-runtime-release-v2','release_id':release_id,
              'code_root':str((dest/'code').relative_to(root)),
              'files':staged_files,
              'data_path':str(generation.relative_to(root)),'data_manifest_sha256':sha(generation/'manifest.json'),
              'previous_active_sha256':sha(active),'authorization_sha256':sha(dest/'authorization.json'),
              'validation_sha256':sha(dest/'validation.json'),'quality_certified':False,
              'deployment_basis':'VALIDATED_ADR_PROMOTION' if qualification else 'USER_DIRECTED_CUTOVER','legacy_fallback':False,
              'created_at':datetime.now(timezone.utc).isoformat(),
              'integration':integration}
    if qualification:manifest['qualification']=qualification
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
    qualification=manifest.get('qualification')
    if qualification:
        from .release_qualification import verify
        checked=verify(root,json.loads((manifest_path.parent/'authorization.json').read_text()),json.loads((manifest_path.parent/'validation.json').read_text()))
        if checked!=qualification:raise ValueError('release qualification drift')
    active=root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';receipts=root/'01_DATA/ACTIVE/local/receipts';receipts.mkdir(exist_ok=True)
    with (active.parent/'.semantic-cutover.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if sha(active)!=manifest['previous_active_sha256']:raise ValueError('stale activation plan')
        old=json.loads(active.read_text());generation=int(old.get('generation',0))+1
        if generation > 1:
            from .release_integration import check as check_integration
            validation=json.loads((manifest_path.parent/'validation.json').read_text())
            checked=check_integration(root,{'pointer':old,'pointer_sha256':sha(active)},
                                      manifest['files'],validation.get('integration'))
            if checked!=manifest.get('integration'):
                raise ValueError('release integration receipt differs from active MAIN')
        pointer={'schema_version':'semantic-runtime-active-v2','release_id':manifest['release_id'],'generation':generation,
                 'manifest_path':str(manifest_path.relative_to(root)),'release_manifest_sha256':sha(manifest_path),
                 'activated_at':datetime.now(timezone.utc).isoformat(),'deployment_basis':'VALIDATED_ADR_PROMOTION' if qualification else 'USER_DIRECTED_CUTOVER',
                 'quality_certified':False,'legacy_fallback':False,'previous_active_sha256':sha(active)}
        receipt={'action':'USER_DIRECTED_CUTOVER','before':old,'after':pointer,'manifest_sha256':sha(manifest_path),
                 'quality_gate_override':True,'note':'User explicitly requested latest downstream despite unmet performance thresholds.'}
        if qualification:
            pointer['qualification']=qualification
            receipt.update(action='VALIDATED_ADR_PROMOTION',quality_gate_override=False,qualification=qualification,
                           note='User-authorized promotion of completed Accepted out-of-sample arm; exact rebase and checks verified.')
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


def rehash_engines(root,apply=False,add_new=False):
    """Re-pin engine code and runtime schemas after an edit; data pins are only checked.

    Engine manifests pin every runtime file, PIPELINE.json pins each manifest and schema.
    Index, glossary and projection hashes select data and are never rewritten here.
    """
    root=Path(root).resolve();pipeline=root/'00_SYSTEM/PIPELINE.json'
    text=pipeline.read_text();config=json.loads(text)
    code,unlisted,manifests,schemas,data=[],set(),[],[],[]
    pending={}
    for name,entry in sorted(config['engines'].items()):
        path=root/entry['manifest'];raw=path.read_text();manifest=json.loads(raw)
        files=dict(manifest['files'])
        for file,expected in files.items():
            actual=sha(root/file)
            if actual!=expected:files[file]=actual;code.append(file)
        # New modules appear next to the engine entrypoint; other listed files are single pins.
        for folder in [(root/manifest['entrypoint']['path']).parent]:
            for f in sorted(folder.glob('*.py')):
                rel=f.relative_to(root).as_posix()
                if rel not in files and f.name not in BUILD_ONLY:
                    unlisted.add(rel)
                    if add_new:files[rel]=sha(f)
        if files!=manifest['files']:
            manifest['files']=dict(sorted(files.items()))
            pending[path]=json.dumps(manifest,ensure_ascii=False,indent=2)+('\n' if raw.endswith('\n') else '')
            new=hashlib.sha256(pending[path].encode()).hexdigest()
        else:new=sha(path)
        if new!=entry['sha256']:manifests.append({'engine':name,'manifest':entry['manifest'],'old':entry['sha256'],'new':new})
    for name,entry in sorted(config['contracts'].items()):
        actual=sha(root/entry['schema_path'])
        if actual!=entry['schema_sha256']:schemas.append({'contract':name,'old':entry['schema_sha256'],'new':actual})
    for node in config['profiles'].get('legal-rag',{}).get('nodes',[]):
        term=node.get('parameters',{}).get('term_agent')
        if not term:continue
        index=term['index'];actual=sha(root/index['path']/'manifest.json')
        data.append({'pin':'index','path':index['path'],'ok':actual==index['manifest_sha256']})
        if term.get('fulltext'):
            gen=Path(index['path']).parent;ft=term['fulltext']
            data.append({'pin':'fulltext','path':str(gen/ft['path']),'ok':(root/gen/ft['path']/'manifest.json').is_file() and sha(root/gen/ft['path']/'manifest.json')==ft['manifest_sha256']})
        for kind in ('origin_projections','alias_projections'):
            for b in term.get(kind,[]):data.append({'pin':kind,'path':b['path'],'ok':(root/b['path']).is_file() and sha(root/b['path'])==b['sha256']})
    changed=bool(pending or manifests or schemas)
    if apply and changed:
        for path,value in pending.items():path.write_text(value)
        # Replace only the pinned hash strings so concurrent edits to other fields survive.
        text=pipeline.read_text()
        for m in manifests:text=text.replace('"'+m['old']+'"','"'+m['new']+'"')
        for s in {x['old']:x['new'] for x in schemas}.items():text=text.replace('"'+s[0]+'"','"'+s[1]+'"')
        pipeline.write_text(text)
    return {'applied':apply and changed,'changed_code':sorted(set(code)),'unlisted_runtime_files':sorted(unlisted),
            'unlisted_added':add_new and bool(unlisted),'engine_manifests':manifests,'schemas':schemas,
            'data_pins_checked_not_rewritten':data,
            'next':None if not changed or apply else 'rerun with --apply to write these pins'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path.cwd());sub=p.add_subparsers(dest='command',required=True)
    load=sub.add_parser('load');load.add_argument('--source-store',type=Path,required=True);load.add_argument('--output',type=Path,required=True);load.add_argument('--data-status',choices=['DRAFT','APPROVED','EXAMPLE'],default='DRAFT');load.add_argument('--export-allowed',action='store_true')
    pre=sub.add_parser('prepare');pre.add_argument('--code-root',type=Path,required=True);pre.add_argument('--generation',type=Path,required=True);pre.add_argument('--release-id',required=True);pre.add_argument('--authorization',type=Path,required=True);pre.add_argument('--validation',type=Path,required=True);pre.add_argument('--integration-preview',type=Path)
    nav=sub.add_parser('build-term-index');nav.add_argument('--generation',type=Path,required=True);nav.add_argument('--legal',type=Path,required=True);nav.add_argument('--dictionary',type=Path,required=True);nav.add_argument('--output',type=Path,required=True)
    ft=sub.add_parser('build-fulltext');ft.add_argument('--navigation',type=Path,required=True);ft.add_argument('--output',type=Path,required=True);ft.add_argument('--workers',type=int,default=8)
    ft.add_argument('--granularity',choices=['article','unit'],default='article')
    ft.add_argument('--generation',type=Path,help='Selected structured generation; required for unit fulltext')
    alias=sub.add_parser('build-alias-projection');alias.add_argument('--generation',type=Path,required=True);alias.add_argument('--origin-projection',type=Path,required=True);alias.add_argument('--output',type=Path,required=True)
    issues=sub.add_parser('relation-issues');issues.add_argument('--kind',choices=['bridge','reference']);issues.add_argument('--limit',type=int,default=50)
    rehash=sub.add_parser('rehash-engines');rehash.add_argument('--apply',action='store_true');rehash.add_argument('--add-new',action='store_true')
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
    elif args.command=='build-fulltext':
        from .fulltext import build
        if args.output.exists():raise SystemExit('refusing to overwrite '+str(args.output))
        manifest=build(args.navigation,args.output,args.workers,granularity=args.granularity,generation=args.generation)
        result={**manifest,'manifest_sha256':sha(args.output/'manifest.json')}
    elif args.command=='build-alias-projection':
        from .storage import Store
        from .document_aliases import build
        if args.output.exists():raise SystemExit('refusing to overwrite '+str(args.output))
        source=Store(args.generation)
        try:value=build(args.root,source,json.loads(args.origin_projection.read_text()))
        finally:source.close()
        write(args.output,value)
        result={'output':str(args.output),'sha256':sha(args.output),'generation_id':value['generation_id'],'documents':len(value['documents']),'skipped':value['skipped']}
    elif args.command=='relation-issues':
        from .relation_issues import summary
        result=summary(Path(args.root)/'90_RUNTIME/semantic/relation-issues/rejections.sqlite',args.kind,args.limit)
    elif args.command=='rehash-engines':
        result=rehash_engines(args.root,args.apply,args.add_new)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        stale=(result['engine_manifests'] or result['schemas']) and not result['applied']
        broken=[d for d in result['data_pins_checked_not_rewritten'] if not d['ok']]
        raise SystemExit(1 if stale or broken else 0)
    elif args.command=='prepare':result=str(prepare(args.root,args.code_root,args.generation,args.release_id,args.authorization,args.validation,args.integration_preview))
    elif args.command=='apply':result=activate(args.root,args.manifest,args.confirm_main)
    elif args.command=='rollback':result=rollback(args.root,args.confirm_main)
    else:result=json.loads((args.root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
