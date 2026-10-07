"""Bind only the requested policy/display changes to the delivered R2 baseline."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT=Path.cwd()
OUT=Path(__file__).resolve().parent
NAME='GENOS_RELATION_READING_20261006_R1'
OLD=ROOT/'08_DEPLOYMENT/GENOS/handoffs/source_recall_timeout_20261006_r2'
DEPLOY=ROOT/'09_ARTIFACTS/DELIVERIES/relation_reading_20261006_r1'
PARENTS=[ROOT/'08_DEPLOYMENT/GENOS/handoffs'/name for name in (
    'request_input_20261006_r2/GENOS_V6_REQUEST_INPUT_20261006_R2.zip',
    'nfs_state_sqlite_20261006_r1/GENOS_NFS_STATE_SQLITE_20261006_R1.zip',
    'source_recall_timeout_20261006_r1/GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1.zip',
    'source_recall_timeout_20261006_r2/GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2.zip')]
CHANGED=['02_BACKEND/semantic_runtime/legal_agent/'+name for name in (
    'source_recall.py','unit_reading.py','unit_selection.py','unit_relations.py',
    'relation_read_policy.py','unified_rag.py','memory_rag.py','bounded_source_session.py')]
CHANGED += ['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def contents(path):
    with zipfile.ZipFile(path) as z:
        m=json.loads(z.read('CODE_MANIFEST.json'))
        result={r['path']:z.read(r['path']) for r in m['files']}
        assert all(sha(result[r['path']])==r['sha256'] for r in m['files'])
        return result


snapshots=[];prior={}
for path in PARENTS:
    prior={**prior,**contents(path)};snapshots.append(prior)
for name in CHANGED:
    before=OUT/'before-working'/name
    if before.exists():assert before.read_bytes()==prior[name], 'Unreviewed upstream drift: '+name
payload={**contents(PARENTS[-1]),**{name:(ROOT/name).read_bytes() for name in CHANGED}}
config=prior['00_SYSTEM/PIPELINE.json'].decode();required={};changed_manifests=[]
for entry in json.loads(config)['engines'].values():
    name=entry['manifest'];m=json.loads(prior[name])
    if not set(CHANGED)&set(m['files']):continue
    for source in set(CHANGED)&set(m['files']):m['files'][source]=sha(payload[source])
    helper='02_BACKEND/semantic_runtime/legal_agent/relation_read_policy.py'
    if '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py' in m['files']:
        m['files'][helper]=sha(payload[helper])
    raw=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode()
    payload[name]=raw;changed_manifests.append(name)
    config=config.replace('"'+entry['sha256']+'"','"'+sha(raw)+'"')
    required.update(m['files'])
payload['00_SYSTEM/PIPELINE.json']=config.encode()
required={name:digest for name,digest in required.items() if name not in payload}
assert all(sha(prior[name])==digest for name,digest in required.items())

# Working metadata can contain unrelated, not-yet-shipped changes. Preserve
# its original fields and pin only this task; field metadata follows prior ZIP.
working_config=(OUT/'before-working/00_SYSTEM/PIPELINE.json').read_text()
working_receipt=[]
for entry in json.loads(working_config)['engines'].values():
    target=ROOT/entry['manifest'];backup=OUT/'before-working'/entry['manifest']
    original=backup.read_bytes() if backup.exists() else target.read_bytes()
    m=json.loads(original)
    if not set(CHANGED)&set(m['files']):continue
    for name in set(CHANGED)&set(m['files']):m['files'][name]=sha(payload[name])
    if '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py' in m['files']:
        m['files'][helper]=sha(payload[helper])
    raw=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode();target.write_bytes(raw)
    working_config=working_config.replace('"'+entry['sha256']+'"','"'+sha(raw)+'"')
    working_receipt.append({'path':entry['manifest'],'before':sha(original),'after':sha(raw),
                            'field_metadata_sha256':sha(payload[entry['manifest']])})
(ROOT/'00_SYSTEM/PIPELINE.json').write_text(working_config)
(OUT/'WORKING_PIN_RECEIPT.json').write_text(json.dumps(working_receipt,indent=2)+'\n')
rows=[{'path':name,'sha256':sha(raw),'bytes':len(raw),
       'allowed_predecessors':sorted({sha(s[name]) for s in snapshots if name in s}),
       'allow_missing_predecessor':name not in snapshots[0]} for name,raw in sorted(payload.items())]
manifest={'format':'8agent-code/1','id':NAME,'parent_code_zip_sha256':sha(PARENTS[-1].read_bytes()),
    'scope':'typed/directional minimum READ, required dependency checks and read display aggregation; preserve SQL/AD R5, routing R2, NFS SQLite and compact reader',
    'files':rows,'required_files':[{'path':name,'sha256':digest} for name,digest in sorted(required.items())]}
archive=OUT/(NAME+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name,raw in sorted(payload.items()):
        assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        z.writestr(name,raw)
    z.writestr('CODE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(OUT/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
script=(OLD/'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2_APPLY.txt').read_text().replace(
    'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2',NAME).replace('source-recall-routing-r2-logs','relation-reading-r1-logs')
script=re.sub(r"if sha\(archive\)!='[0-9a-f]{64}'","if sha(archive)!='"+sha(archive.read_bytes())+"'",script)
script=script.replace("os.environ.get('GENOS_GENERATION','/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation')",
    "os.environ.get('GENOS_GENERATION')")
script=script.replace(' path=Path(value)'," if not value:raise ValueError('Supply actual GENOS_GENERATION or an explicit existing generation path; no automatic selection')\n path=Path(value)")
(OUT/(NAME+'_APPLY.txt')).write_text(script)
(OUT/(NAME+'_WORKFLOW_PYTHON.txt')).write_bytes(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
for name,raw in {**prior,**payload}.items():
    target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
(OUT/'HANDOFF.json').write_text(json.dumps({
    'version':NAME,'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha((OUT/'CODE_MANIFEST.json').read_bytes()),
    'apply_txt_sha256':sha((OUT/(NAME+'_APPLY.txt')).read_bytes()),'deployment_checkout':str(DEPLOY),
    'working_validation_root':str(ROOT),'changed_source':CHANGED,'code_files':len(payload),'required_files':len(required),
    'compact_reader_sha256':required['02_BACKEND/semantic_runtime/full_glossary.py'],
    'policy_revision':'relation-reading-policy-20261006-r1',
    'display_revision':'reasoner-display-read-summary-20261006-r1',
    'generation_absolute_path':None,'generation_manifest_sha256':None,'field_commit':None,'field_revision':None,
    'genos_deployed':False,'field_workflow_editor_updated':False,'main_promotion':False,
    'external_model_calls':0,'validation_kind':'synthetic unit/integration contracts; no quality/performance experiment'
},ensure_ascii=False,indent=2)+'\n')
print('Built',NAME,len(payload),'files;',len(required),'unchanged pins;',archive.stat().st_size,'ZIP bytes')
