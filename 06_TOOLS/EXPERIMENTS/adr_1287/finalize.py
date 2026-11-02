"""Close the user-directed release audit; preserve the failed model experiment."""
from common import *
import re
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==133 and active['release_id']==RELEASE
p=ROOT/active['manifest_path'];release=read(p);stage=read(DES/'stage.json');f=read(DES/'freeze.json')
entry=read(OUT/'main-entry.json');gold=read(OUT/'gold-entry.json');api=read(ART/'prepared-api/result.json');scenario=read(ART/'prepared-scenarios/result.json');ontology=read(OUT/'ontology-capability-check.json')
assert entry['passed'] and gold['passed'] and api['passed']==13 and api['failed']==0 and scenario['passed']==7 and scenario['failed']==0
assert ontology['passed'] and all(sha(ROOT/release['code_root']/n)==sha(ROOT/n)==h for n,h in release['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
inherited=read(DES/'inherited-verification.json');live=read(ROOT/inherited['actual']['path']);tech=read(ROOT/inherited['technical']['path'])
assert live['status']=='NOT_PASSED' and tech['status']=='TECHNICAL_PASS'
result={'status':'PASS','status_scope':'Local user-directed cutover and consumer integrity only; semantic experiment remains NOT_PASSED',
 'release_id':RELEASE,'generation':133,'serving_files':len(release['files']),'working_tested_files':len(f['files']),
 'changed_serving_files':stage['changed'],'added_files':len(stage['added']),'deleted_files':0,'product_changes':36,'pin_changes':31,
 'deployment_basis':active['deployment_basis'],'quality_certified':False,'prepared_api_passed':13,'prepared_scenario_api_passed':7,
 'root_conditions':len(entry['checks']),'gold_conditions':len(gold['checks']),
 'ontology_recorded_condition_checks':len(ontology['recorded_conditions']),'ontology_operator_checks':len(ontology['existing_operator_checks']),
 'ontology_effect_N1_expression_registered':ontology['recorded_plan']['effect_N1_has_typed_expression'],
 'inherited_verification':inherited,'inherited_contracts':tech['contract_passed'],'actual_qwen_status':live['status'],
 'new_model_calls':0,'oracle_calls':0,'ontology_writes':0,'genos_deployed':False,'git_pushed':False,
 'rollback':'MAIN132 official pointer rollback plus preserved Gold binding; source data and layout4 retained',
 'ontology_review':bind(OUT/'남은문제와_온톨로지_해결범위.txt'),
 'limitations':['Actual ADR1286 core claim adoption1/3; low answer still has repetitive nonexistent gap references',
 'Normal historical comparison falsely rejected; changed-rule prose still uses old limit',
 'Typed plan only evaluates N2/N3; N1 effect lacks an approved expression',
 'Ontology calculation cannot create missing facts or certify legal scope, exceptions or prose',
 'Oracle E2E, GENOS/NFS durability, load and broad legal quality unverified'],
 'preserved_preparation_failures':['artifacts/prepare.log','artifacts/prepare-resume.log'],
 'preparation_failure_explanation':'Historical technical artifact path and literal status name were corrected before prepare/apply; no product code or old result was changed.'}
put(RUN/'result.json',result);put(OUT/'summary.json',result)
m=read(ADR/'실험/manifest.json');m['design']['frozen_pre_cutover_isolation']=m['design']['code_isolation'];m['design']['operational_audit']=True
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover',
 'reason':'Current user explicitly requested all completed work in MAIN. Exact already-tested cumulative code is selected without reclassifying failed actual Qwen results.',
 'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],
 'release':{'manifest_path':str(p.relative_to(ROOT)),'sha256':sha(p),'release_id':RELEASE}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'generation':132,'historical_only':True},'selected':result},judge_disagreements=0,
 usage={'new_model_calls':0,'oracle_calls':0},latency={'prepared_api_seconds':api['elapsed_seconds'],'prepared_scenario_seconds':scenario['seconds']},
 error_taxonomy=[{'type':'KNOWN_SEMANTIC_LIMITS','detail':result['limitations']},{'type':'PREPARATION_RECORD_LOOKUP','detail':result['preparation_failure_explanation']}]);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '현재 사용자 지시에 따라 지금까지 통합한 작업을 MAIN133/scenario-cumulative-20261102-r1으로 반영했다. 서빙513파일, MAIN132대비67변경(제품36+pin31), 신규9/삭제0. 실제 root 서비스와 Gold 엔진 연결을 확인했다. 사용자 지시 반영이며 품질 인증은 아니다.',
 'MAIN132 선택 코드에는 이후 작업의 검토 표시·가정 비교·타입 계산·현재 사건 입력 통합·공유 검토 연결이 없었다. 작업527파일은 완료1285와 실제1286의 동결본과 정확히 같았으며 추가 제품 변경 없이 공식 서빙513파일을 선택했다. 연구/보조14파일은 작업에 유지한다.',
 '[사전 기준](artifacts/design/criteria.json). 코드·원문·권한·상태·예산·매핑 보존, 공식 준비 릴리스/실제 소비자 확인, 실패 결과와 미구현 제안 구분. 새모델/Oracle/현장배포0.',
 '완료1285 verified의 누적 코드를 그대로 동결하고 실패1286은 informed_by로 참조했다. MAIN132/Gold 이전 binding 보존→공식 preview/rebase/prepare→준비 API검사→공식 apply→실제 root/Gold 확인. 이전 준비 요약 경로/상태값 조회 실패2건은 원본 보존 후 바로잡았고 당시 제품·선택 변경0이었다.',
 '후보/작업527파일, 공식 선택513파일 정확결속. 기존 원문 세대·Gold 쿼리릴리스/매핑/연결기/온톨로지 설정과 Oracle layout4·구조화Oracle/상세NFS 정책 유지. Gold는 엔진 binding만 MAIN133에 맞췄다.',
 f'준비 복구 API13 + 가정 API7 통과, 실제 root{len(entry["checks"])}조건/Gold{len(gold["checks"])}조건 통과. 기존 기술 계약283/모의API7/작업API7은1285에 있고 합산 독립표본이 아니다. 온톨로지 실제 저장 조건3대조 및 기존 연산8조건 통과(법률 품질 검사 아님).',
 '1286 실패는 그대로다: 저액만 주장5 채택이나gap참조24회/존재하지 않는 번호/과거 사건 표시 잔존, 고액은 정상 과거 비교를 현재 설명에 써서 과차단, 규칙은 옛한도 적용을 그대로 반복해 거절됐다. 1/3을 전체 품질 성공으로 쓰지 않는다.',
 f'이번 새모델 비용0·Oracle0. 준비 API {api["elapsed_seconds"]:.3f}초, 가정 API {scenario["seconds"]:.3f}초는 합성 검사 시간이다. 과거 실제1286=8호출/596.888초/$0.077952/UNKNOWN0이며 이번 새 실행으로 중복 계산하지 않는다.',
 '온톨로지는 현재 금액·한도·승인 미확인을 이미 정확히 계산한다. 계산 결과의 서버 표시를 확장하면 모델의 금액 재작성과 비교문 위치 제약을 줄일 수 있다. 다만 현재 N1 효과에는 타입식이 없고 관계만 있으므로 자동 최종허용 계산은 아니다. [상세 범위](../../../09_ARTIFACTS/AUDITS/20261102-scenario-cumulative-main133/남은문제와_온톨로지_해결범위.txt).',
 'gap 반복·공유 참조·현재 사건 표시는 출력 계약 수정이 필요하다. 미확인 실제 사실·법적 적용 범위·예외·원문 의미의 옳음을 온톨로지가 자동 생성/인증하지 않는다. 후속 서버 표시/효과식 제안은 미구현·미승인·미게시. 법률품질·Oracle E2E·GENOS·NFS·부하 미검증.',
 'MAIN133 선택 완료. 롤백은 08_DEPLOYMENT/RELEASES/scenario-cumulative-20261102-r1/rollback/ACTIVE_RELEASE.json의 MAIN132와 감사 gold-before.json의 이전 binding을 함께 사용한다. 원문/운영DB/DDL/Git push/메일/현장배포 변경0. 새 기록·과거 실패 삭제0.',
 'prepare.py(과거요약경로 차단)→prepare_resume.py(상태명 수정 전 실패 보존)→공식preview→prepare_release.py→check_agent_loop_recovery.py --api-only→check_scenarios.py→ontology_check.py→activate.py→main_entry.py→gold_entry.py→finalize.py→hash/status/validate/graph. 완료 apply 재실행 금지.'
]
path=ADR/'README.md';front=path.read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: Accepted',front);front=re.sub(r'(?m)^main_wiring:.*$','main_wiring: user-directed-cutover',front)
path.write_text('---'+front+'---\n\n# ADR1287 누적 작업 MAIN133 반영 및 온톨로지 해결 범위\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(OUT/'메인반영과_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
question=read(DES/'criteria.json')['authorization']
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
qv=['run-001/selected. 현재 사용자 지시 반영 감사, 모델 비교 아님.',question,'기준답변·채점모델0. 판정은 동결 코드 동일성과 실제 API 소비자 연결.','원문/코드/Gold baseline과 freeze 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수 비교 없음, stage_ledger not_applicable.','새 모델 호출0. 준비 API는 모의 모델이며 실제 root는 HEALTH·렌더 소비자, Gold는 DB 연결 없는 실제 connector import.','중간 외부 모델 호출0. 이전1286 원응답은 해당 ADR에 보존.','외부 채점0. 준비 API/온톨로지 기능 확인 결과는 별도 영수증. 모델 품질 점수 아님.','MAIN133 반영/소비자 확인 PASS, 실제1286 의미 실험 NOT_PASSED 유지. 온톨로지 후속 제안 미구현.']
(ADR/'실험/질문-001-main-and-ontology.md').write_text('# MAIN 반영과 온톨로지 범위\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,qv),1))+'\n')
(ADR/'실험/README.md').write_text('# 반영 감사\n\n[질문](질문-001-main-and-ontology.md) · [manifest](manifest.json) · [결정](../README.md). 새모델/Oracle0.\n')
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
files=[x for x in ART.rglob('*') if x.is_file() and x!=ART/'manifest.json' and 'runtime' not in x.relative_to(ART).parts and 'selected-entry-runtime' not in x.relative_to(ART).parts and '__pycache__' not in x.parts]+[x for x in OUT.iterdir() if x.is_file()]
am=read(ART/'manifest.json');am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Exact code, official cutover, consumer checks and read-only ontology review',contains_raw_prompts_and_outputs=False) for x in sorted(files)]
(ART/'manifest.json').write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print({'generation':133,'serving_files':513,'changed':67,'prepared_api':20,'root':len(entry['checks']),'gold':len(gold['checks']),'actual_qwen_status':live['status']})
