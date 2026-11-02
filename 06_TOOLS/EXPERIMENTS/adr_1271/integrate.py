"""Integrate the verified coordinate fix only; selected MAIN remains unchanged."""
from common import *
import shutil,difflib
test=read(ART/'candidate-contracts/result.json')
assert test['passed']==71 and test['failed']==0 and test['tests_unchanged']
assert (ART/'live-runner-summary.json').exists()
F=read(DES/'freeze.json');C=ROOT/F['code_root'];before=read(DES/'working-before.json')
changed=[n for n,h in before.items() if sha(C/n)!=h]
product='02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py'
assert len(changed)==32 and all(n==product or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in changed)
assert all(sha(ROOT/n)==before[n] for n in changed),'Concurrent root change; preserve it'
assert all(sha(C/n)==h for n,h in F['files'].items())
guard=read(DES/'transport-dependency-addendum.json')
assert all(sha(ROOT/n)==h for n,h in guard['files'].items())
out=ROOT/'09_ARTIFACTS/AUDITS/20261102-agent-loop-qwen-recovery/coordinate-fix'
out.mkdir(exist_ok=False);patch=[]
for n in changed:
 dest=out/'before'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
 patch+=list(difflib.unified_diff((ROOT/n).read_text().splitlines(True),(C/n).read_text().splitlines(True),fromfile='before/'+n,tofile='after/'+n))
for n in changed:shutil.copyfile(C/n,ROOT/n)
(out/'product-changes.patch').write_text(''.join(patch))
put(ART/'working-integration.json',{'changed':changed,'product_module_count':1,'pins':31,
 'candidate':str(C.relative_to(ROOT)),'frozen_revision':F['candidate_revision'],
 'source_equal':all(sha(ROOT/n)==sha(C/n) for n in changed),
 'active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256'],
 'guard_addendum_unchanged':True,'main_promoted':False})
print('Integrated source goal coordinate fix and 31 pins; selected MAIN130 unchanged')
