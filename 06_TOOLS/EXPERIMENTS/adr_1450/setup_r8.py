"""Candidate r8 (before any r8 model call): r7 cell judged the related questions correctly; turn 4 ended in a
clarification because 're-ask part of an earlier topic's answer' read as FOLLOWUP vs ANSWER_PRESENT. r8 adds two
prompt sentences (CONTINUE / RESEARCH_CONTINUE for re-asking part of a goal's answer, earlier topics included)."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r8/staged'
base=read(DES/'baseline.json');files=base['release']['files']
os.replace(DES/'arm-candidate.json',DES/'arm-candidate.r7-cell.json')
put(DES/'freeze-live.r7.json',read(DES/'freeze-live.json'))
put(DES/'candidate-r7-superseded.json',{'reason':'r7 cell (public-live/earlier-topics-4turn-candidate-r7): related judgments correct on turns 3 and 4; turn 3 answered, turn 4 clarification after ANSWER_PRESENT vs FOLLOWUP disagreement.'})
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'candidate-r8',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot';inventory={n:sha(STAGED/n) for n in files}
for n in files:shutil.copyfile(STAGED/n,snap/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
changed=sorted(n for n in files if inventory[n]!=files[n])
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,
 'tested_copy':str(STAGED.relative_to(ROOT)),'contract_regression':'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r8/regression-compare.json',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
old=read(DES/'freeze-live.json');files_f=dict(old['files'])
for p in [DES/'arm-candidate.json',Path(__file__).resolve()]:files_f[str(p.relative_to(ROOT))]=sha(p)
put(DES/'freeze-live.json',{**old,'files':files_f,'refrozen_for':'candidate r8 before any r8 model call; r7 freeze kept in freeze-live.r7.json'})
print('FROZEN candidate r8',len(changed),'files changed')
