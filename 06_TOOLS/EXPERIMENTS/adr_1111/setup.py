from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1111-genos-mode-scope-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-1109-genos-mode-admission-main';C=R/'02_BACKEND/lawrag/research/candidates/adr_1111/mode-scope-r1';PC=R/'02_BACKEND/lawrag/research/candidates/adr_1109/mode-admission-r1';S=A/'artifacts/staged-code';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria=json.loads((P/'artifacts/design/criteria.json').read_text());criteria['validation_correction']='Observe exact authorized category document set at real UnifiedRag.open; final citations must be a nonempty permitted subset, because model selects evidence. Compare principal document IDs as a set. No product edits. Existing regression failures compared on immutable MAIN106.';put(D/'criteria.json',criteria)
m=json.loads((P/'실험/manifest.json').read_text());scaffold=json.loads((A/'실험/manifest.json').read_text())
for k in ('adr_id','experiment_id','reservation','lineage','relationships'):m[k]=scaffold[k]
m['design']['hypothesis']+=' Scope observation corrected, no product edits.';m['design']['code_isolation']['candidates']=[]
m['results'].update(status='not_run',by_arm={},error_taxonomy=[]);m['runs'][0].update(status='planned',artifact_path='TODO',sha256='PENDING');m['runs'][0].pop('success_criteria_met',None)
m['dataset'].update(frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));put(A/'실험/manifest.json',m)
base=json.loads((P/'artifacts/design/baseline.json').read_text());put(D/'baseline.json',base)
files=[x['target_path'] for x in json.loads((PC/'candidate.json').read_text())['files']]
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--experiment-id',m['experiment_id'],'--candidate-id','mode-scope-r1','--arm-id','integrated','--run-id','run-001']
for n in files:cmd+=['--source',n]
subprocess.run(cmd,check=True,cwd=R)
for n in files:shutil.copyfile(PC/'revisions/rev-001/snapshot'/n,C/'snapshot'/n)
staging=json.loads((P/'artifacts/design/staging.json').read_text())
for n,h in staging['files'].items():
 src=P/'artifacts/staged-code'/n;assert sha(src)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,p)
(S/'01_DATA').symlink_to(R/'01_DATA',target_is_directory=True);staging['code_root']=str(S.relative_to(R));put(D/'staging.json',staging)
r=Path(__file__).parent/'run_tests.py';runner=(R/'06_TOOLS/EXPERIMENTS/adr_1109/run_tests.py').read_text().replace('ADR-1109-genos-mode-admission-main','ADR-1111-genos-mode-scope-qualification');r.write_text(runner)
p=R/'05_TESTS/CONTRACTS/test_genos_applied_mode.py';s=p.read_text();s=s.replace("    gid=None\n", """    from semantic_runtime.legal_agent.unified_rag import UnifiedRag
    original_open=UnifiedRag.open;opened=[]
    def observe_open(self,state,principal,body):
        opened.append({'category':state['source_category'],'documents':set(self.documents(state,principal))})
        return original_open(self,state,principal,body)
    monkeypatch.setattr(UnifiedRag,'open',observe_open)
    gid=None
""");s=s.replace("        assert {x['document_id'] for x in answer['assembly']['context']}==expected,answer", "        assert opened[-1]['documents']==expected,opened\n        assert opened[-1]['category']==['internal','external','ALL'][n]\n        assert set() < {x['document_id'] for x in answer['assembly']['context']} <= expected,answer")
s=s.replace("assert seen[0][1]['document_ids']==['internal','external']","assert set(seen[0][1]['document_ids'])=={'internal','external'}");p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,cwd=R)
c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1];b={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(D/'freeze.json',{'candidate':b,'runner':{'path':str(r.relative_to(R)),'sha256':sha(r)},'test':{'path':str(p.relative_to(R)),'sha256':sha(p)}})
m['design']['code_isolation']['candidates']=[{**b,'candidate_id':c['candidate_id'],'arm_id':'integrated','experiment_id':c['experiment_id'],'run_ids':['run-001'],'runner_path':str(r.relative_to(R)),'runner_sha256':sha(r)}];put(A/'실험/manifest.json',m)
print('Frozen identical product bytes; actual scope oracle')
