"""New ADR after observed output; preserve ADR0682 bytes and failed findings."""
import hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
OLD=R/'04_EXPERIMENTS/ADR/ADR-0682-core-evidence-shortcut-multiturn/artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*v):subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/COMMANDS/adr_candidate.py',*map(str,v)],cwd=R,check=True)
b=read(OLD/'baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
put(D/'baseline.json',b)
criteria=read(OLD/'criteria.json');criteria['followup_observed_failures']={'source':'ADR-0682-experiment-v1/core-route',
    'product':['V3 KnowledgeRepository projection omitted sw_unit source paths','New READ incorrectly restored completed prior SELECT investigation state'],
    'fixture':['Injected RESEARCH omitted its required action target and repaired to READ_PARENT','Interrupted retry increments an existing goal revision; verify currentness without assuming revision number']}
criteria['closure_acceptance']=['One canonical v4 wiki projection includes compact source path and points to current SQL head',
    'A newly acquired READ restarts current selection instead of reviving a completed older SELECT',
    'Synthetic HTTP confirms actual selected spans change, old head stays unavailable during interruption, and fresh RESEARCH reaches existing fulltext']
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');old=read(OLD.parent.parent/'실험/manifest.json')
m['decision_eligible']=True;m['design'].update(hypothesis=criteria['scope']+'; close actual wiki and multiturn consumers',
    primary_metric='All prespecified core-source invariants and native HTTP/projection contracts pass; no new maintained contract failures',
    success_criteria='; '.join(criteria['acceptance']+criteria['closure_acceptance']),failure_criteria='Any source/currentness/scope corruption, wiki omission, stale final selection or new critical regression rejects',criteria_frozen_before_run=True,
    retrieval_stage_plan=old['design']['retrieval_stage_plan'])
for arm in m['design']['arms']:arm.update(changes='Exact selected generation45 baseline' if arm['id']=='baseline' else 'ADR0682 source path with wiki/current READ consumer closure',controls=criteria['provenance'])
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['runs'][0].update(purpose='holdout',selection_rule='Frozen synthetic source/revision/HTTP/projection conditions and maintained contracts',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name=criteria['dataset'],version='core-path-consumer-20261007-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['stage_ledger']['mode']='measured';put(A/'실험/manifest.json',m)
freeze=read(OLD/'freeze.json');source=R/freeze['code_root'];C=R/'02_BACKEND/lawrag/research/candidates/adr_0683/core-route'
present=[f for f in freeze['serving_files'] if (R/f).is_file()];absent=[f for f in freeze['serving_files'] if not (R/f).exists()]
run('snapshot','--adr',A,'--candidate-id',C.name,'--experiment-id',m['experiment_id'],'--arm-id','core-route','--run-id','run-001',*[v for f in present for v in ('--source',f)])
for f in freeze['serving_files']:
    p=C/'snapshot'/f;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/f,p)
    if f in absent:run('register',C,'--target',f,'--upstream-state','absent')
tests=R/'06_TOOLS/EXPERIMENTS/adr_0683';tests.mkdir(exist_ok=True)
for f in ('test_core_routes.py','test_core_api.py'):shutil.copy2(R/'06_TOOLS/EXPERIMENTS/adr_0682'/f,tests/f)
put(D/'starting-binding.json',{'upstream_adr':'ADR-0682-experiment-v1/core-route','rejected_result':str((OLD.parent/'run-001/result.json').relative_to(R)),
    'rejected_result_sha256':sha(OLD.parent/'run-001/result.json'),'old_frozen_code':str(source.relative_to(R)),'new_snapshot':str((C/'snapshot').relative_to(R)),
    'working_before':{f:sha(R/f) if (R/f).is_file() else None for f in freeze['serving_files']}})
print('New ADR criteria frozen before closure implementation; old result preserved')
