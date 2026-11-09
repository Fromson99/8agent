"""Freeze criteria, the field-shaped 3-turn case and the arms before any model call.

Usage: setup.py design      (baseline = selected MAIN174 release code, unchanged)
       setup.py candidate   (candidate = MAIN174 + the branch fix files from the working tree, re-pinned)
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
step=sys.argv[1];assert step in ('design','candidate')
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
rel=read(ROOT/ptr['manifest_path']);S=ROOT/rel['code_root'];files=rel['files']
LA='02_BACKEND/semantic_runtime/legal_agent/'
if step=='design':
 DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
 assert ptr['generation']==174 and ptr['release_id']=='vector-structure-20261107-r1'
 assert all(sha(S/n)==h for n,h in files.items())
 put(DES/'baseline.json',{'pointer':ptr,'release':rel})
 public=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
 criteria={'authorization':'지금 멀티턴 하는데 사용자 질문을 이어서 가거나 새롭게 판단하거나 이 두가지 분기를 잘 못해 (현장 사진 3장, 2026-11-07)',
  'scope':'Actual local root service, isolated runtime, SQLite source, public allowlist documents intersected with financial_team; default profile (guided loop on, as in the field). Each cell runs alone. GENOS inaccessible; this is not a field-model result.',
  'hypothesis':'Field photos: turn 2, an unrelated new topic after a guided answer, ended in a clarification asking to continue the old question or change its purpose (no new-question option); turn 3, the reply "새롭게 질문을 해줘", was routed as plain guidance. Baseline (MAIN174) is run first to see where the branch fails with Qwen; the candidate makes the new-topic/continue branch explicit and applies the reply to a pending clarification.',
  'primary_metric':'Turn 2 starts a new question (CASE_START, a new goal) and answers from 주식회사 등의 외부감사에 관한 법률 (내부회계관리제도); no clarification. If a clarification is given, the turn-3 reply starts the pending question as a new goal. Every turn HTTP 200 and no UNKNOWN.',
  'secondary':['Per turn HTTP status, physical calls, seconds, UNKNOWN, method_id, goal_id, executed stages',
               'Resolver choice, checker request_relation/requested_task, and every rejected proposal with its issue codes',
               'Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
  'limits':{'physical_total':120,'per_cell_client_calls':60,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':2,'ram_start_gib':6,'ram_floor_gib':3,'worker_rss_gib':5,'worker_swap_growth_mib':128,'workers':1},
  'stop':'UNKNOWN/resource/source/ACL/code failure stops the cell and every later cell (no sending after an unknown outcome); no same-question retry. Baseline before candidate; one cell at a time.',
  'quality_certified':False,'in_sample':True,
  'prior_observation':'Field photos 2026-11-07 (GENOS internal model, B05 risk chatbot, guided mode): T1 "내규: 현업에서 EXIT 분양률을 초과하는 부동산 PF 딜 심사를 요청했는데 의사결정기구가 어떻게 될까?" 193.2 s answered; T2 "내부회계관리제도 구축의무와 그 면제 기준은 무엇인가요" 21.3 s/3 calls -> "이번 요청을 기존 조사에 연결하는 판단이 맞지 않아 적용하지 않았습니다 ... 기존 질문의 조사를 이어갈까요, 아니면 이번에 확인할 목적을 바꿀까요?"; T3 "새롭게 질문을 해줘" 7.0 s/1 call -> "구체적인 질문을 입력해 주세요 ...". Internal documents; not sent here.'}
 cases=[{'id':'topic-switch-3turn','document_ids':public,'steps':[
   {'number':1,'question':'위험관리위원회는 어떤 사항을 심의·의결해?','mode':'외규'},
   {'number':2,'question':'내부회계관리제도 구축의무와 그 면제 기준은 무엇인가요','mode':None},
   {'number':3,'question':'새롭게 질문을 해줘','mode':None}]}]
 put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
 put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
 assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
 put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'Public-law reproduction of the field branch failure (three utterances); intersect current financial team. No internal documents or grading answers are sent.'})
 put(DES/'grading-reference.json',{'cases':{'topic-switch-3turn':{'turn1':'금융회사의 지배구조에 관한 법률 위험관리위원회 심의·의결 사항','turn2':'주식회사 등의 외부감사에 관한 법률 제8조(내부회계관리제도의 운영 등) and its exemption in the enforcement decree; a new goal, not the turn-1 goal'}},'product_input':False})
 transport=ART/'transport';transport.mkdir(exist_ok=True)
 pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
 for name in pins['files']:
  target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
 put(transport/'transport-pins.json',pins)
 put(DES/'arm-baseline.json',{'code_root':rel['code_root'],'selected_files':files,'changed_vs_main174':[],'note':'selected MAIN174 release code, immutable release directory'})
 m=read(ADR/'실험/manifest.json')
 m['lineage']['hypothesis_delta']=criteria['hypothesis']
 m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=[criteria['primary_metric'],*criteria['secondary']],
     failure_criteria=[criteria['stop'],'Turn 2 continues or rewrites the turn-1 goal','Turn 2 asks to continue/change purpose without a new-question option'],
     criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
 m['dataset'].update(name='Field-shaped topic switch (public documents): 3 turns',version='frozen-v1',
     frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
 m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
 put(ADR/'실험/manifest.json',m)
 paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'arm-baseline.json',DES/'grading-reference.json']
 put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
 print('FROZEN baseline=MAIN174; model0')
else:
 assert not (DES/'arm-candidate.json').exists()
 base=read(DES/'baseline.json');B=ROOT/base['release']['code_root'];files=base['release']['files']
 CHANGED=sorted(read(DES/'candidate-files.json')['files'])
 m=read(ADR/'실험/manifest.json')
 inventory=dict(files)
 can=ac.snapshot(ADR,'candidate',list(inventory),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
 snap=can/'snapshot'
 for n in inventory:shutil.copyfile((ROOT if n in CHANGED else B)/n,snap/n)
 pipeline_path=snap/'00_SYSTEM/PIPELINE.json';config=json.loads(pipeline_path.read_text())
 for name,entry in config['engines'].items():
  path=snap/entry['manifest'];manifest=json.loads(path.read_text())
  for relative in list(manifest.get('files',{})):manifest['files'][relative]=sha(snap/relative)
  path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(path)
 pipeline_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
 inventory={n:sha(snap/n) for n in files}
 changed=sorted(n for n in files if inventory[n]!=files[n])
 assert set(CHANGED)<=set(changed),changed
 ac.freeze(can);assert not ac.validate(can),ac.validate(can)
 cm=read(can/'candidate.json');rev=cm['revisions'][-1]
 snapshot=can/'revisions'/rev['revision_id']/'snapshot'
 assert all(sha(snapshot/n)==h for n,h in inventory.items())
 desc={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main174':changed,'work_code_files':CHANGED,
  'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
 put(DES/'arm-candidate.json',desc)
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],
     runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
 put(ADR/'실험/manifest.json',m)
 put(DES/'freeze-candidate.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in [DES/'arm-candidate.json',DES/'candidate-files.json',*Path(__file__).parent.glob('*.py')]},'model_calls_before_freeze':'baseline only'})
 print('FROZEN candidate',len(changed),'files changed vs MAIN174')
