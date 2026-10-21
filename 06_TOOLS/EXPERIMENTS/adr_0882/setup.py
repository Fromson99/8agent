from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract';D=A/'artifacts/design';D.mkdir(exist_ok=True)
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
criteria={'hypothesis':'Separate condition leaves from a bounded Boolean expression and restore exact canonical trees; mechanically bind exact request quotes and kind-implied gap fields, preserve all verified original context and MAIN85.',
 'success':['No ambiguity between condition group position and leaf index; exact operator/text/evidence preservation and full canonical revalidation','Ordinary scoped RAG uses existing exact whole-request host quote binding, no paraphrase recovery loop','MISSING_FACT carries null legal-material ID and empty legal locator by schema; source gaps cannot ask for user facts','Repair feedback includes actual rejected wire proposal and concrete structural error','Existing bounded read choice and verified retained originals continue through actual service, with unchanged total budget/ACL/hash/state guards'],
 'failure':['Ambiguous condition inference or silently deleted source/fact/condition','Invalid original, unauthorized source or budget/reset/duplicate regression','Lost MAIN85 code; new structural failures from deterministic reconstruction'],
 'design':['condition_tree wire is null or {leaves:[{text,evidence_refs}],expression:string}. Human-readable1-based leaf positions and ALL/ANY/UNKNOWN operators; max canonical depth3/fanout8; all leaves used, no unknown token, max585leaves/4096expression chars','Restore existing v8 canonical tree without changing any connective. Invalid expression includes raw proposal and precise error in existing one-correction path','Use existing bind_task_quotes for every scoped request; exact complete admitted user input is host-owned, issue meaning remains model-proposed','Each gap kind has its own schema branch. MISSING_FACT fixes material_id=null,missing_target=empty,suggested_action=REQUEST_FACT. Other kinds retain source selection, cannot REQUEST_FACT. GENERAL_RULE facts remain empty','READ_ARTICLES shared path includes initial definition reads and later model reads. Only actually delivered non-deferred/non-excluded pages can be retained;50k-character context bound, no automatic adoption or source expansion'],
 'limits':{'calls_per_case':40,'wall_seconds':1800,'concurrency':1,'rss_gib':8,'as_gib':9},
 'evaluation':'Same registered CM five once each; known probe not legal holdout. Independent finite technical qualification before MAIN. Detailed semantic errors remain explicit and do not automatically block under user policy.',
 'resource_policy':'Serial heavy workers, shared read-only generation, no original-data clone, hash-verified compressed raw archives'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','expressions','--experiment-id','ADR-0882-experiment-v1','--arm-id','expressions','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact requested original reading, completed useful answer, no diagnostic generation loop',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'expressions','role':'candidate','derived_from':['ADR-0881-experiment-v1/retained'],'changes':criteria['design'],'controls':'Same MAIN85 data, five original CM questions, model/profile40/1800 unchanged; no reference answer in product'}]
m['runs'][0].update(arm_ids=['expressions'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':200}]
m['dataset'].update(name='CM51 registered five known cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'expressions':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN85 preserved; prospective criteria and isolated snapshot ready')
