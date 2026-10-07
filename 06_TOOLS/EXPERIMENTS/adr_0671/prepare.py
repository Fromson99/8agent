from pathlib import Path
import json,hashlib,sys,shutil,importlib.util
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0671-persistent-investigation-chain'
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((A/'실험/manifest.json').read_text());arm='investigation-chain'
changes='Persistent append-only action/selection chain and immutable menus for every search/law/read/reference point; RETURN_TO restores original menu/query/page with current decisions intact. Current-window candidates, adopted evidence ledger, scoped reference menus, multi-article reads. No answer hints, original grounding/ACL/repair guards preserved.'
m['lineage']['hypothesis_delta']=changes
m['design'].update(hypothesis='Restorable menus plus the full explicit action/selection chain let the model revisit any prior decision point without forgetting later judgments, while current-window context avoids repeated deferred payloads.',primary_metric='Return-to-search/read/reference exact menu restoration and no judgment/history rollback; both natural public API requests complete.',success_criteria='All affected grounding/ownership/retry/native API contracts and new restoration/resume/multi-read contracts pass. Both fresh questions return HTTP200 complete; each later SELECT/reference input retains all prior executed action reasons. Original provider transcripts and source binding retained.',failure_criteria='History loss, rewind of acquired/adopted state, invalid or invented historical target, incomplete original adoption, leaked scope, unbounded corrective loop or API failure.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':arm,'role':'candidate','derived_from':['ADR-0670-experiment-v1/public-schema-adapter'],'changes':changes,'controls':'Same exact parent frozen code/public145 data/model policy; natural venture then accounting; output6400/40calls/1800sec. Archived ADR0668 full natural runs are descriptive historical comparator, not a concurrent matched control.'}]
m['design']['retrieval_stage_plan']['stages_by_arm']={arm:[{'stage_id':k,'kind':kind,'parent_stage_ids':[] if i==0 else [['source','recall','select','present'][i-1]]} for i,(k,kind) in enumerate([('source','source'),('recall','retrieve'),('select','select'),('present','present')])]}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
dataset=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0668-selection-provider-anyof/artifacts/design/dataset.json').read_text());put(A/'artifacts/design/dataset.json',dataset)
m['dataset'].update(name='Two user supplied public legal questions, unchanged',version=dataset['source_generation'],frozen_source=str((A/'artifacts/design/dataset.json').relative_to(R)),sha256=sha(A/'artifacts/design/dataset.json'))
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':[arm],'selection_rule':'Fresh natural venture first then accounting. No forced backtracking or legal answer/coordinates injected. Restoration separately tested through synthetic contracts.','status':'planned','artifact_path':str((A/'artifacts/run-001/results.json').relative_to(R)),'sha256':'PENDING'}]
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/stage-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m);put(A/'artifacts/design/preimplementation-design.json',{'design':m['design'],'dataset':m['dataset'],'runs':m['runs'],'lineage':m['lineage'],'model':m['llm_policy']})
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
spec=importlib.util.spec_from_file_location('candidate_tools',R/'06_TOOLS/COMMANDS/adr_candidate.py');ac=importlib.util.module_from_spec(spec);spec.loader.exec_module(ac)
p=R/'02_BACKEND/lawrag/research/candidates/adr_0670/public-schema-adapter';pm=json.loads((p/'candidate.json').read_text());parent=p/'revisions/rev-001/snapshot'
present=[x['target_path'] for x in pm['files'] if (R/x['target_path']).is_file()]
c=ac.snapshot(A,arm,present,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
for row in pm['files']:
 target=row['target_path'];dest=c/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/target,dest)
 if target not in present:ac.register_file(c,target,upstream_state='absent')
for name,src in [('run_probe.py','adr_0668'),('summarize_probe.py','adr_0668'),('run_contracts.py','adr_0670')]:
 text=(R/f'06_TOOLS/EXPERIMENTS/{src}/{name}').read_text().replace('ADR-0668-selection-provider-anyof','ADR-0671-persistent-investigation-chain').replace('adr0668','adr0671').replace('adr_0670/public-schema-adapter','adr_0671/investigation-chain')
 if name=='run_probe.py':
  text=text.replace('from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport','from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport, provider_request').replace('client.chat_completions(body,','client.chat_completions(provider_request(body),')
 if name=='run_contracts.py':text=text.replace("files=['", "files=['test_investigation_chain_adr0671.py','")
 (R/f'06_TOOLS/EXPERIMENTS/adr_0671/{name}').write_text(text)
print(c)
