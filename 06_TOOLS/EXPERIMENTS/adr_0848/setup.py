"""Prospective contract/size experiment; private field data never enters a model."""
from pathlib import Path
import hashlib, json, subprocess, sys

R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0848-minimal-model-output'
D = A/'artifacts/design'
D.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')

assert not (D/'criteria.json').exists()
pointer = read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(R/pointer['manifest_path'])
assert pointer['generation'] == 81
put(D/'baseline.json', {'pointer':pointer, 'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'manifest':release})
put(D/'working-before.json', {n:sha(R/n) if (R/n).exists() else None for n in release['files']})
criteria = {
 'hypothesis':'A common reversible model-output projection removes provably constant fields and repeated action schemas, while canonical JSON, semantic choices, exact citations and recovery ownership remain unchanged.',
 'success':['Canonical reconstruction for every valid prospective synthetic case; no invented semantic value',
    'Reject wrong constants, unknown fields/choices, ambiguous branches and malformed outputs',
    'Navigation schema bytes decrease by at least 50 percent on prospectively declared synthetic multi-action cases',
    'Gateway, workflow response recovery, AD and GENOS document/VLM structured boundaries use the same codec',
    'Raw provider response preserved separately from reconstructed JSON; one repair owner, no extra model calls',
    'Relevant regression/API checks pass or pre-existing failures reproduced against pinned baseline'],
 'failure':['Citation/permission/version/state check bypass','Different canonical semantic value',
    'A missing semantic field is invented to pass validation','Raw response overwritten','Added blind retry'],
 'scope':['question routing','RAG navigation and references','assessment and final answer',
    'comparison workflow','AD interpretation','GENOS document/VLM structured generation'],
 'failure_contract':{'classification':'model JSON/schema or host projection contract',
    'owner':'existing gateway or stage; projection itself never retries',
    'allowed':'singleton constants, schema-implied empty containers, canonical branch selection, lossless field reconstruction',
    'forbidden':'inferred legal meaning, fabricated reasons/citations, altered evidence or state',
    'budget':'existing physical-call, repair, deadline and resume counters unchanged',
    'terminal':'existing partial/failed/resumable contracts; UNKNOWN transport is not a successful answer'},
 'cases':{'navigation_action_counts':[1,4,12], 'branch_counts':[0,2,8],
    'unicode':['','한국어 원문','😀\n인용 그대로'], 'adversarial':['unknown field','wrong constant','missing semantic',
        'ambiguous branch','bad enum','malformed JSON','stale state','interrupted response recovery']},
 'model_policy':'Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8, effort none, no fallback if a public synthetic model probe is run',
 'field_photo':'Read-only diagnostic: 122296 canonical request bytes, 29321 message chars, 78856 response_format bytes. No original field payload available; do not claim exact replay or resolved GENOS latency.',
 'in_sample':True, 'decision_eligible':False,
 'main_wiring':'unchanged until a separate exact-code qualification and authorized promotion',
 'retained_meaning':'Keep one concise reason for real judgments and user-visible opinions/unknowns; no hidden reasoning requested. Preserve final requested detail and literal quotations.'}
put(D/'criteria.json',criteria)
sources=list(release['files'])
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
    '--candidate-id','compact','--experiment-id','ADR-0848-experiment-v1','--arm-id','compact','--run-id','run-001']
for n in sources:
    cmd += ['--source',n]
subprocess.run(cmd,cwd=R,check=True)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0848/compact'
put(D/'candidate-start.json',{'path':str(C.relative_to(R)), 'files':{n:sha(C/'snapshot'/n) for n in sources},
    'working_vs_selected':{n:{'working':sha(R/n),'selected':h} for n,h in release['files'].items() if sha(R/n)!=h}})
m=read(A/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact reconstruction, integrity and schema/output byte counts',
    success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:
    arm.update(changes='Pinned current working code over MAIN81' if arm['id']=='baseline' else criteria['hypothesis'],
        controls=['same sources and canonical contracts','same model policy','no private payload export','same retry ownership'])
m['dataset'].update(name='minimal-output-finite-contracts',version='20261016-v1',
    frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),
    legal_version_checked=False,reference_version_checked=False)
m['runs'][0].update(selection_rule='All prospective finite contract categories; synthetic data only',
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
reason='Output protocol projection only; no retrieval policy or legal-quality comparison.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
print('Criteria fixed; isolated candidate:',C)
