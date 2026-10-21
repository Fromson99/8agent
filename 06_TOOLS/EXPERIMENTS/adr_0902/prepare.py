from pathlib import Path
import hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0902-read-input-contract-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0901-read-choice-information-preservation';old=json.loads((P/'artifacts/design/freeze.json').read_text());oldcode=R/old['code_root']
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria=read(P/'artifacts/design/criteria.json');criteria['evaluation']='Same prospectively enumerated finite software boundaries, with synthetic law IDs corrected and pre-existing session_identity dependency included. Known failed harness is not a legal holdout. No product algorithm change from ADR0901 and no live model calls.'
put(D/'criteria.json',criteria)
for name in ['baseline.json','changes.json']:shutil.copyfile(P/'artifacts/design'/name,D/name)
before=read(P/'artifacts/design/working-before.json');before['02_BACKEND/semantic_runtime/session_identity.py']=sha(R/'02_BACKEND/semantic_runtime/session_identity.py')
assert all(sha(R/n)==h for n,h in before.items())
put(D/'working-before.json',before)
cm=read(R/old['candidate']['manifest_path']);names=[x['target_path'] for x in cm['files']]+['02_BACKEND/semantic_runtime/session_identity.py']
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Finite input preservation and connected API contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']='Unchanged ADR0901 implementation with corrected synthetic fixture IDs and complete existing session-identity dependency packaging.'
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0901-experiment-v1/preserved'],'changes':m['lineage']['hypothesis_delta'],'controls':'Same projection code/hash and technical boundary set; no model or legal evaluation'}]
m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='finite-input-preservation-contracts',version='20261019-r2',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['retrieval_accounting']['not_applicable_reason']='Synthetic software contracts; no corpus/model retrieval comparison.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id',m['experiment_id'],'--arm-id','qualified','--run-id','run-001']
for name in names:cmd+=['--source',name]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0902/qualified';S=C/'snapshot'
for row in read(D/'changes.json'):shutil.copyfile(oldcode/row['path'],S/row['path'])
# Preserve the exact failed fixture in ADR0901; this new fixture changes only missing host-required law IDs.
text=(P/'artifacts/failed-test-source.py').read_text().replace('parents[2]','parents[3]')
text=text.replace("{'name': '모의 규정', 'document_id': 'D1'", "{'id': 'L1', 'name': '모의 규정', 'document_id': 'D1'")
text=text.replace("data['laws'] = [{'read_action': 'T1', 'preview': x} for x in ['① 승인한다.', '② 통지한다.', '② 통지한다.']]", "data['laws'] = [{'id': 'L1', 'articles': [{'read_action': 'T1', 'preview': x} for x in ['① 승인한다.', '② 통지한다.', '② 통지한다.']]}]")
(T/'test_input.py').write_text(text)
runner=(R/'06_TOOLS/EXPERIMENTS/adr_0901/run_tests.py').read_text().replace('ADR-0901-read-choice-information-preservation','ADR-0902-read-input-contract-qualification')
(T/'run_tests.py').write_text(runner)
plan=read(P/'artifacts/design/execution-plan.json');plan['tests'][0]=str((T/'test_input.py').relative_to(R));put(D/'execution-plan.json',plan)
subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','refresh',str(C)],check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
files={str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']}
for folder in [T,D]:
 for p in folder.glob('*'):
  if p.is_file():files[str(p.relative_to(R))]=sha(p)
for name in [x.split('::')[0] for x in plan['tests']]+['06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py','06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py','06_TOOLS/EXPERIMENTS/adr_0832/test_delivery.py','05_TESTS/conftest.py','06_TOOLS/EXPERIMENTS/resource_guard.py']:
 files[name]=sha(R/name)
put(D/'freeze.json',{'code_root':str(code.relative_to(R)),'files':files,'candidate':binding,'serving_files':{n:sha(code/n) for n in old['serving_files']},'legal_holdout':False})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**binding,'candidate_id':'qualified','arm_id':'qualified','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str((T/'run_tests.py').relative_to(R)),'runner_sha256':sha(T/'run_tests.py')}]);put(A/'실험/manifest.json',m)
print('Frozen unchanged product plus existing dependency, 712 files; corrected 3 synthetic law-ID fixtures.')
