#!/usr/bin/env python3
"""Attach reviewed ontology to an existing generation without modifying its assets."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from it35_common import *

def patch_plan(root):
    old=(root/CONFIG_PATH).read_bytes()
    new=patched_config((HERE/'configuration.before.py').read_bytes())
    if old not in ((HERE/'configuration.before.py').read_bytes(),new):
        raise ValueError('Unsupported checkout configuration.py; no overwrite')
    pipeline_path=root/'00_SYSTEM/PIPELINE.json'
    pipeline_raw=pipeline_path.read_bytes();pipeline=json.loads(pipeline_raw)
    changes={};dependencies={};checked={}
    if old!=new: changes[CONFIG_PATH]=new
    replacements={}
    for entry in pipeline['engines'].values():
        name=entry['manifest'];raw=(root/name).read_bytes()
        if sha(raw)!=entry['sha256']:raise ValueError('Existing engine manifest mismatch: '+name)
        manifest=json.loads(raw)
        for path,expected in manifest['files'].items():
            if path not in checked:checked[path]=sha((root/path).read_bytes())
            if checked[path]!=expected:raise ValueError('Existing engine code mismatch: '+path)
            dependencies[path]=checked[path]
        if CONFIG_PATH in manifest['files'] and old!=new:
            updated=raw.replace(sha(old).encode(),sha(new).encode())
            if updated==raw:raise ValueError('Missing old configuration pin')
            changes[name]=updated;replacements[sha(raw)]=sha(updated)
    if old!=new and not replacements:raise ValueError('Ontology configuration is not pinned by this checkout')
    if replacements:
        for before,after in replacements.items():pipeline_raw=pipeline_raw.replace(before.encode(),after.encode())
        changes['00_SYSTEM/PIPELINE.json']=pipeline_raw
    dependencies.update({e['manifest']:e['sha256'] for e in pipeline['engines'].values()})
    dependencies['00_SYSTEM/PIPELINE.json']=sha((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    for path,raw in changes.items():dependencies[path]=sha(raw)
    dependencies[CONFIG_PATH]=sha(new)
    return changes,dependencies

def atomic(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        os.chmod(name,0o644);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def install(root,generation,output,apply=False):
    verify_package();root=Path(root).resolve();g=Path(generation)
    if not g.is_absolute() or g.is_symlink():raise ValueError('Absolute actual GENOS_GENERATION required')
    g=g.resolve(strict=True);manifest=read_json(g/'manifest.json')
    if manifest['schema_version'] not in ('term-source-generation-v1','term-source-generation-v2'):
        raise ValueError('Unsupported source generation')
    msha=sha((g/'manifest.json').read_bytes())
    # Original bytes and registered coordinates must match before NFS or code writes.
    if (g/'store.sqlite').is_symlink() or file_sha(g/'store.sqlite')!=manifest['store_sha256']:
        raise ValueError('Existing generation source store hash mismatch')
    units=sqlite_sources(g/'store.sqlite');snapshot()
    deployment=root/'00_SYSTEM/GENOS_SERVING_PATHS.json'
    if deployment.exists():
        selected=read_json(deployment)
        if selected.get('generation')!=str(g) or selected.get('generation_manifest_sha256')!=msha:
            raise ValueError('GENOS_SERVING_PATHS.json overrides this generation; select the actual deployed binding')
    initial_pipeline=(root/'00_SYSTEM/PIPELINE.json').read_bytes()
    initial_hashes={CONFIG_PATH:file_sha(root/CONFIG_PATH),'00_SYSTEM/PIPELINE.json':sha(initial_pipeline)}
    initial_hashes.update({v['manifest']:v['sha256'] for v in json.loads(initial_pipeline)['engines'].values()})
    changes,deps=patch_plan(root)
    target=g/'ontology'/'integration-external-b03-b05-r4'
    config={'version':'ontology-connection-v1','environment':'genos-nfs',
        'database':{'kind':'sqlite-published','path':str(target/'ontology.sqlite'),
                    'sha256':sha((PAYLOAD/'ontology.sqlite').read_bytes())},
        'source_generation':{'path':str(g),'manifest_sha256':msha},
        'workspace_runtime_scopes':[]}
    expected={'ontology.sqlite':(PAYLOAD/'ontology.sqlite').read_bytes(),
              'runtime_config.json':json_bytes(config),
              'binding.json':json_bytes({'source_generation':config['source_generation'],
                'ontology_json_sha256':sha((PAYLOAD/'ontology.json').read_bytes()),'source_units':units})}
    if target.exists():
        if target.is_symlink() or set(p.name for p in target.iterdir())!=set(expected):
            raise ValueError('Existing ontology directory differs; preserve it')
        for name,raw in expected.items():
            if (target/name).is_symlink() or (target/name).read_bytes()!=raw:
                raise ValueError('Existing ontology differs; no overwrite: '+name)
    result={'status':'PREFLIGHT_PASS','generation':str(g),'manifest_sha256':msha,
        'code_root':str(root),'source_units':units,'bundles':inventory()['bundles'],'paths':inventory()['paths'],
        'original_database_writes':0,'code_files_to_change':sorted(changes),
        'environment':{'DP':'nfs','GENOS_RAG_ONTOLOGY_ENABLED':'on',
            'GENOS_RAG_ONTOLOGY_CONFIG':str(target/'runtime_config.json')},
        'commit':None,'serving_revision':None,'field_serving_verified':False}
    if not apply:return result
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    if changes and (output/'code-before.json').exists():
        raise ValueError('Previous patch receipt exists; use its rollback or a fresh output directory')
    before={p:initial_hashes[p] for p in changes}
    for p,expected_sha in before.items():
        if file_sha(root/p)!=expected_sha:raise ValueError('Concurrent checkout change before installation: '+p)
    if changes:
        for p in changes:atomic(output/'code-before'/p,(root/p).read_bytes())
        atomic(output/'code-before.json',json_bytes(before))
        atomic(output/'code-after.json',json_bytes({p:sha(v) for p,v in changes.items()}))
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.it35-',dir=target.parent))
        try:
            for name,raw in expected.items():atomic(staging/name,raw)
            os.chmod(staging,0o755)
            # Directory rename publishes the complete sealed snapshot together.
            staging.rename(target)
        finally:
            if staging.exists():shutil.rmtree(staging)
    for p,raw in changes.items():
        if sha((root/p).read_bytes())!=before[p]:raise ValueError('Concurrent checkout edit: '+p)
        atomic(root/p,raw)
    patch_plan(root)  # All target engine pins and dependencies must still match.
    if sha((g/'manifest.json').read_bytes())!=msha:raise ValueError('Source generation changed during installation')
    selected=sorted(set(changes)|{CONFIG_PATH,'00_SYSTEM/PIPELINE.json'})
    code_manifest={'format':'8agent-code/1','files':[
        {'path':p,'sha256':sha((root/p).read_bytes()),'bytes':(root/p).stat().st_size} for p in selected],
        'required_files':[{'path':p,'sha256':v} for p,v in sorted(deps.items()) if p not in selected]}
    with zipfile.ZipFile(output/'DEPLOY_CODE.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in selected:archive.writestr(p,(root/p).read_bytes())
        archive.writestr('CODE_MANIFEST.json',json_bytes(code_manifest))
    result.update(status='PREPARED_NOT_DEPLOYED',code_zip_sha256=sha((output/'DEPLOY_CODE.zip').read_bytes()),
                  code_files={p:sha((root/p).read_bytes()) for p in selected})
    atomic(output/'INSTALL_RECEIPT.json',json_bytes(result))
    atomic(output/'SERVING_ENV.txt','\n'.join(k+'='+v for k,v in result['environment'].items()).encode()+b'\n')
    return result

def rollback(root,output):
    root=Path(root).resolve();output=Path(output).resolve()
    before=read_json(output/'code-before.json');after=read_json(output/'code-after.json')
    for p,expected in after.items():
        if sha((root/p).read_bytes()) not in (expected,before[p]):raise ValueError('Code edited since installation: '+p)
        if sha((output/'code-before'/p).read_bytes())!=before[p]:raise ValueError('Backup changed: '+p)
    for p in before:atomic(root/p,(output/'code-before'/p).read_bytes())
    return {'status':'CODE_RESTORED','generation_data_preserved':True,
            'next':'Restore previous code-serving revision and ontology environment settings'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--code-root',required=True);p.add_argument('--generation')
    p.add_argument('--output',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--rollback-code',action='store_true')
    a=p.parse_args()
    result=rollback(a.code_root,a.output) if a.rollback_code else install(a.code_root,a.generation or os.environ['GENOS_GENERATION'],a.output,a.apply)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
