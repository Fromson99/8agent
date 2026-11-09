"""Candidate r6 (before any r6 model call): r5 cell showed the selector explaining a related question in
its reason while returning an empty list; r6 chooses by question order with the reason first."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r6/staged'
base=read(DES/'baseline.json');files=base['release']['files']
os.replace(DES/'arm-candidate.json',DES/'arm-candidate.r5-cell.json')
put(DES/'candidate-r5-superseded.json',{'reason':'r5 cell: turn 3 first selection and both turn 4 selections returned related=[] while the reason named the related question; r6 selects by order (1..N) with reason first.','r5_cell':'public-live/earlier-topics-4turn-candidate'})
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'candidate-r6',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot';inventory={n:sha(STAGED/n) for n in files}
for n in files:shutil.copyfile(STAGED/n,snap/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
changed=sorted(n for n in files if inventory[n]!=files[n])
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,
 'tested_copy':str(STAGED.relative_to(ROOT)),'contract_regression':'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r6/regression-compare.json',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
print('FROZEN candidate r6',len(changed),'files changed')
