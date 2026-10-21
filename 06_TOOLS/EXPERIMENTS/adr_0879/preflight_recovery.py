from pathlib import Path
import json,hashlib,copy
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0879-read-first-compact-assessment';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
s=(T/'live.py').read_text().replace("O = A/'artifacts/run-001'","O = A/'artifacts/run-002'")
(T/'live_v2.py').write_text(s)
s=(T/'run_all.py').read_text().replace("(cid+'.log')","('run002-'+cid+'.log')").replace("'resource-'+cid","'resource-run002-'+cid").replace("T/'live.py'","T/'live_v2.py'")
(T/'run_all_v2.py').write_text(s)
f=read(D/'freeze.json');f['files'].update({str(p.relative_to(R)):sha(p) for p in (T/'live_v2.py',T/'run_all_v2.py',Path(__file__))});f['runner_recovery']='Zero-model freeze filename preflight only; candidate rev001 unchanged';put(D/'freeze-v2.json',f)
pre=A/'artifacts/run-001/result.json';put(pre,{'status':'complete','outcome':'pre-model runner path error','model_calls':0,'candidate_loaded':False,'cause':'live.py expected freeze-v2.json which was not yet created','cases':['cm-001','cm-003','cm-008','cm-033','cm-051']})
m=read(A/'실험/manifest.json');run=copy.deepcopy(m['runs'][0]);m['runs'][0].update(status='complete',purpose='audit',sha256=sha(pre));run.update(run_id='run-002',artifact_path=str((A/'artifacts/run-002/result.json').relative_to(R)));run.pop('sha256',None);m['runs'].append(run);m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-002',artifact_path=str((A/'artifacts/run-002/retrieval-ledger.json').relative_to(R)))
m['design']['code_isolation']['candidates'][0]['run_ids'].append('run-002');put(A/'실험/manifest.json',m)
print('Preflight retained; physical model schedule and immutable product code unchanged')
