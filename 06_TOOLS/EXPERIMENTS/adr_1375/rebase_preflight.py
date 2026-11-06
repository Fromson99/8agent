"""Keep failed preparation and take a fresh snapshot when another workspace patch lands."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
desc=read(DES/'candidate-path.json'); old=ROOT/desc['candidate']; before=read(DES/'working-before.json')
product=desc['product_files'][0]
working={n:sha(ROOT/n) for n in desc['files']}
assert working[product]==before[product], 'Concurrent editing of this product'
changes=[n for n in working if working[n]!=before[n]]
put(ART/'initial-freeze-stopped.json',{'reason':'upstream changed before freeze','changed_paths':changes,'calls':0})
new=ac.snapshot(ADR,'repaired-current',desc['files'],experiment_id=read(ADR/'실험/manifest.json')['experiment_id'],arm_id='repaired',run_ids=['run-001'])
assert all(sha(new/'snapshot'/n)==h for n,h in working.items())
shutil.copyfile(old/'snapshot'/product,new/'snapshot'/product)
put(DES/'working-before.json',working)
put(DES/'candidate-path.json',{**desc,'candidate':str(new.relative_to(ROOT))})
