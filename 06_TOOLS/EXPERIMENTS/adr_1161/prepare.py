from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1161-cm3-focused-qwen';D=A/'artifacts/design';S=Path(__file__).parent;P=R/'04_EXPERIMENTS/ADR/ADR-1155-investigation-focus-offline';O=R/'06_TOOLS/EXPERIMENTS/adr_1151'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
(S/'common.py').write_text((O/'common.py').read_text().replace('ADR-1151-main109-cm51-qwen','ADR-1161-cm3-focused-qwen'))
shutil.copyfile(O/'cm_authorization.py',S/'cm_authorization.py')
old=R/'04_EXPERIMENTS/ADR/ADR-1151-main109-cm51-qwen/artifacts/design'
cases=[c for c in read(old/'cases.json') if c['id'] in ('cm-001','cm-007','cm-009')];put(D/'cases.json',cases)
for n in ['corpus.json']:put(D/n,read(old/n))
auth=read(old/'authorization.json');auth.update(user_request='cm실패했던 질문들 다시 실행해봐 3개정도',max_model_calls=120,scope='Only cm001/007/009, isolated unchanged ADR1155 rev002; no batch resume');auth['case_question_sha256']={c['id']:hashlib.sha256(c['request']['json']['question'].encode()).hexdigest() for c in cases};put(D/'authorization.json',auth)
base=read(P/'artifacts/design/baseline.json');base['active_at_live']=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');put(D/'baseline.json',base)
refs=read(R/'04_EXPERIMENTS/ADR/ADR-1151-main109-cm51-qwen/artifacts/evaluation-only/cases.json');put(A/'artifacts/evaluation-only/cases.json',[c for c in refs if c['id'] in {x['id'] for x in cases}])
criteria={'hypothesis':'Unchanged ADR1155 rev002 search retention/excerpts/progress/menu can finish known failed CM questions with original-backed actual claims.', 'success':['3 cases each dispatched once','Original spans and ACL exact; valid actual final claims; clarification alone not success','Track initial needed candidates, source reads, progress reviews and final claim use separately','No output token cap, provider fallback, reference leakage, active MAIN mutation'], 'failure':'Ordinary bounded product failure retained, continue next frozen case; integrity/resource/hash failure stops batch. Native40/1024/1800 unchanged. Max120 model calls total; no whole-case retries; no evaluator calls.', 'selection':'cm001 first HTTP422;cm007 final review failure and repeated investigation;cm009 interrupted selection drift. Known in-sample, historical MAIN109 not randomized concurrent baseline.', 'retrieval':'Record delivered candidate union -> original reads -> final citations on canonical article-root identities; raw visible menus retained per call; gold assessed only offline after all choices. Does not measure unreturned SQL pool.', 'quality':'Operational and source correctness audit only; no certified legal accuracy. Active MAIN111 differs from tested MAIN110-based candidate.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Original read through final claims, failure and call accounting for3known cases',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'focused','role':'candidate','derived_from':['ADR-1155-experiment-v1/focused'],'changes':'No further code change; live execution of rev002','controls':'Same data/ACL/model/budgets, one pass per question; no gold input'}],retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'focused':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
put(A/'실험/manifest.json',m)
f=read(P/'artifacts/design/freeze.json');parent=R/f['code_root'];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'focused',present,experiment_id=m['experiment_id'],arm_id='focused',run_ids=['run-001'])
for n,h in f['files'].items():
 assert sha(parent/n)==h
 out=C/'snapshot'/n;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(parent/n,out)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
ac.freeze(C);assert not ac.validate(C)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
# Reuse audited transport and exact CM authorization; inject isolated app explicitly.
s=(O/'live.py').read_text().replace("arm='selected'","arm='focused'")
a=s.index("sys.path[:0]=");b=s.index('from cm_authorization import install')
setup=(R/'06_TOOLS/EXPERIMENTS/adr_1141/live.py').read_text();x=setup.index('sys.path[:0]=');y=setup.index('if setup:')
block=setup[x:y].replace("'MAIN107'","'MAIN110/ADR1155' ").replace("f['binding']","f['candidate_revision']")
block=block.replace('from semantic_runtime.app import create_app','from types import SimpleNamespace\nfrom semantic_runtime.app import create_app')
block=block.replace('from lawrag.research.experiment_client import','import lawrag\nlawrag.__path__.append(str(ROOT/\'02_BACKEND/lawrag\'))\nfrom lawrag.research.experiment_client import')
s=s[:a]+block+s[b:];s=s.replace('actual MAIN109, health200,440files','isolated ADR1155, health200,666files').replace("'selected MAIN109 service.service; exact user-authorized CM experiment host grant'","'isolated MAIN110-based ADR1155 candidate HTTP; exact CM grant'").replace("'app_injected':False","'app_injected':True")
(S/'live.py').write_text(s)
b=(O/'batch.py').read_text().replace('==51','==3').replace("'total':51","'total':3").replace("'cases':51","'cases':3").replace("'/51'","'/3'").replace('ALL51 COMPLETE','ALL3 COMPLETE');(S/'batch.py').write_text(b)
s=(O/'summarize.py').read_text().replace("'total':51","'total':3").replace("'MAIN':109","'MAIN':'isolated ADR1155 (MAIN110 base)' ").replace('MAIN109 CM51 Qwen 전체 실행 결과','ADR1161 CM3 Qwen 수정본 실행 결과').replace('제품코드·모델·프로필·데이터·예산은 변경하지 않았다.','ADR1155 수정본을 실행했고 모델·데이터·예산은 유지했다.');(S/'summarize.py').write_text(s)
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'focused','arm_id':'focused','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((S/'live.py').relative_to(R)),'runner_sha256':sha(S/'live.py')}]);m['dataset'].update(name='Known failed CM001/007/009',version='registry-v2-risk_cm CM approved',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False);m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}];m['runs'][0].update(arm_ids=['focused'],purpose='primary',selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None);put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'code_root':str(code.relative_to(R)),'files':f['files'],'candidate_revision':rev,'inputs':{str(p.relative_to(R)):sha(p) for p in D.glob('*.json')},'scripts':{str(p.relative_to(R)):sha(p) for p in S.glob('*.py')},'client_sha256':sha(R/'02_BACKEND/lawrag/research/experiment_client.py'),'model_calls':0})
print('Frozen3cases, exact parent666files; native40call cap each; zero calls so far')
