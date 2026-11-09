"""Freeze MAIN164, the local Oracle Gold connector, CM51 questions and criteria before any model call.

Vector-only arm (user choice). Corpus is the local Gold 21 CM documents (ADR-1208), so a
comparison with ADR-1424 (SQLite 44-document keyword) mixes the vector effect with corpus narrowing.
"""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==167 and ptr['release_id']=='oracle-shared-rows-20261106-r1'
rel=read(ROOT/ptr['manifest_path']);C=ROOT/rel['code_root'];main_files=rel['files']
assert all(sha(C/n)==h for n,h in main_files.items())
STAGED=ROOT/'09_ARTIFACTS/AUDITS/20261106-oracle-section-children/staged-167'
files={n:sha(STAGED/n) for n in main_files}  # MAIN167 inventory with the section-children fix and repinned engines
fix=read(ROOT/'09_ARTIFACTS/AUDITS/20261106-oracle-section-children/staged-167.json')['changed_product_files']
changed=sorted(n for n in files if files[n]!=main_files[n])
assert all(n in fix or n.startswith('02_BACKEND/ENGINES/') or n in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py') for n in changed),changed
put(DES/'baseline.json',{'pointer':ptr,'release':rel})
put(DES/'candidate-vs-main167.json',{'changed_files':changed,'fix_product_files':fix,'fix_record':'09_ARTIFACTS/AUDITS/20261106-oracle-section-children'})
code_diff=changed
# frozen Gold connector copy + frozen pointer (other sessions may change the live pointer during the run)
src=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';gp=ART/'gold-connector'
shutil.copytree(src,gp,ignore=shutil.ignore_patterns('__pycache__'))
put(gp/'active-pointer.json',ptr)
binding=read(gp/'binding.json')
assert binding['engine_release_id']==ptr['release_id'] and binding['engine_root']==rel['code_root'] and binding['engine_files']==main_files,'Gold connector must be bound to selected MAIN167'
ontology_off={'schema_version':'gold-ontology-settings-v1','enabled':False};put(DES/'ontology-off.json',ontology_off)
gold_docs=[d['document_id'] for d in read(ROOT/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector/artifacts/design/selected-documents.json')['documents']]
public=set(read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
assert len(gold_docs)==21 and set(gold_docs)<=public
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/design'
cases=[{**c,'document_ids':sorted(gold_docs)} for c in read(prior/'live-cases.json')]
assert len(cases)==51
shutil.copyfile(prior/'grading-only.json',DES/'grading-only.json')
criteria={'authorization':'이건 벡터로 한번 다시 돌려볼래? / 선택: 벡터만 / 쭉진행해봐 (수정 후 재실행)',
 'scope':'MAIN167 + same-section parent-lookup fix (candidate) via the local Oracle Gold connector, Gold 21 CM documents, local BGE-M3 question embedding, GENOS_RAG_INITIAL_SEARCH=vector, ontology OFF, 외규 question prefix; CM51 once each, run alone. No product/MAIN/DB changes.',
 'required':['Selected533/connector/source unchanged; every cell bound to the frozen connector and pointer',
             'Answer matches the registered reference answer on the stored original (same grading as ADR-1424)',
             'Source spans/ACL/wire integrity, physical calls equal budget, duplicate request adds0 calls'],
 'secondary':['No QUERY_NAV_BUDGET from same-section code; every remaining whole-collection Oracle read (Units/SourceMetadata/Sources/SQLMap iteration) recorded with its caller','Per question: whether the vector initial search ran (INITIAL_VECTOR_CANDIDATES), degraded, was empty or was skipped (model search queries or narrowed scope)',
              'Registered required articles acquired/cited by law name and article (same as ADR-1424)',
              'Per-question change versus ADR-1424, labelled as confounded: corpus 44 -> 21 documents and keyword -> vector'],
 'limits':{'physical_total':2040,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':10,'ram_start_gib':5,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'load_swap_growth_mib':512,'worker_rss_gib':5,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, source/ACL/code/resource violation or total budget stop batch. This session runs no tests, data loads or other model work while the batch runs.',
 'quality_certified':False,'in_sample':True,'order':[c['id'] for c in cases],
 'prior_observation':'ADR-1424 MAIN161 SQLite 44 docs keyword: 18 pass / 5 partial / 28 fail. ADR-1426 MAIN164 Gold vector: stopped after 3 questions, all QUERY_NAV_BUDGET from whole-corpus same-section iteration.'}
put(DES/'criteria.json',criteria);put(DES/'live-cases.json',cases);put(DES/'gold-documents.json',gold_docs)
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':sorted(gold_docs),'questions':[c['steps'][0]['question'] for c in cases],'scope':'Registered CM question strings only, public grant ∩ Gold CM21 documents; reference answers never sent'})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered reference-answer match per question',success_criteria=[*criteria['required'],*criteria['secondary']],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'selected':stages}
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Reference only: ADR-1424 (MAIN161, SQLite 44 docs, keyword); not executed here',controls='Same question strings; different corpus and initial search')
 else:arm.update(changes='Gold 21 docs, BGE-M3 vector initial search, MAIN167 + section-children fix',controls='Same question strings, model, profile, ontology OFF')
m['dataset'].update(name='financial CM51 registered questions',version='cm-field-core-e2e-v3',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['selected'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for q,c in zip(m['questions'],cases):
 assert q['case_id']==c['id'];p=ADR/'실험'/q['file']
 p.write_text(f"# {c['id']}\n\n## 1. 실행 메타\n\nMAIN167+같은 절 조회 수정 후보, 로컬 Oracle Gold 21문서, BGE-M3 벡터 초기검색, Qwen3.8 Parasail/none, 출력상한 없음, 외규.\n\n## 2. 사용자 질문 원문\n\n{c['steps'][0]['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\ndesign/grading-only.json (ADR-1424와 동일).\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz와 source-wire-audit.json 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c['id']}-selected/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json와 물리 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n추가 채점 모델0. 실제 원문·행동·저장 기록 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'selected',list(files),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(STAGED/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];snap=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snap/n)==h for n,h in files.items())
desc={'code_root':str(snap.relative_to(ROOT)),'selected_files':files,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','candidate-selected.json','grading-only.json','ontology-off.json','gold-documents.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'connector_files':{str(p.relative_to(ROOT)):sha(p) for p in gp.rglob('*') if p.is_file()},'model_calls_before_freeze':0})
print('Frozen MAIN167+fix candidate + Gold connector copy, CM51 on Gold21 vector, budget2040/cost10; model0; changed vs MAIN167:',code_diff)
