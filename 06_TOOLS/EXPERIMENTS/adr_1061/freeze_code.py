from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1061-ontology-mvp-execution-repair';ART=ADR/'artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1061/execution-repair-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(ROOT))
tested=read(ART/'release-check-summary.json')
assert tested['validation_status']==0 and not tested['new_failures'] and not tested['production_import_leaks'] and not tested['candidate_changed_during_tests']
assert tested['files']=={str(p.relative_to(CAND/'snapshot')):sha(p) for p in (CAND/'snapshot').rglob('*') if p.is_file()}
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
# Each freeze appends a new immutable revision; old validation failures remain.
c.freeze(CAND);assert not c.validate(CAND)
v=read(CAND/'candidate.json');rev=v['revisions'][-1]
m=read(ADR/'실험/manifest.json')
bindings=[]
for arm,name in [('A0','execution-repair-a0-r1'),('A1','execution-repair-a1-r1'),('A2','execution-repair-r1')]:
 directory=CAND.parent/name
 if arm!='A2':
  rows=v['files']
  c.snapshot(ADR,name,[r['target_path'] for r in rows if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
  for row in rows:
   target=directory/'snapshot'/row['target_path'];target.parent.mkdir(parents=True,exist_ok=True)
   shutil.copyfile(CAND/'snapshot'/row['target_path'],target)
   if row['upstream_state']=='absent':c.register_file(directory,row['target_path'],upstream_state='absent')
  c.refresh(directory);c.freeze(directory)
 assert not c.validate(directory)
 manifest=read(directory/'candidate.json');revision=manifest['revisions'][-1]
 assert {r['target_path']:r['snapshot_sha256'] for r in manifest['files']}==tested['files']
 bindings.append({'candidate_id':name,'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':rel(directory/'candidate.json'),'manifest_sha256':sha(directory/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],'runner_path':rel(Path(__file__).parent/'run_matrix.py'),'runner_sha256':sha(Path(__file__).parent/'run_matrix.py')})
m['design']['code_isolation']['candidates']=bindings
save(ADR/'실험/manifest.json',m)
save(ART/'tested-freeze.json',{'candidate':rel(CAND),'revision':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'files':len(tested['files']),'test_summary':rel(ART/'release-check-summary.json'),'sha256':sha(ART/'release-check-summary.json'),'exact_tested_files':True,'external_model_calls':0})
print('FROZEN',len(tested['files']),'files;',tested['passed'],'tests passed')
