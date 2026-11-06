from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
x=read(DES/'candidate-path.json')
old=ROOT/x['candidate'];before=read(ART/'integration-current-base.json');products=x['product_files']
current={n:sha(ROOT/n) for n in before}
drift={n for n in before if current[n]!=before[n]}
assert not drift.intersection(products[:-1])
put(ART/'pre-freeze-drift.json',{'source':'first freeze rejected upstream drift before tests or model calls','paths':sorted(drift),'original_before':before,'previous_candidate':x['candidate']})
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'bound-review',list(current),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
assert all(sha(can/'snapshot'/n)==h for n,h in current.items())
for n in products[:-1]:shutil.copyfile(old/'snapshot'/n,can/'snapshot'/n)
put(ART/'integration-current-base.json',current);put(DES/'candidate-parent.json',{'selected_files':current})
put(DES/'candidate-path.json',{**x,'candidate':str(can.relative_to(ROOT))})
