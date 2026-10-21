from pathlib import Path
import json,hashlib,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0835-comparison-llm-judgment';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path']);old=R/release['code_root']
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release,'selected_release_manifest':release})
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
criteria={'hypothesis':'Let the LLM judge meaning and relevance; keep source/ACL/hash/state integrity and display limitations instead of repeatedly rejecting semantic status combinations.',
'success':['MISSING explanatory text is accepted without repair; arbitrary unquoted commentary remains explicitly unverified','Offered research locator automatically provides its evidence anchor; invented IDs and wrong sides still fail','Rewording retains earlier evidence without an invented CONFLICT; real LLM CONFLICT remains','BASIS gaps, source completeness, applicability and explicit-reference classification are model-visible context, not automatic comparison gates','COMPARE accepts source-grounded model judgments with only relevant numeric dimensions; all supplied citations remain checked','DEFERRED model explanations are preserved in display/storage instead of overwritten','Normal API, partial results, correction exhaustion, resume/duplicate and source/ACL/hash/state invariants remain connected'],
'failure':['invalid/foreign citation accepted','state/hash/ACL guard removed','model-selected content silently rewritten or missing histories lost','unbounded retry or new calls on duplicate','quality claims based only on HTTP200'],
'limits':{'model_calls':6,'each_test_suite_seconds':600},
'failure_contract':{'hard':'JSON/identity, exact citations and side/scope, hashes/revision/ACL; existing gateway and stage owner; maximum one repair and unchanged parent budget','soft':'Semantic consistency and sufficiency remain LLM judgments with original evidence and visible unknowns; no correction call solely for MISSING prose, text changes or incomplete dimension inventory','resume':'Same state/code binding, immutable call identity, original usage/deadline; old published results untouched'},
'known_evidence':'ADR0834 is a development diagnostic, not an unseen holdout. Frozen test fixtures plus up to6 new model calls on supplied exact source packets; no whole-workflow quality claim.',
'in_sample':True,'decision_eligible':False,'quality_certified':False}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-grounded model decisions survive semantic advisory conditions without extra repairs',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='MAIN78 baseline' if arm['id']=='baseline' else 'Advisory semantic gates and simpler model-owned comparison contract',controls=['same data/model/authorization','same native RAG','same exact source and state guards'])
m['runs'][0].update(selection_rule='Fixed focused fixtures, retained source-integrity/API regressions, known item packets and prospectively fixed model contract calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='llm-comparison-contract-development',version='20261016-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[]
reason='Existing exact retrieved sources remain fixed; only comparison validation and wire fields change. No retrieval ranking/effect measurement.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0835/connected'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in release['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in release['files']:shutil.copy2(old/n,C/'snapshot'/n)
print('Frozen criteria and MAIN78 baseline prepared; candidate only')
