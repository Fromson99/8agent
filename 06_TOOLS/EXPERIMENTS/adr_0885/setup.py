from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0885-coherent-navigation-fact-provenance';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==86
release=read(R/pointer['manifest_path']);assert all(sha(R/n)==h for n,h in release['files'].items())
put(D/'baseline.json',dict(pointer=pointer,pointer_sha256=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),release=release))
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0876/scoped/candidate.json')
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']})
cases=read(R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract/artifacts/design/cases.json')
refs=read(R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract/artifacts/design/offline-reference.json')
registered=read(R/'01_DATA/review/cm_core_e2e_v3.json')['cases']
for cid in ('cm-011','cm-022','cm-038'):
 c=next(c for c in registered if c['id']==cid)
 cases.append({'id':cid,'question':c['question'],'api_type':'RAG_ASK','new_call_limit':40})
 refs.append({'id':cid,'reference_answer':c['reference_answer'],'targets':c['evidence_articles']+c.get('required_companions',[])})
put(D/'cases.json',cases);put(D/'offline-reference.json',refs)
criteria={'hypothesis':'One compact decision selects an executable available tool or finishes from originals; removing unsupported EXPLORE handoff avoids contradictory second opinions. No admitted facts means raw question is not case fact evidence.',
'success':['Same frozen eight CM51 questions each run once serially through actual service; all outcomes and source spans audited','CM008 original subject and extension direction preserved; CM003 exclusion vs applicability separated; CM051 delegated calculation read and explained','No neutral exploration loop: each compact model action dispatches the selected canonical tool; read/finish/ACL/hash/state/replay/global budgets preserved','No CASE_APPLICATION backed only by question when admitted state facts empty; question remains in current_request and issue scope','No loss of MAIN86 workflow/compression/basis/Oracle and no new resource ceiling'],
'failure':['Unresolved targeted failure remains explicit, never counted fixed','Citation/source/access/hash/state corruption or lost current MAIN changes','Duplicate external calls on resume or budget reset'],
'design':['Replace compact EXPLORE with model-selected existing tools, including typed structure lookup and pagination/return; preserve read batching and current source provenance. Up to8compact reviews within same40calls/1800seconds','Read candidate menu remains8; no change to BM25 index/order or data generation','When admitted facts empty, modern user_fact_sources is empty rather than U0wholequestion; constrain rule kind to GENERAL_RULE when fact_refs has maxItems0. MISSING_FACT remains available for genuine missing facts; current_request stays visible','Retain parent completeness guidance; explicit incomplete sources and judgment uncertainty do not become new hard stopping checks'],
'limits':{'calls_per_case':40,'wall_seconds':1800,'concurrency':1,'rss_gib':8,'as_gib':9},
'evaluation':'Eight known/additional historically exposed CM51 cases from0884 unchanged, not unseen legal holdout. Prior886baseline and rejected884 descriptive only. Independent finite qualification before MAIN; exact legal detail errors recorded separately.',
'resource_policy':'One8GiBworker, shared read-only generation, allocator trimming instrumentation, lossless compressed raw outputs'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','coherent','--experiment-id','ADR-0885-experiment-v1','--arm-id','coherent','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0884-focused-search-complete-answer/artifacts/design/freeze.json');PC=R/parent['code_root']
C=R/'02_BACKEND/lawrag/research/candidates/adr_0885/coherent/snapshot'
for n,h in read(R/'04_EXPERIMENTS/ADR/ADR-0884-focused-search-complete-answer/artifacts/design/working-before.json').items():
 if sha(PC/n)!=h:(C/n).write_bytes((PC/n).read_bytes())
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact requested original reading, completed useful answer, no diagnostic generation loop',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'coherent','role':'candidate','derived_from':['ADR-0884-experiment-v1/focused'],'changes':criteria['design'],'controls':'Same MAIN86 data, eight original CM questions, model/profile40/1800 unchanged; no reference answer in product'}]
m['runs'][0].update(arm_ids=['coherent'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':320}]
m['dataset'].update(name='CM51 five known and three additional cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'coherent':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN86 preserved; prospective criteria and isolated snapshot ready')
