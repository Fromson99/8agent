"""Freeze criteria, cases and both exact code arms before any model call.

Usage: setup.py design   (MAIN161 selected; candidate = selected inventory)
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==161 and ptr['release_id']=='unread-notes-20261106-r1'
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==533 and all(sha(C/n)==h for n,h in files.items())
parallel=read(ROOT/'09_ARTIFACTS/AUDITS/20261106-unread-notes-main161/excluded-parallel.json')['working_tree_differs_from_main160_but_excluded']
main157=read(ROOT/'09_ARTIFACTS/AUDITS/20261106-unread-notes-main161/baseline.json')['release']['files']  # changes reported against MAIN160
assert set(main157)<=set(files)
working={n:sha(ROOT/n) for n in files if n not in parallel};assert working=={n:h for n,h in files.items() if n not in parallel},'working inventory must equal MAIN161 bytes (parallel edits excluded)'
changed=sorted(n for n in files if files[n]!=main157.get(n))
assert changed,'MAIN161 must differ from MAIN160'
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'1,2둘다 해주고 2에서는 미확인 내용을 상세하게 써줘 / 어떤 조문에 연결된 이 조문을 지금은 현재 ~~한 이유로 읽을 필요가 없다고 판단함 필요하면 말씀하세요 / 미확인 조문은 출처처럼 GENOS에서 눌러서 나오게 (이전 지시: 계획·수정·qwen 실험·메인 반영·삼성메일)',
 'scope':'Actual local root service on selected MAIN161 (candidate arm only), run alone. ADR-1420 MAIN160 is the prior observation. Swap growth measured from after app load (run 128MiB, load 512MiB). Public Commercial Act, default ontology OFF, isolated runtime. GENOS inaccessible. A parallel session edit to oracle_query_service.py is excluded from MAIN161 and not swapped; the loaded-module byte check fails the cell if that file is loaded.',
 'hypothesis':'MAIN161 reads same-section articles whose opening text contains every content word of a small section heading (max 2) within the shared role-chain budget, so the general charter question reads 435 on turn 1 without a model hop; connections seen but not read are written as "X에 연결된 Y: 지금은 ~ 읽을 필요가 없다고 판단했습니다 / 아직 읽지 않았습니다" with their original shown separately as not evidence; a follow-up asking to read them resumes investigation.',
 'primary_metric':'Turn 1: an acquired original of 상법 제435조 and 제434조, both 434 numbers (3분의 2, 3분의 1) in the public answer, and an unread-connection section that names an unread connected article with an origin and a reason. Turn 2 resumes investigation (not CLARIFY/HTTP error).',
 'secondary':['Workflow display renders the unread-article accordion from the actual response (text hash matches)',
              'HTTP status, physical calls, seconds per turn, UNKNOWN count',
              'Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
 'limits':{'physical_total':80,'per_cell_client_calls':80,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':2,'ram_start_gib':5,'ram_floor_gib':3,'swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN/resource/source/ACL/code failure stops the cell; no same-question retry. No concurrent operator work during the cell.',
 'order':[['charter-natural-unread','candidate']],
 'quality_certified':False,'in_sample':True,
 'prior_observation':'ADR-1420 MAIN160: charter-natural turn1 read 433/434 pair and 363, not 435 (seen as a read candidate and a same-section title); turn2 "어 계속 찾아줘" added 435. 434 landing listed 27 borrowers as counts. 19 physical calls, reported 0.04872432 USD.'}
steps=lambda q:[{'number':1,'question':q,'mode':'외규'},{'number':2,'question':'어 계속 찾아줘','mode':'외규'}]
one=lambda q:[{'number':1,'question':q,'mode':'외규'}]
cases=[{'id':'charter-natural-unread','document_ids':public,'steps':[{'number':1,'question':'정관을 변경할 때 주주총회 결의요건은 무엇인가요?','mode':'외규'},
         {'number':2,'question':'확인하지 않은 연결 조문도 읽어줘','mode':'외규'}]}]
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'User-directed public Commercial Act experiment, one question plus one follow-up utterance; intersect current financial team. No internal documents or grading answers are sent.'})
put(DES/'grading-reference.json',{'charter':{'article':'상법 제434조','numbers':['3분의 2','3분의 1'],'pair':'433①','same_section':'상법 제435조'},'product_input':False,
 'source':'ADR-1415 grading-source-locations.json (registered original)','path':'04_EXPERIMENTS/ADR/ADR-1415-main156-charter-quorum-qwen/artifacts/design/grading-source-locations.json'})
transport=ART/'transport';transport.mkdir(exist_ok=True)
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=[criteria['primary_metric'],*criteria['secondary']],
    failure_criteria=[criteria['stop'],'Candidate turn 2 does not resume investigation','Candidate answer states numbers not in an acquired original'],
    criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stage_plan=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stage_plan,'candidate':stage_plan}
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Reference only: ADR-1420 MAIN160 cell, not executed here',controls='Same source generation and question')
 else:arm.update(changes='Same-section reading and unread-connection notes/cards; '+str(len(changed))+' files vs MAIN160',controls='Same source generation and question; promoted unchanged as MAIN161 before its run')
m['dataset'].update(name='Charter amendment quorum natural question plus unread-connection follow-up',version='frozen-v1',
    frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for row,case in zip(m['questions'],cases):
 p=ADR/'실험'/row['file']
 p.write_text(f"# {case['id']}\n\n## 1. 실행 메타\n\ncandidate=MAIN161 unread-notes-20261106-r1; actual root service; Qwen3.8 Parasail FP8, reasoning none, no output cap; isolated runtime per cell.\n\n## 2. 사용자 질문 원문\n\n"+'\n\n'.join(str(x['number'])+'턴: '+x['question'] for x in case['steps'])+f"\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n상법 제434조 두 결의 수치·433조①·같은 절 435조 원문 확보와 미확인 연결 안내 문장을 직접 대조. grading-reference.json은 제품 입력 비공개.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/<case>-<arm>/canonical 및 raw 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{case['id']}-<arm>/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n각 셀 generations.json 및 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n채점 모델0; 원문/행동/실제 전송/답변 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 row['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
descs={}
for arm,source,inventory in (('candidate',C,files),):
 can=ac.snapshot(ADR,arm,list(inventory),experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
 for n,h in inventory.items():
  if sha(can/'snapshot'/n)!=h:shutil.copyfile(source/n,can/'snapshot'/n)
 ac.freeze(can);assert not ac.validate(can),ac.validate(can)
 cm=read(can/'candidate.json');rev=cm['revisions'][-1]
 snapshot=can/'revisions'/rev['revision_id']/'snapshot'
 assert all(sha(snapshot/n)==h for n,h in inventory.items())
 descs[arm]={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main160':changed,'parallel_excluded':parallel,
  'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
 put(DES/('arm-'+arm+'.json'),descs[arm])
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(descs[a]['pin'],candidate_id=a,experiment_id=m['experiment_id'],arm_id=a,run_ids=['run-001'],
    runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py'))) for a in ('candidate',)])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'arm-candidate.json',DES/'grading-reference.json']
put(ART/'preparation-issues.json',[])
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0,'candidate_changed_files':changed})
print('FROZEN candidate MAIN161',len(changed),'changed files vs MAIN160; one case x two turns; model0')
