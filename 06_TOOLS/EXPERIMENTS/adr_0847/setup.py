"""Reserve/freeze implementation scope before candidate edits; no model calls."""
from pathlib import Path
import hashlib, json, subprocess
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0847-basis-link-lifecycle'
D=A/'artifacts/design';D.mkdir(exist_ok=True)
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
pointer=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
release=json.loads((R/pointer['manifest_path']).read_text())
files=set(release['files'])
files.update(str(p.relative_to(R)) for folder in ('02_BACKEND/lawrag/pipeline','02_BACKEND/lawrag/sources','02_BACKEND/lawrag/core/structure') for p in (R/folder).glob('*.py'))
files.update(['06_TOOLS/pipeline.py','06_TOOLS/COMMANDS/composed_build.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
files={f for f in files if (R/f).is_file()}
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
put(D/'working-before.json',{f:sha(R/f) for f in sorted(files)})
criteria={
 'scope':'Shared basis authority, human review/reuse, document discovery, version migration and real ingress wiring',
 'success':['Transactional immutable review and receipt; stale/conflicting requests rejected',
 'Team and document ACL, original hashes and selected generation enforced',
 'Exact approved locations read before search; revocation reflected on subsequent requests and saved displays',
 'Document inventory is exhaustive with durable processed/remaining coverage and budget/deadline preservation',
 'Only unique content AND context identity preserves approval across versions; changed/split/merged/unresolved remain advisory',
 'API/service, normal RAG, comparison, discovery and build consumers call the same authority'],
 'failure':['Unreviewed automatic human approval','Lost source/review history','Cross-team disclosure','Generation mixing','Renewed budget on retry'],
 'recovery':{'review':'One repository transaction; no automatic retry; recover same request receipt',
 'model':'Existing ModelAdapter one correction and gateway transport budget',
 'discovery':'Existing workflow checkpoint and parent physical budget; continuation is explicitly new linked run',
 'migration':'Immutable per-generation bindings and deterministic migration ID; CAS conflicts remain pending'},
 'model_calls':0,'quality_certified':False,
 'onsite':'Oracle table/identity/publication and Dataiku recipe mapping require actual contracts; no SQLite fallback in GENOS'}
put(D/'criteria.json',criteria)
m=json.loads((A/'실험/manifest.json').read_text());m['design'].update(hypothesis=criteria['scope'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['llm_policy']['llm_calls']=[]
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','lifecycle','--experiment-id','ADR-0847-experiment-v1','--arm-id','lifecycle','--run-id','run-001']
for f in sorted(files):cmd+=['--source',f]
subprocess.run(cmd,cwd=R,check=True)
