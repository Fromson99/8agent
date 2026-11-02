"""Apply only tested candidate changes after fixed-code checks; never promote MAIN."""
from pathlib import Path
import json,sys,hashlib,shutil,difflib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1267-legacy-selection-contract-repair';D=A/'artifacts';C=R/json.loads((D/'candidate.json').read_text())['snapshot']
read=lambda p:json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
residual=read(D/'candidate-final/result.json');assert residual['passed']==92 and residual['failed']==0 and residual['tests_unchanged']
full=read(D/'current-loop-final/result.json');rerun=read(D/'current-loop-rerun/result.json')
assert full['passed']==487 and full['failed']==10
assert rerun['passed']==10 and rerun['failed']==0
assert {r['test'] for r in full['rows'] if r['outcome']=='failed'}=={r['test'] for r in rerun['rows'] if r['outcome']=='passed'}
assert full['code_hashes_before']==rerun['code_hashes_before']
assert all(v['code_unchanged'] and v['active_pointer_unchanged'] for v in (full,rerun))
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
if not read(C.parent/'candidate.json').get('revisions'):ac.freeze(C.parent)
assert not ac.validate(C.parent),ac.validate(C.parent)
metadata=read(C.parent/'candidate.json');revision=metadata['revisions'][-1]
before=read(R/'04_EXPERIMENTS/ADR/ADR-1266-agent-loop-recovery-qwen-live/artifacts/design/working-before.json')
changed=[n for n,h in before.items() if sha(C/n)!=h]
product='02_BACKEND/semantic_runtime/legal_agent/decision_projection.py'
assert len(changed)==38 and all(n==product or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in changed)
assert all(sha(R/n)==before[n] for n in changed),'Concurrent root changes: do not overwrite'
out=R/'09_ARTIFACTS/AUDITS/20261102-agent-loop-qwen-recovery';out.mkdir(parents=True,exist_ok=True);patch=[]
for n in changed:
 target=out/'before'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/n,target)
 patch+=list(difflib.unified_diff((R/n).read_text().splitlines(True),(C/n).read_text().splitlines(True),fromfile='before/'+n,tofile='after/'+n))
for n in changed:shutil.copyfile(C/n,R/n)
(out/'product-changes.patch').write_text(''.join(patch))
pin={'manifest_path':str((C.parent/'candidate.json').relative_to(R)),'manifest_sha256':sha(C.parent/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']}
receipt={'changed':changed,'product_module_count':1,'pins':37,'candidate':str(C.relative_to(R)),'frozen_revision':pin,'source_equal':all(sha(R/n)==sha(C/n) for n in changed),'active_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(R/'04_EXPERIMENTS/ADR/ADR-1266-agent-loop-recovery-qwen-live/artifacts/design/baseline.json')['pointer_sha256'],'main_promoted':False}
(D/'working-integration.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='repaired',experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(R)),runner_sha256=sha(Path(__file__).parent/'check.py'))],working_integration_after_synthetic_decision={'path':str((D/'working-integration.json').relative_to(R)),'main_promoted':False})
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print('Integrated',len(changed),'files, one product module, MAIN unchanged')
