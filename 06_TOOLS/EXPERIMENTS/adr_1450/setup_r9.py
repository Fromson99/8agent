"""Candidate r9 (before any r9 model call): r7/r8 turn 4 — the checker endorsed re-presenting the answer (valid=true)
but labelled it FOLLOWUP; r9 maps each command to its relation in the check prompt and defines PRESENTATION for
re-asking content already in the goal answer (resolver: ANSWER_PRESENT; RESEARCH_CONTINUE only for content not in it)."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r9/staged'
base=read(DES/'baseline.json');files=base['release']['files']
os.replace(DES/'arm-candidate.json',DES/'arm-candidate.r8-cell.json')
put(DES/'freeze-live.r8.json',read(DES/'freeze-live.json'))
put(DES/'candidate-r8-superseded.json',{'reason':'r8 cell (public-live/earlier-topics-4turn-candidate-r8): related judgments correct; turn 3 answered; turn 4 clarification (RESEARCH_CONTINUE vs FOLLOWUP). r8 prompt sentences reverted; r9 = r7 + relation mapping.'})
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'candidate-r9',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot';inventory={n:sha(STAGED/n) for n in files}
for n in files:shutil.copyfile(STAGED/n,snap/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
changed=sorted(n for n in files if inventory[n]!=files[n])
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,
 'tested_copy':str(STAGED.relative_to(ROOT)),'contract_regression':'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r9/regression-compare.json',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
old=read(DES/'freeze-live.json');files_f=dict(old['files'])
for p in [DES/'arm-candidate.json',Path(__file__).resolve()]:files_f[str(p.relative_to(ROOT))]=sha(p)
put(DES/'freeze-live.json',{**old,'files':files_f,'refrozen_for':'candidate r9 before any r9 model call; r8 freeze kept in freeze-live.r8.json'})
print('FROZEN candidate r9',len(changed),'files changed')
