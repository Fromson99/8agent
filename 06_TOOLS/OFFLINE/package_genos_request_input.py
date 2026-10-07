"""Cumulative v6 handoff from the verified SQL/AD R5 bytes, without data changes."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/sql_ad_cumulative_20261006_r5/GENOS_V6_SQL_AD_CUMULATIVE_20261006_R5.zip'
BASE_SHA='9d1c3c76bd98adfd25b67625edde016d954b6bc34e4705565daf053857b41086'
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2'
STEM='GENOS_V6_REQUEST_INPUT_20261006_R2'
GENERATION='/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
RUNTIME=['service.py']+['02_BACKEND/semantic_runtime/legal_agent/'+name+'.py' for name in
    ['domain','gateway','relation_views','tiers_views','workflow_tiers_views',
     'relations_tools','workflow_relations_tools','corrected_memory']]
TARGET_SHA={
 'service.py':'89adf358fc975d27be9bdc4528ac24f209ffc047d02c0837b28f8ef0fa94b0b4',
 '02_BACKEND/semantic_runtime/legal_agent/domain.py':'5dd6365831db8918ca7be371b6be492b442e9baf9bffa8d817b84e0f57387bb4',
 '02_BACKEND/semantic_runtime/legal_agent/gateway.py':'ed5f4e717ce31a70566464132abdbe69c5bccf6365927c7c3d1cee9684d4bb6c',
 '02_BACKEND/semantic_runtime/legal_agent/relation_views.py':'ef3e739bab8010dc3c71e748a3a20af30be4a871e863170a1b3c1165bf8cdb72',
 '02_BACKEND/semantic_runtime/legal_agent/tiers_views.py':'8eb7014103685092b458f2d23f7fe724122d72adcc50f3cffc0dea07aa7575b9',
 '02_BACKEND/semantic_runtime/legal_agent/workflow_tiers_views.py':'db85ae5051240d8d4c8f5f2c5bd1baf4d4da5e5e37cb3b4a48a3fe0ca366dcc2',
 '02_BACKEND/semantic_runtime/legal_agent/relations_tools.py':'6a6252cf219070b256d83b141ee24831aa6405cf82e5b46fe5a6fafadacbf9ae',
 '02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py':'4758a3e495310f38abd47b5a53c8e261b568749f5037677a3f24dd20394086a6',
 '02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py':'ce8b7cbf6d206e494ff348618a87f506e13beb6b61f028eb305d7000819c8ffb',
}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def json_bytes(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def main():
    if sha(BASE.read_bytes())!=BASE_SHA:raise ValueError('Parent code ZIP changed')
    if OUT.exists():raise FileExistsError('Immutable handoff exists; use a new revision')
    with zipfile.ZipFile(BASE) as z:
        parent=json.loads(z.read('CODE_MANIFEST.json'))
        payload={row['path']:z.read(row['path']) for row in parent['files']}
        for row in parent['files']:
            if sha(payload[row['path']])!=row['sha256']:raise ValueError('Parent file drift')
    old_payload=dict(payload)
    spec=importlib.util.spec_from_file_location('compact_handoff',ROOT/'06_TOOLS/OFFLINE/package_genos_compact_loader.py')
    compact=importlib.util.module_from_spec(spec);spec.loader.exec_module(compact)
    # Bind only the reviewed target bytes, even when the workspace moves on.
    for name in RUNTIME:
        raw=(ROOT/name).read_bytes()
        if sha(raw)!=TARGET_SHA[name]:raise ValueError('Reviewed code changed: '+name)
        ast.parse(raw,feature_version=(3,11));payload[name]=raw
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    changed=[]
    for entry in pipeline['engines'].values():
        name=entry['manifest'];manifest=json.loads(payload[name]);updated=False
        for source,expected in list(manifest['files'].items()):
            if source not in RUNTIME:continue
            if sha(old_payload[source])!=expected:raise ValueError('Parent engine drift: '+source)
            actual=sha(payload[source])
            if actual!=expected:manifest['files'][source]=actual;updated=True
        if updated:
            payload[name]=json_bytes(manifest);entry['sha256']=sha(payload[name]);changed.append(name)
    payload['00_SYSTEM/PIPELINE.json']=json_bytes(pipeline)
    if payload['00_SYSTEM/PIPELINE.json']!=(ROOT/'00_SYSTEM/PIPELINE.json').read_bytes():
        raise ValueError('Working pipeline contains additional unreviewed changes')
    for name in changed:
        if payload[name]!=(ROOT/name).read_bytes():raise ValueError('Working engine drift: '+name)
    # Preserve the already handed-off compact reader instead of downgrading it
    # to R5's legacy reader. Leave the unrelated local working reader untouched.
    compatibility='02_BACKEND/semantic_runtime/full_glossary.py'
    reference=ROOT/'08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_20261003_R1.zip'
    with zipfile.ZipFile(reference) as z:reader=z.read(compatibility)
    if sha(reader)!='e03dab542ab0e1c9d129336308ddcdd0ab7a0ee1246fc29614f4efa12a8b4406':
        raise ValueError('Verified compact reader changed')
    payload[compatibility]=reader
    for entry in pipeline['engines'].values():
        name=entry['manifest'];manifest=json.loads(payload[name])
        if compatibility in manifest['files']:
            if manifest['files'][compatibility]!=sha(old_payload[compatibility]):
                raise ValueError('Unexpected compact reader predecessor')
            manifest['files'][compatibility]=sha(reader)
            payload[name]=json_bytes(manifest);entry['sha256']=sha(payload[name])
    payload['00_SYSTEM/PIPELINE.json']=json_bytes(pipeline)
    predecessors={name:{sha(raw)} for name,raw in old_payload.items()}
    optional=set()
    ancestor_archives=[ROOT/'08_DEPLOYMENT/GENOS/handoffs/unified_v6_cumulative_20261002_r4/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip',
        ROOT/'08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_20261003_R1.zip']
    for archive in ancestor_archives:
        with zipfile.ZipFile(archive) as z:
            ancestor=json.loads(z.read('CODE_MANIFEST.json'))
            rows={r['path']:r for r in ancestor['files']+ancestor.get('required_files',[])}
            for name in payload:
                if name in rows:predecessors[name].add(rows[name]['sha256'])
                else:optional.add(name)
            if 'service.py' in z.namelist():predecessors['service.py'].add(sha(compact.patch(z.read('service.py'))))
    predecessors['service.py'].add(sha(compact.patch(old_payload['service.py'])))
    rows=[{'path':name,'role':row.get('role','code'),'sha256':sha(payload[name]),'bytes':len(payload[name]),
        'allowed_predecessors':sorted(predecessors[name]),'allow_missing_predecessor':name in optional}
        for row in parent['files'] for name in [row['path']]]
    manifest={'format':'8agent-code/1','id':STEM,'parent_code_zip_sha256':BASE_SHA,
        'scope':'Cumulative v6 + SQL/AD + compact loader; remove input byte guard and resolver document inventories',
        'files':rows,'required_files':[],'changed_runtime_files':RUNTIME+[compatibility],
        'requires_rebuilt_generation':False,'activated':False,'generation_candidate':GENERATION}
    OUT.mkdir(parents=True)
    archive=OUT/(STEM+'.zip');raw_manifest=json_bytes(manifest)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in {**payload,'CODE_MANIFEST.json':raw_manifest}.items():
            info=zipfile.ZipInfo(name,(2026,10,6,0,0,0));info.external_attr=0o100644<<16
            info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    script=compact.SCRIPT.replace('__STEM__',STEM).replace('__ZIP_SHA__',sha(archive.read_bytes())).replace('__GENERATION__',GENERATION)
    script=script.replace('compact-loader-logs','request-input-logs').replace('LOADER_EXIT','REQUEST_INPUT_EXIT')
    needle="  if not path.is_file() or sha(path) not in allowed:\n"
    if script.count(needle)!=1:raise ValueError('Installer template changed')
    script=script.replace(needle,"  if not path.exists() and not applied and row.get('allow_missing_predecessor'):continue\n"+needle)
    (OUT/(STEM+'_APPLY.txt')).write_text(script)
    subprocess.run(['bash','-n',str(OUT/(STEM+'_APPLY.txt'))],check=True)
    (OUT/'CODE_MANIFEST.json').write_bytes(raw_manifest)
    record={'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha(raw_manifest),
        'apply_txt_sha256':sha(script.encode()),'parent_code_zip_sha256':BASE_SHA,
        'runtime_files':RUNTIME,'engine_manifests':changed,'code_files':len(rows),
        'preserved_compact_reader':{'path':compatibility,'sha256':sha(reader),
            'origin_code_zip_sha256':sha(reference.read_bytes()),'local_working_file_modified':False},
        'generation_candidate':GENERATION,'generation_manifest_sha256':None,
        'field_commit':None,'field_revision':None,'genos_deployed':False,'live_workflow_e2e':'NOT_RUN'}
    (OUT/'HANDOFF.json').write_bytes(json_bytes(record));print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
