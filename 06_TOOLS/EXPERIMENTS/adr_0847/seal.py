"""Register and freeze finalized candidate plus prospective technical census."""
from pathlib import Path
import hashlib,json,subprocess,sys,itertools
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0847/integrated';S=C/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0847-basis-link-lifecycle';D=A/'artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
known={r['target_path'] for r in json.loads((C/'candidate.json').read_text())['files']}
for p in sorted(S.rglob('*')):
 if not p.is_file() or '__pycache__' in p.parts:continue
 n=str(p.relative_to(S))
 if n not in known:
  if p.stat().st_size==0:p.write_text('"""Basis lifecycle package."""\n')
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','present' if (R/n).exists() else 'absent'],check=True,stdout=subprocess.DEVNULL)
subprocess.run([str(R/'.venv/bin/python'),str(Path(__file__).with_name('pins.py'))],check=True)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
# Unique 24 kind/state/perspective combinations are a finite technical census.
# No held-out law answers or semantic accuracy claims are made.
cases=[{'kind':k,'state':s,'perspective':p} for k,s,p in itertools.product(('BASIS','IMPLEMENTS','RELATED'),('PROPOSED','APPROVED','REJECTED','REVOKED'),('CURRENT_BASIS','HISTORICAL_ORIGIN'))]
put(D/'cases.json',cases)
base=json.loads((D/'baseline.json').read_text());put(D/'data-binding.json',{'path':base['release']['data_path'],'manifest_sha256':base['release']['data_manifest_sha256']})
files={str(p.relative_to(R)):sha(p) for p in Path(__file__).parent.glob('*.py')}
files.update({str((code/f['target_path']).relative_to(R)):sha(code/f['target_path']) for f in cm['files']})
files[str((D/'cases.json').relative_to(R))]=sha(D/'cases.json')
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':files,'candidate':binding,'prospective_technical_states':24,'legal_holdout':False})
m=json.loads((A/'실험/manifest.json').read_text());m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']='Shared source/review authority with exact live reuse and immutable per-version mappings; no model performance claim.'
m['design']['primary_metric']='Finite technical state census and actual source/API integrity'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**binding,'candidate_id':'integrated','arm_id':'lifecycle','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0847/run_tests.py','runner_sha256':sha(Path(__file__).with_name('run_tests.py'))}])
for arm in m['design']['arms']:arm.update(changes='Historical MAIN81' if arm['id']=='baseline' else 'Shared basis lifecycle implementation',controls=['immutable selected data','same configured model policy','zero external model calls; scripted proposals only'])
m['runs'][0].update(arm_ids=['lifecycle'],selection_rule='24 prospectively fixed finite technical states plus identified development regression; no legal holdout',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='basis-lifecycle-technical-state-census',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
why='Software integrity and exact original-reading contracts. New priority path is tested against verified source spans; no retrieval ranking, recall or legal accuracy comparison.'
m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why
put(A/'실험/manifest.json',m)
print('Frozen',rev['revision_id'],'files',len(cm['files']))
