"""Re-snapshot a pre-run candidate after concurrent upstream movement."""
import hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0682-core-evidence-shortcut-multiturn';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0682/core-route-reviewed'
OLD=C.parent/'core-route'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*args):subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/COMMANDS/adr_candidate.py',*map(str,args)],cwd=R,check=True)
m=read(A/'실험/manifest.json');b=read(D/'baseline.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
rows=read(OLD/'candidate.json')['files'];present=[r['target_path'] for r in rows if r['upstream_state']=='present']
drift={r['target_path']:{'reserved':r['upstream_sha256'],'current':sha(R/r['target_path'])} for r in rows if r['upstream_state']=='present' and r['upstream_sha256']!=sha(R/r['target_path'])}
run('snapshot','--adr',A,'--candidate-id',C.name,'--experiment-id',m['experiment_id'],'--arm-id','core-route','--run-id','run-001',*[v for f in present for v in ('--source',f)])
for row in rows:
    p=C/'snapshot'/row['target_path'];p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OLD/'snapshot'/row['target_path'],p)
    if row['upstream_state']=='absent':run('register',C,'--target',row['target_path'],'--upstream-state','absent')
code=C/'snapshot';pipe=read(code/'00_SYSTEM/PIPELINE.json')
new='02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py'
for engine in pipe['engines'].values():
    ep=code/engine['manifest'];value=read(ep)
    value['files'][new]=sha(code/new)
    for f in value['files']:value['files'][f]=sha(code/f)
    put(ep,value);engine['sha256']=sha(ep)
put(code/'00_SYSTEM/PIPELINE.json',pipe)
run('freeze',C);run('validate',C)
cm=read(C/'candidate.json');rev=cm['revisions'][-1]
tests=[R/'06_TOOLS/EXPERIMENTS/adr_0682'/f for f in ('run_contracts.py','test_core_routes.py','test_core_api.py')]
serving={f:sha(code/f) for f in [*b['manifest']['files'],new]}
put(D/'pre-run-rebind.json',{'prior_unfrozen_candidate':str(OLD.relative_to(R)),'current_candidate':str(C.relative_to(R)),
    'reason':'Concurrent PIPELINE upstream movement before first formal effect run; preserve initial provenance and rejected freeze instead of rewriting upstream hashes',
    'drift':drift,'model_calls_before_rebind':0,'old_snapshot_preserved':True})
put(D/'freeze.json',{'code_root':str((C/'revisions'/rev['revision_id']/'snapshot').relative_to(R)),
    'candidate_manifest':str((C/'candidate.json').relative_to(R)),'candidate_manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'serving_files':serving,
    'tests':{str(p.relative_to(R)):sha(p) for p in tests},'criteria_sha256':sha(D/'criteria.json')})
stages=m['design']['retrieval_stage_plan']
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate',
    'stages_by_arm':{a['arm_id']:a['stages'] for a in stages}}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
    'candidate_id':C.name,'experiment_id':m['experiment_id'],'arm_id':'core-route','run_ids':['run-001'],
    'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
    'runner_path':str(tests[0].relative_to(R)),'runner_sha256':sha(tests[0])}])
put(A/'실험/manifest.json',m)
print('Frozen',len(serving),'serving files; criteria and source contracts unchanged')
