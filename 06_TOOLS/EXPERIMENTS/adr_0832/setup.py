from pathlib import Path
import json,hashlib,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0832-compact-evidence-delivery';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path']);old=R/release['code_root']
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release})
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
criteria={'hypothesis':'Record actual compact assessment option subspans in the current child journal, so strict publication can verify successful delivery without borrowing prior request presentations or weakening guards.',
'success':['Exact compact source option matches a currently acquired source/document/block/span and is recorded in the actual outgoing view','wrong identity/text/hash/offset, unread source, foreign scope and failed model attempts cannot satisfy publication','source metadata alone is never a receipt','split/multiline/duplicate/subset options preserve only exactly delivered spans','fresh/rebound assessment passes strict _ref through actual API','retained831 original journals unchanged; no external model calls','existing58workflow and214common regressions have no new failures'],
'failure':['fabricated successful model receipt','publication guard relaxed','wrong-side/unread/altered evidence accepted','extra physical calls or resetting budget','model payload text changed as part of receipt fix'],
'limits':{'model_calls':0,'each_test_suite_seconds':600},'recovery_owner':'BoundedSourceSession constructs and verifies current outgoing source receipts before save_view; gateway alone records physical attempt success. Invalid receipt is ContractError, no retries or semantic correction.','publication':'Keep unified_publication._ref unchanged; no fake old views and no rewriting failed originals.','in_sample':True,'decision_eligible':False,'quality_certified':False}
put(D/'criteria.json',criteria)
source=next((R/'04_EXPERIMENTS/ADR/ADR-0831-comparison-main77-live-check/artifacts/run-001/public-liquidity-01/runtime').rglob('84bae082b1ac4344bdd07520c4274f06/journal.sqlite'))
put(D/'known-failure.json',{'journal':str(source.relative_to(R)),'sha256':sha(source),'role':'known diagnostic; no holdout or legal accuracy claim'})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Strict source presentation and publication integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='MAIN77 current baseline' if arm['id']=='baseline' else 'Exact current assessment option delivery receipts only',controls=['same source/model payload/authorization','publication validator unchanged'])
m['runs'][0].update(selection_rule='Full declared source-delivery edge-case suite; known831 diagnostic and retained API/common regression suites',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='compact-evidence-delivery-contracts',version='20261016-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[]
reason='Source receipt accounting on fixed exact originals; no retrieval or model effectiveness measurement.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0832/connected'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in release['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in release['files']:shutil.copy2(old/n,C/'snapshot'/n)
print('Design and unchanged MAIN77 snapshot prepared before product edits')
