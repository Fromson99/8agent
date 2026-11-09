"""Freeze criteria, the 3-turn case and the exact candidate arm before any model call.

Usage: setup.py design
Candidate = selected MAIN170 inventory with the guided reading/continuation work-code files
(byte-equal to the isolated copy that passed the contract checks) and re-pinned engine manifests.
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==170 and ptr['release_id']=='structure-catalogue-20261106-r1'
rel=read(ROOT/ptr['manifest_path']);S=ROOT/rel['code_root'];files=rel['files']
assert len(files)==536 and all(sha(S/n)==h for n,h in files.items())
LA='02_BACKEND/semantic_runtime/legal_agent/'
CHANGED=[LA+n+'.py' for n in ('guided_navigation','law_navigation','decision_projection','memory_rag','corrected_memory',
         'memory_methods','guided_answer','completion_execution','law_candidates','connection_scope')]+['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json',
         '02_BACKEND/semantic_runtime/oracle_query_plans.py','02_BACKEND/semantic_runtime/legal_agent/output_contract.py']
TESTED=ROOT/'09_ARTIFACTS/AUDITS/20261106-guided-followup-reads/main_prep/staged170f'
STAGED=read(ROOT/'09_ARTIFACTS/AUDITS/20261106-guided-followup-reads/main_prep/staged170f.json')
assert STAGED['base_release_id']==ptr['release_id'] and all(sha(TESTED/n)==h for n,h in STAGED['files'].items())
assert all(n in files for n in CHANGED)
# Candidate bytes come from the contract-tested isolated copy. Working-tree edits by other sessions made after
# that copy (not tested here) are recorded and excluded.
CONCURRENT={n:{'working_tree':sha(ROOT/n),'tested':sha(TESTED/n)} for n in CHANGED if sha(ROOT/n)!=sha(TESTED/n)}
PINS=['00_SYSTEM/PIPELINE.json',*sorted(n for n in files if n.startswith('02_BACKEND/ENGINES/'))]
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'1,2,3 전부다 수정해봐 그리고 실험 / 두단계로 쪼개고 그리고 우리 중복되는거 이런거 다 빼버리고 멀티턴 딱 잘돌게 진행해줘 (ADR-1444 결과의 남은 문제 수정 후 같은 사례 재확인)',


 'scope':'Actual local root service with the frozen candidate (MAIN170 + guided reading work code r5 (two-step resolver, bounded READ rounds, answer-first scope questions), byte-identical to main_prep/staged170f), each cell run alone, no concurrent operator work by this session; other agent sessions may run checks, so worker swap is measured separately from host swap. Public Commercial Act and other public allowlist documents intersected with financial_team; internal forms are not sent. Default ontology OFF, isolated runtime, SQLite source. GENOS inaccessible; this is not a field-model result.',
 'hypothesis':'On the ADR-1444 tree: (1) free READ decisions are bounded per request (guided_read_rounds=4) and each READ may pick up to four candidates, and continuation reads stay on the question, so "이어서 읽어봐봐" no longer runs one READ per model call (ADR-1444 turn 3: 31 READ decisions, 37 calls, 602.8 s); (2) a SCOPE/SOURCE question asked after originals were read is shown after an answer from those originals, so "주주총회는?" and "정관을 바꿀 때는?" (ADR-1444: claims 0, asked whether to answer) are answered.',
 'primary_metric':'Every turn of the three multi-turn cases returns HTTP 200 with claims>0 (no UNKNOWN); shareholder turn 3 uses at most 4 READ decisions; board/shareholder/articles turns 2 and 3 state the 제368조① and 제434조 numbers from acquired originals. Zero chose-but-not-read.',
 'secondary':['Per turn HTTP status, physical calls, seconds, UNKNOWN count, method_id, executed stages',
              'Which chapter_title_matches entries the model chose to READ, and title-noise reads (e.g. 판결의/흠결의) ',
              'Answer article numbers not present in any acquired or listed location (guessed numbers)',
              'Turn-2/3 command choice (RESEARCH_CONTINUE vs PURPOSE_REVISE) and kept_points use',
              'Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
 'limits':{'physical_total':200,'per_cell_client_calls':80,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'ram_start_gib':6,'ram_floor_gib':3,'worker_rss_gib':5,'worker_swap_growth_mib':128,'host_swap_limits':'not applied: host swap holds idle pages of other programs; worker swap is measured','workers':1},
 'stop':'UNKNOWN/resource/source/ACL/code failure stops the cell and every later cell (no sending after an unknown outcome); no same-question retry. The field-photo 3-turn case runs first because it is the target of this change. Each cell runs alone after the machine is free; no concurrent operator work; another live experiment must not run at the same time.',
 'order':[[c,'candidate'] for c in ('shareholder-resolution-3turn','articles-amendment-2turn','board-shareholder-articles-3turn')],
 'quality_certified':False,'in_sample':True,
 'prior_attempt':'ADR-1444 (staged170d): all 8 turns HTTP 200, UNKNOWN 0, two-step resolver 2-3 s per follow-up; shareholder turn 1 368①+434, turn 2 ANSWER_PRESENT 15.4 s, turn 3 31 READ decisions/37 calls/602.8 s; articles 2/2 answered; board case turns 2-3 ASK_USER after reading (claims 0).',
 'prior_observation':'Field photos 2026-11-06 (GENOS internal model, MAIN161 code serving, SPAC form available): turn 1 SPAC form only; turn 2 located 368/369 titles but did not read them; turn 3 "이어서 읽어봐봐" re-searched and read 517/518/519. Not the same model, documents or code; context only.'}
cases=[{'id':'shareholder-resolution-3turn','document_ids':public,'steps':[
  {'number':1,'question':'주주총회 결의 요건','mode':'외규'},
  {'number':2,'question':'어어 상법상 주주총회 결의 요건을 확인해줘','mode':'외규'},
  {'number':3,'question':'이어서 읽어봐봐','mode':'외규'}]},
 {'id':'board-resolution','document_ids':public,'steps':[{'number':1,'question':'상법상 이사회 결의는 어떻게 해?','mode':'외규'}]},
 {'id':'dissolution-resolution','document_ids':public,'steps':[{'number':1,'question':'주식회사를 해산하려면 주주총회에서 어떤 결의가 필요해?','mode':'외규'}]},
 {'id':'capital-reduction-resolution','document_ids':public,'steps':[{'number':1,'question':'주식회사가 자본금을 줄이려면 어떤 결의가 필요해?','mode':'외규'}]},
 {'id':'articles-amendment-2turn','document_ids':public,'steps':[
  {'number':1,'question':'상법상 정관 변경 요건 알려줘','mode':'외규'},
  {'number':2,'question':'종류주식을 발행한 회사면 뭐가 더 필요해?','mode':'외규'}]}]
cases.append({'id':'board-shareholder-articles-3turn','document_ids':public,'steps':[
  {'number':1,'question':'상법상 이사회 결의는 어떻게 해?','mode':'외규'},
  {'number':2,'question':'주주총회는?','mode':'외규'},
  {'number':3,'question':'정관을 바꿀 때는?','mode':'외규'}]})
ORDER=['shareholder-resolution-3turn','articles-amendment-2turn','board-shareholder-articles-3turn']
cases=[next(c for c in cases if c['id']==i) for i in ORDER]
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'User-directed public-law experiment, three multi-turn cases (eight utterances); intersect current financial team. No internal documents or grading answers are sent.'})
REF={'shareholder-resolution-3turn':{'originals':['상법 제368조제1항','상법 제434조'],'numbers':['과반수','4분의 1','3분의 2','3분의 1']},
 'board-resolution':{'originals':['상법 제391조제1항'],'numbers':['과반수']},
 'dissolution-resolution':{'originals':['상법 제518조','상법 제434조'],'numbers':['3분의 2','3분의 1']},
 'capital-reduction-resolution':{'originals':['상법 제438조','상법 제434조','상법 제368조제1항'],'numbers':['3분의 2','3분의 1'],'also':'결손 보전 감소는 제368조제1항 결의'},
 'articles-amendment-2turn':{'originals':['상법 제433조','상법 제434조','상법 제435조'],'numbers':['3분의 2','3분의 1'],'turn2':'제435조 종류주주총회 결의(3분의 2·그 종류 발행주식총수 3분의 1)'}}
REF['board-shareholder-articles-3turn']={'originals':['상법 제391조제1항','상법 제368조제1항','상법 제433조','상법 제434조'],
  'numbers':['과반수','4분의 1','3분의 2','3분의 1'],'turns':{'1':'제391조① 이사 과반수 출석·출석이사 과반수','2':'제368조①(제434조 특별결의 언급 가능)','3':'제433조① 주주총회 결의, 제434조 3분의 2·3분의 1'}}
put(DES/'grading-reference.json',{'cases':REF,'product_input':False,'source':'registered original text, local store 7bbe815ff43b6635 (units 1403/1512/1769/1772/1773/1780/2169)'})
transport=ART/'transport';transport.mkdir(exist_ok=True)
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=[criteria['primary_metric'],*criteria['secondary']],
    failure_criteria=[criteria['stop'],'A model-chosen located original stays unread in its request','Answer states numbers not in an acquired original'],
    criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stage_plan=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stage_plan,'candidate':stage_plan}
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Reference only: field photos (MAIN161 code serving, GENOS internal model), not executed here',controls='Same question wording')
 else:arm.update(changes='ADR-1444 tree plus bounded free READ rounds and answer-first scope questions (staged170f bytes); '+str(len(CHANGED))+' files vs MAIN170 plus re-pinned engine manifests',controls='Same source generation; MAIN170 selected and unchanged')
m['dataset'].update(name='Commercial Act resolution requirements: three multi-turn cases (field-photo 3-turn, articles 2-turn, board/shareholder/articles 3-turn)',version='frozen-v1',
    frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for row,case in zip(m['questions'],cases):
 p=ADR/'실험'/row['file']
 p.write_text(f"# {case['id']}\n\n## 1. 실행 메타\n\ncandidate=MAIN170 + guided reading work r5: two-step resolver, bounded READ rounds, answer-first scope questions (unpromoted, = main_prep/staged170f); actual root service; Qwen3.8 Parasail FP8, reasoning none, no output cap; isolated runtime.\n\n## 2. 사용자 질문 원문\n\n"+'\n\n'.join(str(x['number'])+'턴: '+x['question'] for x in case['steps'])+"\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n"+', '.join(REF[case['id']]['originals'])+" 원문 확보와 공개 답변 수치("+', '.join(REF[case['id']]['numbers'])+")를 직접 대조. grading-reference.json은 제품 입력 비공개.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/<case>-<arm>/canonical 및 raw 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/"+case['id']+"-<arm>/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n각 셀 generations.json 및 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n채점 모델0; 원문/행동/실제 전송/답변 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 row['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
# Candidate snapshot: release bytes, then the tested work-code files, then engine pins re-bound.
inventory=dict(files)
can=ac.snapshot(ADR,'candidate',list(inventory),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot'
for n in inventory:
 shutil.copyfile((TESTED if n in CHANGED else S)/n,snap/n)
pipeline_path=snap/'00_SYSTEM/PIPELINE.json';config=json.loads(pipeline_path.read_text())
for name,entry in config['engines'].items():
 path=snap/entry['manifest'];manifest=json.loads(path.read_text())
 for relative in list(manifest.get('files',{})):manifest['files'][relative]=sha(snap/relative)
 path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(path)
pipeline_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
inventory={n:sha(snap/n) for n in files}
changed=sorted(n for n in files if inventory[n]!=files[n])
assert inventory==STAGED['files'],'candidate must equal the staged promotion tree'
assert set(CHANGED)<=set(changed) and set(changed)<=set(CHANGED)|set(PINS),changed
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
desc={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main170':changed,'work_code_files':CHANGED,
 'tested_copy':str(TESTED),'excluded_concurrent_working_tree_edits':CONCURRENT,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'arm-candidate.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],
    runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'arm-candidate.json',DES/'grading-reference.json']
put(ART/'preparation-issues.json',[])
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0,'candidate_changed_files':changed})
print('FROZEN candidate',len(changed),'files changed vs MAIN170 (work code',len(CHANGED),'+ pins);',len(cases),'cases; model0')
