from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0880-compact-read-or-finish';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==85
release=read(R/pointer['manifest_path']);assert all(sha(R/n)==h for n,h in release['files'].items())
put(D/'baseline.json',dict(pointer=pointer,pointer_sha256=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),release=release))
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0876/scoped/candidate.json')
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']})
for n in ('cases.json','offline-reference.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0878-main85-cm-registered-live/artifacts/design'/n,D/n)
criteria={'hypothesis':'Compact model choice reads requested bodies despite peripheral originals, or finishes on selected delivered sources; minimal assessment preserves content once.', 'success':['Same five registered CM cases get requested originals or explicit bounded unavailable outcomes','No source-free model termination without examining offered readable choices','No repeating assessment diagnostic fields or completion length failure','Exact original/ACL/hash/state/budgets and MAIN85 changes retained'], 'failure':['Wrong or fabricated original/authority','Budget reset, duplicate execution or unbounded extra model retry','Lost MAIN85 changes'], 'design':['Read-choice uses model relevance selection, only presently offered READ_ARTICLES, no gold or legal inference by host; maximum four reviews per request, max four targets per review, review even when peripheral originals were delivered; model may select FINISH with exact delivered basis or EXPLORE with concrete reason; all semantic choices remain model-owned','Read choice has one existing bounded correction owner; all calls share 40attempt1800s deadline, finalization reserve and durable state','Modern assessment wire removes redundant disposition and issue diagnostic reasons; model still chooses issue coverage, claims, material gaps. Host derives disposition/reasons deterministically; retains exact evidence checks and one structural correction','One exploration row maximum for single-target/single-issue actions, no semantic merging or deleted rationale'], 'limits':{'calls_per_case':40,'wall_seconds':1800,'concurrency':1,'rss_gib':8,'as_gib':9}, 'evaluation':'Known CM001/003/008/033/051 probe versus completed0878; not holdout. New independent finite boundary qualification before promotion; legal semantic imperfections reported separately.', 'resource_policy':'Shared read-only generation; no dataset copy; serial heavy workers, lossless raw archive after audit'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','focused','--experiment-id','ADR-0880-experiment-v1','--arm-id','focused','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact requested original reading, completed useful answer, no diagnostic generation loop',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'focused','role':'candidate','derived_from':['ADR-0879-experiment-v1/focused'],'changes':criteria['design'],'controls':'Same MAIN85 data, five original CM questions, model/profile40/1800 unchanged; no reference answer in product'}]
m['runs'][0].update(arm_ids=['focused'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':200}]
m['dataset'].update(name='CM51 registered five known cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'focused':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN85 preserved; prospective criteria and isolated snapshot ready')
