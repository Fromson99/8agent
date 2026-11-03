from common import *
import re,collections
f=read(DES/'freeze.json');b=read(DES/'baseline.json');a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/a['manifest_path'])
assert a['generation']==136 and a['release_id']==RELEASE
loader=read(ART/'loader-integration.json')
assert all(sha(ROOT/n)==sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items() if n not in loader['files'])
assert all(sha(ROOT/n)==h for n,h in loader['files'].items())
assert all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in r['files'].items())
checks={name:read(ART/name/'result.json') for name in ('scope-final-r2','regression-scope-final','prepared-api-r2','oracle-select-verified')}
assert checks['scope-final-r2']['passed']==38 and checks['regression-scope-final']['passed']==177 and checks['prepared-api-r2']['passed']==14
assert all(x.get('failed',0)==0 for x in checks.values())
assert all(read(OUT/name)['passed'] for name in ('main-entry.json','gold-entry.json'))
status=collections.Counter(x['implementation_status'] for x in read(OUT/'optimization-disposition.json'))
result={'status':'LOCAL_MAIN_SELECTED','release':RELEASE,'generation':136,'quality_certified':False,
 'candidate':f['candidate_revision'],'loader_candidate':loader['candidate'],'loader_contracts_passed':read(ART/'loader-rowid-final/result.json')['passed'],'candidate_files':len(f['files']),'serving_files':len(r['files']),'main_delta_files':read(DES/'stage.json')['changed'],
 'new_and_targeted_contracts':38,'regression_checks_passed':177,'known_existing_fixture_failures':6,'prepared_api':14,'root_entry_conditions':16,'gold_entry_conditions':9,
 'oracle_select_cases':15,'oracle_select_queries_final':45,'oracle_scope':'Synthetic bind-only rows; SQL semantics, not real Gold E2E/latency',
 'oracle_task_total':{'successful_selects':180,'failed_selects':1,'failure':'Initial synthetic JSON_TABLE fixture chaining ORA-40556; fixture isolated with ROWNUM, no product workaround'},
 'test_overlap':'Prepared14 repeat prior API cases; repeated passes, Oracle reruns, previous revisions are not summed as independent samples',
 'optimization_disposition':dict(status),'external_model_calls':0,'model_cost_usd':0,'DDL':0,'production_writes':0,'field_deployed':False,'git_pushed':False,'mail_sent':False,
 'data_unchanged':r['data_path']==b['release']['data_path'] and r['data_manifest_sha256']==b['release']['data_manifest_sha256'],
 'validation':{name:bind(ART/name/'result.json') for name in checks},'prior_failure_comparison':bind(ART/'regression-qualified/result.json'),
 'activation':bind(OUT/'activation.json'),'r7_package':bind(ART/'r7-verified-package.json'),'disposition':bind(OUT/'optimization-disposition.json')}
put(ART/'run-001/result.json',result)
text=f'''Gold·SQLite 쿼리 최적화와 로컬 MAIN136 반영 — 2026-11-03

반영 상태
{RELEASE}, 서빙517파일/MAIN135대비48파일 변경. 최종 scope-fixed/rev-001 런타임591파일+후속 로더73파일·작업 코드 동일, 실제 선택 서빙517파일 해시 동일. 공식 prepare/apply로 MAIN136 선택, Gold 엔진도 같은 코드. 사용자 “싹다 고쳐봐”에 따른 로컬 반영이며 USER_DIRECTED_CUTOVER / quality_certified=false. 원문 generation·Gold query release·물리 매핑·온톨로지 설정·layout4를 유지했다. 기존 작업의 답변 표시 수정도 보존했다.

실제로 바꾼 처리
1. 같은 요청의 검증 완료 구조·좌표·원문 메타·블록 ID·SQL 결과를 재사용한다. 공유 캐시는 직렬화 기준 총16MiB/항목4MiB/128항목, 블록 ID는5만개 상한. 실패/부분 조회는 성공 캐시로 만들지 않는다. 요청 판본·원문 manifest·snapshot·ACL·기한을 검사한다. Python 객체 실제 RSS는 직렬화 바이트보다 크므로 실행 자원 감시를 별도로 적용했다.
2. 문서 전체 검색은 문서 범위를 그대로 전달한다. source ID 전체를 펼치고 모든 source 본문으로 하위범위를 확인하던 경로를 제거했다. 키·점수·소속·블록 메타에서 정확한 중복/총계를 계산한 뒤 선택 페이지의 본문·카드만 읽는다. title/literal 검색도 페이지 밖 노드 카드 생성을 피한다. unit-first recall의 전체 hit 보존 경로까지 없앴다는 뜻은 아니다.
3. Oracle 단일 토큰은 저장 tf를 쓰고 전역 df/권한 내 tf를 분리한다. phrase는 기존 위치 인접 비교와 전역 df를 유지한다. length의 source 조건은 OWNER_ID, 일반 EQ/IN/안전한 OR/JSON ID집합은 물리키에 전달한다. 불필요 literal CLOB JOIN도 제거했다.
4. Oracle FTS 2048개 이하 키·점수는 group/hit 페이지에서 공유한다. 큰 결과는 정확한 기존 SQL 경로를 유지한다. SQLite 탐색 메타와 같은 glossary 페이지도 상한 내 재사용한다. 문서 ID/원문 ID의 문자열이 같아도 범위 종류가 다르면 캐시·cursor를 공유하지 않는다.
5. 원문 확보 뒤 남은 필요에 연결된 후속 행동이 없으면 no-progress 복구 탐색을 추가로 열지 않는다. 미해결 need 자체를 닫거나 답변 완료로 바꾸지 않는다. 기존 최대3회 복구, 예산·예약·재개·실제 새 원문 확보에 따른 progress 갱신을 유지한다. 실제 모델 호출 감소는 아직 측정하지 않았다.
6. 온톨로지 허용 게시본 본문과 현재 게시/철회 확인을 배치로 묶었다. payload 읽기 전 ACL 확인, 매 요청 현재 authority 확인은 유지한다.
7. R7 적재 후속 패키지는 일반 테이블/FTS 길이/posting 생산자 커서를 저장해 완료 위치 다음부터 재개한다. posting 재개는 이미 완료한 길이 전체 집계를 생략한다. 기존 R6 체크포인트 첫 재개와 source/native 단계는 여전히 앞부분 순회가 필요하다. R6 원본은 manifest72파일 해시로 불변 확인했고 R7 검증 ZIP74파일/{read(ART/'r7-verified-package.json')['bytes']}bytes를 따로 만들었다. 현장 실행은 하지 않았다.

검증 결과
최종 후보 새·표적 계약38, 기존 회귀177 통과. 준비 릴리스 모의 API14, 실제 root 진입16조건/Gold 연결9조건 통과. 준비14는 후보 API와 겹치므로 독립 성공으로 합산하지 않는다. 새 실모델0, 답변 정답률·전체 지연 개선율 미측정.
로컬 Oracle에서 합성 CLOB bind 데이터로 단어·구문·중복 단어·복수 질의·zero-hit와 권한/원문 범위15조건을 비교했다. 기존 원본 SQL과 최적화 SQL의 키·점수 동일성을 확인했고 최종 범위 수정본도15조건/45SELECT 재확인했다. 전체 작업 중 성공SELECT180/실패SELECT1, 전부 읽기 전용 합성 자료이며 실제 Gold 데이터 전체 실행 성능이 아니다.
검색 계약은 중복 최소단위의 최초 순서/마지막 값, source 단위 top-K, 동점 순서, 정확한 총계, 원문 바이트/블록/소속, ACL·판본·기한·미완료 조회를 확인했다. R7은 합성 일반 테이블과 FTS5 두 개의 모든 행 경계에서 ID·payload·순서가 동일하게 이어졌다.

보존한 실패
초기 JSON ID집합 pushdown 검사1개에서 Alias 처리가 빠져 수정했다. 마지막 범위 종류 충돌은 MAIN 선택 전에 새 검사로 재현(37통과/1실패)하고 scope-fixed 후보로 수정했다. r1 준비 릴리스는 선택하지 않았다.
이전 Oracle 회귀49개는 통과했으나 감시 스레드가 테스트의 Path.open monkeypatch 영향으로 중단된 경고가 있었다. /proc 읽기를 독립 open으로 바꾸고 후속 감시를 적용했다. 첫 pytest 플러그인 인자명 오류와 legacy ontology 모듈 수집 경로 오류도 준비 실패로 남겼다.
전체 회귀 최초176통과/7실패 중 6개는 온톨로지 RESPONSE_RECEIVED 기대가 PREPARED_NOT_SENT로 나온 기존 가정 fixture 실패다. 수정 전 코드에서도 동일6실패/14통과로 대조했다. 나머지1개는 격리 snapshot에서 과거 ADR 원시 파일을 찾던 경로 문제이며 저장소 artifact 경로로 독립 재검사해 통과했다. 최종177개에서 그 기존6개만 명시 제외했고 실패 원본은 보존했다.
Oracle 최초1실패는 합성 fixture의 JSON_TABLE 중첩 ORA-40556이며 fixture inline merge 경계를 고쳤다. 제품 쿼리 오류로 합산하지 않았다. 로더 후속검사에서 words content 첫 조회와 rowid=0 재개가 음수/0행을 건너뛸 수 있음을 수정했고, 음수·0을 포함한 모든 행 경계 재개10검사가 통과했다. 초기 ZIP은 보존하고 _verified.zip만 최종본으로 표시했다.
후보를 작업에 반영한 뒤 기존 후보의 upstream 상태로 다시 동결하려던 절차는 보호 중단됐다. 기존 후보/준비 r1/부분 동결과 실패를 보존하고 현 작업을 부모로 한 새 scope-fixed 후보를 공식 snapshot/freeze했다. 산출물 이름 충돌도 덮어쓰지 않고 final 경로로 분리했다.

27개 항목의 완료 범위
14개 코드 반영, 6개 부분 개선, 3개 기존 최적화 유지, 2개 조건부 유지, 2개 현장 확인 필요. 자세한 항목은 27개_항목별_반영과_남은조건.txt 및 optimization-disposition.json.
남는 비용은 임의 부분문자열/포함검색 최초 스캔, 큰 FTS 결과의 점수 재계산, 서로 다른 glossary token 페이지의 랭킹, OFFSET 상수 SQL, source/native 적재 prefix 재생, JDBC literal/LOB 변환, 드문 CLOB fallback이다. NLSSORT/숫자 CAST의 실제 plan과 인덱스·통계는 현장 확인이 필요하다. 순위나 substring 의미를 바꾸거나 등록되지 않은 함수 인덱스/새 ngram/ANN을 넣어 해결했다고 표시하지 않았다.
Gold_운영_읽기전용_실행계획_통계점검.sql을 준비했다. DBMS_STATS/DDL/현장 배포/메일/Git push0. Dataiku native prepared-bind 공개 API는 확인되지 않아 없는 호출을 추가하지 않았다.

원복
MAIN135 포인터: 08_DEPLOYMENT/RELEASES/{RELEASE}/rollback/ACTIVE_RELEASE.json
이전 Gold binding: 이 폴더 gold-before.json. 최초 작업 코드 보관: ADR artifacts/working-before, 후속 scope 수정 전 보관: working-before-r2b. 원문 세대는 바뀌지 않았다. MAIN136의 실제 질문 총 처리시간·Near AI 답변 품질·GENOS/Dataiku 원격 성능은 이번 결과로 인증하지 않는다.
'''
(OUT/'수정과_검증_메인반영결과.txt').write_text(text)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[f'MAIN136/{RELEASE} 로컬 선택. 사용자 지시 코드 반영이며 실모델/현장 품질 인증이 아니다.',
 '153개 document-keyset SQL 구간155.603744초와 FTS8개0.990591초의 기존 감사에 따라 반복 목록/범위 전달/페이지 전 본문 로딩을 우선. 같은 입력의 반복 여부는 기존 성공 bind 미보존으로 단정하지 않는다.',
 '[사전 기준](artifacts/design/criteria.json). 27항목을 동일 계약 코드 수정 또는 근거 있는 유지/조건부로 판정. 새 범위 종류 경계 실패는 보존 후 수정.',
 '원래 optimized rev001~004 후보, 작업 통합 후 scope-fixed rev001. 동일 단위/회귀/API fixture, 읽기 전용 Oracle 합성 SQL 대조. 실제 법률질문/모델 품질시험이 아니다.',
 '최종 런타임591+후속로더73/서빙517 정확 결속. 과거 원시 artifact는 저장소에서 읽고 실행 코드만 후보에서 로드. 모델0/합성 Oracle만. 원문 corpus 변경0.',text,
 '실패와 수정 전 동일 실패6개, 준비·관측기 오류, cache scope 오류를 위 결과와 artifacts에 보존. 성공 회수만 선별한 서비스 성능 주장을 하지 않는다.',
 '모델0/보고비용$0. Oracle 성공180/실패1 합성SELECT. 최종15조건45SELECT는 동일조건 반복 확인이며 180개 독립 사례가 아니다. 물리 SQL/본문/메타/카드와 모델 호출을 분리.',
 'DB 내부 인덱스만으로 해결되지 않는 반복조회와 선행 본문 로딩을 줄였다. 정확한 총계·순위·원문 검증은 유지. 27개 전부가 제거됐다고 주장하지 않는다.',
 '운영 Oracle19/Dataiku 실제 plan·대용량·GENOS/NFS·Qwen 답변품질/호출감소/시간개선 미검증. 기존 온톨로지 fixture6실패 유지. 부분 개선과 field 요구는 항목표 참조.',
 'USER_DIRECTED_CUTOVER/quality_certified=false. MAIN135 pointer 및 이전Gold binding 원복 보존. R7 별도 ZIP, 원래R6/데이터/Goldquery/매핑/layout4 보존, 외부게시0.',
 'prepare→edit→freeze→계약/Oracle SELECT→추가 scope 실패→새 scope-fixed snapshot/freeze→38/177검사→prepare r2→API14→apply→root16/Gold9→기록/보존. 신규 비교실험은 기존 결과를 덮어쓰지 않고 새ADR로 수행.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^main_wiring:.*$','main_wiring: user-directed-cutover',front)
p.write_text('---'+front+'---\n\n# ADR1308 Gold·SQLite 쿼리 최적화와 MAIN136\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
(ADR/'실험/001-query-contracts.md').write_text('# 검색 계약·SQL 대조·로컬 반영\n\n## 1. 실행 메타\n\nrun-001/optimized, 모델0.\n\n## 2. 사용자 요청\n\n쿼리 최적화 할 부분 전부 다 찾아봐봐 → 싹다 고쳐봐\n\n## 3. 입력과 기준\n\n'+vals[3]+'\n\n## 4. 결과와 판정\n\n'+text+'\n\n## 5. 재현과 한계\n\n'+vals[-1]+'\n')
(ADR/'실험/README.md').write_text('# 검증 기록\n\n[계약·SQL·반영](001-query-contracts.md) · [manifest](manifest.json)\n')
m=read(ADR/'실험/manifest.json');put(ART/'candidate-isolation-before-cutover.json',m['design']['code_isolation'])
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover',
 'reason':'User requested all diagnosed query fixes; isolated candidates validated and then official local MAIN136 selected. No legal quality certification.',
 'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],
 'release':{'manifest_path':a['manifest_path'],'sha256':sha(ROOT/a['manifest_path']),'release_id':RELEASE}}
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'main':135,'preexisting_fixture_failures':6},'optimized':result},judge_disagreements=0,
 usage={'external_model_calls':0,'cost_usd':0,'oracle_select_success':180,'oracle_select_failure':1},latency={'scope':'component checks only; no whole-service speed claim'},
 error_taxonomy=[{'type':'BASELINE_ONTOLOGY_FIXTURE','count':6},{'type':'SCOPE_KIND_CACHE_COLLISION_FIXED','count':1},{'type':'JSON_ALIAS_PUSHDOWN_FIXED','count':1},{'type':'HISTORICAL_ARTIFACT_ROOT_FIXED','count':1},{'type':'READ_ONLY_ORACLE_FIXTURE_CHAIN_FIXED','count':1}])
put(ADR/'실험/manifest.json',m)
entry=f'''<!-- GOLD_QUERY_MAIN136_1308_20261103 -->
**2026-11-03 로컬 MAIN136 — Gold·SQLite 반복 조회/FTS/중단 최적화:** [수정·검증](09_ARTIFACTS/AUDITS/20261103-gold-query-optimization/final/수정과_검증_메인반영결과.txt) · [27항목 범위](09_ARTIFACTS/AUDITS/20261103-gold-query-optimization/final/27개_항목별_반영과_남은조건.txt) · [ADR1308](04_EXPERIMENTS/ADR/ADR-1308-gold-query-optimization/README.md). **{RELEASE}·서빙517/MAIN135대비48변경·런타임591+후속로더73/작업664일치**, 공식 prepare/apply·Gold같은MAIN. 요청결속상한cache·SourceScope·페이지본문/카드·tf/전역df·물리key조건·불필요literalJOIN·블록목록·glossary·ontology배치·남은need없는추가복구차단. 문서/원문ID같은문자열 cache충돌은선택전검출수정. **새계약38/회귀177/준비API14/root16/Gold9**, Oracle합성15조건동일(최종45SELECT;전체180성공/fixture1실패)·실모델0. **기존가정fixture6동일실패보존**, 27중14반영/6부분/3기존유지/4조건부·현장필요. R7재개ZIP74파일별도/R6불변·현장미실행, source/native prefix·큰검색/substring·OFFSET/JDBC/LOB잔여. 원문/Goldquery/매핑/설정/layout4보존·DDL/외부배포/메일/Git0. **USER_DIRECTED_CUTOVER/quality_certified=false·실제답품질/전체속도미측정**, MAIN135/Gold이전binding원복보존. 아래MAIN135는이전시점.
<!-- /GOLD_QUERY_MAIN136_1308_20261103 -->
'''
p=ROOT/'AGENTS.md';s=p.read_text();assert 'GOLD_QUERY_MAIN136_1308_20261103' not in s;i=s.index('\n')+1;p.write_text(s[:i]+'\n'+entry+'\n'+s[i:])
p=ROOT/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();i=s.index('\n')+1;p.write_text(s[:i]+'\n**2026-11-03 로컬 MAIN136:** `'+RELEASE+'`·서빙517·Gold동일. 반복조회/범위전달/페이지본문/FTS tf·정확순위/need기반복구를 수정했다. [검증과 잔여조건](../09_ARTIFACTS/AUDITS/20261103-gold-query-optimization/final/수정과_검증_메인반영결과.txt). 실제모델·현장속도 미인증. 기존원문·layout4·Goldquery/매핑보존. 아래MAIN135는이전시점.\n\n'+s[i:])
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
print('Documented MAIN136, exact checks and all partial/conditional items')
