"""Add the v6 direct-input gate to the exact cumulative timeout/NFS delivery."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT=Path.cwd()
OUT=Path(__file__).resolve().parent
DEPLOY=ROOT/'09_ARTIFACTS/DELIVERIES/source_recall_timeout_20261006_r1'
NAME='GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2'
OLD=ROOT/'08_DEPLOYMENT/GENOS/handoffs/source_recall_timeout_20261006_r1'
BASE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2/GENOS_V6_REQUEST_INPUT_20261006_R2.zip'
NFS=ROOT/'08_DEPLOYMENT/GENOS/handoffs/nfs_state_sqlite_20261006_r1/GENOS_NFS_STATE_SQLITE_20261006_R1.zip'
TIMER=OLD/'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1.zip'
CHANGED=['02_BACKEND/semantic_runtime/legal_agent/'+name for name in
    ('source_query_planning.py','case_repository.py','shortcut_cases.py','unified_runtime.py','readable_log.py')]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def contents(path):
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        data={r['path']:z.read(r['path']) for r in manifest['files']}
        assert all(sha(data[r['path']])==r['sha256'] for r in manifest['files'])
        return data
base,nfs,timer=contents(BASE),contents(NFS),contents(TIMER)
snapshots=[base,{**base,**nfs},{**base,**nfs,**timer}]
prior=snapshots[-1]
payload={**timer,**{name:(ROOT/name).read_bytes() for name in CHANGED}}
config=prior['00_SYSTEM/PIPELINE.json'].decode()
required={}
manifests=[]
for entry in json.loads(config)['engines'].values():
    name=entry['manifest'];m=json.loads(prior[name])
    if not set(CHANGED)&set(m['files']):continue
    for source in set(CHANGED)&set(m['files']):m['files'][source]=sha(payload[source])
    raw=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode()
    payload[name]=raw;manifests.append(name)
    config=config.replace('"'+entry['sha256']+'"','"'+sha(raw)+'"')
    required.update(m['files'])
payload['00_SYSTEM/PIPELINE.json']=config.encode()
required={name:digest for name,digest in required.items() if name not in payload}
assert all(sha(prior[name])==digest for name,digest in required.items())
rows=[{'path':name,'sha256':sha(raw),'bytes':len(raw),
       'allowed_predecessors':sorted({sha(s[name]) for s in snapshots if name in s}),
       'allow_missing_predecessor':name not in base} for name,raw in sorted(payload.items())]
manifest={'format':'8agent-code/1','id':NAME,'parent_code_zip_sha256':sha(TIMER.read_bytes()),
    'scope':'v6 direct guidance before command replay; preserve timeout removal, NFS SQLite, compact reader and all data',
    'files':rows,'required_files':[{'path':name,'sha256':digest} for name,digest in sorted(required.items())]}
archive=OUT/(NAME+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name,raw in sorted(payload.items()):
        assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        z.writestr(name,raw)
    z.writestr('CODE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(OUT/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
script=(OLD/'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1_APPLY.txt').read_text().replace(
    'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1',NAME)
script=script.replace('source-recall-timeout-logs','source-recall-routing-r2-logs')
script=re.sub(r"if sha\(archive\)!='[0-9a-f]{64}'","if sha(archive)!='"+sha(archive.read_bytes())+"'",script)
(OUT/(NAME+'_APPLY.txt')).write_text(script)
for name,raw in payload.items():
    target=DEPLOY/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
before=OUT/'before-working';receipts=[]
config=(ROOT/'00_SYSTEM/PIPELINE.json').read_text()
for entry in json.loads(config)['engines'].values():
    path=ROOT/entry['manifest'];old=path.read_bytes();m=json.loads(old)
    if not set(CHANGED)&set(m['files']):continue
    backup=before/entry['manifest'];backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():backup.write_bytes(old)
    for source in set(CHANGED)&set(m['files']):m['files'][source]=sha(payload[source])
    raw=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode();path.write_bytes(raw)
    config=config.replace('"'+entry['sha256']+'"','"'+sha(raw)+'"')
    receipts.append({'manifest':entry['manifest'],'before':sha(old),'after':sha(raw)})
backup=before/'00_SYSTEM/PIPELINE.json';backup.parent.mkdir(parents=True,exist_ok=True)
if not backup.exists():backup.write_bytes((ROOT/'00_SYSTEM/PIPELINE.json').read_bytes())
(ROOT/'00_SYSTEM/PIPELINE.json').write_text(config)
(OUT/'WORKING_PIN_RECEIPT.json').write_text(json.dumps(receipts,indent=2)+'\n')
(OUT/'HANDOFF.json').write_text(json.dumps({
    'code_zip_sha256':sha(archive.read_bytes()),'code_manifest_sha256':sha((OUT/'CODE_MANIFEST.json').read_bytes()),
    'apply_txt_sha256':sha((OUT/(NAME+'_APPLY.txt')).read_bytes()),'deployment_checkout':str(DEPLOY),
    'changed_source':CHANGED,'code_files':len(payload),'required_files':len(required),
    'compact_reader_sha256':required['02_BACKEND/semantic_runtime/full_glossary.py'],
    'generation_candidate':'/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation',
    'generation_manifest_sha256':None,'field_commit':None,'field_revision':None,'genos_deployed':False,
    'routing_changed':True,'source_recall_timers_removed':[120,180],'whole_request_deadline_removed':False
},ensure_ascii=False,indent=2)+'\n')
print('Built cumulative routing R2:',len(payload),'files,',len(required),'unchanged pins')
