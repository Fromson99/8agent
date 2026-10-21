from pathlib import Path
import datetime, hashlib, json, subprocess, sys

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0901-read-choice-information-preservation'
D = A / 'artifacts/design'
D.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
assert not (D / 'criteria.json').exists()
active = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(R / active['manifest_path'])
assert active['generation'] == 87
criteria = {
 'hypothesis': 'Mechanical preservation of stored candidate hints and executable action context fixes R1/R2/R3 without changing source selection authority, original text, output schema or durable recovery budgets.',
 'success': ['Stored title/surface and existing preview survive projection and provider wire',
  'Same target combines nonempty metadata without overwriting; conflicting hints remain explicit; different targets/documents/scopes never merge',
  'Parent/scope/page and return actions retain exact target identity and available human-readable path/context',
  'Originals, schema expansion, one repair, accepted replay, budgets, invalid targets and dependency source checks retain their existing behavior',
  'Same frozen code and pins pass focused regressions and actual service-dispatch contract checks',
  'Only decision_projection and its code-hash pins are integrated into current working files after finite acceptance; active MAIN stays unchanged'],
 'failure': ['Original/ACL/hash/state/output/recovery regression', 'Unregistered candidate file or source drift', 'Resource guard stop'],
 'evaluation': 'Prospective finite technical boundary census, not legal accuracy or latency evaluation. Recorded ADR0900 inputs are known diagnosis only. No model calls in this ADR.',
 'recovery': {'owner': 'existing read-choice DecisionJournal and native validator', 'max_added_model_calls': 0,
  'conflicting_hints': 'retain actual values, no semantic arbitration', 'wrong_document_hint': 'fatal host contract error, not a model repair',
  'resume': 'preserve existing decision identity and global persistent budget; code binding protects revision changes'},
 'limits': {'workers': 1, 'rss_gib': 2, 'as_gib': 3, 'min_available_gib': 4, 'min_disk_gib': 10},
 'selection': ['Unicode/empty titles', 'duplicate order/empty/conflicting metadata', 'same number in different documents and ranges',
  'READ_PARENT/READ_SCOPE/VIEW_SAVED_SOURCE/RETURN_TO descriptions', 'rejected target and dependency',
  'repair success/failure, accepted replay, reserved unknown outcome and budget reserve', 'wire original preservation', 'actual service dispatch'],
 'legal_holdout': False, 'quality_certified': False, 'genos_execution': False}
put(D / 'criteria.json', criteria)
parent = read(R / '02_BACKEND/lawrag/research/candidates/adr_0895/consistent/candidate.json')
names = [x['target_path'] for x in parent['files']]
before = {n: sha(R/n) for n in names}
put(D / 'working-before.json', before)
put(D / 'baseline.json', {'pointer': active, 'release': release,
 'pointer_sha256': sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_differences_from_selected': [n for n,h in release['files'].items() if sha(R/n)!=h],
 'basis': 'Current working code preserves concurrent pre-existing development. Runtime baseline differs from selected MAIN87; changed file matches MAIN87 before this repair.'})
m = read(A/'실험/manifest.json')
m.update(in_sample=False, decision_eligible=True)
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Finite input-preservation and failure-boundary contracts',
 success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'preserved','role':'candidate','derived_from':['ADR-0896-experiment-v1/qualified'],
 'changes':'R1/R2/R3 input metadata preservation only, rebased on hash-recorded current working code',
 'controls':'Originals, output schema, tools, model settings, retries, state and budgets unchanged; no live quality comparison'}]
m['runs'][0].update(arm_ids=['preserved'], selection_rule=criteria['evaluation'], artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='finite-input-preservation-contracts', version='20261019-r1', frozen_source=str((D/'criteria.json').relative_to(R)), sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[]
why='Finite synthetic software contracts only, no corpus retrieval/model evaluation. Known ADR0900 diagnosis is not rescored.'
m['retrieval_accounting']['not_applicable_reason']=why
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','preserved',
 '--experiment-id',m['experiment_id'],'--arm-id','preserved','--run-id','run-001']
for n in names: cmd += ['--source', n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Frozen criteria and current working baseline; candidate snapshot:',len(names),'files; no source generation copied.')
