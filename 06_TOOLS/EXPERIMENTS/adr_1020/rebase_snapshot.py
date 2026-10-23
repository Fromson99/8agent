from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');old=ROOT/s['candidate_dirs']['candidate'];cm=read(old/'candidate.json');m=read(ADR/'실험/manifest.json')
changes=[{'path':r['target_path'],'original_upstream':r['upstream_sha256'],'current_upstream':sha(ROOT/r['target_path'])} for r in cm['files'] if r['upstream_state']=='present' and sha(ROOT/r['target_path'])!=r['upstream_sha256']]
save(ART/'freeze-upstream-drift.json',{'failed_candidate':str(old.relative_to(ROOT)),'reason':'Concurrent Oracle work changed upstream before freeze. Preserve failure; re-register current upstream while retaining exact tested snapshot bytes. No old Oracle files will be integrated into working code.','changes':changes})
new=ac.snapshot(ADR,'candidate-rebased',[r['target_path'] for r in cm['files'] if r['upstream_state']=='present'],experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
for r in cm['files']:
 target=r['target_path'];shutil.copyfile(old/'snapshot'/target,new/'snapshot'/target)
 if r['upstream_state']=='absent':ac.register_file(new,target,upstream_state='absent')
 assert sha(old/'snapshot'/target)==sha(new/'snapshot'/target)
s['candidate_dirs']['candidate']=str(new.relative_to(ROOT));s['roots']['candidate']=str((new/'snapshot').relative_to(ROOT));save(ART/'stage.json',s)
p=Path(__file__).with_name('freeze.py');text=p.read_text().replace("'candidate_id':arm", "'candidate_id':read(d/'candidate.json')['candidate_id']");p.write_text(text)
print('Exact tested bytes retained in',new)
