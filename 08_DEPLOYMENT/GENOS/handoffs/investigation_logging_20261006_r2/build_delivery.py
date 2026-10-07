"""Preserve the immutable R3 delivery, replacing only declared logging files."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
NAME='GENOS_INVESTIGATION_LOGGING_20261006_R2'
PARENT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/rag_control_flow_20261006_r3'
BASE=ROOT/'09_ARTIFACTS/DELIVERIES/rag_control_flow_20261006_r3'
DEPLOY=ROOT/'09_ARTIFACTS/DELIVERIES/investigation_logging_20261006_r2'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    archive=OUT/(NAME+'.zip')
    if archive.exists() or DEPLOY.exists():raise FileExistsError('Use a new revision after building a delivery')
    changed=json.loads((OUT/'CHANGED_FILES.json').read_text())
    parent_record=json.loads((PARENT/'HANDOFF.json').read_text())
    parent_zip=PARENT/(parent_record['version']+'.zip')
    assert sha(parent_zip.read_bytes())==parent_record['code_zip_sha256']
    with zipfile.ZipFile(parent_zip) as z:
        parent=json.loads(z.read('CODE_MANIFEST.json'))
        payload={r['path']:z.read(r['path']) for r in parent['files']}
    prior={r['path']:r for r in parent['files']+parent['required_files']}
    for row in parent['required_files']:
        assert sha((BASE/row['path']).read_bytes())==row['sha256'],row['path']
    for name in changed:payload[name]=(ROOT/name).read_bytes()
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json']);manifests=[]
    new='02_BACKEND/semantic_runtime/legal_agent/investigation_diagnostics.py'
    for entry in pipeline['engines'].values():
        name=entry['manifest'];engine=json.loads(payload.get(name) or (BASE/name).read_bytes())
        if any(p in engine['files'] for p in changed):
            for p in changed:
                if p in engine['files'] or p==new:engine['files'][p]=sha(payload[p])
            payload[name]=encoded(engine);entry['sha256']=sha(payload[name]);manifests.append(name)
    payload['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
    files=[]
    for name,raw in sorted(payload.items()):
        row=prior.get(name,{})
        predecessors={row['sha256'],*row.get('allowed_predecessors',[])} if row else set()
        files.append({**row,'path':name,'sha256':sha(raw),'bytes':len(raw),
            'allowed_predecessors':sorted(predecessors),
            'allow_missing_predecessor':not row or row.get('allow_missing_predecessor',False)})
    required=[r for r in parent['required_files'] if r['path'] not in payload]
    manifest={**parent,'id':NAME,'parent_code_zip_sha256':sha(parent_zip.read_bytes()),
        'scope':'Causal reference/selection/failure logging; preserve R3 execution and compact/AD readers; no data rebuild or MAIN activation',
        'files':files,'required_files':required,'changed_runtime_files':changed,
        'diagnostic_revision':'investigation-diagnostics-v1','progress_display_revision':'agent-causal-diagnostics-20261006-r1'}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted({**payload,'CODE_MANIFEST.json':encoded(manifest)}.items()):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            if name.endswith('.py'):ast.parse(raw,feature_version=(3,11))
            z.writestr(name,raw)
    script=(PARENT/(parent_record['version']+'_APPLY.txt')).read_text()
    script=script.replace(parent_record['version'],NAME).replace(parent_record['code_zip_sha256'],sha(archive.read_bytes()))
    script=script.replace('rag-control-flow-r3-logs','investigation-logging-r2-logs').replace('RAG_CONTROL_FLOW_EXIT','INVESTIGATION_LOGGING_EXIT')
    (OUT/(NAME+'_APPLY.txt')).write_text(script)
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    for name,raw in {**{r['path']:(BASE/r['path']).read_bytes() for r in required},**payload}.items():
        target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    support=json.loads((ROOT/'08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r1/TEST_SUPPORT.json').read_text())
    for row in support:
        target=DEPLOY/row['path']
        if target.exists():continue
        raw=(BASE/row['path']).read_bytes();assert sha(raw)==row['sha256']
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    shutil.copytree(ROOT/'05_TESTS/CONTRACTS',DEPLOY/'05_TESTS/CONTRACTS')
    # Empty layout directories are test scaffolding, never data packages or ZIP members.
    for row in json.loads((DEPLOY/'00_SYSTEM/WORKSPACE.json').read_text())['roots']:
        (DEPLOY/row['canonical_path']).mkdir(exist_ok=True)
    for name in ('pytest.ini','05_TESTS/conftest.py'):
        target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    compiler='02_BACKEND/semantic_runtime/full_glossary.py'
    assert sha((DEPLOY/compiler).read_bytes())==parent_record['compiler_sha256']
    workflow=payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
    (OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(workflow)
    record={'version':NAME,'parent_zip_sha256':sha(parent_zip.read_bytes()),
        'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha(encoded(manifest)),
        'apply_txt_sha256':sha(script.encode()),'workflow_txt_sha256':sha(workflow),
        'verified_runtime_root':str(DEPLOY),'runtime_changes':changed,
        'cumulative_runtime_changes':sorted(set(changed+parent_record['runtime_changes'])),
        'compiler_sha256':sha((DEPLOY/compiler).read_bytes()),'engine_manifests_changed':manifests,
        'code_files':len(files),'required_files':len(required),'requires_rebuilt_generation':False,
        'push_checkout':'~/DEV (field; not verified)','push_commit':None,
        'selected_generation_path':None,'selected_generation_manifest_sha256':None,
        'genos_deployed':False,'field_generation_gate':'NOT_RUN','field_revision':None,
        'main_promotion':False,'external_model_calls':0,'shipping_version':False}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps({'code_files':len(files),'required_files':len(required),'zip_sha256':record['code_zip_sha256']}))


if __name__=='__main__':main()
