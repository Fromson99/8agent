from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0803-system-owned-workflow-mechanics';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);base=read(R/pointer['manifest_path'])
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(p),'manifest':base})
put(D/'data-binding.json',read(R/'04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification/artifacts/design/data-binding.json'))
criteria={'delta':'Host-owned citation IDs, child scope and rendering, verified definition-reference reads, deterministic comparison gates and durable partial outcomes; preserve multi-issue links.',
 'controls':['MAIN74 selected serving files and data; retain ADR0802 multi-issue contract; no model/provider fallback','Same 40 physical attempt/1800 second budget; exactly one known question observation; no adaptive rerun','No automatic legal adoption, applicability or compliance inference; integrity failures fail closed'],
 'success':['Exact source citation assembly from supplied IDs; reject stale/unknown IDs and altered originals','Child scope reaches navigation and assessment; structured child rendering consumes no composition model call','Verified definition locations and resolved references acquired once with existing read receipts, ACL, hashes and budget','Known ineligible pairs produce DEFERRED without LLM; successful pair rows survive later proposal failure and restart','Only actual decisive citations published; no all-child-evidence fallback','Preserve distinct issues, unique tool execution and original request quotes','Normal, recovery, exhausted, duplicate, restart, stale/hash/ACL and actual service consumer tests pass'],
 'failure_contract':{'owner':'Existing stage correction owner, gateway owns only transport retries; host mechanics never model-repair integrity violations','normalization':'Only schema-declared projection of source IDs/constants; original proposal and projection binding journaled; no inferred legal content','limits':'One stage repair, shared physical-call/deadline budget survives restart; system definition seeding bounded to one first page and 8 unique reads with remaining links visible','partial':'Persist validated rows before next pair; failed pair remains unresolved; no promotion of failed or unverified statements','transport':'Definite connect-before-accept errors retryable at gateway; uncertain acceptance not resent'},
 'known_observation':{'question':'대사: 유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?','repeats':1,'in_sample':True,'decision_eligible':False,'original':'04_EXPERIMENTS/ADR/ADR-0802-multi-issue-investigation-retry/artifacts/live/result.json'},
 'qualification':'Probe candidate only; technical qualification and explicit release binding separate from legal accuracy.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['delta'];m['design'].update(hypothesis=criteria['delta'],primary_metric='Mechanical calls avoided with source integrity and preserved partial results',success_criteria=criteria['success'],failure_criteria=['any integrity or execution-count regression','same multi-issue proposal rejected after fix'],criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
for arm in m['design']['arms']:arm.update(changes='Selected MAIN74 baseline' if arm['id']=='baseline' else criteria['delta'],controls=criteria['controls'])
m['runs'][0].update(selection_rule='Finite v6/v7/v8 relation matrix plus one known liquidity service request; baseline archived observed failure only, no fresh baseline LLM',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='multi-issue-investigation-contract-and-known-liquidity',version='20261015-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
# No retrieval ranking/filter/index change; known live traversal is observational,
# never a paired recall or gold accuracy claim.
reason='Provenance validation boundary; no retrieval ranking/filter/index change or recall claim. Actual traversal remains in native immutable journal; no approved gold for this known question.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
cmd=['.venv/bin/python','06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
extras=['05_TESTS/CONTRACTS/test_focused_input_modality.py','05_TESTS/CONTRACTS/test_investigation_scope_recovery.py']
for name in list(base['files'])+extras:cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0803/connected/snapshot'
for name,h in base['files'].items():
 source=R/base['code_root']/name;assert sha(source)==h
 target=C/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
source=R/'02_BACKEND/lawrag/research/candidates/adr_0802/connected/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/investigation_scope.py'
shutil.copyfile(source,C/'02_BACKEND/semantic_runtime/legal_agent/investigation_scope.py')
print('MAIN74 isolated with ADR0802 multi-issue delta; criteria frozen before edit')
