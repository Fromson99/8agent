from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
m=read(ADR/'실험/manifest.json');before=read(DES/'working-before.json')
old=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1251/generalized/snapshot'
changes=[n for n,h in before.items() if sha(ROOT/n)!=h]
own=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('need_continuity.py','read_judgment_final.py','output_contract.py')]
assert not set(changes)&set(own),'Concurrent edits overlap owned files'
# New candidate records the ACTUAL current upstream hashes. Explicitly preserve
# the already-tested isolated baseline; do not change or revert working files.
new=ac.snapshot(ADR,'generalized-isolated',list(before),experiment_id=m['experiment_id'],arm_id='generalized',run_ids=['run-001'])/'snapshot'
for n in before:shutil.copyfile(old/n,new/n)
put(DES/'isolation.json',{'reason':'Initial freeze rejected concurrent unrelated ontology workspace edits. New candidate records current upstream, then deliberately retains original tested experiment scope. No workspace rollback.','initial_freeze_error':'present upstream changed before candidate freeze: completion_execution.py','external_model_calls_before_failure':0,'concurrent_paths':changes,'working_hashes':{n:sha(ROOT/n) for n in before},'isolated_files':{n:sha(new/n) for n in before},'own_product_paths':own,'old_candidate_preserved':str(old.relative_to(ROOT)),'new_candidate':str(new.parent.relative_to(ROOT))})
for name in ('freeze.py','repin.py','check.py'):
 p=Path(__file__).parent/name;s=p.read_text().replace('adr_1251/generalized','adr_1251/generalized-isolated').replace("candidate_id='generalized'","candidate_id='generalized-isolated'");p.write_text(s)
print('Isolated',len(before),'files; preserved',len(changes),'unrelated working changes')
