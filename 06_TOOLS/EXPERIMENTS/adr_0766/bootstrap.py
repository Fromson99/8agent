"""Reserve-derived design and isolated MAIN53 snapshot, before candidate work."""
from pathlib import Path
import hashlib, json, subprocess

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0766-rich-grounded-answer-stream'
D = A / 'artifacts/design'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

assert not D.exists()
pointer = read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(R/pointer['manifest_path'])
assert pointer['generation'] == 53
criteria = {
    'hypothesis': 'A source-bound final writing call can turn accepted v8 judgments into a clear conclusion and useful explanations, with paragraph streaming through the existing native gateway and GENOS channel.',
    'change': 'Guarded grounded-narrative-v1 presentation, original judgment/quotes/ACL/gaps preserved. One final composition call, no new retrieval, no automatic semantic judge or new model/provider.',
    'criteria': ['All contract tests for native production path, stable source/assessment binding, paragraph coverage, gap preservation, early paragraph before provider completion, no duplicate final, failure after visible output not retried must pass.', 'Public probe: direct conclusion, explanatory context and appropriate detail; no newly invented duty, number, exception or source. Report explicit source consistency separately from structural pass.', 'All physical calls and failures retained, no adaptive reruns; <= 180 seconds per composition and unchanged overall native budgets. No minimum length padding.'],
    'sample': 'Development probe based on user-observed terse answer. Synthetic contracts and 3 fixed public source cases. Never claim unseen qualification. A separate frozen independent evaluation is needed for MAIN selection.',
    'model': 'qwen/qwen3.8-27b, Parasail FP8, effort none, no fallback; public/synthetic only. GENOS internal model not callable here.',
    'baseline': 'Selected MAIN53 v8 deterministic compose; sources and accepted assessments held fixed for presentation comparisons.',
    'authorization': 'User requests fuller polished final answers and asks about streaming. Changes and tests authorized; no email instruction.',
    'rollback': 'Keep original structured path selectable; immutable MAIN53 release and GENOS shipped bundles retained.'
}
put(D/'criteria.json', criteria)
put(D/'baseline.json', {'pointer': pointer, 'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'manifest':release})
put(D/'dataset.json', {'version':'v1', 'cases':['synthetic-permission-and-duty','synthetic-nested-conditions','synthetic-missing-evidence','synthetic-stream-interruption','public-frozen-originals'], 'private_question_export':False})
m = read(A/'실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['change']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Grounding, useful explanation, and native paragraph-stream correctness', success_criteria=criteria['criteria'], failure_criteria='Any source, state, stream or content regression; preserve failure and do not promote.', criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[])
for arm in m['design']['arms']:
    arm.update(changes=criteria['baseline'] if arm['id']=='baseline' else criteria['change'], controls='Same immutable source generation and approved documents, model, accepted assessment and native budgets; no search changes.')
m['dataset'].update(name='Rich answer development contracts and fixed public composition probes',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Fixed synthetic contracts and frozen public composition inputs; no adaptive repeats', artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting']['not_applicable_reason']='Composition-only probe consumes frozen accepted judgments; no retrieval runs or changes.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','narrative','--experiment-id',m['experiment_id'],'--arm-id','narrative','--run-id','run-001']
names=set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','08_DEPLOYMENT/GENOS/stream_app.py'}
for name in sorted(names):
    cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
put(D/'working-base.json',{'files':{n:sha(R/n) for n in sorted(names)},'differences_from_release':{n:{'release':release['files'].get(n),'working':sha(R/n)} for n in sorted(names) if sha(R/n)!=release['files'].get(n)}})
print('Design frozen; working snapshot created over MAIN53 lineage; no product/model calls.')
