"""Freeze criteria, cases and both exact code arms before any model call.

Usage: setup.py design   (MAIN157 selected; candidate = current working inventory)
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==160 and ptr['release_id']=='citation-roles-20261106-r1'
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];files=rel['files']
assert len(files)==533 and all(sha(C/n)==h for n,h in files.items())
main157=read(ROOT/'09_ARTIFACTS/AUDITS/20261106-continue-connection-main158/baseline.json')['release']['files']  # changes reported against MAIN157
assert set(main157)<=set(files)
working={n:sha(ROOT/n) for n in files};assert working==files,'working inventory must equal MAIN158 bytes'
changed=sorted(n for n in files if files[n]!=main157.get(n))
assert changed,'MAIN158 must differ from MAIN157'
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'계획하고 코드 수정하고 qwen으로 실험하고 메인에 반영하고 삼성메일로 쏴줘 (멀티턴 "계속 찾아줘" 미동작, 연결관계를 최종답변에서 묻기만 하는 문제)',
 'scope':'Actual local root service on selected MAIN160 (candidate arm only), run alone with no concurrent operator work. ADR-1416/1417/1418/1419 are prior observations. Swap growth is measured from after app load and health (run limit 128MiB); load growth limit 512MiB. Public Commercial Act, default ontology OFF, isolated runtime per cell. GENOS inaccessible.',
 'hypothesis_old':'MAIN157 answers the general charter-amendment quorum question from 433 only and asks whether to look further; a naive "어 계속 찾아줘" is not mapped to a resumed investigation. MAIN158 reads located needed sources without asking, bounds exploration per request, and maps the naive continuation to RESEARCH_CONTINUE.',
 'hypothesis':'Deterministic citation roles let the guided reader acquire forward citations and specifies/exception pairs without a model hop, so the rule cluster is the same whether the search lands on 433, 434 or an exception article; reuse/mutatis citers are not read; same-section titles expose uncited neighbours such as 435.',
 'primary_metric_old':'By the end of turn 2, the public answer states both special-resolution numbers (출석 주주 의결권 3분의 2 이상, 발행주식총수 3분의 1 이상) from an acquired original of 상법 제434조',
 'primary_metric':'Per case: charter-natural turn1 states the 434 numbers from an acquired 434 original; charter-434 acquires 433 paragraph 1 and reads no 434 borrower bodies; exception-542-4 acquires both 542-4 and 363 originals. 435 read-or-flag is observed, not a pass condition.',
 'secondary':['Turn 2 resumes investigation (method RESEARCH_CONTINUE or RESEARCH_REENTER at SELECT) instead of CLARIFY/HTTP error',
              'HTTP status of every turn, physical calls and seconds per turn, UNKNOWN count',
              'Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
 'limits':{'physical_total':200,'per_cell_client_calls':80,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'ram_start_gib':5,'ram_floor_gib':3,'swap_growth_mib':128,'workers':1},
 'stop':'UNKNOWN/resource/source/ACL/code failure (STOP_EXTERNAL or resource-stop) stops all later cells; no same-question retry. Order: charter-natural-continue then charter-433-continue, candidate arm. No concurrent operator work during cells.',
 'order':[['charter-natural-continue','candidate'],['charter-434-landing','candidate'],['exception-542-4-landing','candidate']],
 'quality_certified':False,'in_sample':True,
 'prior_observation':'ADR-1417 MAIN158: both questions turn1 READ 433 then ANSWER without a connection lookup, COVERED without the quorum numbers; turn2 resource-guard stop while the operator ran concurrent work (protocol deviation: cell2 ran despite the stop rule). ADR-1416 MAIN157: both questions answered from 433 only and asked to continue; natural turn2 "어 계속 찾아줘" CLARIFY (no investigation); 433 turn2 memory-resolve UNKNOWN/504 after 179.9s. 18 physical calls, reported 0.022188 USD.'}
steps=lambda q:[{'number':1,'question':q,'mode':'외규'},{'number':2,'question':'어 계속 찾아줘','mode':'외규'}]
one=lambda q:[{'number':1,'question':q,'mode':'외규'}]
cases=[{'id':'charter-natural-continue','document_ids':public,'steps':steps('정관을 변경할 때 주주총회 결의요건은 무엇인가요?')},
       {'id':'charter-434-landing','document_ids':public,'steps':one('상법 제434조에 따른 주주총회 결의요건을 알려줘.')},
       {'id':'exception-542-4-landing','document_ids':public,'steps':one('상장회사는 주주총회 소집통지를 전자적 방법의 공고로 갈음할 수 있나요?')}]
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'User-directed public Commercial Act multi-turn experiment, two question strings plus one continuation utterance; intersect current financial team. No internal documents or grading answers are sent.'})
put(DES/'grading-reference.json',{'charter':{'article':'상법 제434조','numbers':['3분의 2','3분의 1'],'pair':'433①'},'exception':{'articles':['상법 제542조의4','상법 제363조']},'product_input':False,
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
 if arm['id']=='baseline':arm.update(changes='Reference only: ADR-1416 MAIN157 cells, not executed here',controls='Same source generation, questions and continuation utterance')
 else:arm.update(changes='Continue contract, re-entry cursor/grant fixes, bounded guided auto-follow; '+str(len(changed))+' files vs MAIN157',controls='Same source generation, questions and continuation utterance; promoted unchanged as MAIN158 before its run')
m['dataset'].update(name='Charter amendment quorum, natural and 433 formulations, plus naive continuation',version='frozen-v1',
    frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for row,case in zip(m['questions'],cases):
 p=ADR/'실험'/row['file']
 p.write_text(f"# {case['id']}\n\n## 1. 실행 메타\n\ncandidate=MAIN160 citation-roles-20261106-r1; actual root service; Qwen3.8 Parasail FP8, reasoning none, no output cap; isolated runtime per cell.\n\n## 2. 사용자 질문 원문\n\n"+'\n\n'.join(str(x['number'])+'턴: '+x['question'] for x in case['steps'])+f"\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n정관 사례는 상법 제434조 두 결의 수치·433조①, 예외 사례는 542조의4와 363조 원문 확보를 직접 대조. grading-reference.json은 제품 입력 비공개.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/<case>-<arm>/canonical 및 raw 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{case['id']}-<arm>/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n각 셀 generations.json 및 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n채점 모델0; 원문/행동/실제 전송/답변 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
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
 descs[arm]={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main157':changed if arm=='candidate' else [],
  'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
 put(DES/('arm-'+arm+'.json'),descs[arm])
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(descs[a]['pin'],candidate_id=a,experiment_id=m['experiment_id'],arm_id=a,run_ids=['run-001'],
    runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py'))) for a in ('candidate',)])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'arm-candidate.json',DES/'grading-reference.json']
put(ART/'preparation-issues.json',[])
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0,'candidate_changed_files':changed})
print('FROZEN candidate MAIN160',len(changed),'changed files vs MAIN157; two cases x two turns; model0')
