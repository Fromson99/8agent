"""Candidate r2 (before any candidate model call): the exact contract-tested stage tree
(MAIN175 + three branch files, re-pinned with regenerated SQL plan metadata) and a MAIN175 baseline arm."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==175 and ptr['release_id']=='published-ontology-20261107-r1'
rel=read(ROOT/ptr['manifest_path']);S5=ROOT/rel['code_root'];files=rel['files']
assert all(sha(S5/n)==h for n,h in files.items())
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-new-topic-branch-r4/staged'
inventory={n:sha(STAGED/n) for n in files}
changed=sorted(n for n in files if inventory[n]!=files[n])
os.replace(DES/'arm-candidate.json',DES/'arm-candidate.r3-plain-cell.json')
os.replace(DES/'freeze-injection.json',DES/'freeze-injection.superseded-r3.json')
put(DES/'candidate-r3-superseded.json',{'reason':'r3 (stage 20261107-multiturn-new-topic-branch-r3) ran the plain candidate cell; that cell showed the new question still inheriting the previous turn source_category, so one prompt sentence was added (r4). Injection cells had not run.','r3_plain_cell':'public-live/topic-switch-3turn-candidate'})
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'candidate-r4',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot'
for n in files:shutil.copyfile(STAGED/n,snap/n)
assert {n:sha(snap/n) for n in files}==inventory
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
desc={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'base':'MAIN175 published-ontology-20261107-r1','changed_vs_main175':changed,
 'tested_copy':str(STAGED.relative_to(ROOT)),'contract_regression':'09_ARTIFACTS/AUDITS/20261107-multiturn-new-topic-branch-r4/regression-compare.json',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'arm-candidate.json',desc)
put(DES/'arm-baseline175.json',{'code_root':rel['code_root'],'selected_files':files,'note':'selected MAIN175 release code, immutable; baseline of the injection cells'})
paths=[Path(__file__).with_name('live_inject.py'),Path(__file__).with_name('setup_r4.py'),DES/'injection.json',DES/'live-cases-injection.json',DES/'criteria-injection.json',DES/'arm-candidate.json',DES/'arm-baseline175.json',DES/'candidate-files.json',Path(__file__)]
put(DES/'freeze-r4.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'model_calls_before_freeze':'baseline plain cell only (MAIN174)'})
print('FROZEN candidate r4',len(changed),'files changed vs MAIN175; baseline175 arm')
