"""One TRANSFER TXT applies common CM code, registers data, gates and pushes.

The two existing NFS paths are supplied by the sealed handoff, not the operator.
The only optional CLI switch is for isolated offline contract validation.
"""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import uuid
import zipfile

VERSION='GENOS_CM_ONECLICK_20261008_R15'
CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def library(spec):
    module=types.ModuleType('sealed_common_installer')
    exec(compile(base64.b64decode(spec['r6_library']),'sealed_common_installer.py','exec'),module.__dict__)
    return module

def git(root,*args,allow=()):
    r=subprocess.run(['git','-C',str(root),*args],capture_output=True)
    if r.returncode and r.returncode not in allow:raise ValueError('Git '+args[0]+' failed; exit='+str(r.returncode))
    return r.stdout.decode().strip(),r.returncode

def blob(spec,fingerprint):
    raw=base64.b64decode(spec['blobs'][fingerprint],validate=True)
    if sha(raw)!=fingerprint:raise ValueError('sealed blob hash differs')
    return raw

def budget_library(spec):
    sealed=spec['investigation_budget_overlay']
    raw=base64.b64decode(sealed['library'],validate=True)
    if sha(raw)!=sealed['library_sha256']:raise ValueError('sealed budget library hash differs')
    module=types.ModuleType('sealed_budget_installer')
    module.__file__='sealed_budget_installer.py'
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    if module.VERSION!=sealed['spec']['revision']:raise ValueError('sealed budget revision differs')
    return module,sealed['spec']

def budget_metadata(manifest,spec):
    meta=manifest.get('investigation_budget_settings')
    if meta is None:return None
    _,policy=budget_library(spec)
    expected={'revision':policy['revision'],'prior_inventory_sha256':meta.get('prior_inventory_sha256'),
              'modified_paths':['service.py'],'settings':policy['settings'],
              'default_model_attempts_changed':False,'field_deployed':False}
    if meta!=expected or not isinstance(meta['prior_inventory_sha256'],str) or len(meta['prior_inventory_sha256'])!=64:
        raise ValueError('unknown budget metadata; preserved')
    return meta

def without_budget(raw,spec):
    module,policy=budget_library(spec)
    text=raw.decode('utf-8')
    for op in reversed(policy['operations']):
        if text.count(op['after'])!=1:raise ValueError('unknown or partial budget code; preserved')
        text=text.replace(op['after'],op['before'],1)
    original=text.encode('utf-8')
    if module.transform(original,policy)!=raw:raise ValueError('budget code differs from sealed transformation')
    return original

def original_budget_inventory(original,payload,spec):
    manifest=json.loads(original);meta=budget_metadata(manifest,spec)
    if meta is None:return original,payload
    normalized={**payload,'service.py':without_budget(payload['service.py'],spec)}
    manifest.pop('investigation_budget_settings')
    found=[]
    for row in manifest['files']:
        if row['path']=='service.py':
            if row['sha256']!=sha(payload['service.py']) or row['bytes']!=len(payload['service.py']):
                raise ValueError('budget service inventory differs; preserved')
            row.update(sha256=sha(normalized['service.py']),bytes=len(normalized['service.py']));found.append(row)
    if len(found)!=1:raise ValueError('budget service inventory missing or duplicated')
    for row in manifest.get('required_files',[]):
        if isinstance(row,dict) and row['path']=='service.py':
            if row['sha256']!=sha(payload['service.py']):raise ValueError('budget required service hash differs')
            row['sha256']=sha(normalized['service.py'])
    restored=encoded(manifest)
    if sha(restored)!=meta['prior_inventory_sha256']:
        raise ValueError('budget parent inventory differs; preserved')
    return restored,normalized

def logging_library(spec):
    sealed=spec['full_error_logging_overlay']
    raw=base64.b64decode(sealed['library'],validate=True)
    if sha(raw)!=sealed['library_sha256'] or sha(encoded(sealed['spec']))!=sealed['spec_sha256']:
        raise ValueError('sealed full-error library/spec hash differs')
    module=types.ModuleType('sealed_full_error_installer')
    exec(compile(raw,'sealed_full_error_installer.py','exec'),module.__dict__)
    if module.VERSION!=sealed['spec']['revision']:raise ValueError('sealed full-error revision differs')
    return module,sealed['spec']

def logging_payload(payload,spec):
    module,policy=logging_library(spec)
    final=dict(payload)
    for name,operations in policy['files'].items():final[name]=module.transform(payload[name],operations)
    affected={n for n in policy['files'] if final[n]!=payload[n]}
    if affected:
        pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
        for name,raw in payload.items():
            if name.startswith('02_BACKEND/ENGINES/') and name.endswith('.json'):
                engine=json.loads(raw);paths=set(engine.get('files',{}))&affected
                if paths:
                    for path in paths:engine['files'][path]=sha(final[path])
                    final[name]=encoded(engine)
        for binding in pipeline['engines'].values():binding['sha256']=sha(final[binding['manifest']])
        final['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
    module.verify_bindings(final);module.local_verification(final,policy)
    return final

def logging_origin(root,manifest,spec,lib,expected=None):
    """Authenticate R10's immutable receipt/archive, then reconstruct its parent.

    Never reverse fragments in today's files or accept today's self-reported
    pins as a new baseline. The archive and every changed-file backup must
    reproduce the sealed transformation and the exact prior inventory.
    """
    meta=manifest.get('full_error_logging')
    if meta is None:
        if expected is not None:raise ValueError('preserved full-error metadata missing')
        return None
    module,policy=logging_library(spec)
    if set(meta)!={'revision','prior_inventory_sha256','modified_paths','field_deployed'} or meta['revision']!=module.VERSION or meta['field_deployed'] is not False:
        raise ValueError('unknown full-error metadata; preserved')
    folders=[]
    if expected is not None:
        folders=[lib.path_at(root,expected['backup'])]
    else:
        parent=lib.path_at(root,'TRANSFER/full-error-logging-r10')
        if parent.is_dir():
            for candidate in sorted(parent.glob('backup-*')):
                folder=lib.path_at(root,candidate.relative_to(root).as_posix())
                saved=lib.path_at(folder,'CODE_MANIFEST.json')
                if saved.is_file() and sha(saved.read_bytes())==meta['prior_inventory_sha256']:folders.append(folder)
    if len(folders)!=1:raise ValueError('full-error verified parent backup missing or ambiguous; preserved')
    folder=folders[0]
    folder.relative_to(lib.path_at(root,'TRANSFER/full-error-logging-r10'))
    receipt_raw=lib.path_at(folder,'receipt.json').read_bytes();receipt=json.loads(receipt_raw)
    if receipt.get('revision')!=module.VERSION or receipt.get('state')!='VERIFIED' or receipt.get('root')!=str(root):
        raise ValueError('full-error receipt identity/state differs; preserved')
    archive=lib.path_at(folder,'APPLIED_CODE.zip')
    if receipt.get('code_zip')!=str(archive) or sha(archive.read_bytes())!=receipt.get('code_zip_sha256'):
        raise ValueError('full-error applied archive hash differs; preserved')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or z.testzip() is not None:raise ValueError('full-error archive members differ')
        after_raw=z.read('CODE_MANIFEST.json');after=json.loads(after_raw)
        wanted={'CODE_MANIFEST.json',*[r['path'] for r in after['files']]}
        if set(names)!=wanted:raise ValueError('full-error archive inventory differs')
        applied={n:z.read(n) for n in names if n!='CODE_MANIFEST.json'}
    if after.get('full_error_logging')!=meta or sha(after_raw)!=receipt.get('applied_identity',{}).get('code_manifest_sha256'):
        raise ValueError('full-error archive identity differs; preserved')
    parent_raw=lib.path_at(folder,'CODE_MANIFEST.json').read_bytes();parent=json.loads(parent_raw)
    if sha(parent_raw)!=meta['prior_inventory_sha256']:raise ValueError('full-error parent inventory hash differs')
    base=dict(applied);rows=receipt['files'];paths=[r['path'] for r in rows]
    if len(paths)!=len(set(paths)) or set(paths)!=set(meta['modified_paths'])|{'CODE_MANIFEST.json'}:
        raise ValueError('full-error receipt changed-file set differs')
    for row in rows:
        name=row['path'];saved=lib.path_at(folder,name).read_bytes()
        result=after_raw if name=='CODE_MANIFEST.json' else applied[name]
        if sha(saved)!=row['before_sha256'] or sha(result)!=row['after_sha256']:
            raise ValueError('full-error backup/after hash differs; preserved: '+name)
        if name!='CODE_MANIFEST.json':base[name]=saved
    def check_inventory(value,payload):
        rows=value['files']
        if value.get('format')!='8agent-code/1' or len(rows)!=len(payload) or {r['path'] for r in rows}!=set(payload):
            raise ValueError('full-error parent/applied inventory members differ')
        for row in rows:
            data=payload[row['path']]
            if sha(data)!=row['sha256'] or len(data)!=row['bytes']:raise ValueError('full-error parent/applied file hash differs')
        module.verify_bindings(payload)
    check_inventory(parent,base);check_inventory(after,applied)
    if logging_payload(base,spec)!=applied:raise ValueError('full-error archive differs from sealed transformation')
    rebuilt=json.loads(parent_raw)
    for row in rebuilt['files']:row.update(sha256=sha(applied[row['path']]),bytes=len(applied[row['path']]))
    for row in rebuilt.get('required_files',[]):
        if not isinstance(row,dict):raise ValueError('unsupported full-error parent required inventory')
        if row['path'] in applied:row['sha256']=sha(applied[row['path']])
    modified=sorted(n for n in applied if applied[n]!=base[n])
    rebuilt['full_error_logging']={'revision':module.VERSION,'prior_inventory_sha256':sha(parent_raw),
        'modified_paths':modified,'field_deployed':False}
    if encoded(rebuilt)!=after_raw:raise ValueError('full-error manifest differs from sealed transformation')
    proof={'revision':module.VERSION,'backup':folder.relative_to(root).as_posix(),
        'receipt_sha256':sha(receipt_raw),'code_zip_sha256':sha(archive.read_bytes()),
        'prior_inventory_sha256':sha(parent_raw),'applied_inventory_sha256':sha(after_raw),
        'library_sha256':spec['full_error_logging_overlay']['library_sha256'],
        'spec_sha256':spec['full_error_logging_overlay']['spec_sha256']}
    if expected is not None and proof!=expected:raise ValueError('preserved full-error origin binding differs')
    return parent_raw,base,after_raw,applied,proof

def inspect_base(root,spec,lib,original,payload):
    current=json.loads(original)
    budget=budget_metadata(current,spec)
    lookup=original
    normalized_service=None
    if budget is not None:
        service=payload['service.py']
        legacy=current.get('cm_oneclick',{})
        if legacy.get('revision') in ('GENOS_CM_ONECLICK_20261007_R11','GENOS_CM_ONECLICK_20261007_R12','GENOS_CM_ONECLICK_20261008_R13','GENOS_CM_ONECLICK_20261008_R14') and legacy.get('preserved_investigation_budget')==budget:
            # Each upgrade preserves the original budget parent. Follow and
            # verify each exact backup receipt until that parent is reached.
            parent=current;seen=set()
            while parent.get('cm_oneclick',{}).get('preserved_investigation_budget')==budget:
                node=parent['cm_oneclick'];revision=node.get('revision')
                folders={'GENOS_CM_ONECLICK_20261007_R11':'cm-oneclick-r11',
                         'GENOS_CM_ONECLICK_20261007_R12':'cm-oneclick-r12',
                         'GENOS_CM_ONECLICK_20261008_R13':'cm-oneclick-r13',
                         'GENOS_CM_ONECLICK_20261008_R14':'cm-oneclick-r14'}
                if revision not in folders or revision in seen:
                    raise ValueError('unknown or cyclic preserved budget parent; preserved')
                seen.add(revision);folder='TRANSFER/'+folders[revision]+'/code-backup/'
                receipt=json.loads(lib.path_at(root,folder+'receipt.json').read_bytes())
                raw=lib.path_at(root,folder+'CODE_MANIFEST.json').read_bytes()
                if (receipt.get('revision')!=revision or receipt.get('state')!='APPLIED'
                        or receipt.get('root')!=str(root) or sha(raw)!=node.get('prior_inventory_sha256')
                        or budget_metadata(json.loads(raw),spec)!=budget):
                    raise ValueError('preserved budget parent backup differs; preserved')
                parent=json.loads(raw)
            original_budget_inventory(raw,{'service.py':service},spec)
            normalized_service=without_budget(service,spec)
        else:
            lookup,normalized=original_budget_inventory(original,{'service.py':service},spec)
            normalized_service=normalized['service.py']
    legacy=current.get('cm_oneclick',{})
    upgrades={'GENOS_CM_ONECLICK_20261007_R8':('r8_upgrades','r8_inventories'),
              'GENOS_CM_ONECLICK_20261007_R10':('r10_upgrades','r10_inventories'),
              'GENOS_CM_ONECLICK_20261007_R11':('r11_upgrades','r11_inventories'),
              'GENOS_CM_ONECLICK_20261007_R12':('r12_upgrades','r12_inventories'),
              'GENOS_CM_ONECLICK_20261008_R13':('r13_upgrades','r13_inventories'),
              'GENOS_CM_ONECLICK_20261008_R14':('r14_upgrades','r14_inventories')}
    if legacy.get('revision') in upgrades:
        mapping,inventories=upgrades[legacy['revision']]
        prior=legacy.get('recipe_id');target=spec.get(mapping,{}).get(prior)
        if target is None:raise ValueError('unknown prior CM code recipe; preserved')
        expected=spec['inventories'][spec[inventories][prior]]
        normalized={**payload,'service.py':normalized_service} if budget is not None else payload
        if {p:sha(v) for p,v in normalized.items() if p!=CONFIG}!=expected:
            raise ValueError('prior CM code differs from the verified upgrade inventory; preserved')
        return original,payload,spec['recipes'][target]
    options=spec['states'].get(sha(lookup),[])
    for recipe_id in options:
        recipe=spec['recipes'][recipe_id]
        matched=True
        for name,fingerprint in spec['inventories'][recipe['before']].items():
            if name not in payload:matched=False;break
            raw=payload[name]
            comparison=normalized_service if name=='service.py' and budget is not None else raw
            if sha(comparison)!=fingerprint:matched=False;break
        if matched and set(payload)==set(spec['inventories'][recipe['before']]):return original,payload,recipe
    raise ValueError('현재 코드는 확인한 R4/R6 또는 NFS 목록 패치 상태와 다릅니다. 기존 파일은 보존했습니다. RUN.log를 전달하세요.')

def inspect_input(root,spec,lib):
    original=lib.path_at(root,'CODE_MANIFEST.json').read_bytes();current=json.loads(original)
    if current.get('full_error_logging') is not None or current.get('cm_oneclick') is not None:
        payload=lib.inventory(root,current)
    else:
        # Some sealed initial NFS-list states have stale legacy inventory rows.
        # They remain acceptable only through the exact original manifest hash
        # AND the already sealed recipe's complete actual-file hashes below.
        payload={r['path']:lib.path_at(root,r['path']).read_bytes() for r in current['files']}
    origin=logging_origin(root,current,spec,lib)
    if origin is None:
        _,_,recipe=inspect_base(root,spec,lib,original,payload)
        return original,payload,recipe,None,payload
    parent,base,applied_raw,applied,proof=origin
    if original!=applied_raw or payload!=applied:raise ValueError('current full-error code differs from verified archive; preserved')
    _,_,recipe=inspect_base(root,spec,lib,parent,base)
    return original,payload,recipe,proof,base

def compose_output(base,spec,recipe,binding,budget,proof):
    final=dict(base)
    for name,fingerprint in spec['patch_sets'][recipe['patches']].items():final[name]=blob(spec,fingerprint)
    if budget is not None:
        module,policy=budget_library(spec);final['service.py']=module.transform(final['service.py'],policy)
        module.local_verification(final['service.py'],policy)
    final[CONFIG]=encoded(binding)
    normalized={**final,'service.py':without_budget(final['service.py'],spec)} if budget is not None else final
    if {n:sha(v) for n,v in normalized.items() if n!=CONFIG}!=spec['inventories'][recipe['after']]:
        raise ValueError('composed CM code differs from sealed recipe; preserved')
    if proof is not None:final=logging_payload(final,spec)
    return final

def verify_output(root,spec,lib,binding):
    raw=lib.path_at(root,'CODE_MANIFEST.json').read_bytes();manifest=json.loads(raw)
    meta=manifest.get('cm_oneclick',{})
    if meta.get('revision')!=VERSION:raise ValueError('oneclick code not installed')
    recipe=spec['recipes'].get(meta.get('recipe_id'))
    if recipe is None:raise ValueError('unknown oneclick code recipe')
    payload=lib.inventory(root,manifest)
    budget=budget_metadata(manifest,spec)
    if meta.get('preserved_investigation_budget')!=budget:
        raise ValueError('preserved budget binding differs')
    proof=meta.get('preserved_full_error_logging')
    if proof is not None:
        origin=logging_origin(root,manifest,spec,lib,expected=proof)
        parent,base,_,_,_=origin
        if budget_metadata(json.loads(parent),spec)!=budget:raise ValueError('preserved full-error budget differs')
        _,_,selected=inspect_base(root,spec,lib,parent,base)
        if selected['id']!=recipe['id']:raise ValueError('preserved full-error CM recipe differs')
        if compose_output(base,spec,recipe,binding,budget,proof)!=payload:
            raise ValueError('installed CM/full-error composition differs from sealed code')
    else:
        if manifest.get('full_error_logging') is not None:raise ValueError('unbound full-error overlay; preserved')
        normalized={**payload,'service.py':without_budget(payload['service.py'],spec)} if budget is not None else payload
        if {n:sha(v) for n,v in normalized.items() if n!=CONFIG}!=spec['inventories'][recipe['after']]:
            raise ValueError('installed code differs from sealed recipe')
    if payload.get(CONFIG)!=encoded(binding):raise ValueError('installed serving paths or generation binding changed')
    lib.verify_bindings(payload);lib.local_verification(root)
    if budget is not None:
        module,policy=budget_library(spec);module.local_verification(payload['service.py'],policy)
    return manifest,payload

def prepare(root,spec,lib,binding):
    current=json.loads(lib.path_at(root,'CODE_MANIFEST.json').read_bytes())
    if current.get('cm_oneclick',{}).get('revision')==VERSION:
        manifest,payload=verify_output(root,spec,lib,binding)
        return None,payload,{},manifest
    before,payload,recipe,proof,base=inspect_input(root,spec,lib)
    if json.loads(before).get('cm_oneclick',{}).get('revision') in ('GENOS_CM_ONECLICK_20261007_R8','GENOS_CM_ONECLICK_20261007_R10','GENOS_CM_ONECLICK_20261007_R11','GENOS_CM_ONECLICK_20261007_R12','GENOS_CM_ONECLICK_20261008_R13','GENOS_CM_ONECLICK_20261008_R14') and payload.get(CONFIG)!=encoded(binding):
        raise ValueError('prior CM selected generation binding differs; preserved')
    budget=budget_metadata(json.loads(before),spec)
    final=compose_output(base,spec,recipe,binding,budget,proof)
    for name,raw in final.items():
        if name.endswith('.py'):compile(raw,name,'exec')
        if Path(name).suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise ValueError('JavaScript excluded')
    lib.verify_bindings(final)
    manifest=json.loads(before)
    updates={n:(r['sha256'],sha(final[n])) for r in manifest['files'] for n in [r['path']] if r['sha256']!=sha(final[n])}
    lib.rebind(manifest,updates)
    manifest['files']=[{'path':n,'bytes':len(raw),'sha256':sha(raw)} for n,raw in sorted(final.items())]
    required={r['path']:r['sha256'] for r in manifest['files']}
    manifest['required_files']=[{'path':r,'sha256':required[r]} if isinstance(r,str) else r for r in manifest.get('required_files',[])]
    manifest.update(id=VERSION,cm_oneclick={'revision':VERSION,'recipe_id':recipe['id'],
        'prior_inventory_sha256':sha(before),'prior_state':recipe['label'],'generation_manifest_sha256':binding['generation_manifest_sha256'],
        'consumer_user_team_registration':False,'field_revision_verified':False,
        'preserved_investigation_budget':budget,'preserved_full_error_logging':proof})
    changes={n:raw for n,raw in final.items() if raw!=payload.get(n)}
    changes['CODE_MANIFEST.json']=encoded(manifest)
    return before,payload,changes,manifest

def apply(root,spec,lib,binding,artifacts):
    before,payload,changes,manifest=prepare(root,spec,lib,binding)
    backup=artifacts/'code-backup';receipt=backup/'receipt.json'
    if before is None:return manifest,payload,backup
    if backup.exists():raise ValueError('existing partial backup preserved; inspect STATUS.json')
    for name in changes:
        if name not in payload and name!='CODE_MANIFEST.json' and lib.path_at(root,name).exists():
            raise ValueError('unrecorded file preserved: '+name)
    backup.mkdir()
    journal={'revision':VERSION,'root':str(root),'state':'PREPARED','files':[]}
    for name,new in changes.items():
        old=before if name=='CODE_MANIFEST.json' else payload.get(name)
        path=lib.path_at(root,name)
        if old is None and path.exists():raise ValueError('unrecorded file preserved: '+name)
        mode=(path.stat().st_mode&0o777) if old is not None else 0o644
        if old is not None:lib.atomic(lib.path_at(backup,name),old,mode)
        journal['files'].append({'path':name,'before_sha256':sha(old) if old is not None else None,'after_sha256':sha(new),'mode':mode})
    lib.atomic(receipt,encoded(journal))
    for row in journal['files']:
        path=lib.path_at(root,row['path']);actual=sha(path.read_bytes()) if path.exists() else None
        if actual!=row['before_sha256']:raise ValueError('code changed during preparation; preserved')
    for row in journal['files']:lib.atomic(lib.path_at(root,row['path']),changes[row['path']],row['mode'])
    journal['state']='APPLIED';lib.atomic(receipt,encoded(journal))
    manifest,payload=verify_output(root,spec,lib,binding)
    return manifest,payload,backup

def recover_partial(root,lib,artifacts):
    file=artifacts/'code-backup/receipt.json'
    if not file.exists():return
    record=json.loads(file.read_bytes())
    current=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    if current.get('cm_oneclick',{}).get('revision')==VERSION:return
    if record['root']!=str(root) or record['revision']!=VERSION:raise ValueError('backup identity changed')
    for row in record['files']:
        path=lib.path_at(root,row['path']);actual=sha(path.read_bytes()) if path.exists() else None
        if actual not in (row['before_sha256'],row['after_sha256']):raise ValueError('later code changes preserved during recovery')
        saved=lib.path_at(file.parent,row['path'])
        if row['before_sha256'] is not None and sha(saved.read_bytes())!=row['before_sha256']:raise ValueError('backup hash differs')
    for row in record['files']:
        path=lib.path_at(root,row['path'])
        if row['before_sha256'] is None:path.unlink(missing_ok=True)
        else:lib.atomic(path,lib.path_at(file.parent,row['path']).read_bytes(),row['mode'])
    file.parent.rename(artifacts/('recovered-backup-'+uuid.uuid4().hex))
    print('부분 적용을 백업으로 복원했고 같은 작업을 재개합니다.',flush=True)

def main(spec,argv=None):
    parser=argparse.ArgumentParser(description='TRANSFER에 올린 이 TXT를 인자 없이 실행합니다.')
    parser.add_argument('transfer',type=Path)
    parser.add_argument('--validation-prefix',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    transfer=args.transfer.resolve(strict=True)
    if transfer.name!='TRANSFER':raise ValueError('이 TXT를 기존 DEV/TRANSFER에 올려 실행하세요.')
    root=transfer.parent.resolve(strict=True);lib=library(spec)
    generation=Path(spec['paths']['generation']);runtime=Path(spec['paths']['runtime'])
    if args.validation_prefix:
        prefix=args.validation_prefix.resolve(strict=True)
        if (prefix/'.genos-offline-validation').read_text()!='offline fixture':raise ValueError('isolated fixture marker required')
        generation=prefix/generation.relative_to('/');runtime=prefix/runtime.relative_to('/')
    if generation.is_symlink() or not generation.is_dir():raise ValueError('다른 메일의 NFS 데이터 복원을 먼저 마쳐야 합니다: '+str(generation))
    generation_sha=sha((generation/'manifest.json').read_bytes())
    binding={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed','generation':str(generation),
             'runtime':str(runtime),'state':None,'generation_manifest_sha256':generation_sha,'source':'confirmed field paths and NFS transfer mail 1a115df82c32b2f5'}
    artifacts=transfer/'cm-oneclick-r15';artifacts.mkdir(exist_ok=True)
    status_file=artifacts/'STATUS.json'
    previous=json.loads(status_file.read_bytes()) if status_file.exists() else {}
    status={'revision':VERSION,'state':'RUNNING','code_root':str(root),'generation':str(generation),
            'generation_manifest_sha256':generation_sha,'runtime':str(runtime),'state_dir':None,
            'steps':{},'model_calls':0,'code_serving_revision':None,'workflow_verified':False,
            'data_created_by_oneclick':previous.get('data_created_by_oneclick',False),
            'sys_executable':sys.executable,'python':sys.version.split()[0]}
    def step(name,value=True):status['steps'][name]=value;status['phase']=name;lib.atomic(status_file,encoded(status));print('완료: '+name,flush=True)
    try:
        if git(root,'rev-parse','--show-toplevel')[0]!=str(root):raise ValueError('existing DEV Git checkout required')
        original_manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        allowed={r['path'] for r in original_manifest['files']}|set(spec['managed_paths'])|{'CODE_MANIFEST.json'}
        for kind in [('diff','--cached','--name-only','-z'),('diff','--name-only','-z')]:
            dirty=set(filter(None,git(root,*kind)[0].split('\0')))
            if dirty-allowed:raise ValueError('다른 작업의 변경은 보존했습니다. RUN.log에서 충돌 파일을 확인하세요: '+','.join(sorted(dirty-allowed)))
        remote=git(root,'remote','get-url','origin')[0]
        if args.validation_prefix and (not Path(remote).is_absolute() or not Path(remote).is_relative_to(args.validation_prefix)):
            raise ValueError('offline validation must use a local fixture remote')
        recover_partial(root,lib,artifacts)
        with lib.locked(root):manifest,payload,backup=apply(root,spec,lib,binding,artifacts)
        step('공통 코드 적용',{'backup':str(backup),'inventory_sha256':sha((root/'CODE_MANIFEST.json').read_bytes()),
                           'service_sha256':sha(payload['service.py']),
                           'preserved_investigation_budget':manifest['cm_oneclick']['preserved_investigation_budget'],
                           'preserved_full_error_logging':manifest['cm_oneclick']['preserved_full_error_logging']})
        package=artifacts/'CM51_SOURCE_PACKAGE.json';raw=blob(spec,spec['package_sha256'])
        if package.exists() and package.read_bytes()!=raw:raise ValueError('existing CM package preserved')
        lib.atomic(package,raw)
        env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),
             'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_GENERATION':str(generation),'GENOS_RUNTIME_DIR':str(runtime),
             'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
        env.pop('GENOS_STATE_DIR',None)
        runtime.mkdir(parents=True,exist_ok=True)
        data_receipt=artifacts/'CM51_REGISTERED.json'
        def data(command,source,output):
            cmd=[sys.executable,'-c','import sys;from lawrag.pipeline.unified_memory import main;raise SystemExit(main(sys.argv[1:]))',
                 command,'--common','--store-version','4','--root',str(root),'--runtime',str(runtime),
                 '--generation',str(generation),'--source',str(source),'--output',str(output)]
            r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True)
            lib.atomic(artifacts/(command+'.log'),(r.stdout+r.stderr).encode())
            if r.returncode:raise ValueError('공통 등록 단계 실패: '+command+'; 자동 저장한 단계 로그를 확인하세요.')
            return json.loads(output.read_bytes())
        checked=data('package-check',package,artifacts/'DATA_CHECKED.json')
        if checked['cases']!=51 or checked['source_entries']!=98:raise ValueError('CM51/98 source counts differ')
        step('현장 원문 51건·근거98개 연결',{'cases':checked['cases'],'source_entries':checked['source_entries'],
             'documents':len(checked.get('resolved_documents',[])),'details':str(artifacts/'DATA_CHECKED.json')})
        check_script='import service; c,g,b=service._resolve_binding(); assert str(g)==__GEN__; assert service._DEPLOYMENT_PATHS["runtime"]==__RUN__; print("AUTO_SERVING_PATHS PASS")'
        check_script=check_script.replace('__GEN__',repr(str(generation))).replace('__RUN__',repr(str(runtime)))
        subprocess.run([sys.executable,'-c',check_script],cwd=root,env={k:v for k,v in env.items() if k not in {'GENOS_GENERATION','GENOS_RUNTIME_DIR','GENOS_STATE_DIR'}},check=True)
        step('환경변수 없이 서빙 경로 선택')
        code_paths=['CODE_MANIFEST.json',*[r['path'] for r in manifest['files']]]
        git(root,'add','-f','--',*code_paths);git(root,'diff','--cached','--check')
        _,clean=git(root,'diff','--cached','--quiet',allow=(1,))
        if clean:git(root,'-c','user.name=GENOS CM handoff','-c','user.email=genos-cm-handoff@localhost','commit','-m','Apply common CM catalogue and automatic GENOS paths')
        commit=git(root,'rev-parse','HEAD')[0];step('코드 commit',commit)
        archive=artifacts/'APPLIED_CODE.zip'
        if not archive.exists():
            with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
                z.writestr('CODE_MANIFEST.json',(root/'CODE_MANIFEST.json').read_bytes())
                for n,v in sorted(payload.items()):z.writestr(n,v)
        step('같은 checkout 배포 게이트 시작')
        subprocess.run([sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),'--code-zip',str(archive),
                        '--deploy-root',str(root),'--generation',str(generation)],cwd=root,env=env,check=True)
        step('같은 commit·generation 배포 게이트 통과',{'commit':commit,'code_zip_sha256':sha(archive.read_bytes())})
        selected=subprocess.run([sys.executable,'-c','import sys;from semantic_runtime.legal_agent.shortcut_store import selected_store;print(selected_store(sys.argv[1]))',str(runtime)],cwd=root,env=env,capture_output=True,text=True,check=True)
        dbpath=Path(selected.stdout.strip());sqlbackup=artifacts/'CASE_STATE_BEFORE.sqlite.gz'
        if dbpath.exists() and not sqlbackup.exists():
            with tempfile.TemporaryDirectory() as directory:
                target=Path(directory)/'before.sqlite'
                with sqlite3.connect(dbpath) as src,sqlite3.connect(target) as dst:src.backup(dst)
                with target.open('rb') as src,gzip.open(sqlbackup,'wb') as dst:shutil.copyfileobj(src,dst)
        registered=data('package-import',package,data_receipt)
        status['data_created_by_oneclick'] |= not registered.get('already_imported',False)
        step('공통51건 등록',{'cases':len(registered['records']),'receipt':str(data_receipt),'already_imported':registered.get('already_imported',False)})
        verified=data('package-verify',data_receipt,artifacts/'DATA_VERIFIED.json');step('등록 검증',verified)
        if sha((generation/'manifest.json').read_bytes())!=generation_sha:raise ValueError('generation changed during handoff')
        verify_output(root,spec,lib,binding)
        step('push 시작',{'commit':commit});git(root,'push','origin','HEAD');step('Git push',commit)
        status.update(state='READY_FOR_REVISION_DEPLOYMENT',commit=commit,code_zip_sha256=sha(archive.read_bytes()),receipt=str(data_receipt))
        lib.atomic(status_file,encoded(status))
        print('\n공통 CM51 등록·검증·commit·push 완료. 환경변수 추가 입력 없음.\n코드서빙 화면에서 이 commit으로 새 리비전을 배포하세요.\nCOMMIT='+commit+'\nSTATUS='+str(status_file),flush=True)
        return 0
    except Exception as exc:
        status.update(state='FAILED',error=str(exc));lib.atomic(status_file,encoded(status))
        print('실패 단계='+status.get('phase','사전 확인')+'; '+str(exc)+'\n기존 자료와 복구 기록은 보존했습니다. LOG='+str(artifacts),file=sys.stderr,flush=True)
        return 1
