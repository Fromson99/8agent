"""Freeze criteria, the 3-turn case and the exact candidate arm before any model call.

Usage: setup.py design
Candidate = selected MAIN166 inventory with the guided reading/continuation work-code files
(byte-equal to the isolated copy that passed the contract checks) and re-pinned engine manifests.
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(parents=True,exist_ok=True);assert not (DES/'freeze-live.json').exists()
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==166 and ptr['release_id']=='fts-literal-20261106-r1'
rel=read(ROOT/ptr['manifest_path']);S=ROOT/rel['code_root'];files=rel['files']
assert len(files)==535 and all(sha(S/n)==h for n,h in files.items())
LA='02_BACKEND/semantic_runtime/legal_agent/'
CHANGED=[LA+n+'.py' for n in ('guided_navigation','law_navigation','decision_projection','memory_rag','corrected_memory',
         'memory_methods','guided_answer','completion_execution','law_candidates','connection_scope')]+['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']
TESTED=Path('/tmp/a8-followup-iso166')
assert all(n in files for n in CHANGED)
assert all(sha(ROOT/n)==sha(TESTED/n) for n in CHANGED),'work code must equal the contract-tested isolated copy'
PINS=['00_SYSTEM/PIPELINE.json',*sorted(n for n in files if n.startswith('02_BACKEND/ENGINES/'))]
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
public=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
criteria={'authorization':'못읽는경우 이거 읽어야 겠다 있는경우에는 그거 읽게 강제해봐 그떄는 차감안되게 / 읽어야 겠다 했는데 못읽는경우 없어야해 / 수정해주고 qwen으로 실험해줘 (이전 지시: 한 번에 못 읽는 문제·멀티턴 LLM 판단·필요한 부분만 찾아 그 부분만 수정)',
 'scope':'Actual local root service with the frozen candidate (MAIN166 + guided reading/continuation work code), run alone, no concurrent operator work by this session; other agent sessions may run checks, so worker swap is measured separately from host swap. Public Commercial Act and Capital Markets Act among the public allowlist intersected with financial_team; internal forms are not sent. Default ontology OFF, isolated runtime, SQLite source. GENOS inaccessible; this is not a field-model result.',
 'hypothesis':'Articles of the same section whose title contains a word of the question are offered as READ candidates even in a large section (상법 제1관 28 articles), so reading 제363조 exposes 제368조 총회의 결의방법…; READ of a located candidate no longer spends the guided search allowance, and after the allowance only READ/ANSWER run; when the answer chooses located originals in next_reads, the server reads them in the same request without a search and the answer is written again; a same-purpose follow-up that names what to check continues the same investigation (RESEARCH_CONTINUE) and keeps unchanged earlier points.',
 'primary_metric':'Whether 상법 제368조 is offered as a same-section title match and read in turn 1. Zero cases where the model chose to read a located original (navigation READ or answer next_reads) and it was not read in that request (ANSWER_READ_REENTRY_UNAVAILABLE, a chosen read skipped, or a DECLINED read-only stop while that original stayed unread). Report per turn: whether 상법 제368조제1항 and 제434조 originals were acquired, and whether the public answer states 과반수·4분의 1 (ordinary) and 3분의 2·3분의 1 (special).',
 'secondary':['Per turn HTTP status, physical calls, seconds, UNKNOWN count, method_id, executed stages',
              'Answer-time forced reads (ANSWER_READ_REENTRY_PLANNED rounds) and navigation reads after the search limit',
              'Turn-2/3 command choice (RESEARCH_CONTINUE vs PURPOSE_REVISE) and kept_points use',
              'Source/ACL/wire mismatch 0; duplicate request adds 0 calls'],
 'limits':{'physical_total':120,'per_cell_client_calls':120,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'ram_start_gib':6,'ram_floor_gib':3,'worker_rss_gib':5,'worker_swap_growth_mib':128,'host_swap_limits':'not applied: host swap was full of idle pages of other programs (neo4j/java/other sessions) while 8+GiB RAM was available','workers':1},
 'stop':'UNKNOWN/resource/source/ACL/code failure stops the cell; no same-question retry. No concurrent operator work during the cell; another live experiment must not run at the same time.',
 'order':[['shareholder-resolution-3turn','candidate']],
 'quality_certified':False,'in_sample':True,
 'prior_attempt':'ADR-1434 (same case, no title matches): turn 1 forced 2 answer-chosen read rounds (4 originals, 0 chose-but-unread) but search landed on 제363조 and 제368조 was never offered; turn 2 memory-resolve provider blank 660 bytes/179.8s UNKNOWN. Earlier ADR-1427, ADR-1428, ADR-1430: same candidate/case; all resource stops before any model call (host swap +132.6MiB; +522.5MiB with worker swap 0; admission RAM 4.85GiB < 5GiB) while other sessions ran checks, tests and a live cell. 0 physical calls, no cost. ADR-1432 never reached admission (host swap full of idle pages; 0 calls). User directed an immediate run: the runner waits without model calls until available RAM >= 6GiB, then starts; in-run guard keeps RAM >= 3GiB, worker RSS <= 5GiB and worker swap growth <= 128MiB, without host swap limits.',
 'prior_observation':'Field photos 2026-11-06 (GENOS internal model, MAIN161 code serving, SPAC form available): turn 1 SPAC form only; turn 2 located 368/369 titles but did not read them; turn 3 "이어서 읽어봐봐" re-searched and read 517/518/519. Not the same model, documents or code; context only.'}
cases=[{'id':'shareholder-resolution-3turn','document_ids':public,'steps':[
  {'number':1,'question':'주주총회 결의 요건','mode':'외규'},
  {'number':2,'question':'어어 상법상 주주총회 결의 요건을 확인해줘','mode':'외규'},
  {'number':3,'question':'이어서 읽어봐봐','mode':'외규'}]}]
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases)
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
assert read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')==read(DES/'provider-policy.json')
put(DES/'authorization.json',{'request':criteria['authorization'],'documents':public,'scope':'User-directed public-law experiment, one question plus two follow-up utterances; intersect current financial team. No internal documents or grading answers are sent.'})
put(DES/'grading-reference.json',{'ordinary':{'article':'상법 제368조제1항','numbers':['과반수','4분의 1']},'special':{'article':'상법 제434조','numbers':['3분의 2','3분의 1']},
 'product_input':False,'source':'registered original text, local store 7bbe815ff43b6635 units 1404/1772'})
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
 else:arm.update(changes='Free guided READ, answer-chosen forced reads, follow-up continue_reads and kept_points; '+str(len(CHANGED))+' files vs MAIN166 plus re-pinned engine manifests',controls='Same source generation; MAIN166 selected and unchanged')
m['dataset'].update(name='Shareholders meeting resolution requirement, 3 turns as in the field photos',version='frozen-v1',
    frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for row,case in zip(m['questions'],cases):
 p=ADR/'실험'/row['file']
 p.write_text(f"# {case['id']}\n\n## 1. 실행 메타\n\ncandidate=MAIN166 + guided reading/continuation work code (unpromoted); actual root service; Qwen3.8 Parasail FP8, reasoning none, no output cap; isolated runtime.\n\n## 2. 사용자 질문 원문\n\n"+'\n\n'.join(str(x['number'])+'턴: '+x['question'] for x in case['steps'])+"\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n상법 제368조제1항(과반수·4분의 1)과 제434조(3분의 2·3분의 1) 원문 확보와 공개 답변 수치를 직접 대조. grading-reference.json은 제품 입력 비공개.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/<case>-<arm>/canonical 및 raw 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/"+case['id']+"-<arm>/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n각 셀 generations.json 및 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n채점 모델0; 원문/행동/실제 전송/답변 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 row['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
# Candidate snapshot: release bytes, then the tested work-code files, then engine pins re-bound.
inventory=dict(files)
can=ac.snapshot(ADR,'candidate',list(inventory),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
snap=can/'snapshot'
for n in inventory:
 shutil.copyfile((ROOT if n in CHANGED else S)/n,snap/n)
pipeline_path=snap/'00_SYSTEM/PIPELINE.json';config=json.loads(pipeline_path.read_text())
for name,entry in config['engines'].items():
 path=snap/entry['manifest'];manifest=json.loads(path.read_text())
 for relative in list(manifest.get('files',{})):manifest['files'][relative]=sha(snap/relative)
 path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(path)
pipeline_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
inventory={n:sha(snap/n) for n in files}
changed=sorted(n for n in files if inventory[n]!=files[n])
assert set(CHANGED)<=set(changed) and set(changed)<=set(CHANGED)|set(PINS),changed
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==h for n,h in inventory.items())
desc={'code_root':str(snapshot.relative_to(ROOT)),'selected_files':inventory,'changed_vs_main166':changed,'work_code_files':CHANGED,
 'tested_copy':str(TESTED),'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'arm-candidate.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],
    runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'arm-candidate.json',DES/'grading-reference.json']
put(ART/'preparation-issues.json',[])
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0,'candidate_changed_files':changed})
print('FROZEN candidate',len(changed),'files changed vs MAIN166 (work code',len(CHANGED),'+ pins); one case x three turns; model0')
