from common import *
import shutil
OUT=ART/'main';RELEASE='query-latency-native-20261104-r1';rp=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json'
r=read(ART/'analysis.json');activation=read(OUT/'activation.json');f=read(DES/'candidate-after.json');stage=read(OUT/'stage.json');b=read(DES/'baseline.json')
for n in ('main-entry','gold-entry','selected-gold-read'):assert read(OUT/(n+'.json'))['passed']
assert read(ART/'prepared-api/result.json')['failed']==0
put(ART/'final-checks.json',{'prepared_sql_plans':638,'engine_preflight':{'engines':30,'files':496},'new_batch_contracts':14,'batch_suite_passed':56,'prepared_api_and_contracts_passed':40,'actual_main_entry_checks':16,'actual_gold_binding_checks':9,'actual_selected_gold_checks':4,'actual_selected_gold_read':read(OUT/'selected-gold-read.json'),'working_candidate_files':len(f['selected_files']),'serving_files':len(stage['files']),'changed_vs_main136':stage['changed'],'current_source_hashes_exact':all(sha(ROOT/n)==h for n,h in f['selected_files'].items()),'new_models':0})
m=read(ADR/'실험/manifest.json');put(ART/'candidate-experiment-before-cutover.json',m)
m['phase']='audit';m['in_sample']=False;m['decision_eligible']=False
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover','reason':'User explicitly requested further fixes and MAIN integration. Isolated frozen539file candidate passed source/query/API checks before official local MAIN137 activation. Earlier prospective candidate boundaries retained in candidate-experiment-before-cutover.json and design/freeze.json. This final audit records actual cutover, not legal quality certification.','production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],'release':{'manifest_path':str(rp.relative_to(ROOT)),'sha256':sha(rp),'release_id':RELEASE}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'source':'ADR1315after immutable exact results'},'after':r['arms']},comparisons=r['same_db_pairs'],usage={'new_models':0,'oracle_actual_case_selects':r['oracle_selects'],'oracle_writes':0,'ddl':0},latency={'oracle_root':r['oracle_root']},error_taxonomy=[{'type':'inherited_fixture_failures','count':2,'new_product_regressions':0}]);put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=['MAIN137 '+RELEASE+' 실제 선택·Gold 같은엔진 결속 완료. 작업6모듈+pin31=37파일, MAIN136대비53변경·서빙524파일·동결후보/작업539파일 일치. 실모델품질인증 없이 사용자 명시 요청에 따른 로컬 반영이다.',
'1315 종류별projection만으로root49.451→49.173초/40SQL이라 효과없음. 물리pack에는 문서/부모값이 JSON 안에 있고 매번 전체 native.unit을 펼쳤다. 원본 source_unit의 문서·판본 색인으로 ID만 먼저 얻고, 각 ID의digest를 기존 lookup색인에99개씩 묶어 읽도록 수정. 최종자료는 그대로published native.unit이다.',
'criteria.json 사전동결: 원문·선택hash·catalogue 동일, Oracle root 개선, 페이지100상한 유지, ACL·판본·기한 유지, 누락/중복/개수불일치 실패·부분cache 금지. 개발계 opt-in매핑 설정도 코드와 함께pin. 동결후결과를보고제품수정0.',
'완료1315after를부모로539파일 후보rev001. 신규배치14·원래root11·관련쿼리/네이티브등56계약 통과. 동일상법 SQLite17·Oracle18조건각1회, 이전원응답과35조건직접대조. 순차실행·자원상한유지. 이후동일코드공식prepare/API/apply/선택된서비스검사.',
'원문세대·source_manifest·query publication 보존. 로컬 Oracle23 readonly·최신CHAN_NO/RFRN_DATA/RGSN_ASTM/docID100매핑 보존, 현장Oracle19/Dataiku/A8패키지환경은별도. 새모델0·DDL/DML0·외부배포0.',
'SQLite17/17·18.758초, Oracle18/18·16.117초. Oracle root49.173→12.081초(-75.43%), 전체53.692→16.117초(-69.98%). 같은DB35결과/catalogue 동일, 두DB원문6·성공선택6기록 동일. 준비된릴리스40검사·실제MAIN16·Goldbinding9·선택된Gold원문/root4 통과.',
'1315의fixture전용SQL미등록19실패는fixture쿼리등록후30통과/1기존실패로확인. release_id없는모의request·manifest변경기대2건은수정전과같음. 초기enginehash3불일치/bytecode freeze준비실패보존. 1316새제품실패0. 선택설정누락위험은기존development_g19_1.json과모듈pin함께포함해해결.',
'Oracleroot40→81SQL:원본ID40+proof1+정확키99개씩40회. driverexecute/fetch39.485→0.531초, JSON자료검증/복사등Python처리포함root총12.081초. 적은SQL수가항상빠른것은아님. FTS4조건본문·순서·페이지동일. 새모델토큰/비용0.',
'ID조회는후보좁히기용이며근거로사용하지않는다. source ID마다native row완전확보·document ID·개수·hash검증을통과한후완료구조cache를사용. 기존한문서4096unit/16MiB상한·초과fallback·사본반환·범위/기한검증유지. SQLite의공유객체freeze와문서JSON반복제거는1315검증수정도같이반영.',
'한문서단회순차비교로일반성능보장아님. SQLite1315첫전후전체23.525→20.643초·resources18.187→16.843초였고1316같은SQLite코드관측18.758/15.126초는변동포함. SQLite초기준비약15초·Oracle구조Python비용약11.55초·모델응답대기남음. 새답정확도/실제FINISH효과/제공자안정성미측정.',
'사용자 “추가 수정하고 메인에 반영해”에따라공식prepare/apply·MAIN137·Gold동일엔진. 기존FINAL검토표기본값·제공자설정·원문세대·온톨로지설정보존. fallback0실모델시험설정은이전시험범위. rollback은새release/rollback/ACTIVE_RELEASE.json의MAIN136 및 main/gold-before.json binding으로복원. 실제코드/원문/권한문제시되돌림,느리다는이유로검증해제안함.',
'setup→edit→native SQL재생성→freeze→validate→batch-contracts→query after sqlite/oracle→analyze→release_prepare(작업CAS통합·preview/prepare)→prepared-api40→activate(confirm-main)→main_entry/gold_entry/selected_gold_read→무손실runtime보관→hash/validate/status/final/graph. 모든실제결과artifacts,최종전환main디렉터리.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0].replace('phase: probe','phase: audit').replace('in_sample: true','in_sample: false').replace('main_wiring: unchanged','main_wiring: user-directed-cutover')+'\n---\n';p.write_text(front+'\n# Oracle 구조 조회 개선과 MAIN137 반영\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{x}' for i,(t,x) in enumerate(zip(titles,bodies),1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file'];s=p.read_text().replace('현재미실행.','실행 완료.').replace('보존예정.','보존완료.').split('## 8. 사례 최종 판정')[0];p.write_text(s+'## 8. 사례 최종 판정\n\n'+bodies[5]+'\n\n'+bodies[8]+'\n\n'+bodies[10]+'\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-query-latency-main137';report.mkdir(exist_ok=True)
text='''추가 수정과 MAIN137 반영 결과 — 2026-11-04

완료: 로컬 MAIN137(query-latency-native-20261104-r1) 선택. Gold도 같은 엔진을 사용한다.
작업6모듈+pin31=37파일 반영, MAIN136 대비53변경·서빙524파일, 검증후보/작업539파일 일치.
실제 로컬 서비스16확인, Gold 연결9확인, 선택된 Gold 원문/3946구조/재사용4확인 통과.
현장 GENOS/Dataiku 배포와 Git push/메일은 하지 않았다.

고친 부분
- SQLite: 구조 메타데이터의 같은 객체 중복 복사와 문서 JSON 반복 파싱을 줄였다.
- Oracle Gold: source_unit 색인에서 문서의 구조ID만 먼저 읽고, native.unit 원문자료를
  99개 lookup키씩 묶어 조회한다. 자료 종류별 projection도 기존 기능에 연결했다.
- 이전 작업의 원문/구조 재사용, children색인, 조건부 FINISH 종료 수정, Oracle 준비SQL 및
  ORDS 전송기를 함께 반영했다. 개발계 선택매핑의 JSON 설정 누락도 pin 결속으로 막았다.
- 최신 CHAN_NO/RFRN_DATA/RGSN_ASTM/문서ID100 매핑, 원문·권한·판본·기한·hash 검증 보존.
  검토표 기본값은 이번에 변경하지 않았다.

실제 측정
Oracle 대범위 구조 조회: 49.1726초 → 12.0811초 (75.43% 감소).
Oracle 전체35종중 해당18조건 검사: 53.6921초 → 16.1166초 (69.98% 감소).
root SQL은40→81회지만 driver실행/반환시간은39.4846→0.5308초로 줄었다.
원본ID40페이지+proof1회+정확키40묶음이다. 매 페이지 전체 JSON을 펼치는 일을 피했다.

SQLite 첫 추가수정 전후 전체23.5250→20.6434초, 초기준비18.1867→16.8433초.
최종 동일 SQLite코드 검사18.7584초/초기준비15.1255초는 재관측값으로 환경변동도 포함한다.
Oracle 개선율을 SQLite나 전체 실모델 답변시간 개선율로 옮겨 말하지 않는다.

검증
SQLite17/17, 실제 readonly 로컬Oracle Gold18/18. 동일DB 전후35조건 결과 동일.
원문6개·성공 구조선택6기록은 양쪽 DB/전후 모두 동일, catalogue도 동일.
정상/누락·범위·제외·중복·없음·FTS 페이지·빈검색·권한·변조·기한을 검사했다.
새배치14를 포함한 계약56 통과, 준비된릴리스의API/중단/원문검사40 통과.
앞선1315의 추가49/회귀179/fixture준비30/native실제SELECT+ORDS71통과는 서로 중복이 있어 합산하지 않는다.
기존 fixture2실패는 before에서도 같은 오류. 테스트 전용 SQL 미등록 실패와 준비 실패도 원본 보존했다.
Oracle 사전준비638계획 --check 및 엔진30/의존파일496 preflight 통과.

남은 부분
- SQLite 초기 준비 약15초와 Oracle 구조처리 중 Python 검증·복사 약11.55초.
- 모델 응답 대기, 실제 답변 정확도, FINISH 분기 실효는 이번 새모델0회로 미측정.
- 같은 상법문서의 여러 조회 조건을 단회 순차비교했다. 모든 법령/부하의 성능 보장은 아니다.
- 로컬Oracle23 결과이며 현장Oracle19·Dataiku·A8 패키지 제한 환경 인증이 아니다.

롤백
새 릴리스의 rollback/ACTIVE_RELEASE.json은 MAIN136을 보존한다.
Gold 이전 binding은 ADR1316/artifacts/main/gold-before.json에 있다.
원문·Gold 게시·데이터DML/DDL 변경0. 사용자 지시에 따른 로컬 반영이며 quality_certified=false.
근거: ADR1315(종류별 제한만으로 Oracle개선 실패 포함), ADR1316 analysis/main/actual.
'''
(report/'추가수정_실측_메인반영결과.txt').write_text(text)
for n in ('analysis.json','final-checks.json'):shutil.copyfile(ART/n,report/n)
shutil.copyfile(OUT/'activation.json',report/'activation.json')
print('MAIN137 audit/report prepared; runtime archive and final validation remain')
