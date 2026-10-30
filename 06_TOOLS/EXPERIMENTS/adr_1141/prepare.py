from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];H=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1141-exact-gap-progress';P=R/'04_EXPERIMENTS/ADR/ADR-1140-final-recovery-native-contract';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
m.update(in_sample=True,decision_eligible=False,design=old['design'],dataset=old['dataset'],retrieval_accounting=old['retrieval_accounting']);m['design']['code_isolation']['candidates']=[]
m['design']['hypothesis']='A first exact missing-source lookup is progress; final-review rejection cannot consume this bounded chance. Repeated exact target, source/evidence/ACL failures and request budgets remain enforced.'
m['design']['success_criteria']=['Native API: rejected final review twice, independent second source read, real claim and answer, cached repeat without new calls','No rejection adopted; same target/restart, budget/deadline/authorization and scope guards','All prior technical contracts unchanged','Known public privacy question reaches originals and final answer']
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1140-experiment-v1/repaired'],'changes':'Historical1140','controls':'Same data/model/budget'},{'id':'repaired','role':'candidate','derived_from':['baseline'],'changes':'Record new exact-source lookup progress after rejected final review','controls':'Existing correction/reentry/call/tool/time limits'}]
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['repaired'],'selection_rule':'All frozen technical contracts','status':'planned','artifact_path':'not_run','sha256':'0'*64},{'id':'run-002','purpose':'primary','parent_run_id':'run-001','arm_ids':['repaired'],'selection_rule':'Known public question once after contracts pass','status':'planned','artifact_path':'not_run','sha256':'0'*64}];put(A/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
absent=[n for n in f['files'] if not (R/n).exists()];C=ac.snapshot(A,'repaired-r1',[n for n in f['files'] if n not in absent],experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
for n in absent:ac.register_file(C,n,upstream_state='absent')
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1140').glob('*.py'):
 if p.name in ('setup.py','prepare.py'):continue
 (H/p.name).write_text(p.read_text().replace(P.name,A.name).replace('adr_1140','adr_1141'))
for p in (P/'artifacts/design').glob('*.json'):
 if p.name!='freeze.json':shutil.copyfile(p,D/p.name)
put(D/'criteria.json',{'hypothesis':m['design']['hypothesis'],'criteria':m['design']['success_criteria'],'progress_rule':'Only first independently verified exact missing-source target, preserve signature receipt and all request budgets. Historical navigation no_progress stored on receipt; new bounded target investigation starts at zero. No claims or rejected opinions committed.','out_of_sample':False})
p=S/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py';t=p.read_text().replace("            or execution.s.context.remaining() <= policy['selection_time_reserve_seconds']\n            or investigation.get('no_progress',0) >= policy['max_no_progress']):","            or execution.s.context.remaining() <= policy['selection_time_reserve_seconds']):")
t=t.replace("    checkpoint.setdefault('final_review_recovery', []).append(receipt)","    receipt['previous_no_progress'] = checkpoint.get('no_progress', 0)\n    checkpoint.setdefault('final_review_recovery', []).append(receipt)\n    # A first exact lookup of an unread target is concrete progress. A repeated\n    # target with the same originals was rejected above; request budgets survive.\n    checkpoint['no_progress'] = 0\n    checkpoint.setdefault('request_progress', []).append('verified-gap-lookup:' + signature)")
p.write_text(t)
p=H/'test_recovery_limits.py';t=p.read_text().replace("'counter','no_progress','fact'","'counter','fact'").replace("    if guard=='no_progress':a['investigation']['no_progress']=3\n",'');t=t.replace("h,e,v,s,a,c,events,b=fixture(monkeypatch);before=deepcopy(v)","h,e,v,s,a,c,events,b=fixture(monkeypatch);before=deepcopy(v)\n    a['investigation']['no_progress']=3")
t=t.replace("    payload=result.value.payload","    payload=result.value.payload\n    assert payload['investigation_state']['no_progress']==0\n    assert payload['investigation_state']['final_review_recovery'][0]['previous_no_progress']==3")
p.write_text(t)
print(S)
