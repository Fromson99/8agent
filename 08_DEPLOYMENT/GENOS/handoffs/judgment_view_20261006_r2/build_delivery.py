"""Cumulative display handoff over the exact compact-glossary repair bytes."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import zipfile

ROOT=Path.cwd()
OUT=Path(__file__).resolve().parent
NAME='GENOS_JUDGMENT_VIEW_20261006_R2'
PARENT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r1'
BASE=ROOT/'09_ARTIFACTS/DELIVERIES/judgment_view_20261006_r1'
DEPLOY=ROOT/'09_ARTIFACTS/DELIVERIES/judgment_view_20261006_r2'
CHANGED=['02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py',
         '02_BACKEND/semantic_runtime/legal_agent/unified_publication.py',
         '02_BACKEND/semantic_runtime/legal_agent/readable_log.py',
         '02_BACKEND/semantic_runtime/chat_adapter.py',
         '02_BACKEND/semantic_runtime/progress.py',
         '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
NEW='02_BACKEND/semantic_runtime/legal_agent/judgment_view.py'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda value:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    archive=OUT/(NAME+'.zip')
    if archive.exists() or DEPLOY.exists():raise FileExistsError('Use a new revision for a completed delivery')
    parent_zip=PARENT/'GENOS_JUDGMENT_VIEW_20261006_R1.zip'
    assert sha(parent_zip.read_bytes())=='5496746f1e76cbabc99ebcf51efbf3564eb5ac40ace72c3a26d53d7339dad5f2'
    with zipfile.ZipFile(parent_zip) as z:
        parent=json.loads(z.read('CODE_MANIFEST.json'))
        payload={r['path']:z.read(r['path']) for r in parent['files']}
    rows={r['path']:r for r in parent['files']+parent['required_files']}
    for name in CHANGED:
        before=(OUT/'before-working'/name).read_bytes()
        assert sha(before)==rows[name]['sha256'],name+' does not match the shipped baseline'
        payload[name]=(ROOT/name).read_bytes()
    payload[NEW]=(ROOT/NEW).read_bytes()
    config=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    manifests=[]
    for entry in config['engines'].values():
        name=entry['manifest']
        raw=payload.get(name) or (BASE/name).read_bytes()
        engine=json.loads(raw);changed=False
        for source in CHANGED:
            if source in engine['files']:
                engine['files'][source]=sha(payload[source]);changed=True
        if any(n in engine['files'] for n in (CHANGED[0],CHANGED[2],'02_BACKEND/semantic_runtime/progress.py')):
            engine['files'][NEW]=sha(payload[NEW]);changed=True
        if changed:
            payload[name]=encoded(engine);entry['sha256']=sha(payload[name]);manifests.append(name)
    payload['00_SYSTEM/PIPELINE.json']=encoded(config)
    files=[]
    for name,raw in sorted(payload.items()):
        prior=rows.get(name,{})
        predecessors={prior['sha256'],*prior.get('allowed_predecessors',[])} if prior else set()
        files.append({**prior,'path':name,'sha256':sha(raw),'bytes':len(raw),
                      'allowed_predecessors':sorted(predecessors),
                      'allow_missing_predecessor':not prior or prior.get('allow_missing_predecessor',False)})
    required=[r for r in parent['required_files'] if r['path'] not in payload]
    manifest={**parent,'id':NAME,'parent_code_zip_sha256':sha(parent_zip.read_bytes()),
              'scope':'Code-authored nested judgment toggles, recorded data/actions and Mermaid; preserve compact glossary, AD R2 and relation R2',
              'files':files,'required_files':required,'requires_rebuilt_generation':False,
              'changed_runtime_files':CHANGED+[NEW],'judgment_display_revision':'judgment-view-20261006-r1'}
    raw_manifest=encoded(manifest)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted({**payload,'CODE_MANIFEST.json':raw_manifest}.items()):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            if name.endswith('.py'):ast.parse(raw,feature_version=(3,11))
            z.writestr(name,raw)
    script=(PARENT/'GENOS_JUDGMENT_VIEW_20261006_R1_APPLY.txt').read_text()
    script=script.replace('GENOS_JUDGMENT_VIEW_20261006_R1',NAME)
    script=script.replace('judgment-view-r1-logs','judgment-view-r2-logs')
    script=script.replace('GLOSSARY_BINDING_REPAIR_EXIT','JUDGMENT_VIEW_EXIT')
    script=script.replace(sha(parent_zip.read_bytes()),sha(archive.read_bytes()))
    script=script.replace("print('COMPACT_COMPILER_RESTORED'", "print('COMPACT_COMPILER_PRESERVED'")
    (OUT/(NAME+'_APPLY.txt')).write_text(script)
    (OUT/'CODE_MANIFEST.json').write_bytes(raw_manifest)
    for row in required:
        assert sha((BASE/row['path']).read_bytes())==row['sha256']
    for name,raw in {**{r['path']:(BASE/r['path']).read_bytes() for r in required},**payload}.items():
        target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    workflow=payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
    (OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(workflow)
    # Explicitly identified fixture-only dependencies are never added to the ZIP.
    support=json.loads((PARENT/'TEST_SUPPORT.json').read_text())
    for row in support:
        name=row['path']
        if (DEPLOY/name).exists():continue
        raw=(BASE/name).read_bytes() if (BASE/name).is_file() else (ROOT/name).read_bytes()
        assert sha(raw)==row['sha256']
        target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    shutil.copytree(ROOT/'05_TESTS/CONTRACTS',DEPLOY/'05_TESTS/CONTRACTS')
    for name in ('pytest.ini','05_TESTS/conftest.py'):
        target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    compiler='02_BACKEND/semantic_runtime/full_glossary.py'
    assert sha((DEPLOY/compiler).read_bytes())=='e03dab542ab0e1c9d129336308ddcdd0ab7a0ee1246fc29614f4efa12a8b4406'
    record={'version':NAME,'parent_zip_sha256':sha(parent_zip.read_bytes()),
            'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha(raw_manifest),
            'apply_txt_sha256':sha(script.encode()),'workflow_txt_sha256':sha(workflow),
            'deployment_checkout':str(DEPLOY),'runtime_changes':CHANGED+[NEW],
            'compiler_sha256':sha((DEPLOY/compiler).read_bytes()),'engine_manifests_changed':manifests,
            'code_files':len(files),'required_files':len(required),
            'genos_deployed':False,'field_generation_gate':'NOT_RUN','field_revision':None,
            'main_promotion':False,'external_model_calls':0}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':main()
