"""ADR-1450: the ADR-1449 chat and criteria, candidate = stage 20261107-multiturn-related-questions-r7 (MAIN176 + six files)."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1449-multiturn-related-questions-qwen/artifacts/design'
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==176
rel=read(ROOT/ptr['manifest_path']);S=ROOT/rel['code_root'];files=rel['files']
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r7/staged'
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'baseline_cell':'04_EXPERIMENTS/ADR/ADR-1449-multiturn-related-questions-qwen/artifacts/public-live/earlier-topics-4turn-baseline'})
criteria={**read(P/'criteria.json'),'hypothesis':'r7 judges each earlier question yes/no after the overall reason; the r5/r6 free list was returned empty while the reason named the related question. Expected: turn 3 continues the turn-1 question, turn 4 the turn-2 question.'}
put(DES/'criteria.json',criteria)
for name in ('live-cases.json','authorization.json','grading-reference.json','provider-policy.json'):put(DES/name,read(P/name))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
transport=ART/'transport';transport.mkdir(exist_ok=True)
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot';inventory={n:sha(STAGED/n) for n in files}
for n in files:shutil.copyfile(STAGED/n,snap/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
changed=sorted(n for n in files if inventory[n]!=files[n])
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,
 'tested_copy':str(STAGED.relative_to(ROOT)),'contract_regression':'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r7/regression-compare.json',
 'oracle_guard':'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r7/oracle-guard/보고서.txt',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=[criteria['primary_metric'],*criteria['secondary']],
    failure_criteria=[criteria['stop']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['dataset'].update(name='Earlier-topic 4-turn chat (public documents, = ADR-1449)',version='frozen-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*(DES/n for n in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','arm-candidate.json','grading-reference.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('FROZEN candidate r7',len(changed),'files changed; model0')
