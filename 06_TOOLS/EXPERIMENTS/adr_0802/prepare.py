from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0802-multi-issue-investigation-retry';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);base=read(R/pointer['manifest_path'])
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(p),'manifest':base})
put(D/'data-binding.json',read(R/'04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification/artifacts/design/data-binding.json'))
criteria={'delta':'Allow multiple different issue provenance rows per selected target; preserve unique executable targets and every exact issue quote/dependency. No automatic semantic merge or extra tool execution.',
 'controls':['MAIN74 serving files/data/model/profile/definition-first/latest selection unchanged except exploration relation contract and dependent hashes','40 model attempts and 1800 seconds per existing workflow; one fresh explicitly requested known-question observation; no adaptive rerun','Existing single navigation correction and gateway retry ownership unchanged; transport unknown is not blindly resent'],
 'success':['v6/v7/v8 accept one target linked to distinct issues with no mutated proposal','Reject duplicate target-issue pairs, missing/extra targets, unknown/unselected issues, fabricated quotes/dependencies','8-target batches can carry all selected issue links within bounded schema','Accepted action stores both issue links and runs each target once; old shape remains accepted','Targeted recovery/budget/restart and actual API tests pass','Real-model rerun records actual connection result, internal/external states and comparison rows without treating HTTP200 as successful answer'],
 'failure_contract':{'classification':'cross-field target/issue relationship; not schema size','owner':'investigation_scope validates; existing law_navigation correction at most one; no higher-layer repeat','state':'unaltered proposal and exact rows saved in existing accepted/decision journal; targets remain distinct executable set','stop':'existing pending/partial/failure if correction or transport fails; never turn read originals into accepted claims'},
 'known_observation':{'question':'대사: 유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?','repeats':1,'in_sample':True,'decision_eligible':False,'original':'04_EXPERIMENTS/ADR/ADR-0800-workflow-literal-request-quotes/artifacts/live/result.json'},
 'qualification':'Known-case probe only. Successful contracts or connection do not establish legal accuracy or authorize MAIN promotion.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['delta'];m['design'].update(hypothesis=criteria['delta'],primary_metric='multi-issue provenance acceptance without duplicated target execution; connection retry observed',success_criteria=criteria['success'],failure_criteria=['any integrity or execution-count regression','same multi-issue proposal rejected after fix'],criteria_frozen_before_run=True)
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
C=R/'02_BACKEND/lawrag/research/candidates/adr_0802/connected/snapshot'
for name,h in base['files'].items():
 source=R/base['code_root']/name;assert sha(source)==h
 target=C/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for name in ('repin.py','freeze.py','audit_pinned.py','run_tests.py','live.py'):
 text=(R/'06_TOOLS/EXPERIMENTS/adr_0800'/name).read_text().replace('0800','0802').replace('workflow-literal-request-quotes','multi-issue-investigation-retry').replace('MAIN73','MAIN74')
 (R/'06_TOOLS/EXPERIMENTS/adr_0802'/name).write_text(text)
print('MAIN74 isolated, design frozen before candidate edit')
