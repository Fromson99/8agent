from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0881-retained-original-flat-conditions';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==85
release=read(R/pointer['manifest_path']);assert all(sha(R/n)==h for n,h in release['files'].items())
put(D/'baseline.json',dict(pointer=pointer,pointer_sha256=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),release=release))
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0876/scoped/candidate.json')
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']})
for n in ('cases.json','offline-reference.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0878-main85-cm-registered-live/artifacts/design'/n,D/n)
criteria={'hypothesis':'Retain exact model-requested delivered originals across navigation and into assessment; generate bounded flat condition nodes and reconstruct the same canonical nested contract; no redundant control diagnostics or general-rule facts.',
 'success':['Requested original pages remain available after navigating to another source within bounded context','Model READ/FINISH/EXPLORE semantic choice and all MAIN85 integration preserved','Flat conditions restore exact AND/OR/UNKNOWN and source references, reject cycles/unreachable/too-deep/foreign nodes','GENERAL_RULE fact_refs is host-owned empty; case application still cites actual user facts','Same CM5 actual calls; no original/ACL/hash/state/budget regression; legal imperfections explicitly recorded'],
 'failure':['Fabricated original, altered connective or silently discarded semantic node','Budget/retry reset, cross-scope retained original, stale or excluded source revived','Lost MAIN85 changes'],
 'design':['Retain only previously presented exact pages from model-requested READ_ARTICLES; track ordered group IDs in durable state; verify page identity/receipt/scope; omit entire excess pages with explicit metadata when half-context character budget exceeded','Final assessment receives all exact non-deferred/non-excluded model-requested delivered pages as available context, distinct from answer adoption; final claims still independently select and validate evidence','Wire condition_tree becomes null or flat ordered nodes: leaf text/evidence or ALL/ANY/UNKNOWN with earlier node indexes, final node is root. All nodes must be reachable, children unique, max depth3 and fanout8; host restores canonical tree without legal inference','General-rule branch requires empty fact_refs, model selects rule kind; compact prompt explicitly separates general rule from user-case application','Existing four read-review cap,40modelcalls1800s, finalization reserve and one correction owner unchanged'],
 'limits':{'calls_per_case':40,'wall_seconds':1800,'concurrency':1,'rss_gib':8,'as_gib':9},
 'evaluation':'Known five CM questions once each versus completed0878/0880; not holdout. New independent finite software qualification required before MAIN. No gold enters product.',
 'resource_policy':'Read-only shared generation and serial workers; compact code snapshots; byte-verified raw archives after audit'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','retained','--experiment-id','ADR-0881-experiment-v1','--arm-id','retained','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact requested original reading, completed useful answer, no diagnostic generation loop',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'retained','role':'candidate','derived_from':['ADR-0879-experiment-v1/retained'],'changes':criteria['design'],'controls':'Same MAIN85 data, five original CM questions, model/profile40/1800 unchanged; no reference answer in product'}]
m['runs'][0].update(arm_ids=['retained'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':200}]
m['dataset'].update(name='CM51 registered five known cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'retained':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN85 preserved; prospective criteria and isolated snapshot ready')
