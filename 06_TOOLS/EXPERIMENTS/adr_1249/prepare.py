from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1249-model-error-sqlite-retest';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==129
r=read(R/p['manifest_path']);C=R/r['code_root'];put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':r})
criteria={'hypothesis':'Preserve original transport deadline and unknown status; typed proposal/generic exceptions cannot trigger unrelated provider switch or mask the original cause. Then retry same public article369 once on SQLite.', 'success':['Injected timeout returns MODEL_DEADLINE_EXCEEDED/504 with UNKNOWN and cause/diagnostics preserved; no further physical calls','Generic errors remain UNKNOWN with original cause; proposal/contract errors remain FAILED; no provider switch except confirmed429','Native API error/state/failure logs agree; budgets and successful normal path preserved','One actual SQLite case completes final answer, saved reply and source/wire integrity checks; no crash/resource stop'], 'limits':{'physical_model_calls':40,'tool_actions':1024,'wall_seconds':1800,'per_model_seconds':180,'rss_GiB':4,'available_GiB':3,'swap_growth_MiB':128},'failure':'Preserve any failure; no same-case redispatch after actual model result; no masking of incomplete state','scope':'Current MAIN129 base plus gateway repair in isolated candidate; integrate verified minimal fixes to working files after tests. No selected MAIN promotion, no Oracle access, no ontology change; SQLite ontologyOFF. User explicitly authorized same public question/source and current external Qwen/Parasail routing in prior turn and asks repeat after repair.','quality':'Known question, no legal quality certification or DB-only A/B.'}
put(D/'criteria.json',criteria)
old=R/'04_EXPERIMENTS/ADR/ADR-1247-main128-sqlite-live-retest/artifacts/design'
for n in ('cases.json','corpus.json','authorization.json','explicit-user-approval.json'):
 v=read(old/n)
 if n=='cases.json':v[0]['request']['json'].update(session_id='adr1249-sqlite',request_id='repaired-sqlite-gold369')
 put(D/n,v)
put(D/'user-request.json',{'instruction':'실험 연결기랑 오류 처리부터 고치고 sqlite로 다시 실험해봐','prior_explicit_approval':str((old/'explicit-user-approval.json').relative_to(R))})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Failure contract correctness then actual SQLite completion',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1248-experiment-v1/selected'],'changes':'Current MAIN129; synthetic failure reproduction only','controls':'No fresh baseline model'}, {'id':'repaired','role':'candidate','derived_from':['baseline'],'changes':'Gateway exception branches, experiment transport cause and reserved-send adapter only','controls':'Same source scope/question/model/budgets; no prompt or search changes'}]
m['runs'][0].update(arm_ids=['repaired'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),selection_rule='Synthetic failures then same known public question once')
m['dataset'].update(name='Same public article369 one-document question',version='MAIN129 base/local SQLite',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='No retrieval implementation/effect comparison; source and actual wire audited; legal recall not measured.'
m['retrieval_accounting'].update(changed=False,corpus_total=1547,not_applicable_reason=reason,stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':reason})
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
sources=list(r['files'])+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py']
S=ac.snapshot(A,'repaired',sources,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])/'snapshot'
for n in r['files']:shutil.copyfile(C/n,S/n)
put(D/'working-before.json',{n:sha(R/n) for n in sources})
print('candidate',S,'sources',len(sources))
