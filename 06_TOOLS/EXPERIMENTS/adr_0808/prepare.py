from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0808-workflow-mechanical-boundaries';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0807-nonblank-generation-grammar';T=R/'06_TOOLS/EXPERIMENTS/adr_0808';T.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for name in ['baseline.json','working-before.json','data-binding.json']:put(D/name,read(P/'artifacts/design'/name))
criteria=read(P/'artifacts/design/criteria.json');criteria.update(delta='Require the union of action-specific semantic selections in the compact grammar. Normalize only action-inactive empty arrays; bind BASIS side/issue/endpoint IDs to offered choices; validate followup facts against original parent request. Replay one saved BASIS presentation once; no complete live workflow or quality claim.',
 known_observation={**criteria['known_observation'],'original':'04_EXPERIMENTS/ADR/ADR-0807-nonblank-generation-grammar/artifacts/live/result.json'})
criteria['success']+=['Provider-projected schema cannot accept RESEARCH without targets/queries/exploration','Every optional omitted mechanical field is reconstructed before canonical validation; semantic missing values never inferred']
criteria['success']+=['1..12 independent parent issues survive side-specific task binding; no fabricated user facts; child entry uses zero model calls','Same original user utterance and native case/ACL/hash/consumer verification; only existing parent semantics reused','Initial trusted child fulltext discovery retains exact structural hints; no missing-document-as-absence shortcut','Investigation action issue_refs and literal request_quote restored from actual selected issue links; dependency uses delivered source IDs','Final table locations do not introduce uncited evidence IDs']
criteria['system_rules']=['Parent creates business issues, per-side questions, search hints and exact user facts once; no child semantic reinterpretation','Child task schema validates complete supplied issue set up to12, literal fact quotes and fixed side before native entry','Default initial fulltext uses accepted queries and still resolves explicit structural positions through existing native discovery','Exploration ID join and request quote copy are server-owned; legacy exact quotes remain supported for saved callers','Preserve all ADR0803 mechanical source/state/budget/integrity controls']
criteria['retrieval_measurement']='Same declared stages and no approved gold. Archive ADR0803 versus one new observed query; no controlled accuracy/latency claim.'
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['delta'];m['design'].update(hypothesis=criteria['delta'],primary_metric='No child entry model calls; bound parent tasks, original facts and exact issue links',success_criteria=criteria['success'],failure_criteria=['scope/fact/hash/ACL drift','lost issue links or duplicate execution'],criteria_frozen_before_run=True,retrieval_stage_plan=old['design']['retrieval_stage_plan'])
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
for a in m['design']['arms']:a.update(changes='Completed ADR0803/connected known observation' if a['id']=='baseline' else criteria['delta'],controls=criteria['controls'])
m['runs'][0].update(selection_rule='Finite parent-task and mechanical-boundary contracts; one known question; archived baseline only',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='parent-task-native-boundaries',version='20261015-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None);put(A/'실험/manifest.json',m)
base=read(D/'baseline.json')['manifest'];cmd=['.venv/bin/python','06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in base['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0808/connected/snapshot';parent=R/read(P/'artifacts/design/freeze.json')['code_root']
for p in parent.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts:
  dest=C/p.relative_to(parent);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
for p in (R/'06_TOOLS/EXPERIMENTS/adr_0807').glob('*.py'):
 if p.name in ['prepare.py','close.py']:continue
 (T/p.name).write_text(p.read_text().replace('0807','0808').replace('nonblank-generation-grammar','workflow-mechanical-boundaries'))
p=T/'account.py';s=p.read_text().replace('ADR-0802-multi-issue-investigation-retry','ADR-0807-nonblank-generation-grammar');p.write_text(s)
print('ADR0804 reserved and isolated completed parent; criteria saved before edits')
