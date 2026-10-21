from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0884-focused-search-complete-answer';D=A/'artifacts/design';D.mkdir(exist_ok=True)
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
criteria={'hypothesis':'Carry the exact requested subject and unmet need into compact search/reference actions; judge completeness from operative conditions, exceptions and formulas in original text, preserving MAIN86.',
'success':['All eight original questions run sequentially through frozen actual service; every outcome and citation audited','CM008 reaches correct subject-specific original and returns a useful response; CM003 connects operative exclusion to classification; CM051 reads and explains delegated calculation','Existing CM001/033 and additional CM011/022/038 retain exact evidence, user scope, side/version/ACL/hash/state and bounded recovery','Compact exploration executes exactly the model-selected available action; it does not discard the unmet need for a second independent decision'],
'failure':['Unauthorized or fabricated evidence, lost recent MAIN code, stale/replay/budget regression','Core targeted issues remain unresolved: preserve as followup, do not call defect fixed'],
'design':['Compact choice gains model-controlled SEARCH and CONNECT mapped to existing canonical tools and budget; retain exact issue/source provenance and journal','Subject/action and requested rule vs case application stay explicit; formula/exception delegation needs operative original rather than bare citation, general rules do not require individual facts','Expose up to8article candidates per document as existing normal menu; scope, index, pagination and read budget remain unchanged'],
'limits':{'calls_per_case':40,'wall_seconds':1800,'concurrency':1,'rss_gib':8,'as_gib':9},
'evaluation':'Eight registered CM51 questions selected before gold review; five known regression cases and three additional historically exposed cases, not legal holdout. Compare with preserved MAIN86 run artifacts descriptively; no causal/randomized claim. New finite technical qualification required for promotion.',
'resource_policy':'Serial workers, shared immutable data; allocator trim only in test harness; hash-verified compressed raw logs'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','focused','--experiment-id','ADR-0884-experiment-v1','--arm-id','focused','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact requested original reading, completed useful answer, no diagnostic generation loop',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'focused','role':'candidate','derived_from':['ADR-0883-experiment-v1/qualified'],'changes':criteria['design'],'controls':'Same MAIN86 data, eight original CM questions, model/profile40/1800 unchanged; no reference answer in product'}]
m['runs'][0].update(arm_ids=['focused'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':320}]
m['dataset'].update(name='CM51 five known and three additional cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'focused':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN86 preserved; prospective criteria and isolated snapshot ready')
