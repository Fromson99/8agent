"""Freeze criteria, the 4-turn chat and both arms before any model call.

baseline  = selected MAIN176 release code (immutable release directory)
candidate = the contract-tested stage tree 20261107-multiturn-related-questions-r5 (MAIN176 + six files)
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==176 and ptr['release_id']=='agent-roundtrips-20261107-r1'
rel=read(ROOT/ptr['manifest_path']);S=ROOT/rel['code_root'];files=rel['files']
assert all(sha(S/n)==h for n,h in files.items())
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r5/staged'
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'내가 생각한 방향은 질문이 10개가 있으면 그중에서 연관된 질문을 선택을해 여러개도 가능하고 그리고 그 내용을 가지고 내 질문과 함께 어떻게 할지 판단하는거야',
 'scope':'Actual local root service, isolated runtime, SQLite source, public allowlist documents intersected with financial_team, default profile (guided loop on). One cell at a time; baseline before candidate. Not a field-model result.',
 'hypothesis':'Each new question runs in its own investigation, so MAIN176 shows the resolver only the current topic: a later turn that points back to an earlier topic by position ("첫 번째 질문") cannot reach it. The candidate lists every earlier question of the chat, chooses the related ones (several possible) and decides from them; continuing an earlier question returns to its investigation.',
 'primary_metric':'Turn 3 selects the turn-1 question and answers about 위험관리위원회 composition from 금융회사의 지배구조에 관한 법률 (not 내부회계); turn 4 selects the turn-2 question and answers the asset threshold of the 내부회계관리제도 exemption from 외감법/시행령. HTTP 200, UNKNOWN 0.',
 'secondary':['Per turn method, goal, investigation (internal session), physical calls, seconds','Selected related questions and the decision menu','Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
 'limits':{'physical_total':120,'per_cell_client_calls':60,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':2,'ram_start_gib':6,'ram_floor_gib':3,'worker_rss_gib':5,'worker_swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN/resource/source/ACL/code failure stops the cell and every later cell; no same-question retry.',
 'quality_certified':False,'in_sample':True}
cases=[{'id':'earlier-topics-4turn','document_ids':public,'steps':[
  {'number':1,'question':'위험관리위원회는 어떤 사항을 심의·의결해?','mode':'외규'},
  {'number':2,'question':'내부회계관리제도 구축의무와 그 면제 기준은 무엇인가요','mode':None},
  {'number':3,'question':'첫 번째 질문에서 말한 위원회는 어떻게 구성해야 해?','mode':None},
  {'number':4,'question':'그럼 아까 면제 기준에서 자산총액은 얼마 미만이었지?','mode':None}]}]
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'Public-law 4-turn chat; intersect current financial team. No internal documents or grading answers are sent.'})
put(DES/'grading-reference.json',{'cases':{'earlier-topics-4turn':{'turn3':'금융회사의 지배구조에 관한 법률 위험관리위원회 구성(위원회 구성 일반 규정 포함)','turn4':'외감법 제8조제1항 단서 직전 사업연도 말 자산총액 1천억원 미만(주권상장법인 제외), 시행령 제9조 5천억원 미만 기준'}},'product_input':False})
transport=ART/'transport';transport.mkdir(exist_ok=True)
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
put(DES/'arm-baseline.json',{'code_root':rel['code_root'],'selected_files':files,'note':'selected MAIN176 release code'})
m=read(ADR/'실험/manifest.json')
can=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot'
inventory={n:sha(STAGED/n) for n in files}
for n in files:shutil.copyfile(STAGED/n,snap/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
changed=sorted(n for n in files if inventory[n]!=files[n])
put(DES/'arm-candidate.json',{'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main176':changed,
 'tested_copy':str(STAGED.relative_to(ROOT)),'contract_regression':'09_ARTIFACTS/AUDITS/20261107-multiturn-related-questions-r5/regression-compare.json',
 'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=[criteria['primary_metric'],*criteria['secondary']],
    failure_criteria=[criteria['stop']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['dataset'].update(name='Earlier-topic 4-turn chat (public documents)',version='frozen-v1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'arm-baseline.json',DES/'arm-candidate.json',DES/'grading-reference.json']
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('FROZEN baseline=MAIN176, candidate',len(changed),'files changed; model0')
