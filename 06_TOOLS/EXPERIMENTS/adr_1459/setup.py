"""Freeze the staged candidate (MAIN178 + 3 search fixes), the Oracle/vector environment and the
nine financial CM questions (same as ADR-1458) before any model call."""
from common import *
import shutil,subprocess
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
sys.path.insert(0,str(Path(__file__).parent));import oracle_local as ol
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==178 and ptr['release_id']=='unread-labels-20261108-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==544
stage=read(ROOT/'09_ARTIFACTS/AUDITS/20261108-oracle-vector-search-fixes/release/main-release.json')
assert stage['stage']['status']=='PASSED' and stage['stage']['base_release_id']==ptr['release_id']
S=ROOT/stage['stage']['code_root'];staged={n:sha(S/n) for n in files};changed=sorted(n for n in files if staged[n]!=files[n])
product=[n for n in changed if n.endswith('.py') and 'legal_agent' in n]
assert set(product)=={'02_BACKEND/semantic_runtime/legal_agent/guided_answer.py','02_BACKEND/semantic_runtime/legal_agent/guided_navigation.py','02_BACKEND/semantic_runtime/legal_agent/connection_scope.py'},product
tests=read(ROOT/'09_ARTIFACTS/AUDITS/20261108-oracle-vector-search-fixes/release/regression-compare.json');assert tests['status']=='PASSED' and not tests['new_failures']
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'stage':stage['stage'],'staged_changed_files':changed,'product_files':product,'regression':{'status':tests['status'],'new_failures':len(tests['new_failures']),'fixed':len(tests['fixed']),'same_failures':len(tests['same_failures']),'files':tests['files']}})
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1458-main177-cm51-search-subset-qwen/artifacts/design'
cases=read(prior/'live-cases.json');grades=read(prior/'grading-only.json');ORDER=[c['id'] for c in cases]
assert ORDER==['cm-007','cm-009','cm-016','cm-023','cm-030','cm-039','cm-041','cm-045','cm-040']
qpath=ROOT/'01_DATA/review/cm_core_e2e_v3.json';rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(qpath) for f in auth['files'])
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(c['steps'][0]['question']==registry[c['id']]['question'] for c in cases)
# Oracle Gold environment, read before freezing
conn=ol.connect();cur=conn.cursor()
cur.execute(f"select RFRN_CHNL_NAME,RFRN_POST_HASH_VALU,CHAN_NO from {ol.GOLD_OWNER}.IDD_B03_LGL_SRCH_CHNL where RFRN_CHNL_NAME=:c",{'c':ol.CHANNEL});chan=cur.fetchone();assert chan
cur.execute(f"select RFRN_POST_IFMN_CTNT from {ol.GOLD_OWNER}.IDD_B03_LGL_SRCH_POST where RFRN_POST_HASH_VALU=:h",{'h':chan[1]});qrel=json.loads(cur.fetchone()[0])
base_qid=qrel['extension']['base_query_id']
cur.execute(f"select VCTR_POST_ID from {ol.GOLD_OWNER}.IDD_B03_LGL_VCTR_HEAD where RFRN_POST_HASH_VALU=:h",{'h':base_qid});vid=cur.fetchone()[0]
cur.execute(f"select VCTR_POST_IFMN_CTNT from {ol.GOLD_OWNER}.IDD_B03_LGL_VCTR_POST where VCTR_POST_ID=:v",{'v':vid});vpost=json.loads(cur.fetchone()[0])
cur.execute(f"select RGLT_DOC_ID,RGLT_DOC_NAME from {ol.GOLD_OWNER}.IDD_B03_LGL_DOC_VER");docs={r[0]:r[1] for r in cur.fetchall()}
assert qrel['dataset_version']==rel['data_manifest_sha256']==vpost['manifest']['dataset_version'],'Gold dataset differs from the selected local generation'
assert set(vpost['manifest']['documents'])==set(docs) and vpost['completion']['status']=='READY'
profile=vpost['manifest']['profile'];assert profile['model']=='BAAI/bge-m3' and profile['dimensions']==1024
public=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'];granted=sorted(set(public)&set(docs))
assert len(granted)==21
# Embedding validation rows: exact published inputs (prefix + segment) with stored vectors
cur.execute(f"select RGLT_DOC_ID,BODY_UNIT_ID,VCTR_DTLS_IFMN_CTNT,VECTOR_SERIALIZE(EMBD_VCTR RETURNING CLOB) from {ol.GOLD_OWNER}.IDD_B03_LGL_VCTR_ITEM where (RGLT_DOC_ID,BODY_UNIT_ID) in (('7bbe815ff43b6635','1108'),('27c02e2a7e1c59cb','345'),('963c5eda366b86c9','271'),('7bbe815ff43b6635','1486'),('3521c3aaa5a735fd','142'))")
validate=[]
for did,uid,meta,vec in cur.fetchall():
 m=json.loads(meta);ids=m['blocks']
 cur2=conn.cursor();cur2.execute(f"select BODY_SLC_ID,BODY_CTNT from {ol.GOLD_OWNER}.IDD_B03_LGL_DOC_BLK where RGLT_DOC_ID=:d and BODY_SLC_ID in (%s)"%','.join("'%s'"%i for i in ids),{'d':did})
 texts={r[0]:r[1] for r in cur2.fetchall()};group='\n'.join(texts[i] for i in ids)
 assert hashlib.sha256(group.encode()).hexdigest()==m['group_text_sha256']
 inp=m['prefix']+group[m['start']:m['end']];assert hashlib.sha256(inp.encode()).hexdigest()==m['input_sha256']
 validate.append({'unit':did+':'+uid,'input':inp,'vector':json.loads(vec)})
conn.close()
put(DES/'embed-validate.json',validate);put(DES/'embed-profile-files.json',profile['files'])
put(DES/'oracle-gold.json',{'container':ol.CONTAINER,'owner':ol.GOLD_OWNER,'channel':ol.CHANNEL,'query_release_id':chan[1],'base_query_id':base_qid,'vector_post_id':vid,
 'dataset_version':qrel['dataset_version'],'documents':docs,'granted_documents':granted,'vector_profile':{k:v for k,v in profile.items() if k!='files'},'vector_count':vpost['completion']['count'],
 'navigation_compilers':qrel.get('navigation_compilers'),'bridge':'direct oracledb as SYSTEM (local container); ORDS HTTP envelope replaced, statements unchanged','agent_tables':'SIDDA.LGL_AGT_*_A / LGL_EXEC_ST_A (gold mapping), namespace per case'})
criteria={'authorization':"우리 이제 오라클만 쓸꺼임 그리고 벡터로 search를 돌릴거임 일단 코드 수정해보고 실험해봐",
 'scope':'Staged candidate = selected MAIN178 + three search fixes (named-article reads, reference normalization, cross-law citation locations, same-subject incoming links, menu dedupe/stopwords). Local Oracle Gold A8_GR12_CM1208 (21 financial documents, dataset = selected generation), channel cm-r12-engine, DP=oracle + gold mapping, GENOS_RAG_INITIAL_SEARCH=vector with the published bge-m3 vectors and a local bge-m3 endpoint verified against stored vectors. Nine financial CM questions (ADR-1458 set) once each, 외규 mode. Reference answers grading-only. No MAIN change.',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree',
  'Primary: registered required articles acquired per question (law name + article on the current generation), compared with ADR-1458 (MAIN177, SQLite keyword) and ADR-1424 (MAIN161)',
  'Secondary: answer matches the registered reference answer on the current stored original; questions back, partial or source-only replies are not full answers',
  'Named-article reads: when an answer names an in-scope article it has not read, the server reads it in the same request (event GUIDED_ANSWER_NAMED_ARTICLES)',
  'Source spans/ACL/wire integrity against the same dataset, physical calls equal budget, duplicate request adds0 calls, Oracle SQL per question recorded'],
 'limits':{'physical_total':360,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':3,'time_box_minutes':40,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'workers':1,'embedding_calls_per_question':'recorded, no limit'},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, source/ACL/code/resource violation, total budget or the 40-minute time box (checked before each next question) stop the batch. No other tests or model work while the batch runs.',
 'quality_certified':False,'in_sample':True,'order':ORDER,
 'prior_observation':'ADR-1458 on MAIN177/SQLite keyword: 8 NOT_READ questions → PASS1 PARTIAL1 FAIL6; required articles 4/18. Failures traced to named articles never resolved, cross-law citations not followed, same-subject incoming links counted away, duplicate evidence refs rejected.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',[{**c,'document_ids':granted} for c in cases])
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),'question_policy':'Local experiments use the financial cm51; question strings authorized for the external experiment model by CM_EXPORT_AUTHORIZATION_20261024.'})
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,'scope':'Registered CM question strings only; reference answers and coordinates are never sent; originals come from local Oracle Gold (same dataset as the public generation)'})
transport=ART/'transport';transport.mkdir()
pins=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
 target=transport/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);pins['files'][name]=sha(target)
put(transport/'transport-pins.json',pins)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired per question on the current generation (Oracle Gold, vector initial search), compared with ADR-1458/ADR-1424',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution','A claim cites an unread connection target'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'vector','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['vector']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'candidate':stages}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1458 MAIN177 SQLite keyword outcomes for the same nine questions; not executed here','controls':'Same question strings and reference grading'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN178 + 3 product files (staged, tests passed), DP=oracle gold mapping on local Gold, vector initial search with local bge-m3 endpoint','controls':'Same default profile, same dataset version, independent requests'}]
m['dataset'].update(name='financial CM nine-question subset',version='cm-field-core-e2e-v3',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['candidate'],selection_rule=criteria['stop'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['questions']=[]
readme=ADR/'README.md';rows=[]
for i,c in enumerate(cases,1):
 fn=f"질문-{i:03d}-{c['id']}.md";p=ADR/'실험'/fn
 p.write_text(f"# {c['id']}\n\n## 1. 실행 메타\n\nMAIN178+3 staged candidate, local Oracle Gold(cm-r12-engine)·벡터 초기검색(bge-m3 로컬 엔드포인트), 기본 Qwen3.8 Parasail/none, 출력상한 없음, 외규 모드.\n\n## 2. 사용자 질문 원문\n\n{c['steps'][0]['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n등록 기준답변·근거 좌표는 design/grading-only.json에만 있고 제품 입력에서 제외. 현재 저장 원문과 실제 답변을 대조한다.\n\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/{c['id']}-candidate 참조.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c['id']}-candidate/raw 및 canonical.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json와 물리 calls.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n추가 채점 모델0. 실제 원문·행동·저장 기록 직접 대조.\n\n## 8. 사례 최종 판정\n\n실행 전 동결.\n")
 m['questions'].append({'number':i,'case_id':c['id'],'file':fn,'sha256':sha(p)});rows.append(f"| {i:03d} | `{c['id']}` | `run-001` | TODO | TODO | TODO | [{fn}]({fn}) |")
text=readme.read_text()
if '질문-001' not in text:readme.write_text(text.rstrip('\n')+'\n\n## 질문 목록\n\n| 번호 | case_id | run | 판정 | 비고 | 비고2 | 파일 |\n|---|---|---|---|---|---|---|\n'+'\n'.join(rows)+'\n')
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
for n in files:
 if sha(can/'snapshot'/n)!=staged[n]:shutil.copyfile(S/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==staged[n] for n in files)
desc={'code_root':str(snapshot.relative_to(ROOT)),'candidate_files':staged,'base_release_files':files,'changed_from_main178':changed,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=True,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,
 candidates=[dict(desc['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live.py')))])
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','candidate-selected.json','grading-only.json','oracle-gold.json','embed-validate.json','embed-profile-files.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen MAIN178+3 candidate (544 files,',len(changed),'changed), Oracle Gold',ol.CHANNEL,'docs',len(granted),'vector items',vpost['completion']['count'],'; nine CM questions; budget 360/$3/40min; model0')
