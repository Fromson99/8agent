"""Cumulative display handoff over the exact compact-glossary repair bytes."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import zipfile

ROOT=Path.cwd()
OUT=Path(__file__).resolve().parent
NAME='GENOS_PROGRESSIVE_READING_20261006_R1'
PARENT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r2'
BASE=ROOT/'09_ARTIFACTS/DELIVERIES/judgment_view_20261006_r2'
DEPLOY=ROOT/'09_ARTIFACTS/DELIVERIES/progressive_reading_20261006_r1'
CHANGED=['02_BACKEND/semantic_runtime/legal_agent/relation_read_policy.py', '02_BACKEND/semantic_runtime/legal_agent/source_recall.py', '02_BACKEND/semantic_runtime/legal_agent/source_recall_global.py', '02_BACKEND/semantic_runtime/legal_agent/source_tools.py', '02_BACKEND/semantic_runtime/legal_agent/unit_reading.py', '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py', '02_BACKEND/semantic_runtime/legal_agent/unit_selection.py', '02_BACKEND/semantic_runtime/progress.py', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda value:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    archive=OUT/(NAME+'.zip')
    if archive.exists() or DEPLOY.exists():raise FileExistsError('Use a new revision for a completed delivery')
    parent_zip=PARENT/'GENOS_JUDGMENT_VIEW_20261006_R2.zip'
    assert sha(parent_zip.read_bytes())=='c4eae5615c2eebba44673e1f0a1e70f3a3fe18891b89f281d3e93ba752b9c2b6'
    with zipfile.ZipFile(parent_zip) as z:
        parent=json.loads(z.read('CODE_MANIFEST.json'))
        payload={r['path']:z.read(r['path']) for r in parent['files']}
    rows={r['path']:r for r in parent['files']+parent['required_files']}
    for name in CHANGED:
        before=(OUT/'before-working'/name).read_bytes()
        assert sha(before)==rows[name]['sha256'],name+' does not match the shipped baseline'
        payload[name]=(ROOT/name).read_bytes()
    config=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    manifests=[]
    for entry in config['engines'].values():
        name=entry['manifest']
        raw=payload.get(name) or (BASE/name).read_bytes()
        engine=json.loads(raw);changed=False
        for source in CHANGED:
            if source in engine['files']:
                engine['files'][source]=sha(payload[source]);changed=True
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
              'scope':'Progressive grouped original reads, explicit sufficiency stop, bounded UI updates and conditional decision repair; preserve compact glossary, AD R2 and judgment R2',
              'files':files,'required_files':required,'requires_rebuilt_generation':False,
              'changed_runtime_files':CHANGED,'progress_display_revision':'reasoner-display-read-batches-20261006-r2', 'candidate_acquisition_revision':'progressive-grouped-v1'}
    raw_manifest=encoded(manifest)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted({**payload,'CODE_MANIFEST.json':raw_manifest}.items()):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            if name.endswith('.py'):ast.parse(raw,feature_version=(3,11))
            z.writestr(name,raw)
    script=(PARENT/'GENOS_JUDGMENT_VIEW_20261006_R2_APPLY.txt').read_text()
    script=script.replace('GENOS_JUDGMENT_VIEW_20261006_R2',NAME)
    script=script.replace('judgment-view-r2-logs','progressive-reading-r1-logs')
    script=script.replace('JUDGMENT_VIEW_EXIT','PROGRESSIVE_READING_EXIT')
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
    support=json.loads((ROOT/'08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r1/TEST_SUPPORT.json').read_text())
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
            'deployment_checkout':str(DEPLOY),'runtime_changes':CHANGED,
            'compiler_sha256':sha((DEPLOY/compiler).read_bytes()),'engine_manifests_changed':manifests,
            'code_files':len(files),'required_files':len(required),
            'genos_deployed':False,'field_generation_gate':'NOT_RUN','field_revision':None,
            'main_promotion':False,'external_model_calls':0}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':main()
