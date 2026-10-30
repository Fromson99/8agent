from pathlib import Path
import json,hashlib,sys,ast,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1136-ontology-framework-main-toggle';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_1136/framework-r1';S=C/'snapshot';T=Path(__file__).parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in list(T.glob('*.py'))+list((S/'02_BACKEND/semantic_runtime/legal_agent').glob('ontology_*.py'))+[S/'service.py']:ast.parse(p.read_text())
pipeline=read(S/'00_SYSTEM/PIPELINE.json');new=['02_BACKEND/semantic_runtime/legal_agent/'+p.name for p in (S/'02_BACKEND/semantic_runtime/legal_agent').glob('ontology_*.py')]
for ref in pipeline['engines'].values():
 p=S/ref['manifest'];e=read(p)
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' not in e['files']:continue
 for n in new:e['files'][n]=sha(S/n)
 for n in e['files']:
  if (S/n).is_file():e['files'][n]=sha(S/n)
 put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipeline)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');rev=c['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';files={str((R/row['frozen_path']).relative_to(code)):row['snapshot_sha256'] for row in rev['files']}
binding={'candidate_id':C.name,'experiment_id':c['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'check.py').relative_to(R)),'runner_sha256':sha(T/'check.py')}
base=read(D/'baseline.json');stage=A/'artifacts/staged-code';serving={n:files[n] for n in list(base['manifest']['files'])+new}
for n,h in serving.items():
 p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code/n,p);assert sha(p)==h
(stage/'01_DATA').symlink_to(R/'01_DATA',target_is_directory=True)
put(D/'staging.json',{'code_root':str(stage.relative_to(R)),'files':serving,'changed':[n for n,h in serving.items() if base['manifest']['files'].get(n)!=h],'data_packaged':False,'data_symlink':'test/release tooling reference to existing generation only; not in serving inventory'})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'code_root':str(code.relative_to(R)),'files':files,'candidate':binding,'scripts':{str(p.relative_to(R)):sha(p) for p in T.glob('*.py')},'criteria_sha256':sha(D/'criteria.json'),'manifest_sha256_at_freeze':sha(A/'실험/manifest.json'),'pointer_sha256':base['pointer_sha256'],'stage':str(stage.relative_to(R)),'serving_files':len(serving)})
print('FROZEN',len(files),'serving',len(serving))
