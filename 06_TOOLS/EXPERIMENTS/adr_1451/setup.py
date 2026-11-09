"""ADR-1451: ADR-1448 field 3-turn case and turn-2 checker disagreement injection, candidate = stage r9 (MAIN176 + six files)."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1448-multiturn-new-topic-branch-qwen/artifacts/design'
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==176
rel=read(ROOT/ptr['manifest_path']);files=rel['files']
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r9/staged'
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'baseline_cell':'04_EXPERIMENTS/ADR/ADR-1448-multiturn-new-topic-branch-qwen/artifacts/public-live/topic-switch-3turn-baseline175-inject-r4'})
for name in ('live-cases.json','live-cases-injection.json','injection.json','authorization.json','grading-reference.json','provider-policy.json'):put(DES/name,read(P/name))
crit={**read(P/'criteria-injection.json'),'order':[['topic-switch-3turn','candidate','inject'],['topic-switch-3turn','candidate','plain']],
 'hypothesis':'With the related-question step (r9), the clarification after an injected turn-2 disagreement still names both branches, and "새롭게 질문을 해줘" starts the pending question as a new goal (all earlier questions judged unrelated); without injection turn 2 starts a new question and turn 3 is plain guidance.'}
put(DES/'criteria.json',crit)
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
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,'tested_copy':str(STAGED.relative_to(ROOT)),
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
m['lineage']['hypothesis_delta']=crit['hypothesis']
m['design'].update(hypothesis=crit['hypothesis'],primary_metric=crit['primary'],success_criteria=[crit['primary']],failure_criteria=[crit['stop']],
    criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['dataset'].update(name='Field-shaped topic switch (public documents): 3 turns, = ADR-1448',version='frozen-v1',frozen_source=str((DES/'live-cases-injection.json').relative_to(ROOT)),sha256=sha(DES/'live-cases-injection.json'),legal_version_checked=True,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*(DES/n for n in ('criteria.json','live-cases-injection.json','injection.json','authorization.json','provider-policy.json','arm-candidate.json','grading-reference.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('FROZEN candidate r9',len(changed),'files changed; model0')
