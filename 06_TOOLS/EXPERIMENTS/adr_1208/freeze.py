from pathlib import Path
import json,sys,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=R/read(D/'candidate.json')['root']
if (D/'freeze.json').exists():
    old=read(D/'freeze.json');put(D/('freeze-'+old['revision_id']+'.json'),old)
for p in (C/'snapshot/08_DEPLOYMENT/LOCAL/gold_connection_r12').glob('*.py'):
    T=str(p.relative_to(C/'snapshot'))
    if not any(x.get('target_path',x.get('upstream_path'))==T for x in read(C/'candidate.json')['files']):ac.register_file(C,T,upstream_state='absent')
ac.freeze(C);errors=ac.validate(C)
if errors:raise ValueError(errors)
rev=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'candidate_id':'gold-b03','arm_id':'gold-b03','experiment_id':read(A/'실험/manifest.json')['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1208/run.py','runner_sha256':sha(Path(__file__).with_name('run.py'))}
inputs=[D/'criteria.json',D/'cm-scope.json',D/'selected-documents.json',D/'baseline.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',Path(__file__).with_name('run.py')]
inputs+=list((R/'02_BACKEND/lawrag/pipeline').glob('oracle*.py'))
inputs.append(Path(__file__).with_name('exec_module.py'))
base=read(D/'baseline.json')['manifest'];data=R/base['data_path']
inputs+=[R/base['code_root']/n for n in base['files']]
inputs+=[data/p for p in ['manifest.json','store.sqlite','navigation/navigation.sqlite','fulltext/units.sqlite','fulltext/manifest.json']]
put(D/'freeze.json',{'files':{str(p.relative_to(R)):sha(p) for p in inputs},'code_root':str(code.relative_to(R)),**binding})
put(D/('freeze-'+rev['revision_id']+'.json'),read(D/'freeze.json'))
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);put(A/'실험/manifest.json',m)
print('FROZEN',rev['revision_id'],len(inputs),'input files')
