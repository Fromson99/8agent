from pathlib import Path
import json,sys,shutil,hashlib
ROOT=Path(__file__).resolve().parents[3];P=ROOT/'04_EXPERIMENTS/ADR/ADR-1158-ontology-workflow-consumer-check';A=ROOT/'04_EXPERIMENTS/ADR/ADR-1159-ontology-workflow-ready';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1158').glob('*.py'):
 if p.name in ('setup.py','finish_failure.py','add_delivery.py'):continue
 s=p.read_text().replace('ADR-1158-ontology-workflow-consumer-check','ADR-1159-ontology-workflow-ready').replace('adr_1158','adr_1159')
 (T/p.name).write_text(s)
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
for name in ('baseline.json','criteria.json','test-support.json','api-sources.json'):shutil.copyfile(P/'artifacts/design'/name,D/name)
criteria=read(D/'criteria.json');criteria['hypothesis']='Skip authoring capture until accepted judgments exist; validate actual judged-source capture, same lifecycle, native453-file consumer, UI, Dataiku ingest and running isolated Oracle.';put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for k in ('design','dataset','retrieval_accounting'):m[k]=old[k]
m['design']['code_isolation']['candidates']=[];m['design']['hypothesis']=criteria['hypothesis'];m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0]['derived_from']=['ADR-1158-experiment-v1/connected'];m['design']['arms'][1]['changes']='Repair test variables/import path; existing UI connected-state text; Dataiku ingestion adapter. Same runtime behavior.'
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(ROOT)),sha256=sha(D/'criteria.json'),version='1159-v1')
m['runs'][0].update(arm_ids=['connected'],selection_rule='Prior19workflow+216regression+4DBHTTP and realUI; Oracle/delivery/capture checks as prospectively specified',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(ROOT)));m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m)
f=read(P/'artifacts/design/freeze.json');sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'connected-r1',[n for n in f['files'] if (ROOT/n).is_file()],experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,dst)
 if not (ROOT/n).exists():ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/ontology_work/capture.py';s=p.read_text().replace("    try:\n        work=capture(inv,", "    if not any(state.get('heads') for state in inv.p.get('read_judgments',{}).values()):return\n    try:\n        work=capture(inv,")
p.write_text(s)
p=T/'test_database_native.py';s=p.read_text();a=s.index("        if mode=='normal':\n            captured=[]");b=s.index("        catalogs=[v for v in t.views",a);s=s[:a]+s[b:];p.write_text(s)
# Capture the parent fixture that actually submits source judgments.
p=T/'test_capture.py';p.write_text("""import json,sqlite3

def test_accepted_agent_judgments_export_to_work(tmp_path,term_glossary,monkeypatch):
    from test_native_integrated import test_read_judgment_api_retains_decisions_and_reuses_request
    monkeypatch.setenv('GENOS_ONTOLOGY_CAPTURE_ENABLED','on')
    test_read_judgment_api_retains_decisions_and_reuses_request(tmp_path,term_glossary,'normal',monkeypatch)
    captured=[];failed=[]
    for path in tmp_path.rglob('*.sqlite'):
        with sqlite3.connect(path) as db:
            if 'payload_json' not in [r[1] for r in db.execute('PRAGMA table_info(event)')]:continue
            captured.extend(json.loads(r[0]) for r in db.execute(\"SELECT payload_json FROM event WHERE kind='ONTOLOGY_WORK_INPUT'\"))
            failed.extend(json.loads(r[0]) for r in db.execute(\"SELECT payload_json FROM event WHERE kind='ONTOLOGY_WORK_CAPTURE_UNAVAILABLE'\"))
    assert captured,failed
    assert all(r['input']['judgments'] and r['input']['originals'] for r in captured)
    assert all(not r['automatic_approval'] for r in captured)
    assert not failed,failed
""")
p=T/'check.py';s=p.read_text().replace("'database','ui')","'database','ui','capture')").replace("'ui':['test_ui.py']}","'ui':['test_ui.py'],'capture':['test_capture.py']}");p.write_text(s)
# Refresh pins after capture guard change.
pipe=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipe['engines'].values():
 p=S/ref['manifest'];e=read(p)
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipe)
print('Prepared1159 capture guard and actual judgment fixture')
