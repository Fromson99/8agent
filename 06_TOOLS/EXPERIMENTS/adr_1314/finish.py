from common import *
import shutil
r=read(ART/'analysis.json');m=read(ADR/'실험/manifest.json');w=read(ART/'working-verify/result.json');assert w['passed']==43 and w['failed']==1 and w['code_unchanged'];m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'before':{'reference':'ADR1313actualexisting, immutablealloutputs'},'after':r['arms']},comparisons=r['same_db_before_after'],usage={'new_model_calls':0,'oracle_selects':r['oracle_actual_selects'],'oracle_writes':0,'ddl':0},latency={'oracle_root':r['oracle_root']},error_taxonomy=[{'type':'preexisting_fixture','count':2,'new_regressions':0}]);put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=['실제SQLite17/17·로컬OracleGold18/18재검증통과. Oracle문서root조회229.486→47.749초(-79.19%),1397→40SQL(-97.14%). 제품oracle_query_matcher1+pin31=32파일작업반영,선택MAIN136그대로.','Oracleroot선택이3946unit문서를40페이지로먼저읽고버렸다. 약5.9MB여서기존완료페이지4MiB상한미달이아닌초과였다. 이후부모조회166회/166.193초·개별조회1191회/1.291초발생. 단순전체본문검색FTS부재문제가아니다.','같은원문/구조기록/metadata_hash/선택hash를유지하고OracleSQL을줄인다. 요청내1문서4096unit/16MiB상한·완료뷰만저장·범위/판본/권한/기한검증유지. 부분/큰문서fallback유지. criteria.json 실행전동결.','before/after는1313캡처에서검증된oracle_dp만격리복원하여전체엔진pin전수확인. 병행작업파일은수정하지않음. after만Units의root완료뷰재사용1모듈+종속pin. 이전실제1313기준과동일17/18사례각단회. before새실제DB재실행없고이전원응답비교.','SQLite전체세대의같은상법원문과실제로컬Oracle23 Goldreadonly게시원문. 원문store SHA동일. 새모델0·OracleDDL/DML0. FTS localGold게시21문서·56475검색행/1499236토큰,SQLite255806검색행/5690178토큰으로BM25통계범위차이.','계약230통과/기존2실패,새root11검사와정상API3포함. 작업통합후43통과/기존1실패(앞선과중복). 수정후SQLite17/17·21.083초,Oracle18/18·51.886초. 기존각22.058/234.487초. 모든35개조건의같은DB결과동일;성공구조6건·원문6개두DB완전동일. 원문/선택반복추가SQL0.','기존실패는release_id없는Oracle모의request와manifest변경뒤encoding오류대신binding오류를기대해야하는fixture. 1313API3해시불일치는격리검증코드복원후모두해소. 1313관측기/동결실패는원본별도보존,후보정상값으로대체하지않음. 이번새회귀0.','Oracleroot SQL1397→40,벽시간229.486→47.749초;전체234.487→51.886초. 남은40SQLexecute/fetch벽시간38.374초·3946rows. SQL시간은순수DBCPU아님. 최초원문6블록27SQL/반복0;FTS실제본문조회유지로반복hit검색1SQL남음. 모델/토큰/비용0.','Units가완료한문서root뷰를부모별목록·unitID맵으로보존해이미검증한행을재사용한다. 실패/부분조회는캐시안함,초과는기존경로. 반환deepcopy로사용자변조전파차단. cachedpoint/children도매번requestrelease/snapshot/ACL/manifest및기한확인. 원문판단/최종검토/중단결정은수정하지않음.','단일순차전후여서DB파일cache등변동가능. 같은SQL제거수와결과동일성은확인했지만현장Oracle19/Dataiku/최종법률답품질/실모델FINISH효과인증아님. 40페이지(약38.4초)조회·SQLite최초자료준비약20초·공급자대기가별도남음.','작업oracle_query_matcher정확후보hash반영·현재모든엔진pin확인,동시작업oracle_dp/새ORDS변경은그대로보존. MAIN136/Goldbinding/원문세대/기본검토표/기본제공자/배포/메일/Gitpush변경0. 작업원복자료working-before와working-integration.json보관.','setup→edit→freeze(모든엔진pin검사)→root11/확장계약→실제querysqlite/oracle→직접결과대조/FTS통계→1모듈작업통합→43검사→runtime전파일SHA보관→hash/validate/status/final/graph.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0]+'\n---\n';p.write_text(front+'\n# Oracle 구조 반복 조회 수정과 두 DB 검증\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{b}' for i,(t,b) in enumerate(zip(titles,bodies),1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file'];s=p.read_text().split('## 8. 사례 최종 판정')[0].replace('현재미실행.','실행완료.').replace('보존예정.','보존완료.');s+='## 8. 사례 최종 판정\n\n'+bodies[5]+'\n\n../artifacts/analysis.json의사례별원값비교및actual/sqlite,actual/oracle전체결과참조.\n';p.write_text(s)
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-sqlite-oracle-diverse';report.mkdir(exist_ok=True)
summary='''SQLite·Oracle 실제 다양한 케이스 검증 결과 — 2026-11-04

이번에는 SQLite와 실제 로컬 Oracle Gold 읽기 경로를 모두 실행했다.
범위: 단일/복수 조문, 범위와 제외, 중복과 순서, 없는 조문, 전부 제외, 역순 범위,
문서 전체에서 조문 선택, 원문 반복조회, 본문 검색·페이지 이동·빈 결과, 권한/변조 거절,
Oracle 캐시 기한 초과. 같은 상법의 다양한 조회 조건이며 전체 법률 답변 품질 시험은 아니다.

최종 검사: SQLite 17/17, Oracle 18/18. 계약230 통과·기존 fixture2 실패.
작업 반영 후43 통과·기존 fixture1 실패(앞선과 겹침). 신규 rootcache11 검사 포함.
원문6개와 성공 구조선택6기록은 SQLite/Oracle 및 수정 전후 모두 완전히 동일.
반복 원문 조회·동일 선택 재검증의 추가 SQL은 양쪽 모두0회.

새로 발견해 고친 병목:
Oracle이 3946개 구조 노드를 한 번 읽고도 약5.9MB가 기존4MiB 캐시 한도를 넘어 버렸다.
그 뒤 부모별조회166회와 개별조회1191회가 추가됐다.
요청 안에서 완료한 문서 구조1개만 4096노드/16MiB 한도로 재사용하도록 수정했다.
권한·판본·기한·원문 hash 검증, 초과 시 기존경로, 실패/부분 캐시 금지를 유지했다.

같은 Oracle 대범위 사례: 229.486초 → 47.749초 (79.19% 감소)
실제 SQL: 1397회 → 40회 (97.14% 감소), 결과·선택해시 동일.
Oracle 검사 전체: 234.487초 → 51.886초. SQLite 최종 전체21.083초.
단회 순차비교로 일반 성능 보장이 아니다. SQLite 변화율을 이번 Oracle 수정효과로 주장하지 않는다.

더 할 일:
1. Oracle 남은40페이지 구조조회: driverexecute/fetch38.374초. Gold의 pack/JSON_TABLE 경로,
   물리조건과 페이지당 반환량·정렬계획을 실제매핑에서 추가최적화할 여지가 크다.
2. SQLite 첫 자료준비 약20초: 기존 전역metadata 준비 비용이 남아 있다.
3. NearAI 응답대기/공백스트림과 FINISH 실제효과: 이번시험은 새모델0회이므로 미측정.
   앞선1312 UNKNOWN결과를 성공으로 바꾸지 않는다.
4. 검색점수 동일성: SQLite255806행/5690178토큰, 로컬Gold56475행/1499236토큰(게시21문서).
   BM25통계범위가 달라 점수차이 자체는 오류증거가 아니다. 이번 검색4조건의 첫두페이지
   본문·순서·총수는 같았으며, 넓은 품질비교는 게시범위를 맞춰야 한다.

반영: 작업제품1모듈+pin31파일. 선택MAIN136/Goldbinding은 그대로다.
실제Oracle쓰기/DDL/외부배포/메일/Gitpush/새모델0. 현장Oracle19/Dataiku 성능 인증 아님.
1313의 동시작업캡처pin불일치·관측기 준비실패도 보존했다. 격리된 검증코드로 API3건 재확인했고,
동시작업의 Oracle 전송기 수정은 덮어쓰지 않았다.

근거: ADR1313, ADR1314의 analysis.json, 실제SQL관측, 원문/범위결과,
contracts 및 working-verify 결과, 전파일SHA검증 runtime보관자료.
'''
(report/'두DB_다양한케이스_검증과_남은문제.txt').write_text(summary)
shutil.copyfile(ART/'analysis.json',report/'analysis.json');shutil.copyfile(ART/'fts-statistics-diagnosis.json',report/'fts-statistics-diagnosis.json')
print('1314 report and user result ready')
