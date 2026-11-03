# 8-AGENT 작업 가이드

<!-- ORDINARY_ASSESS_MAIN135_1301_20261103 -->
**2026-11-03 현재 로컬 MAIN135 — 일반 RAG 중복 입력·검토 요구 정리:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261103-ordinary-assessment-contract-main/정리와_검증_메인반영결과.txt) · [ADR1301](04_EXPERIMENTS/ADR/ADR-1301-ordinary-assessment-contract-main/README.md). **ordinary-assessment-20261103-r1·서빙516/MAIN134대비34(제품3+pin31)·후보rev001/작업540일치**, 공식 prepare/apply·Gold동일. 일반 ASSESS/보완 무손실입력v2(구v1reader)/shared review_links 확대, 완전확보·비어있지않은 SOURCE_GOAL/STRUCTURE_SELECTION need만 명시scope USE/EXCLUDE/OPEN에서 서버조립·전체기존검증. 의미need/미확보/충돌·범위와이유 유지. **계약196(새25+기존171)/모의API22/준비API13/root16/Gold9 통과**(준비13은중복), fixture회귀1별도. 동일12구성조건에서2개 user24204→19590bytes·질문9→2/첫원문6→1, 자료별목적200개 필수행603→402·user182005→177391/schema34437→31459bytes; bulk200은203→202행, 모든입력전체정확복원. **새모델/Oracle0·대용량실모델효과 미검증**, UNKNOWN/N1·독립검토증가·부분재검토 미해결. 준비오류2/구v3 fixture4/모의공유변환4/가정저장필터4 실패원본보존·제품rev001불변. 원문·Goldquery/매핑/설정/연결기/layout4·기본OFF/GoldON 유지. **USER_DIRECTED_CUTOVER/quality_certified=false**, MAIN134+Gold이전binding 원복보존·DDL/Git push/메일/현장배포0. 아래MAIN134유지는이전시점이다.
<!-- /ORDINARY_ASSESS_MAIN135_1301_20261103 -->


<!-- LOCAL_INTEGRATION_22_1298_20261103 -->
**2026-11-03 — 기본 통합테스트22개·실제 ON/OFF 향상 미입증:** [목록 XLSX](09_ARTIFACTS/REPORTS/DOCUMENTS/20261103-integration-test-list/8-AGENT_기본22개_로컬실행결과_20261103.xlsx) · [실제 결과](09_ARTIFACTS/AUDITS/20261103-local-integration-verified/로컬검증결과.txt) · [ADR1298](04_EXPERIMENTS/ADR/ADR-1298-local-ontology-ab-native-grant/README.md). 기존20+대사표+온톨로지 성능 확인만 포함. **현재 MAIN134 실제 기본조회 API13 HTTP검사 통과/모델0**; 키워드는 탐색시작점2/원문후보0으로 제한. 모의 기능은 MAIN133 계약66통과/4실패, 추가 범위·DOM3통과/고정문구1실패 및 같은사건 사실보완 의미검사1통과로 구분. **실제 A/B는 시작 시 동결 MAIN133/513파일·상법365/369 동일2질문·Qwen26/정상26/UNKNOWN0·보고$0.105873**: OFF2/2 완성(각3주장), ON0/2 최종연결검토 미완료/원문전용. OFF706.530초/13호출/114400보고토큰, ON547.551초/13호출/98716토큰이나 미완료이므로 개선율 계산/성능향상 주장 없음. 두 ON의 기존 게시본 실제wire전달 확인, 369 ON의 PREPARED_NOT_SENT 표시는 실제 전송과 불일치. 확보span56/전달83 대조·원문/ACL/wire불일치0·예산26일치·네 재조회 추가0. **대사 실제2모델 뒤 native supervisor 승인 연결 오류/API500·표생성0**(ADR1293), 모의 표/DOM 통과와 구분. 초기1293 가상주소6GiB 매핑 실패,1294 파생질문 승인,1296 내부사건ID 승인 실패 보존;1298은 원응답 native재생/다음gateway승인/새모델0 확인 후 실행. 이 작업 전체 실제40회/보고$0.12723206이며 실패시험을 제외하지 않음. **제품/MAIN/Gold설정/Oracle쓰기·DDL/게시/메일/현장변경0**, 병행 선택된 MAIN134의 실모델 결과로 확대 금지. 네 ADR 최종검사 통과·graph 기존16/이번새0. 법률품질·GENOS·브라우저 조작 인증 아님.
<!-- /LOCAL_INTEGRATION_22_1298_20261103 -->

<!-- MAIN134_SCHEMA_SCALING_1299_20261103 -->
**2026-11-03 — MAIN134 스키마·자료 증가 진단 완료(제품수정0):** [문제·수치·수정순서 TXT](09_ARTIFACTS/AUDITS/20261103-main134-schema-scaling/문제와_과도한요구_자료증가_점검.txt) · [ADR1299](04_EXPERIMENTS/ADR/ADR-1299-main134-schema-scaling-diagnosis/README.md). 동일539파일/서빙515, 실제1297 일반 ASSESS generation schema·provider schema·user bytes 정확재구성. **원문2개 고유450bytes인데 schema22668/system21171/user24204bytes·질문9회/첫원문6회**, 가정wire는각1회. 실제 최초/보완 claims4·issue/gaps 동일, need2행 C4제외로 연결3오류해소·보완17.730초/$0.00429687; 출력6110bytes중 검토2표3317(54.3%,전부불필요아님). 일반RAG에는 shared review_links·lossless assessment 적용없음(현재scenario조건). **2/10/40/100/200원문×자료별목적/전체묶음2형태+긴원문2=12 offline구성조건 통과·새모델0**. 자료별목적+전체묶음은2→200에서 user24.2→182.0KB/schema22.7→34.4KB/필수판단·need·범위행9→603, bulk200은203행; 추가1000자/200건은user606.3KB·총요청680.2KB/603행. 원문무손실·schema factoring으로단순지수증가아님·KB는토큰아님. **검토행/연결재작성 부담 확인, 공급자공백UNKNOWN의스키마인과는미확정**; 실제대용량모델/검색/Oracle/GENOS 성능 미검증. 일반무손실/공유연결 확대→조사장부 서버조립→변경영향 재검토를 제안했으나 구현/MAIN/DB/DDL/배포0.
<!-- /MAIN134_SCHEMA_SCALING_1299_20261103 -->


<!-- MAIN134_DISPLAY_LIVE_1295_1297_20261103 -->
**2026-11-03 — MAIN134 실제 가정·화면 시험 부분 확인/전체 미통과:** [실제 결과 TXT](09_ARTIFACTS/AUDITS/20261103-main134-display-live/실제실험과_검증결과.txt) · [ADR1297](04_EXPERIMENTS/ADR/ADR-1297-main134-display-observer-live/README.md) · [초기 관측기 실패1295](04_EXPERIMENTS/ADR/ADR-1295-main134-scenario-display-live/README.md). **MAIN134/완료1292 동일539파일·서빙515 정확일치·제품변경0**. 실제 Qwen6(정상4/4291/UNKNOWN1)·322.270초·보고$0.01223689(429/UNKNOWN 사용량 미보고), 기준5물리(429→NearAI1전환 포함)/주장4·최초검토 연결오류3종 기존1회보완 복구. **숫자3분기 금액TRUE/FALSE/TRUE·승인UNKNOWN·N1미등록/최종UNCONFIRMED·모델0**, 기준/숫자/복원5응답 새프로세스 저장검증·화면함수 투영 확인, 기준 온톨로지 RESPONSE_RECEIVED/주장채택NOT_RECORDED. 저액 의미검토1회는 Parasail HTTP200헤더 뒤 공백60조각660bytes/179.924초→UNKNOWN/API504·worker회수; 고액/규칙 의미 미실행·이후모델0·기준사건 보존. **가정 의미완료0/3은 실제1 timeout+2미실행이며 3오답률 아님; 현재/기준 이력분리·정확ID보완·가정계산표 저장은 실모델 미검증**. 실제 저액 wire 질문/원문 각1회·무손실복원1·서버결과 재작성0·미확인ID제시1/선택0. 저장원문대조18(고유2)/모델전달6·원문/ACL/wire불일치0·예산6일치·재조회추가0·자원중단0. **초기1295는 정상HTTP200/20.232초/$0.00307048 뒤 관측기의 불변calls.json 재작성 오류로 제품UNKNOWN/502**, 원응답·비용·원래UNKNOWN 무수정보존/같은journal재실행0; 후속은 관측기 로컬3+자원8검증 후 새ADR. 합계7물리/보고$0.01530737, 두runtime 전체SHA 무손실보관. **제품/MAIN134/Gold/Oracle/운영DDL/Git push/메일/현장변경0**, 브라우저·법률품질·인과개선율 인증 없음.
<!-- /MAIN134_DISPLAY_LIVE_1295_1297_20261103 -->


<!-- RAG_ONTOLOGY_CONSOLE_MAIN134_1292_20261103 -->
**2026-11-03 현재 로컬 MAIN134 — RAG·온톨로지·관리 화면 연결 수정:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261103-rag-ontology-console-integration/수정과_검증_메인반영결과.txt) · [ADR1292](04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration/README.md). **ontology-console-20261103-r1·서빙515/MAIN133대비41(제품10+pin31)·작업539정확결속**, 공식 prepare/apply·Gold 같은MAIN. 두 앱 공통 대시보드/자유작업/도메인/시나리오, 인증 호스트의 별도 reader/writer/용어집·scope·상태 분리. 제시된ID의 사유문오용은 기존1회보완·원응답보존, 현재가정 확인범위와 기준질문/조사이력 별도표시. **계약169(새17)/준비API14·root16/Gold9/UI묶음6 통과**(중복범위 합산금지). 실제 로컬Oracle 격리 작성→승인게시→새프로세스 동일조회/ACL거절→철회/답변차단 통과; 기존3게시/12앵커/9경로 보존. 별도 **ontology_console_20261103_r1.zip/525파일** 준비·backend515해시결속. 최초 화면fixture3/Oracle ID불일치1/모의주입누락1 실패·runtime 보존. **USER_DIRECTED_CUTOVER/quality_certified=false·실모델0**, ADR1290 전체미통과·자연문 비교과차단/미등록gap/N1효과UNKNOWN 유지. 현장 Dataiku/GENOS/NFS/원격호스트 동시성 미검증·DDL/Git push/메일0. MAIN133+Gold+기존UI 원복보존; **새application-v4 저장namespace는 호환reader 필요**, Oraclelayout4유지. 아래 MAIN133 유지 설명은 이전 시점이다.
<!-- /RAG_ONTOLOGY_CONSOLE_MAIN134_1292_20261103 -->


<!-- SCENARIO_SERVER_COMPUTATION_LIVE_1290_20261103 -->
**2026-11-03 — 서버 계산 수정본 실제 Qwen 부분 확인·전체 미통과:** [실제 결과 TXT](09_ARTIFACTS/AUDITS/20261103-scenario-server-computation-live/실제실험과_검증결과.txt) · [ADR1290](04_EXPERIMENTS/ADR/ADR-1290-scenario-server-computation-live/README.md). **완료1289와 동일528파일·Qwen6(정상5/UNKNOWN1)·480.835초·보고$0.03527936(UNKNOWN 사용량 미보고)**. 기준3호출/주장3, 저액1호출/주장5·현재735000금액TRUE/승인UNKNOWN·서버 계산표 저장/새프로세스 검증. **계획3분기 중 핵심채택1/3, 저액도 표시품질 완료 아님**: 205문자gap 반복0이나 computed_gap_ref를 JSON필드 대신 이유문에 써 내부ID노출·기준138만원 요구문 잔존. 가정입력3건 질문/제1조원문 각1회·무손실복원3·조건/적용연결 재작성0·서버 실행계획 사본 제거, **미확인ID 제시각1/구조화 선택0·실제 전개 경로 미검증**. 고액 최초는 제2조 C2에 제1조 근거를 연결해 정당거절, 보완은HTTP200헤더+공백60조각660bytes/179.931초→UNKNOWN/API504·worker회수·이후모델0. 규칙245만원 숫자비교만0모델TRUE·실제 의미분기는 사전중단으로 미실행. 확보22/전달8·원문/ACL/wire불일치0·예산6일치·재조회 추가0·기준사건보존·자원중단0. 실패/전체원응답·runtime 무손실보존, 후처리오류2건 정정·보존. **제품/MAIN133/Gold/Oracle/운영DDL/Git push/메일/현장변경0**, 인과 개선율·법률품질·새3분기 성공 주장 없음.
<!-- /SCENARIO_SERVER_COMPUTATION_LIVE_1290_20261103 -->


<!-- SCENARIO_SERVER_COMPUTATION_1289_20261103 -->
**2026-11-03 — 가정 계산·비교·미확인 입력의 서버 직접 표시 작업 반영:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261103-scenario-server-computation/수정과_검증결과.txt) · [남은 문제](09_ARTIFACTS/AUDITS/20261103-scenario-server-computation/남은문제와_다음검증.txt) · [ADR1289](04_EXPERIMENTS/ADR/ADR-1289-scenario-server-computation/README.md). **제품7+pin31=38파일·신규1/삭제0·후보rev002/작업528일치, 선택 MAIN133 유지**. 승인 계획/현재 조건 대조 후 계산표를 주장0/검토미완료에도 직접 저장·표시, application-v4는 수치/적용연결/비교문 재작성 제거. 미확인 FACT의 명시적 computed_gap_ref+쟁점 선택만 같은 위치에 전개하며 자유문/원문/600자gap 무절단·임의연결추정0. 실행계획 사본은 서버에 보존, 기존v2/v3 reader·옛값거절·권한/근거/예산/재조회 유지. **계약329(새46+기존283)+모의API8 통과, 작업API1 중복확인**. 최초API2 fixture실패/제한환경대기2 원본·runtime6개 무손실 해시복원 보존. **실모델/Oracle0·MAIN/Gold/운영DB/DDL/Git push/메일/현장변경0**. 실제1286 주장채택1/3·저액반복/고액비교 과차단/규칙옛값재사용 실패 유지; 새Qwen효과 미검증. 자유문 비교 과차단·기준요구 옛금액표시·미등록gap 반복·N1효과식은 미해결이며 효과식 자동승인/게시0·법률품질 미인증.
<!-- /SCENARIO_SERVER_COMPUTATION_1289_20261103 -->


<!-- SCENARIO_CUMULATIVE_MAIN133_1287_20261102 -->
**2026-11-02 현재 로컬 MAIN133 — 누적 가정·검토 수정 반영:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261102-scenario-cumulative-main133/메인반영과_검증결과.txt) · [남은 문제/온톨로지 범위](09_ARTIFACTS/AUDITS/20261102-scenario-cumulative-main133/남은문제와_온톨로지_해결범위.txt) · [ADR1287](04_EXPERIMENTS/ADR/ADR-1287-scenario-cumulative-main/README.md). 사용자 “지금까지 한 것 메인 반영”으로 **MAIN133/scenario-cumulative-20261102-r1·서빙513파일·MAIN132대비67변경(제품36+pin31), 신규9/삭제0** 공식 prepare/apply. 검토표·수치가정·타입계획·입력통합·공유검토·적용연결의 누적 작업527은 완료1285/실제1286과 동일, 보조14파일 별도보존. **준비 복구API13+가정API7, 실제root16/Gold9 통과**. 원문 세대·Gold query/매핑/설정/연결기·layout4/구조화Oracle·상세NFS 유지, Gold 엔진 binding만 정렬. **USER_DIRECTED_CUTOVER/quality_certified=false**; 실제1286의8호출/주장채택1/3·저액gap반복·고액정상비교 과차단·규칙옛한도 재사용은 미통과로 보존. 온톨로지 기존조건3대조/연산8확인: N2금액·N3승인 계산 가능, N1효과식은 미등록/UNKNOWN. 서버 수치·비교 표시/미확인ID 연결 개선과 최종효과식 승인 제안은 **미구현·미승인·미게시**이며 법률 의미 자동해결 주장 없음. 준비 기록경로/상태명 오류2건은 반영전 차단·보존. **원복 MAIN132 포인터+Gold 이전binding 보존**, 새실모델/Oracle/운영DB·DDL/Git push/메일/GENOS현장배포0. 아래 MAIN132 유지 설명은 각 이전 시점이다.
<!-- /SCENARIO_CUMULATIVE_MAIN133_1287_20261102 -->

<!-- SCENARIO_SCOPE_LIVE_1286_20261102 -->
**2026-11-02 — 가정 연결 범위 수정본 실제 Qwen 미통과:** [실제 결과 TXT](09_ARTIFACTS/AUDITS/20261102-scenario-scope-contract-live/실제실험과_검증결과.txt) · [ADR1286](04_EXPERIMENTS/ADR/ADR-1286-scenario-scope-contract-live/README.md). **완료1285와 동일527파일·Qwen8/stop8·596.888초·$0.077952·UNKNOWN0**, 기준3호출/주장6, 저액1호출/주장5만 채택, 고액·규칙 각2호출/주장0. **핵심 주장채택1/3이며 저액도 품질완료 아님**: 실제gap1개에 참조1~24와 미완성25를 담은433문자 원응답이 그대로 표시됨(raw=canonical·제품절단0), 기준사건138만원 요구문도 확인범위에 잔존. 고액은 현재172.5만원을 맞게 설명했으나 괄호의 정상적인 변경전138만원 비교가 현재설명 필드에 있어 과차단. 규칙은245만원 참조/별도비교만 맞고 본문은옛100만원 한도를 최초·보완 동일재사용하여 정당거절. **실제가정입력5건 질문/제1조원문 각1회·무손실복원5·조건결과재작성0·공유3정의/9~11참조**, 일반승인/예외설명 가정연결 과요구는 저액에서 해소 확인. 확보26/전달12·원문/권한/wire불일치0·예산8일치·숫자비교/재조회모델0·기준사건보존. 중복원인·개선율 인과A/B 아님. **이번 제품/MAIN132/Gold/Oracle/운영DDL/Git/메일변경0**, 격리SQLite기록·실패원본보존·동일셀재실행0·법률품질/GENOS 미검증.
<!-- /SCENARIO_SCOPE_LIVE_1286_20261102 -->

<!-- SCENARIO_SCOPE_FIX_1285_20261102 -->
**2026-11-02 — 가정 연결 범위·비채택 검토·현재/과거 설명 수정:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261102-scenario-review-scope-fix/수정과_검증결과.txt) · [ADR1285](04_EXPERIMENTS/ADR/ADR-1285-scenario-review-scope-contract/README.md). **작업 제품5+pin31=36파일·후보rev005/작업527일치, MAIN132 유지**. application-v3은 일반 승인/예외 설명에 가정 연결을 강요하지 않고 변경 조건의 실제 적용 연결은 유지한다. 연결 없는 현재 설명도 옛금액 재사용 검사·comparison_text는 전체 비교문 별도보존, 과거참조가 현재옛값을 허용하던 우회 차단. shared-review-v2는 스키마상 빈주장 행에서 claim/link 재작성 없이 정확한 행경로에 []복원·기존상태/근거/gap검증 유지, 공유연결 개수오류를 실제link_ref/정의 위치로 안내. 질문은 문자열절단 없이 원래task/facts에서 조립. **계약283+모의native7통과·작업native7재확인(중복)**, 긴질문/비교문/600자gap/저장변조/재조회 보존·구v2/v1 reader호환. 실제1284 제안5개 컴포넌트검사이며 새실Qwen최종통과 아님. 초기계약1/API6/API4실패·수정/준비차단 보존. **실모델/Oracle0·MAIN/Gold/DDL/Git/메일/현장변경0**, 자연어전체/법률품질 미인증.
<!-- /SCENARIO_SCOPE_FIX_1285_20261102 -->

<!-- SHARED_SCENARIO_LIVE_1284_20261102 -->
**2026-11-02 — 입력 통합·공유 검토 수정본 실제 Qwen 미통과:** [결과 TXT](09_ARTIFACTS/AUDITS/20261102-shared-scenario-contract-live/실제실험과_남은문제.txt) · [ADR1284](04_EXPERIMENTS/ADR/ADR-1284-shared-scenario-contract-live/README.md). **ADR1283와 동일527파일·Qwen11/stop11·753.279초·$0.11360576·UNKNOWN0**, 가정3개 전부 주장0/원문전용. 기준 최초4호출 미완료→사전선언 후속1회 주장4; 저액/고액/규칙 각2회 실패. 설명 전체에 가정연결을 요구하여 일반 예외·승인 설명도 누락거절, 공유참조 복원후 UNRESOLVED 빈주장 제약 충돌. 규칙분기 CURRENT245만/HISTORICAL100만 참조를 달고도 본문은138만을옛100만한도로판단하여 **타입참조만으로 현재/과거 의미 보장 안됨**. 원문6→1·독립동일질문8→1이지만 복합문장속질문1회잔존(전체9→2), 실제6입력 무손실복원·조건결과재작성0·공유3정의/10~15참조. 확보30/전달span18·원문/권한/wire불일치0·숫자비교/재조회 추가모델0·기준사건보존. 이전1/3과 인과A/B 아님. 이번 제품/MAIN132/Gold/Oracle/DDL/Git/메일변경0·실패재실행0·일반 법률품질/GENOS 미검증.
<!-- /SHARED_SCENARIO_LIVE_1284_20261102 -->

<!-- TYPED_SHARED_REVIEW_WORKING_1283_20261102 -->
**2026-11-02 — 타입 적용값·공유 검토 연결 후속 수정:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261102-typed-application-shared-review/수정과_검증결과.txt) · [ADR1283](04_EXPERIMENTS/ADR/ADR-1283-typed-application-shared-review/README.md). **작업 제품10+pin31=41파일·후보rev006/작업527일치, 선택MAIN132 유지**. 가정 ASSESS/보완의 review_links로 판단/need/범위/요구의 동일 주장·근거 조합1회 정의·기존검증 전부유지. scenario-application-v2 CURRENT/HISTORICAL 역할·245만 원 등 KRW 동치표기·서버 수치표시·옛값현재선택/잘못된금액/미확인확정 거절. **계약269+native7통과/실패0·작업API7재확인(중복)**, 공유연결 오류1회보완·원제안/600자gap/원래사건/재조회0호출 보존. 기존reader·일반사건 유지. 초기파싱1/검사기import6/저장스키마2실패와 수정기록 보존. 독립 채택/제외/충돌 의미는 합치지 않음·자연어전체/법률품질/실Qwen효과 미인증·실모델/Oracle0·MAIN/Gold/DB/DDL/Git/메일/현장변경0.
<!-- /TYPED_SHARED_REVIEW_WORKING_1283_20261102 -->

<!-- LOSSLESS_ASSESSMENT_WORKING_1282_20261102 -->
**2026-11-02 — 사건 입력·조건 확정값·gap 무절단 1차 수정:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261102-lossless-assessment-contract/수정과_검증결과.txt) · [ADR1282](04_EXPERIMENTS/ADR/ADR-1282-lossless-assessment-contract/README.md). **작업 제품10+pin31=41파일 반영·동결후보/작업525일치, 선택 MAIN132 유지**. 가정 ASSESS/보완 최소입력v2의 현재 사건 묶음·동일본문 전체참조/v1읽기 호환, 서버 조건표 생성제외·복합const ID결속, gap 전체사유 보존·유일요구 연결/모호성거절·구체오류. **신규41+기존159통과·기존실패2부모동일**, 작업 native API7 재확인(후보와 중복). 600자 끝예외·저장/재조회/미확인상태 보존, 기존 실험입력5개 질문8→1/원문6→1·전체복원동일. 실제모델0/Oracle0·숫자표현제한/의미검토표전면통합 미구현·Qwen효과/인과/GENOS/NFS 미검증. 초기native6실패와 수정기록 보존·원복파일보관·MAIN/Gold/DB/DDL/Git/메일변경0.
<!-- /LOSSLESS_ASSESSMENT_WORKING_1282_20261102 -->

<!-- MAIN132_REVIEW_MULTITURN_20261102 -->
**2026-11-02 현재 로컬 MAIN132 — 최종 검토 복구·실제 멀티턴:** [수정·사용·검증 TXT](09_ARTIFACTS/AUDITS/20261102-final-review-main132/수정과_멀티턴_실제검증_메인반영결과.txt) · [기술1274](04_EXPERIMENTS/ADR/ADR-1274-final-review-multiturn-recovery/README.md) · [실제1277](04_EXPERIMENTS/ADR/ADR-1277-qwen-followup-derived-context/README.md) · [반영1276](04_EXPERIMENTS/ADR/ADR-1276-final-review-recovery-main/README.md). **MAIN132/final-review-multiturn-20261102-r1·504서빙·5제품+pin31=36변경·검증518정확결속**, Gold 동일MAIN. 유일한 명시 필요-주장-USE원문 연결의 target 누락만 모델0회로 결속·전검증 유지. 최종 보완소진은 확보검증원문만/claims0/INCOMPLETE로 반환·거절판단/예산/UNKNOWN 무재전송 보존. 사실보완은 같은사건/원문으로 재판단. **기존641확인·신규17·최종추가104(중복범위), 준비API13/root16/Gold9 통과**. 검사기journal/좌표·timeout표식 회귀 수정과 이전실패보존. **실제1277 Qwen11(첫7+후속4)/UNKNOWN0·348.743초·$0.04022728**, 첫 검토2회주입→원문응답, 후속FACT_UPDATE/같은사건/원문2·사실3→ANSWER/COVERED/주장4·원문재검색0·두재조회추가0. 원문8/전달12·ACL/wire불일치0. **1275 실제10회/$0.03191448은 파생문맥 실험grant 거절500로 미통과 유지**;1277은 제품동일/연결기승인결속수정별도. USER_DIRECTED_CUTOVER/quality_certified=false, 실제법률품질/Oracle E2E/GENOS/NFS·부하미검증·공급자UNKNOWN 내부원인미해결. 기존원문/Goldquery·매핑·설정·연결기·layout4/구조화Oracle상세NFS 유지. **MAIN131+Gold이전binding 원복 보존**, DB/DDL/quota/Git/메일/현장배포0. 아래MAIN131유지는이전반영시점.
<!-- /MAIN132_REVIEW_MULTITURN_20261102 -->


<!-- MAIN131_CUMULATIVE_1272_1273_20261102 -->
**2026-11-02 — 누적 작업 전체 서빙 MAIN131 반영 완료:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261102-cumulative-main131/반영과_검증결과.txt) · [ADR1272](04_EXPERIMENTS/ADR/ADR-1272-cumulative-loop-workspace-main/README.md) · [Gold 호환 ADR1273](04_EXPERIMENTS/ADR/ADR-1273-gold-user-directed-main-binding/README.md). 사용자 “지금까지 된거 메인에 싹다 반영해” 지시로 공식 prepare/apply, **MAIN131/cumulative-loop-workspace-20261102-r1·서빙504파일·MAIN130대비57변경(제품26+pin31), 신규8/삭제0**. 현재 에이전트 오류/중복·충돌 선택 복구·일반 원문 범위/주장 검토·자유 작업공간 컴파일/승인/게시/철회 구현을 전부 선택. 작업518동결과 기존641검사·실제Qwen 오류주입3종 검증 코드 동일; 연구/미등록 보조14파일은 작업에 보존. **이번 새 작업공간110/API13/Gold승인·변조거절16통과, 실제root16조건/Gold연결9조건 통과**; 중복범위 합산금지·새모델/Oracle호출0. Gold 연결기1파일의 명시 승인 영수증 검증과 binding을 함께 반영, 원문/쿼리릴리스R18/물리매핑/온톨로지설정 보존. **USER_DIRECTED_CUTOVER·quality_certified=false**이며 완료 부모를 품질인증으로 재분류하지 않음. 자연 NEED_TARGET_CLAIM_LINK422·공급자 UNKNOWN504, 실제Oracle 작업공간 전체·NFS/GENOS·법률품질은 미해결/미검증 범위 유지. 구조화Oracle/상세NFS·layout4 reader 유지, 기존270MiB상한/DB내용/DDL 변경0. **원복 MAIN130 포인터+Gold 이전 연결기/바인딩 보존**, layout4 미지원MAIN129로 원복금지. Git push/메일/현장배포0. 아래 MAIN130 유지·승격0 설명은 각 이전 시험 시점이다.
<!-- /MAIN131_CUMULATIVE_1272_1273_20261102 -->

<!-- LOOP_RECOVERY_QWEN_1271_20261102 -->
**2026-11-02 — 에이전트 루프 작업 수정·실제 Qwen 오류주입 복구:** [전체 결과 TXT](09_ARTIFACTS/AUDITS/20261102-agent-loop-qwen-recovery/수정과_실제실험_결과.txt) · [ADR1267](04_EXPERIMENTS/ADR/ADR-1267-legacy-selection-contract-repair/README.md) · [ADR1271](04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery/README.md). 기존 응답결속 예외·종료요청 재전송·소유권 전이 보완 위에 **v6/v7 선택 provenance 투영1모듈+pin37**, 실제 보완에서 발견한 **범위 일치 좌표(body:제1조) 정규화1모듈+pin31** 작업 반영. 범위 충돌/복수좌표/원문·권한·최종검토 검증 유지. **현재 작업 통합641pytest/실패0**, 앞선589와 후보71은 겹치므로 합산 독립표본 아님. **작업/마지막 실제 후보518파일 일치, 선택 MAIN130496 유지·승격0**. 실제 native API/SQLite 합성3조문/온톨로지OFF/Qwen3.8-27b·Parasail23/stop23/UNKNOWN0·보고$0.08147056: 중복/충돌/잘린JSON 각각 실제 응답에 주입→실제 보완→HTTP200/답변 저장·동일답변 재조회/추가모델0; 132.566/76.965/116.472초. 확보12/전달28대조·원문/권한/전송불일치0·자원중단0. **1266 기본200 뒤 실험재조회500,1268 공백UNKNOWN504,1269 주입미도달2정상+자연 NEED_TARGET_CLAIM_LINK422,1270 세 좌표거절422 원본 보존**; 모든422/공급자장애 해결이나 법률품질 인증 아님. 재조회 journal의 복원 누적 예산을 더한 감사 중복합산은 별도 정정 영수증으로 기록. 최초 반영 예상pin개수 오류는 쓰기 전 차단·반영전 검사 중단 보존 후 정확한32파일 통합/641재검증. **Oracle/NFS/GENOS·동시 실모델 부하 미검증, 운영 데이터/DDL/Git/메일0**. 관련 검사 실행기는 `06_TOOLS/maintenance/check_agent_loop_recovery.py`; 전체 저장소 모든 테스트 목록은 아님.
<!-- /LOOP_RECOVERY_QWEN_1271_20261102 -->

<!-- MAIN130_PROGRESS_DEDUP_1261_1262 -->
**2026-10-31 — 진행 상태 무손실 중복 축소 MAIN130·실제 모델은 기한 종료:** [반영·실험 TXT](09_ARTIFACTS/AUDITS/20261031-oracle-progress-dedup-main/메인반영과_실제실험_결과.txt) · [기술 ADR1261](04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup/README.md) · [실제 ADR1262](04_EXPERIMENTS/ADR/ADR-1262-main130-progress-dedup-live/README.md). 사용자 지시로 **MAIN130/oracle-progress-dedup-20261031-r1·496파일·저장제품2+pin31=33변경** 선택, 공식 prepare/apply·실제root13조건 통과. 기본 NFS·DP=oracle 구조화 Oracle/상세 NFS 정책 유지·추가표/컬럼/DDL0. 64KiB 이상 `stage_progress`만 내용 기반 조각 공유+불변 root(layout4); 원래 바이트/SHA·모든 역사판본·온톨로지/근거/재개/CAS/예산 보존, 이전2/3형식 호환·scope분리·조각내구후root 공개. **동일342이력 완전복원: 저장 JSON 26,105,777→3,948,560문자(-84.875%), 조각9763→2716, SQL1752→2044(+16.667%)**; 격리메모리전송 재생이며 실제 segment/속도 개선율 아님. **193pytest+새기술holdout24복원·기존14동일/새0**. 병행미반영작업 보존·전체작업tree=선택 아님/이번소유2모듈만 작업·후보·선택정확일치. 실제1262는 DPOracle/GoldR18·ON DB/고정전송기/591동결·369질문1회, **488.128초·정상5+UNKNOWN1/6물리·보고$0.01324052(UNKNOWN미보고)**. 감독6번째 HTTP200헤더→공백60조각660bytes/179.080초 기한종료→504·최종ASSESS/답변0·UNKNOWN뒤호출0. 모델응답 경계 실패이며 공급자내부원인 미확인, 전체실험 Rejected. 새프로세스Oracle4표 **1/1659/3846/34행·FAILED/END·구조화응답5**, 진행213이력 전부해시복원/큰103개layout4·전체1578본문검증·확보원문7대조 불일치/ACL위반0. 이번같은큰이력의저장JSON 10,802,346→2,263,043문자(-79.050%); 할당량/전체DB와분모구분. **SIDDA190.625→192.625MiB(+2MiB),기존300MiB기준63.5417→64.2083%,hard270MiB유지·quota확장/추가삭제0**, 과거다른LLM경로 대비 인과율주장금지. source2590/Agent4901 SQL·자원중단/segfault0. 기존원본이력 재작성/정리0·새기록부터적용, 기존할당공간즉시회수 아님. **layout4 생성뒤 구MAIN129 reader로 새namespace를 읽지 말고 4지원 복구릴리스를 사용**. 실제NFS마운트없음/진단UNCONFIGURED·제품로컬/Oracle 상세로그fallback0, 현장GENOS/ORDS/Oracle19·실제NFS내구/부하·법률품질 미검증. Gold engine binding만130/연결기·매핑·설정·원문 유지·Git/메일/현장배포0. 아래MAIN129유지는각과거시험시점이다.
<!-- /MAIN130_PROGRESS_DEDUP_1261_1262 -->

<!-- WIKI_ORACLE_LITERAL_1260 -->
**2026-10-31 — 자유 작업공간 Oracle 실제 검증 최종 미통과·MAIN129 유지:** [최종 TXT](09_ARTIFACTS/AUDITS/20261030-wiki-oracle-connected-live/결과와_남은검증.txt) · [ADR1260](04_EXPERIMENTS/ADR/ADR-1260-wiki-literal-glossary-oracle-live/README.md). 10월30일 시험의 격리508파일rev001·자동 조각 정확 용어만 복원/명시적 확장검색 유지·미검색 표시/원문검사/예산 유지. 모의88+native9통과. 실제 읽기전용 후보16→3/12→4·상세동일·이전모델참조 보존(SQL163). **실제6물리/정상4·4292·전환1·UNKNOWN0·289.739초**, 축적2/문장2/정규화2 Oracle 저장·새프로세스8객체 확인. Parasail429→허용된Near AI→다시429로 SOURCE_ANALYSIS 거절; **실제컴파일/지식승인/게시/RAG0·추가모델0·MAIN미반영**. sourceSQL494/agent206/work248, 성공응답보고$0.00658679. 마지막SIDDA176,750,592바이트/기존300MiB56.1875%·270MiB상한유지. 전체성능·법률품질 인증 아님. 1257의195.25MiB회수/4표보존은별도;1255/1259/1260 합계12물리·10HTTP200·2HTTP429·외부UNKNOWN0·보고성공비용합계$0.04601291. 완료실패/기록/기존Gold원문·게시 보존·작업제품507/선택MAIN동일, 변경은후보와검사/문서에만. 공급자 제한 해소 후 별도 검증으로 컴파일→승인→RAG 및 승격자격 확인 필요. 실패job/완료ADR을성공으로고쳐쓰거나자동재시도하지 않는다. 현장GENOS/ORDS/NFS/Git/메일0.
<!-- /WIKI_ORACLE_LITERAL_1260 -->


<!-- WIKI_ORACLE_TYPED_1259 -->
**2026-10-30 — 자유 작업공간 실제 Oracle 앞단 통과·전체 미통과 ADR1259:** [결과](04_EXPERIMENTS/ADR/ADR-1259-wiki-typed-proposal-oracle-live/README.md). 격리508파일rev002·실제Qwen4/stop4/외부UNKNOWN0·644.182초. 실제 과거기록2→변경2/문장2→정규화2 Oracle 저장·새 프로세스8객체 재조회·이유/목적4필드 NOT_RECORDED 보존. 자동 문장 조각의 광범위 용어 후보16/12 전체 상세 반복복원으로 sourceSQL1334/agent198/work248·projection600초 예산 종료; 원문 분석 호출/컴파일/승인/게시/RAG0. 후보83계약+native9통과, 초기 import/pin/제한환경 대기와 재조회 필드명 오류 보존. 이전1255의73검사는 작업코드 로드였으므로 후보 검증으로 확대 금지. 실패 scope·모델원문 유지, MAIN129/Gold/DDL/Git/메일 변경0. 후속1260은 자동 조각 정확일치/명시 검색 유지 가설이며 아직 실제 전체 성공 아님. SIDDA195.25MiB 회수는1257 별도 검증,270MiB상한 유지.
<!-- /WIKI_ORACLE_TYPED_1259 -->


<!-- MAIN129_CAPACITY_DIAGNOSIS_20261030 -->
**2026-10-30 — 용량 부족 읽기전용 원인 확인:** [집계·대응](09_ARTIFACTS/AUDITS/20261030-oracle-capacity-diagnosis/원인과_대응.txt). 선택MAIN129495 유지. ADR1258 scope는1876고유BODY/13279조각·원래99,556,257bytes/압축20,660,215bytes. **`SQLROW:stage_progress`342개고유판본이원래93,634,229bytes/압축18,789,664bytes로압축BODY의90.95%**. 가장큰진행판본1,290,245bytes에서`accepted.before`517131문자/`action_chain.frames`360189문자가큰사본이다. `save_selection_progress` 전체REPLACE→Oracle `commit`의불변SQLROW판본추가로변경때마다큰본문누적; 정확히동일한해시만중복방지. 상세raw로그NFS분리만으로이증폭은해소되지않는다. 1258기간전체SIDDA물리할당+85MiB는본문순수크기와구분. BODY전체물리할당약147.1MiB는여러scope/LOB/index/내부여유포함. **기존Gold검색표4394604행·본체/LOB/인덱스8.11GiB**, 주요종류용어출현1508024/본문posting939010행. 이는Agent질의기록과별도의기존검색자료다. SIDDA270MiB계정상한·Free사용자데이터12GB한도·USERS빈extent728MiB를혼동하지않는다. 제안은최신복구checkpoint/필수감사변화와큰이전상태·frame사본을분리해hash참조/차이저장으로공유하는것; 재개/CAS/예산/근거계약검증전삭제·최신값만보존으로단순전환금지. **진단만수행·새모델/제품수정/DB내용·DDL변경0**, 최신1258최종실패는용량이아닌검토계약422다.
<!-- /MAIN129_CAPACITY_DIAGNOSIS_20261030 -->

<!-- MAIN129_FIXED_CAP_FINAL_1258 -->
**2026-10-30 — MAIN129 고정전송기·90%상한 최종단계 실제 재시험 미통과:** [실제결과](09_ARTIFACTS/AUDITS/20261030-main129-fixed-cap-live/실제실험_결과.txt) · [ADR1258](04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live/README.md). 사용자명시승인후병행1257의BODY빈heap반환195.25MiB/270MiBquota유지를1256이중복DDL없이확인. 반환전후전체hash가우리백업과같고,원래9597행전부PK/hash동일·추가BODY25행구분,1256최종통과. **이제SIDDA quota270MiB고정유지·원래300MiB로자동원복하지않는다.** 1258동일MAIN129495/불변전송기·deadline·package/590동결/GoldR18·ON DB/DPOracle·369질문1회. **실제480.675초·Parasail7/stop7·UNKNOWN0·전환0·보고$0.034742(입력69727/출력9404)**. ASSESS최초/보완은정상JSON이지만동일assessment hash·NEED_TARGET_INCOMPLETE4→SOURCE_INVESTIGATION_INCOMPLETE/검토미완료422·답변/PUBLISHED0. SQL원문3109/Agent6921=10030(각native1만/공유관찰25000),경계229.428/87.224초는Oracle CPU만이아님. **Oracle새프로세스4표1/2501/13279/50행·FAILED/END·7최소구조화응답**, 확보원문19/canonical45대조불일치·ACL위반0·디스크runtime/SQLitefallback0. 전송6요청user/schema독립재구성정확일치,최초1은단순gateway재구성차이로전체동등미확인/질문문자열유지;실제raw보존·customSYSTEM전체payload검증주장금지. 모델제안JSON통과를최종검토통과로확대금지. **스왑/자원중단/segfault재현0·정상종료**;rusage RSS4.147GiB/주기표본2.474GiB·가용최소8.929GiB/hostswap증가84.953MiB/프로세스swap표본0. **이번기간SIDDA27.5208→55.8542%(전체할당+85MiB),hard270MiB유지/원복·quotaALTER0**,WSL52.618%/Windows76.235%·90%이내. 이전92.2708%관찰과구분하며전체이력90%준수주장금지. NFS진단UNCONFIGURED/raw누출0·원시연구gzip은별도,현장GENOS/ORDS/Oracle19·실제NFS·부하/법률품질미검증. 제품/MAIN/Gold내용/컬럼/DDL/추가삭제/Git/메일변경0·터미널뒤새실모델0·ADR최종통과. 아래1256승인대기설명은이전시점이며추가승인과검증완료로갱신됐다.
<!-- /MAIN129_FIXED_CAP_FINAL_1258 -->

<!-- WIKI_ORACLE_SPACE_1257 -->
**2026-10-30 — 현재 SIDDA 빈 공간 반환 완료(ADR1257):** 사용자 “기존 SIDDA 공간 정리 후 진행” 선택으로 [별도 보존 검증](04_EXPERIMENTS/ADR/ADR-1257-wiki-oracle-space-recovery/README.md)을 거쳐 BODY heap만 SHRINK. **204,734,464바이트(195.25MiB) 회수, 기존300MiB 기준92.2708→27.1875%**, 현재270MiB상한유지. 현재4표전체값·PK/행수·메타해시동일, row movement DISABLED 복원·추가DELETE/LOB/CASCADE/인덱스/Gold변경0. 이전1256은미실행대기기록으로보존하며중복실행금지. 초기이미90%초과상태를회복한것이며전체기간90%준수주장아님. 새모델0·MAIN129불변; 후속작업공간실제시험은별도1255후보.
<!-- /WIKI_ORACLE_SPACE_1257 -->

<!-- MAIN129_PINNED_QUOTA_APPROVAL_1252_1256 -->
**2026-10-30 — MAIN129 전송기고정·스왑완화 재시험/용량반환 추가승인대기:** [현재상태](09_ARTIFACTS/AUDITS/20261030-main129-pinned-oracle-live/진행상태와_승인요청.txt). **ADR1252 실제179.026초·2정상/UNKNOWN0·보고$0.00512852·최종0**은83.9375→89.6042%/쓰기전2MiB여유중단. 전송기·deadline·package를불변snapshot에서매호출기원/hash검사했고MAIN129495불변;사후분석기sql_audit.py1파일보강은별도명시. 사용자명시승인으로 **ADR1253에서실패1245 namespace만현재전체값stream hash와2175본문검증백업일치후RUN1/REC2987/BODY52742/STATE52삭제**, 다른scope행수보존·원래실험파일불변. 압축백업43.24MiB/전체복원재삽입미시험. 빈BODY블록약187MiB가생겨도할당89.6042%그대로. **ADR1254 실제112.472초·2정상/UNKNOWN0·최종0, ORA01536뒤실패저장중AGENT_LEASE_LOST**로멈춤. 실행중hard270MiB/original300MiB의90%상한유지·종료후300MiB원복. 이후BODY SecureFile LOB할당+8MiB/현재92.2708%관찰·원인주체미확정, **전체기간90%준수주장금지**. 두trial추가segfault/스왑중단0·최종미도달을전체성공으로확대금지. **ADR1256 BODY빈heap SHRINK/rowmovement는자동승인검토가잠금·물리행위치변경위험및별도승인부재로거절,우회/DDL0**. 현재4표전체값백업약7.74MiB·hash검증/검토SQL준비, **공간반환+270MiB상한고정+새ADR실험을사용자추가승인요청중**. 승인전DB변경·추가모델금지. MAIN129/Gold내용/컬럼/GENOS/Git/메일변경0·실제NFS/ORDS/19c·법률품질미검증. 1252/1253/1254최종검사통과·graph기존16/해당ADR새0. 이전1245의Oracle행보존설명은당시상태이며삭제허용/실행은별도1253기록이다.
<!-- /MAIN129_PINNED_QUOTA_APPROVAL_1252_1256 -->

<!-- WIKI_WORKSPACE_IMPLEMENTATION_20261030 -->
**2026-10-30 — 자유 축적→기존 컴파일·승인·RAG 작업 코드 구현:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-wiki-workspace-implementation/구현과_검증결과.txt) · [사용·설정](07_DOCS/REFERENCE/OPERATIONS/ONTOLOGY_WORKSPACE_20261030.md). 프로필 없는 항목/문장/연결/보기, 기존 CLI·Streamlit·Dataiku 반입, 원자 변경·결과불명 복구, 선택 문장→실제 정규화·원문 독립 분석→v1 컴파일→승인·게시·현재 원문 RAG 연결. 명시 철회는 의존 게시본과 생성 중/저장 답변 재사용을 차단한다. **서로 다른 합성110검사 통과(신규계약30+기존43+Gold매핑27+API/화면10), v1핵심4파일 불변·작업엔진30/pin31 결속**. 기존 정규화 fixture25실패는 변경 전 동일·현재 wire 모의 응답으로43통과; Gold 모의행3건은 새 사전조회 열에 맞춰 수정 후 통과. PIPELINE 기존명세오류2/새0. **선택MAIN129 유지·승격0·현장 GENOS/실제 Oracle writer·NFS·실모델/법률품질 미검증**, 운영 데이터/DDL·실모델·Git/메일0. workspace_runtime_scopes 기본빈목록·workspace_publish 명시권한, 기존 OFF 유지. 병행1251 및 기존 작업 변경 보존, 일반 합성 계약 검사이며 모델 품질 실험/배포 인증이 아니다.
<!-- /WIKI_WORKSPACE_IMPLEMENTATION_20261030 -->

<!-- GENERAL_EVIDENCE_REVIEW_SQLITE_1251 -->
**2026-10-30 — 원문 범위 검토·주장 연결 일반화와 SQLite 실제 재시험:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-general-evidence-review/수정과_실제실험_결과.txt) · [ADR1251](04_EXPERIMENTS/ADR/ADR-1251-general-evidence-review/README.md). **작업 제품3+pin31+검사/fixture5=39파일 반영, 선택MAIN129 유지/승격0**. 확보·전체범위 USE/EXCLUDE/OPEN 검토·주장별 채택근거를 분리하고 최초 읽기 목적 보존/복수쟁점·자료 연결, 제외원문 hash 검증·보류gap·중복/누락 거절·v2 영수증·반복오류 식별을 추가. 조문별 예외0. **계약155/API모의8통과·기존2 MAIN129동일/새0, 반영 검사74통과(앞 검사와 중복)**. 동시 온톨로지10파일 변경에 최초동결 차단→새 후보에서 이미 검증한 범위497파일을 명시적 격리; 다른 작업 rollback0·실험 연결기2개도 동결본 import 확인. 실제 SQLite/상법1문서/온톨로지OFF **207.350초·Parasail2/stop1/UNKNOWN1·API504/최종0**, 둘째 탐색 요청 HTTP200헤더+공백60조각660바이트/179.929초 기한종료. **AbsoluteDeadlineExceeded→MODEL_DEADLINE_EXCEEDED/UNKNOWN 보존·추가호출0·worker회수/FAILED/정상종료**, 이전 TypeError/AttributeError 재발0. 최종 ASSESS/새scope검토 실모델 전송0이므로 수정의 실모델 효과 미검증. 보고$0.0014738(UNKNOWN사용량 미보고), 원문1대조/전송2대조 불일치·ACL위반0·최종입력0. RSS최대2.977GiB/가용최저8.246GiB/hostswap증가35MiB·자원중단0. 코드/고정입력 불일치0. Oracle/GENOS/NFS/배포/Git/메일0·법률품질/SQL성능 인증없음·같은질문 재실행0. ADR최종통과/graph기존16·새0.
<!-- /GENERAL_EVIDENCE_REVIEW_SQLITE_1251 -->

<!-- MAIN129_ORACLE_LIVE_RESOURCE_1250 -->
**2026-10-30 — MAIN129 DP Oracle 실제 재시험 자원중단:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-main129-oracle-live/실제실험_결과.txt) · [ADR1250](04_EXPERIMENTS/ADR/ADR-1250-main129-oracle-live-retest/README.md). 고정MAIN129495/GoldR18·ON DB/DPoracle·369질문1회, **Parasail2/stop2·UNKNOWN0·보고$0.00456756**. 원문/Agent 공유SQL한도10000, DB/디스크90%와쓰기전16MiB여유관찰. **호스트전체swap증가>128MiB 감시로exit125·최종API/ASSESS/답변0**, 모델진행중없음·추가재전송0·SIGSEGV근거없음. 마지막내구표본131.479초는정상총시간아님; RSS최대3.694GiB/가용RAM최저8.860GiB/프로세스VmSwap표본0. 트리거직전host증가표본90.352MiB이며초과순간정확값미저장·이번실행단독원인미확정. **Oracle새프로세스4표1/1032/3521/36행·2구조화응답/7원문대조불일치·ACL위반0**, v3본문782개·마지막RUNNING그대로보존/사후실패·성공재작성0. **할당81.271→83.938%(+8MiB)**·기존1245실패scope보존·90%이내. 원문2258시작/2257완료·경계64.024초, Agent3120완료/33.435초·쓰기1388, 공유5378시작·마지막원문SELECT1완료미확인. 중단단계가달라이전전체실행과감소율비교금지. 선택495코드는불변이나공통research experiment_client.py의사후해시가동결과달라전체의존성동일성미충족/로드버전시점미확정. NFS UNCONFIGURED·제품/MAIN/Gold/DDL/Git/메일변경0·새전체재시험0·현장/법률품질미검증. 잘못된namespace0행사후독자결과는원본보존후실행영수증으로바로잡음. 별도1249 모델오류/SQLite작업과분리한다.
<!-- /MAIN129_ORACLE_LIVE_RESOURCE_1250 -->

<!-- MODEL_ERROR_SQLITE_RETEST_1249 -->
**2026-10-30 — 실험 연결기·오류 처리 수정 및 SQLite 재시험:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-model-error-sqlite-retest/수정과_실제실험_결과.txt) · [ADR1249](04_EXPERIMENTS/ADR/ADR-1249-model-error-sqlite-retest/README.md). 사용자 수정→재시험 지시로 현재MAIN129 기반 후보497파일에서 시간초과 원인/진단 보존·예약 전송 공통화, gateway Proposal/일반예외의 잘못된429전환 코드 제거. 기존4결함 재현/5통과→후보18+API2·작업20통과. **작업3코드+pin31=34파일 반영, 선택MAIN129/배포코드는 미변경**이므로 위 이전 작업/선택동일 설명은 당시 상태다. 상법369 동일질문·단일문서/SQLite 원문+기록/온톨로지OFF 실제1회 **106.759초·Parasail6/stop6·UNKNOWN0·보고$0.02638512·HTTP422/답변0**. 최종 최초/보완 모두 NEED_TARGET_INCOMPLETE/NEED_RESOLUTION_CLAIM 거절, 보완 needs/judgments 동일. 실제 연결기예외/충돌0; 시간초과504 보존은 합성API검증이며 이번실제기한종료0. 확보17/전달36원문구간·wire6대조 불일치/권한위반0, physical/reserved6·FAILED새프로세스재조회/cleanup/exit0. runtime6.937MiB/DB5.008MiB·RSS2.993GiB·호스트swap증가33.133MiB/중단없음. 모델통신81.607초·SQL횟수/시간 미계측, 원문/동결497/선택포인터 불변. **오류수정 기술통과와 실제답변 미통과 구분**, 법률품질/순수DB효과/Oracle·GENOS 인증없음. 추가실모델/Oracle/MAIN승격/Git/메일0·실패원본보존·ADR최종통과.
<!-- /MODEL_ERROR_SQLITE_RETEST_1249 -->

<!-- ORACLE_STORAGE_SAFETY_MAIN129_1246_1248 -->
**2026-10-30 — Oracle 저장/갱신 안전성 수정 MAIN129:** [최종 TXT](09_ARTIFACTS/AUDITS/20261030-oracle-record-storage-safety/수정과_검증_메인반영결과.txt) · [기술 ADR1246](04_EXPERIMENTS/ADR/ADR-1246-oracle-record-storage-safety/README.md) · [반영 ADR1248](04_EXPERIMENTS/ADR/ADR-1248-oracle-safe-records-main/README.md). **MAIN129/oracle-safe-records-20261030-r1·제품3+pin31=34변경·495파일 작업/후보/선택 동일**. Oracle RAM SQL의 결과를 먼저 분리하고 deserialize 대신 native backup·RLock·statement cache 비활성으로 갱신. 기존40교차쓰기 재현 SIGSEGV(-11)→수정본 통과; 실제1245 C원인 전체동일성/실모델 재검증은아님. Oracle에서SQLite문자열/압축blob 새factor를생략하고 BODY전체압축후분할(v3), 기존v2/compact reader·해시/CAS/fence 유지·변경행/영수증 동시업로드. **188계약통과/기존14동일·새0·실제rootOracle API2/선택NFS HEALTH200·13조건**. 고정작은실제Oracle100객체/8판본 **BODY74→46(37.84%감소), SQL241→107(55.60%감소), REC54→27**; envelope문자33453→33761로감소없음·전체질의/용량/속도 개선율 아님. 기존실패scope1/2987/52742/52·FAILED 그대로, SIDDA할당81.271%/disk52.563%·90%이내이며과거할당축소0. **DDL/컬럼/Gold내용/새모델/GENOS/Git/메일0**, NFS기본·DPOracle구조화/NFS상세 경계유지, R3 SQL 재생성불필요. v3본문작성후v2전용MAIN128단순다운그레이드금지·호환reader복구필요. **NEED_TARGET_INCOMPLETE/NEED_RESOLUTION_CLAIM·Gold반복조회·전체실제369·현장19/ORDS/NFS·법률품질 미검증**. 기술1246의승격메타누락은사전검사가차단했고완료기록을덮어쓰지않고1248별도반영감사로결속했다. 병행1247 MAIN128/SQLite 고정실험은별도범위다.
<!-- /ORACLE_STORAGE_SAFETY_MAIN129_1246_1248 -->

<!-- MAIN128_SQLITE_LIVE_1247 -->
**2026-10-30 — MAIN128 SQLite 실제 재시험 미통과:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-main128-sqlite-live/실제실험_결과.txt) · [ADR1247](04_EXPERIMENTS/ADR/ADR-1247-main128-sqlite-live-retest/README.md). 사용자 명시승인 후 같은 상법369 질문·문서1개를 현재MAIN128495/local SQLite 원문+기록으로 실제1회 실행. **210.238초/Parasail2·stop1/UNKNOWN1·HTTP500·답변0**, 모델통신191.578초·보고$0.00207208(두번째비용미보고). 두번째 원문선택 요청은 HTTP200헤더 뒤 공백60조각660바이트·179.916초기한종료/worker회수. 이어 **실험연결기의 TransportError(code=...) 미지원 TypeError → MAIN128 gateway 일반예외의 exc.unknown 접근 AttributeError**가 원래 오류를 가림. 공급자 내부원인미확인·SQLite충돌근거아님. FAILED/END·UNKNOWN 보존/새프로세스재조회·cleanup/exit0, 원문1대조·전송2동일·권한위반0·physical/reserved2, 추가모델0. runtime5.116MiB/DB3.695MiB·RSS2.977GiB·swap증가0, 동결원문/495코드불변. **SQLite 온톨로지OFF/기존Oracle ON·벡터경로차이로 순수DB A/B·법률품질/전체속도개선 인증아님**. 모델0회 준비실패3종·승인전거절2회 원본보존. 이번제품/MAIN/Oracle/GENOS/Git/메일변경0; ADR최종검사통과·전역graph 과거16오류/1247오류0. 실제호출 이후 연결기/제품수정·같은질문재실행0, 별도1246 Oracle개선과 구분.
<!-- /MAIN128_SQLITE_LIVE_1247 -->

<!-- MAIN128_ACTUAL_ORACLE_RECORDS_1245 -->
**2026-10-30 — MAIN128 실제 모델/Oracle 기록 시험 미통과:** [실제 결과](09_ARTIFACTS/AUDITS/20261030-main128-oracle-records-live/실제실험_결과.txt) · [ADR1245](04_EXPERIMENTS/ADR/ADR-1245-main128-oracle-records-live/README.md). Gold369 실제1회·MAIN128495/R18/ON DB. **Parasail8/stop8·UNKNOWN0·보고$0.04149832, 정상 API/최종답변0**. 최종 최초/보완 모두 필요-원문 연결 NEED_TARGET_INCOMPLETE/NEED_RESOLUTION_CLAIM 거절→Oracle FAILED/END 보존 뒤 **AnyIO worker의 libsqlite3 SIGSEGV/exit139**. C core/stack없어 근본 원인 미확정, 같은 질문 재전송0. 별도 새 프로세스 Oracle4표1/2987/52742/52행·8최소구조화응답/NFS UNCONFIGURED·원문19대조 불일치/권한위반0·디스크runtime없음 확인. **SIDDA9.3125→77.5833%(+204.8125MiB), 본문52,742조각/2175고유본문**으로 저장 증폭 큼; 90%이내라도 반복/현장투입 준비 완료로 해석하지 않는다. 원문SQL3182/268.825초·Agent9959/91.846초(각 전송포함 경계), Gold별도 연결기각1만/일반DP공유1만 예산 차이를 명시. 마지막내구표본549.123초는 정식 총시간아님. **실제NFS/ORDS/Oracle19/GENOS·부하/법률품질 미검증**, DDL/Gold내용/MAIN/제품/Git/메일 변경0. 실패원본 보존·추가실모델0. ADR1244의 모의모델 기술통과를 실모델 전체통과로 확대하지 않는다.
<!-- /MAIN128_ACTUAL_ORACLE_RECORDS_1245 -->

<!-- STRUCTURED_ORACLE_DETAIL_NFS_MAIN128_20261030 -->
**2026-10-30 — 구조화 Oracle·상세 NFS 최종 MAIN128:** [반영·운영 TXT](09_ARTIFACTS/AUDITS/20261030-oracle-structured-nfs-diagnostics-main/구조화_Oracle_상세로그_NFS_반영결과.txt) · [ADR1244](04_EXPERIMENTS/ADR/ADR-1244-oracle-structured-nfs-diagnostics-main/README.md) · [SQL/설정 R3](08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r3.zip). 사용자 최신 지시로 **MAIN128/oracle-structured-20261030-r1·495파일/제품11+pin31=42변경 정확결속**. `DP=oracle`에서 질문/사실/정정·원문좌표/hash/확보전달·구조화 제안/판단·근거/관계/gap·답변·예산/재개/CAS는 Oracle에 유지, **전체 프롬프트/전송요청·원시응답/SSE·traceback·상세 보고서/trace/로그는 실제 NFS**. 기존 SQLROW/JSON 구조화 본문/메모리 SQL은 유지하며 개별업무컬럼 정규화 전환 아님. Oracle는 상세원문 대신 NFS 위치/hash/크기/capture 상태와 최소 구조화 응답을 저장, workflow복구는NFS무관/모델재전송0. `GENOS_SHARED_LOG_DIR` 실제NFS·선택GENOS_DETAIL_LOG_DIR 사용, 겹쳐 data/state를 포함하는 logroot 거절·로컬/Oracle 로그fallback0. QUEUED는내구저장성공 아님·미설정/실패명시. 원본불변 명시이관에서 raw는NFS내구저장/Oracle에는구조화+참조·미사용compact로그blob제외. **18+서비스2+기존153=173통과/기존14동일·새0**, 실제root NFS정상/오류2·선택NFS HEALTH200/13조건 통과. 합성NFS어댑터이며현장mount/GENOS/Oracle19·ORDS/실LLM·지연/전량이관 미검증. 추가DDL/Gold0·기존3표21+STATE5 유지·R3 SQL은R2동일. 로컬SIDDA quota대비9.312%/disk52.534%로사용자90%이내, 현장NFS미측정. 이전127/126·원본/Gold연결기·설정/매핑/데이터 보존·engine binding만128. 모델/임베딩/Git push/메일0·법률품질 인증없음·ADR최종/graph기존16·새0. **아래127/126의 상세 로그까지Oracle 설명은 이전 단계다.**
<!-- /STRUCTURED_ORACLE_DETAIL_NFS_MAIN128_20261030 -->

<!-- ORACLE_DEFAULT_MAIN127_20261030 -->
**2026-10-30 — DP 단독 설정 기본경로 보완·최종 MAIN127:** [최종 TXT](09_ARTIFACTS/AUDITS/20261030-oracle-default-runtime-main/최종_메인반영과_사용방법.txt) · [ADR1243](04_EXPERIMENTS/ADR/ADR-1243-oracle-default-runtime-main/README.md) · [최종 Dataiku SQL R2](08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r2.zip). **MAIN127/oracle-default-20261030-r1·494파일 정확결속, MAIN126 대비 제품3+pin31=34변경**. GENOS_RUNTIME_DIR 생략 시 Factory와 service AD/보고서/복구·chat 진행의 기본 경로가 달라지던 조건을 부모에서 실제 API2실패로 재현 후 공통 `runtime_directory`로 수정. **DP=oracle만 지정해도 같은 Oracle 논리 runtime**, NFS 기본/명시 경로 유지. 후보 기존Oracle 저장12+기본경로2+bare-DP 원문/모의모델/기록API2=16통과·실제root2/선택NFS HEALTH200·13조건 통과. 부모1242의167/기존14는 별도 범위이며 합산독립표본 아님. 신규 Agent3표21+기존STATE5 유지·**R2 DDL은 R1동일, 재생성 불필요/Gold추가0**. 이전126/125·Gold연결기/매핑/설정/데이터 보존·engine binding만127. 현장GENOS/Dataiku DDL·NFS전량이관·실LLM·Oracle19/ORDS·부하미검증·속도보장없음, 기본복원256MiB·원본경로/namespace/Oracle신규기록보존·역복사자동0. ADR최종통과/graph기존16·새0·모델/임베딩/Git push/메일0. 아래126은 기록연결 본체 반영 이력이며 최종 선택은127이다.
<!-- /ORACLE_DEFAULT_MAIN127_20261030 -->

<!-- ORACLE_AGENT_RECORDS_MAIN126_20261030 -->
**2026-10-30 — DP Oracle 기록까지 연결 MAIN126:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261030-oracle-agent-records-main/메인반영과_검증결과.txt) · [ADR1242](04_EXPERIMENTS/ADR/ADR-1242-oracle-agent-records-main/README.md) · [Dataiku SQL ZIP](08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r1.zip). **MAIN126/oracle-records-20261030-r1·494파일·제품/워크플로우명세60+pin31=91변경**, 작업/후보rev-010/선택 해시 동일·공식prepare/apply 완료. **DP 미설정/NFS 기본 유지; DP=oracle이면 원문/검색 및 journal·대화·조사·재개·판단·답변·게시/진행·보고서 영구 정본은 Oracle**, NFS/CIFS 마운트와 파일fallback 제거. 기존 SQL/트리거는 **요청 메모리 SQLite**로 호환 실행하며 디스크 SQLite/원문미러 없음. 앞서 준비한 SIDDA **신규3표21컬럼+기존STATE5=4표26컬럼**, Gold DDL0. 실제 로컬Oracle 저장/이관/소유권12+원문→모의답변→저장/중복무호출/재조회2·기존56/14동일·보조97 = **167통과/새실패0**, 실제root Oracle진입2 및 선택NFS HEALTH200/13조건 통과. REPLACE 암묵삭제·물리명predicate/JSON_TABLE·저장판본reader·위키쓰기 수정, 준비/fixture/preview 실패 보존. **현장 NFS 전량 이관/GENOS 리비전/Oracle19·ORDS/실LLM·대용량 성능은 미검증**, 이관기 별도 writer정지 필요·원본 유지·불완전 이관 거절. 기본 namespace/과거 절대 경로 유지, Oracle 신규 기록의 NFS 역복사 자동0. 기본 memory admission256MiB·가속/1초보장 없음. MAIN125/기존Gold연결기·설정/매핑·원문/벡터/게시 데이터 보존, Gold engine binding만 동일MAIN126. 모델/임베딩·Git push/메일0·법률품질 인증없음. ADR최종통과·graph기존16/새0. 아래 DB구조 생성만 완료·외부NFS필수 설명은 이 반영 전 상태다.
<!-- /ORACLE_AGENT_RECORDS_MAIN126_20261030 -->

<!-- AGENT_RECORD_ORACLE_LOCAL_R2_20261030 -->
**2026-10-30 — Oracle Agent 기록 축소안 실제 로컬 생성:** 사용자 적용 지시로 기존 로컬 `FREEPDB1 / SIDDA`에 **`LGL_AGT_RUN_A/REC_A/BODY_A` 신규3표·21사용자컬럼, PK3·조회인덱스7**을 생성했다. 기존 `LGL_EXEC_ST_A`1표5컬럼은 정의·원 내용 유지. [적용·검증 TXT](09_ARTIFACTS/AUDITS/20261030-agent-record-oracle-r2/적용과_검증결과.txt) · [실제 DB 컬럼 Excel R3](07_DOCS/REFERENCE/REPORTS/ORACLE_AGENT_RECORD_LOCAL_APPLIED_20261030_R3/Agent_실제생성_테이블컬럼_R3.xlsx). SYSTEM 유지보수 합성시험 **19개/SELECT11개·990,113바이트16조각 복원/commit·재접속/CAS·다중표rollback 통과**, 시험scope 정리후 신규각0행. VARCHAR 길이 검증기/시간대 인덱스 내부UTC/DATE bind 시간대 실패 원본을 보존하고 보완; 실제 adapter에도 `DB_TYPE_TIMESTAMP_TZ` 계약이 필요하다. Oracle 내부 숨김컬럼2·LOB 인덱스는 신청 사용자컬럼과 구분. SIDDA 기존300MiB한도 유지·사용약16.06MiB, quota확장0. Gold13표 행수·객체/매핑 및 MAIN125 포인터 동일, Gold DDL/DML0. **DB 구조 생성까지 완료, RAG 저장 consumer·ORDS/앱ACL·불변registry·기존기록 이관·NFS 제거·E2E는 아직**. 원격개발계/GENOS·제품/MAIN전환·실모델·Git/메일0. R2설계 당시 MAIN124 스냅샷은 과거 근거이며 실제적용 명세는 R3다.
<!-- /AGENT_RECORD_ORACLE_LOCAL_R2_20261030 -->

<!-- ORACLE_SCOPE_MAIN125_1240_1241 -->
**2026-10-30 — Oracle 본문검색 범위 수정 MAIN125·실제 재검증 자원중단:** [수정·재검증 TXT](09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/수정과_실제재검증_결과.txt) · [ADR1240](04_EXPERIMENTS/ADR/ADR-1240-oracle-fulltext-scope-repair/README.md) · [ADR1241](04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/README.md). **MAIN125/oracle-scope-20261030-r1·489파일·제품3+pin31=34변경**, SQLite/Oracle `scope_keys` 포트로 직접execute 누락 수정·ACL/판본/hash·좌표 유지. **114통과/기존8 MAIN124동일·새0, 후보61·선택204/HEALTH3·모의HTTP3**, 실제 Gold 원문/저장벡터100후보SQL73·온톨로지3/12/9 SQL157·좁은범위4원문/SQL2 통과. Gold같은MAIN·연결기3파일불변·R18/ON·DB유지; 종류제한SQL 후보는속도이득없어미채택. **실제1241 전송경계4/정상3/진행중1미확인, HOST_SWAP_GROWTH>128MiB exit125·최종0·CM009미실행**. 약250.900초는파일시각차(정상timer아님), 정확자원최댓값미저장. 새임베딩1/벡터100후보→원문1·온톨로지369ACQUIRED·원문7/입력8·wire4 불일치0, SQL로그2576완료/경계141.511초·페이지115회114.200초·보고$0.00730248(중단요청미보고). **이번모델은문서전체범위라수정한좁은범위함수재호출아님**, 직접수정검증은1240실제Oracle 구성요소. 최종온톨로지/벡터전달·감독UNKNOWN실효·법률품질미검증. 강제종료누락자료를합성하지않고post-stop읽기전용분석, journal SENT보존·재실행0. 1064동결전후동일·MAIN124/완료실패보존·DB내용/DDL·GENOS/Git/메일0. 반복조회지연과자원중단계측보강남음.
<!-- /ORACLE_SCOPE_MAIN125_1240_1241 -->

<!-- MAIN124_GOLD_LIVE_1239_20261030 -->
**2026-10-30 — MAIN124 Gold 실제 실험 실패·본문검색 포트 누락:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-main124-gold-live/실제실험_결과와_남은결함.txt) · [ADR1239](04_EXPERIMENTS/ADR/ADR-1239-main124-gold-live-revalidation/README.md). 현재MAIN124489·GoldON/DB·R18고정으로 상법369질문1회. **실제303.784초/2물리(Parasail429→NearAI stop1)/SQL추적1503+메타1/보고$0.00118032·최종답변0**. 모델 FULLTEXT+NAMED_SCOPE 선택 뒤 RECALL `law_candidates.fulltext_scope_keys:359`에서 Oracle `UnitIndex`에 SQLite `execute` 호출→AttributeError·FAILED/END. **본문검색 범위→unit key 포트 누락**, MAIN120/124 해당함수동일; 새통합5파일 회귀로단정금지. SQL경계287.299초(Oracle CPU만아님), 주요2조회166/115회 반복. 원문evidence/온톨로지전달/벡터임베딩·검색/최종입력0·UNKNOWN0으로 감독즉시중단 실효도미검증. wire2·물리예산일치/1062파일전후동일/스왑증가0. 첫실패중단기준으로CM009미실행·재실행0. **이번제품수정/MAIN승격/DB내용/GENOS/Git/메일0**, 포트와조회지연수정은남음. ADR최종검사통과·graph기존16/새0. 1238기술검사를전체실모델통과로확대하지않는다. [용어정정](09_ARTIFACTS/AUDITS/20261030-main124-gold-live/용어정정.txt).
<!-- /MAIN124_GOLD_LIVE_1239_20261030 -->

<!-- JUDGMENT_GOLD_MAIN124_20261030 -->
**2026-10-30 — 판단 공백·Gold 수정 통합 MAIN124:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261030-judgment-gold-main124/판단공백_수정과_Gold통합결과.txt) · [ADR1238](04_EXPERIMENTS/ADR/ADR-1238-judgment-recovery-gold-main/README.md). **MAIN124 / judgment-gold-20261030-r1**. 미완료 최종검토의충돌·판단누락표시/중복방지, 감독UNKNOWN전파·pending보존·재개전차단, Gold동일원문새evidence재결속/새claim ID보호를정식코드에통합. **489파일·제품5+pin31=36변경·223통과/기존4MAIN123동일·새0**, 후보59/선택198(3설정)·HEALTH3/모의HTTP3. 모의native UNKNOWN504→최종0/동일재조회추가0. **별도Gold도같은MAIN124직접사용·runtime patch실행0**, 현재VCTR_SCTN_ID/DTLS매핑유지·GoldON/DB, 실제원문/용어/저장벡터3행/native100후보 SQL73·온톨로지3게시12앵커9경로 SQL157통과. 기본MAIN데이터/모델/온톨로지OFF유지·DB내용/DDL0. **외부모델/새임베딩0·전체실모델E2E아님**, 공급자공백원인·법률의미정확성/벡터품질미검증. NEED_TARGET_INCOMPLETE반복제출은계속거절422. MAIN123/고정MAIN120·기존Goldpatch/실패기록보존·GENOS현장/Git/메일0·graph기존16/새0. 아래Gold MAIN120+patch설명은통합전이력이다.
<!-- /JUDGMENT_GOLD_MAIN124_20261030 -->

<!-- GOLD_VCTR_SCTN_R18_20261030 -->
**2026-10-30 — 벡터구간ID 최종 VCTR_SCTN_ID·R18:** 사용자 요청으로 로컬 `A8_GR12_CM1208.IDD_B03_LGL_VCTR_ITEM`의 **VCTR_SEG_ID→VCTR_SCTN_ID 실제 ALTER RENAME1개** 완료. [변경·검증 TXT](09_ARTIFACTS/AUDITS/20261030-gold-vctr-sctn-rename/변경과_검증결과.txt). 현재 활성은 **`ACTIVE_MAPPING.json → mapping_local_vctr_current.json`**, 최종 신청 매핑은 `mapping_r18_registration.json`, [최종 R18 엑셀](07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_TABLE_APPLICATION_20261030_R18/법률에이전트_B03_테이블별_컬럼정의_R18.xlsx). 컬럼1셀·PK/인덱스 참조2셀 수정, 13테이블60컬럼 이름 일치. 행수/59객체/타입/제약/권한/게시명세·온톨로지 및 벡터16,085행 ID·메타데이터 해시 동일. 원문/용어/기존벡터3행/native100후보 SQL73·단위26 통과. 내부 VCTR_SEG_ID는 엔진 호환 논리키이며 SQL 물리명은 새 이름이다. 모델/새임베딩0·전체 E2E 아님, 기존 Gold ON/MAIN·현장 Oracle/GENOS·Git·메일 변경0. R16/R17 및 DTLS 직전 활성 매핑은 변경 전 이력으로 보존.
<!-- /GOLD_VCTR_SCTN_R18_20261030 -->


<!-- GOLD_ON_LIVE_1233_1235 -->
**2026-10-30 — 별도 Gold 온톨로지 ON/DB 및 실제 재검증:** [최종 TXT](09_ARTIFACTS/AUDITS/20261030-gold-ontology-on/ON_최종확인결과.txt) · [사용법](08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ONTOLOGY_ON_GUIDE.txt). `ontology_settings.json enabled=true`·`store.gold_profile` 사용, 최신DTLS 매핑13테이블60컬럼 health통과. 별도runtime patch2개로 **동일원문 새evidence ID 재결속 / 새claim ID와 온톨로지 구성요소 별칭 충돌** 수정·40계약통과. **ADR1233 실제573.871초/7물리/SQL3196/422**에서 위2결함 확인; **1234 실제271.660초/4물리/SQL2770**은 원문4/경로3 전송 확인후429 시험전송기오류. 실패envelope를성공처럼return한 시험어댑터를1235에서수정·7검사, **실제519.365초/9물리/SQL2954/429전환1·보고$0.01701129**. 실제온톨로지369게시물1·원문4·3경로가최종요청에포함되고 C1/C2/C3초안도별개원문refs로복원. 그러나 **감독공백60조각660바이트/179.921초 UNKNOWN1 → 최종/보완 NEED_TARGET_INCOMPLETE → API422·답변0·전체미통과**. UNKNOWN뒤최종/보완2호출은사전종료기준이native인계에서강제되지않은이탈이며동일UNKNOWN요청재시도와구분, 이후새실행0. 원문/권한/wire불일치0·swap증가0. 일반ASSESS경로이며별도SCENARIO_SELECTED/법률품질인증아님. 별도Gold5파일만반영, MAIN123/기존MAIN120파일·원본DB/게시3건유지·GENOS/Git/메일0. 이전OFF기록은과거상태이며전체서비스MAIN이ON된것은아니다.
<!-- /GOLD_ON_LIVE_1233_1235 -->


<!-- GOLD_DTLS_DB_AND_COLUMNS_R17_20261030 -->
**2026-10-30 — DTLS 실제 Oracle 반영·컬럼별 시트 R17:** 사용자 요청으로 로컬 `A8_GR12_CM1208`의 DOC_VER/DOC_UNIT/DOC_BLK/SRC_POST **4컬럼을 MNFST_HASH_VALU→DTLS_HASH_VALU로 실제 ALTER RENAME**했다. [변경·검증 TXT](09_ARTIFACTS/AUDITS/20261030-gold-dtls-rename/변경과_검증결과.txt). 현재 활성은 **`ACTIVE_MAPPING.json → mapping_local_dtls_current.json`**이며 기존 실제 타입·길이 유지. 신청용 `mapping_r16_registration.json`과13테이블60물리명 일치. 13테이블 행수·59객체ID/상태·PK/인덱스 구성·권한·게시명세/온톨로지3/3/12행 내용해시 전후 동일. 실제 원문/용어/저장벡터3행/native100후보 SQL73·온톨로지12원문9경로 SQL157·단위26 통과. 모델/임베딩0·전체답변 E2E 아님. [R17 엑셀](07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_TABLE_APPLICATION_20261030_R17/법률에이전트_B03_테이블별_컬럼정의_R17.xlsx)은 테이블별13컬럼시트의 첫4열을 논리명/물리명/PK/NULL허용으로 정리, 기본값·인덱스·파티션 유지. R16의 DB미변경 설명과 mapping_local_current.json 기본선택은 이전 단계 기록이다. 현장 Oracle/GENOS·MAIN·Git 변경0.
<!-- /GOLD_DTLS_DB_AND_COLUMNS_R17_20261030 -->

<!-- GOLD_DTLS_REGISTRATION_CORRECTION_20261030 -->
**2026-10-30 — 사용자 명세 약어 정정:** 신청 컬럼은 **`DTLS_HASH_VALU`(명세해시값)**이며 과거 사진의 `MNFST_HASH_VALU`보다 이번 사용자 정정이 우선한다. [정정내역](07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_TABLE_APPLICATION_20261030_R16/정정내역.txt). 신청 엑셀 R16의 DOC_VER/DOC_UNIT/DOC_BLK/SRC_POST 4컬럼·PK3/일반인덱스3 참조를 수정했다. 신청 대상 매핑은 `08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/mapping_r16_registration.json`; 내부 MNFST 논리키는 기존 엔진 호환용으로 유지하고 SQL 물리명은 DTLS로 변환한다. **이번 정정은 DB 변경·활성 매핑 전환0**. 현재 실제 로컬 매핑은 `ACTIVE_MAPPING.json → mapping_local_current.json`이며 신청용 매핑으로 임의 전환하지 않는다. 사진·R15·기존 매핑은 과거 근거로 보존한다.
<!-- /GOLD_DTLS_REGISTRATION_CORRECTION_20261030 -->

<!-- GOLD_ONTOLOGY_PUBLICATION_20261030 -->
**2026-10-30 — 실제 Gold 온톨로지3건 게시:** [게시·확인 TXT](09_ARTIFACTS/AUDITS/20261030-gold-ontology-publication/게시와_확인결과.txt). 사용자 “게시 몇개 알아서 너가 해봐라” 위임으로 현재 Oracle 상법365/368/369조를 원문12단위·9시나리오 경로로 작성, 기존 Workflow 초안→검토→게시 실행. **A8_GR12_CM1208 ONTL_POST/HEAD/ANC=3/3/12행·3게시 모두 활성**. 별도 Agent schema A8_GONT_AGENT(NO AUTHENTICATION/32MiB)에 작업·감사2테이블, 작업JSON은01_DATA/ONTOLOGY_WORK/gold-local-20261030. 실제 원문·판본/hash·권한·활성조회/원문도착runtime/입력조립9조건 통과(SQL157); 원문부족9경로보류·변조거절 확인. **구성요소 검사이며 전체 native API/모델 답변 E2E 아님·외부모델0·기본OFF 유지**. 원문21문서/벡터16,085 및 비온톨로지10테이블 행수·Gold 객체ID 동일, MAIN123/고정MAIN120·GENOS/Git/메일 변경0. 사용자 개별 내용심사·법률품질 인증을 받은 것으로 기록하지 않음. 기존0행 설명은 게시 전 상태다.
<!-- /GOLD_ONTOLOGY_PUBLICATION_20261030 -->

<!-- GOLD_PHYSICAL_RENAME_20261030 -->
**2026-10-30 — 실제 골드 Oracle 컬럼명 변경:** [변경·검증 TXT](09_ARTIFACTS/AUDITS/20261030-gold-physical-rename/변경과_검증결과.txt) · [현재 사용 안내](08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/MAPPING_GUIDE.txt). 사용자 요청으로 로컬 `A8_GR12_CM1208`의 **컬럼9종/16위치를 실제 ALTER RENAME**했다. 테이블13개는 등록된 R14/B03 명칭과 이미 같아 테이블 rename0. 타입·크기 보존, 행수13테이블/객체59 ID·상태/제약조건/권한14행/게시명세 hash 전후 동일. 원문21문서·벡터16,085 유지. **기본 연결기는 `ACTIVE_MAPPING.json → mapping_local_current.json`**, 사진 이름+실제 보존 타입을 사용한다. `mapping_r12_local.json/config_b03.json`은 변경 전 이름용이며 현재 DB에 사용하지 않는다. 새 이름의 실제 원문/용어참조/1024차원 벡터3행/native Retriever100후보/온톨로지 EMPTY 조회6항목 SQL74 통과·단위26통과. 모델/새임베딩0, 전체 최종답변 E2E 미실행. 온톨로지3테이블 각각0행·기본OFF 유지, 적재/승인/게시0. DDL16개 성공·부분실패0, 전후명세/되돌림SQL/매핑 포인터 보존. MAIN123·고정MAIN120/완료ADR·GENOS/Git/메일 변경0. 아래 구물리명 설명은 변경 전 기록이다.
<!-- /GOLD_PHYSICAL_RENAME_20261030 -->

<!-- GOLD_PHOTO_COLUMN_MAPPING_20261030 -->
**2026-10-30 — 사진 기준 골드 컬럼 매핑:** [변경·검증 TXT](09_ARTIFACTS/AUDITS/20261030-gold-column-mapping/변경과_검증결과.txt) · [사용 안내](08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/MAPPING_GUIDE.txt). 사진6장 고유38용어/13테이블60컬럼을 `mapping_r14_photos.json`에 반영, 기존R14대비9고유명변경. 별도 Gold 연결기 `--mapping`에 원문/검색/용어/벡터 및 온톨로지3테이블 조회·게시 포트, 실제메타 사전대조·불변매핑/요청binding을 연결했다. **단위25통과·실제 임시Oracle 새물리명/역순컬럼 기존29+추가6확인통과**, 합성승인게시/ACL/판본/CAS/Gold+Agent rollback·요청SQL예산 확인. 실행기import/fixture조건누락/100행포트초과 초기3실패보존·정정. 실제21문서는 **구명칭 매핑**으로 원문/용어참조/1024차원 기존벡터3행 SQL71, native Retriever는 저장벡터주입/100후보 SQL9·검색1. 새임베딩/LLM0. 문자열44위치 R14용량초과0/SELECT13. 현재 로컬구스키마에 사진매핑 지정 시10테이블불일치/본문조회전거절. **온톨로지 실제게시0·EMPTY, 현장DB/실제최종답변 E2E 미검증**. MAIN123/고정MAIN120·adapter의존527해시불변, 실데이터/승격/GENOS/Git/메일0. 온톨로지 기본OFF 유지; 작업/감사2테이블은 명시한 Agent owner에 남는다.
<!-- /GOLD_PHOTO_COLUMN_MAPPING_20261030 -->

<!-- GOLD_E2E_REVALIDATION_1232 -->
**2026-10-30 — 골드 실제 재검증·온톨로지/벡터 E2E:** [결과 TXT](09_ARTIFACTS/AUDITS/20261030-gold-e2e-revalidation/실제재검증_온톨로지_벡터_E2E결과.txt) · [ADR1232](04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation/README.md). 동일MAIN120487/rev036·골드21문서의 실제009 **557.067초·SQL3992·물리6·도구16, 최종ASSESS도달**. 조사5stop 뒤 최종HTTP200헤더/공백60조각660바이트→179.884초기한종료·UNKNOWN1/API504·답변0, 사전중단으로007미실행. Parasail6/전환0·보고$0.03081108(UNKNOWN미보고)·swap증가0·worker회수. **실제벡터 임베딩1/Oracle검색1/100후보→3확보원문→최종입력, 원문146/중첩356/최종78대조불일치0·권한위반0, 전송요청6동일/최종78본문존재**. 골드실제게시명세에approved ontology publications제외·관련종류0, profileOFF/A0·DB설정없음·온톨로지실제전달0. 별도MAIN123489동일·모의native/게시/원문변경/CAS6통과는실제골드Oracle/LLM E2E아님. 초기구fixture6실패→기존1231wire어댑터적용·진단압축reader/필드명오류보존정정. **전체미통과·MAIN123/원본9DB/기존ADR1214/연결부불변·승격/DB수정/GENOS/Git/메일0**. 공급자내부원인미확인, 최종법률내용미검증.
<!-- /GOLD_E2E_REVALIDATION_1232 -->

**1232 후속 설명 정정:** 골드 물리 온톨로지 테이블은 존재한다. `ontology_table_kinds=[]`는 검색 게시 명세의 논리 종류이며 물리 테이블 부재가 아니다. 현재 `A8_GR12_CM1208.IDD_B03_LGL_ONTL_POST/HEAD/ANC` 읽기 전용 확인은 각각0행이다. 기존 repository의 구테이블/컬럼명과 R12 매핑·게시 적재·설정 연결이 남았다. [물리 테이블 확인과 정정](09_ARTIFACTS/AUDITS/20261030-gold-e2e-revalidation/온톨로지_물리테이블_확인과_정정.txt). SELECT6·새모델0·DB변경0·완료ADR불변.

<!-- SOURCE_SEMANTICS_MAIN123_20261030 -->
**2026-10-30 — 원문 독립분석·원기록 이유/목적 MAIN123:** [수정·실제실험 TXT](09_ARTIFACTS/AUDITS/20261030-source-semantics-main123/수정과_실제실험_결과.txt) · [ADR1231](04_EXPERIMENTS/ADR/ADR-1231-source-semantics-state-main/README.md). **MAIN123 / source-semantics-20261030-r1**, 원문만분석→관찰대조·해석text/정확quote분리·선택행위/양태/조건조립·원기록reason/purpose nullable/역할증거·base없음SAME요청금지. 법률/조문/정답/역할단어whitelist없음. **489파일·제품4+pin31=35변경·84계약/후보56/선택189(3설정)/HEALTH3/모의HTTP3통과**, 작업/후보/선택동일·기존47새실패0·canonical프로필4파일불변. **실제1228 5+1230 4=9회: 새정규화2(10구간25좌표)·부재reason/purpose6필드보존, 후속오답SUPPORTED→PARTIAL/양태행위MISMATCH는실제제안에서확인. 하지만식별자관찰SAME/base없음거절→저장0·두번째누적미실행.** 첫원문분석인용혼동/후속생략인용·비EFFECT연결/모든실패보존. 마지막SAME생성제한은오프라인검증만·새실모델0. 진단사본의상태만정정후검증/컴파일통과는실제성공아님. 정상JSON9/error-null0/UNKNOWN0/전환0, 409.054초/$0.05304368·스왑증가0. 독립분석자체오류/추가호출비용남음·법률품질인증없음. MAIN122롤백/데이터/기본OFF유지·전체007/009/GENOS/Git/메일없음. ADR5개최종통과·graph기존16/새0.
<!-- /SOURCE_SEMANTICS_MAIN123_20261030 -->

<!-- MAIN122_AUTHORING_REVALIDATION_1226 -->
**2026-10-29 — MAIN122 실제 정규화·누적 재검증:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main122-authoring-revalidation/재검증결과.txt) · [ADR1226](04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation/README.md). 선택/작업/후보487동일·승인원문5/판단2/용어9로 **새정규화2/2(10구간·31좌표)→누적2판본→컴파일2 완료**, 실제5물리·Parasail5/stop5/error-null0·UNKNOWN0·전환0, 188.104초·보고0.05737812달러. A최초SAME/base없음 거절→기존1회보완NEW/간선정정→저장, B최초통과·기존3노드보존+4추가·이력2/관찰3. 원문·조립영수증/전송/재컴파일동일. **내용기준미통과/Rejected:** 두정규화가본문·식별자를미기록reason/purpose에복사(6필드), A취득의무를보유의전제조건으로해석해SUPPORTED·action보유만, B에서도유지. 세부취득방법/시기/잔여수량기준은둘째판본에보존. 모든preview경로PARTIAL·지식승인/게시0. **제품/MAIN122/데이터불변·GENOS/Git/메일/전체007·009없음**. 106기술검사재실행아님·법률품질인증없음. RAM최소11.404GiB/RSS61.973MiB/swap증가0, ADR최종통과·graph기존16/새0.
<!-- /MAIN122_AUTHORING_REVALIDATION_1226 -->

<!-- AUTHORING_CONTRACT_MAIN122_20261029 -->
**2026-10-29 — 정규화·누적 계약 MAIN122:** [수정·실험 TXT](09_ARTIFACTS/AUDITS/20261029-cumulative-authoring-main122/수정과_실제실험_결과.txt) · [ADR1225](04_EXPERIMENTS/ADR/ADR-1225-cumulative-authoring-main/README.md). 닫힌입력coverage/상태별참조·정확quote+출현순서→좌표조립/원본영수증, 관찰·이전/제안그래프·원문ID구분/enum, 동시참조·SAME오류진단, 원래컴파일을기존보완안에연결. **MAIN122 / cumulative-authoring-20261029-r1, 487파일·제품3+pin31=34변경·후보/작업/선택동일.106계약통과·기존47동일/새0, 후보50·선택171/HEALTH3/모의HTTP3통과.** 실제1220/1222/1224 **합계9물리/stop9/error-null0·정규화2/2(10구간/35좌표)·누적1/2·PARTIAL컴파일1**, 약889.769초·보고0.08591956달러. A취득의무정정/원래관찰보존, B이전노드누락+SAME로거절·보완전예산중단. raw UNKNOWN1은물리before=after인전송전예산오류이며별도정정·외부UNKNOWN0. **전체실험Rejected**, A구조값1을reason/purpose로분류한별도의미문제남음. 마지막SAME진단보강실모델재시험0. 원래profile/compiler/canonical저장·데이터/모델/기본OFF 유지, 승인/게시/GENOS/Git/메일없음. MAIN121롤백·법률품질인증없음. 준비/fixture/문서실패보존정정·최종후보첫106통과. ADR최종통과·graph기존16/새0.
<!-- /AUTHORING_CONTRACT_MAIN122_20261029 -->

<!-- REGEX_WIRE_MAIN121_20261029 -->
**2026-10-29 — error/null 원인 분리·동등 정규식 수정 MAIN121:** [원인·수정 TXT](09_ARTIFACTS/AUDITS/20261029-regex-wire-repair-main121/원인과_수정_검증결과.txt) · [ADR1217](04_EXPERIMENTS/ADR/ADR-1217-bounded-regex-wire-repair/README.md) · [실제1218](04_EXPERIMENTS/ADR/ADR-1218-regex-wire-domain-live/README.md). 합성20조건/22물리로 REF 정규식의 **{0,159} 큰 가변반복 실패**를 분리했다. 작은스키마에서도 원형실패, count32/별표+길이제한 성공. 내부엔진/로그 미확인. 전송사본에서 정확히동등한32+32+32+32+31로변환하고 원래schema/validator/strict유지, error+JSON본문도 미완료거절·원본보존. **MAIN121 / regex-wire-repair-20261029-r1, 487파일·제품2+pin31=33변경·후보/작업/선택동일.402계약통과·1제외, 동일257회귀231통과/기존26실패·새0, 후보45·선택156/HEALTH3/모의HTTP3통과.** 승인된실제입력4요청 **stop/JSON4·error/null0·UNKNOWN0·Parasail4·전환0**, 약318.005초·보고0.059628달러. 그러나A NON_JUDGMENT+참조ID충돌/B coverage입력구간누락으로 **정규화0/2·누적/컴파일0·1218전체Rejected**이며법률품질인증없음. A오류문구를ID누락으로해석하지않는다. wire10784/13629자·원래검증동일·용어본문축약없음. 초기로컬socket권한3실패보존/동일검사통과. **MAIN120롤백·데이터/모델/온톨로지기본OFF 유지·007/009전체재시험/GENOS/Git/메일없음.** ADR최종통과·graph기존16오류/새0.
<!-- /REGEX_WIRE_MAIN121_20261029 -->

<!-- MAIN120_DOMAIN_SCHEMA_LIVE_1211 -->
**2026-10-29 — MAIN120 축약 strict 스키마 실제 도메인 실험 미통과:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main120-domain-schema-live/실험결과.txt) · [ADR1211](04_EXPERIMENTS/ADR/ADR-1211-main120-domain-schema-live/README.md). 사용자 명시승인 후 동일MAIN120서빙487+연구전송1=488파일로 저장판단2조각/공개5unit/용어9후보를1batch 실행. **실제Parasail2회 모두HTTP200/finish_reason=error/content=null, 정규화0/2·누적/컴파일/승인/게시0. 실행구간3.013초(준비제외), 전환0·UNKNOWN0·자원중단0·swap증가0, 토큰/비용미보고.** 실제authoring→ExperimentClient 경계의strict=true·schema159226→10136자·원래구조/messages정확복원·실패JOB2 보존. 누적12976자는사전검사만/실모델누적0. **공통화 전달은확인했으나 생성오류미해결; 공급자내부상세없어grammar/$ref/크기원인확정금지.** 이전1206은NearAI,이번Parasail로인과A/B아님. 자동승인2거절은프로세스전/모델0, 직접승인후실행. MAIN120/작업/선택487/데이터유지·007/009전체재시험/GENOS/Git/메일없음. ADR최종통과·graph기존16오류/새0·법률품질인증없음.
<!-- /MAIN120_DOMAIN_SCHEMA_LIVE_1211 -->

<!-- SCHEMA_FACTOR_MAIN120_20261029 -->
**2026-10-29 — 검증 계약 보존 스키마 공통화 MAIN120:** [구현·검증 TXT](09_ARTIFACTS/AUDITS/20261029-schema-factor-main120/구현과_검증결과.txt) · [ADR1210](04_EXPERIMENTS/ADR/ADR-1210-strict-schema-factor-main/README.md). 사용자 요청으로 **MAIN120 / schema-factor-20261029-r1** 선택. 도메인 authoring·GENOS 일반/stream·기존 local transport의 마지막 전송 사본에 공통화·짧은 정의명 적용, 최종 USE/CONDITIONAL 동등분기 병합. **NORMALIZE159226→10136자(93.63%)·ACCUMULATE61329→12976자(78.84%), 정확복원.487파일·제품6+pin31=37변경, 작업/후보/선택동일.375계약(기존348+신규27)통과·1제외, 동일257회귀231통과/기존26실패·새0.** 원래strict/validator·NOT_USED change_review·필요/claim/gap·복수범위 유지, 중간codec 이후 공통화. 저장49스키마 동등·기존참조45재변환0, 최종540판정조합·24구성구조동등. 후보45·선택156(OFF/ON미설정/ON빈DB)·HEALTH3/모의HTTP3통과. 준비메타·stream fixture1실패 보존/정정, 동결제품불변. **새실모델0·속도/토큰효과/현장GENOS grammar미검증·007/009재시험0·GENOS/Git/메일없음·데이터/모델/온톨로지기본OFF유지.** 용어후보/이력본문은 후속, UNKNOWN원인확정아님. ADR최종통과·graph기존16오류/새0. MAIN119롤백보존·동일저장reader, 법률품질인증없음.
<!-- /SCHEMA_FACTOR_MAIN120_20261029 -->

<!-- SCHEMA_OPTIMIZATION_AUDIT_20261029 -->
**2026-10-29 — MAIN119 스키마 최적화 지점 조사:** [상세 TXT](09_ARTIFACTS/AUDITS/20261029-schema-optimization-audit/최적화_대상과_우선순위.txt). 실제 선택487파일·저장49요청 대조(일반RAG45/도메인3/미채택advisory1). 도메인 authoring은 기존 RAG factor_schema 경로를 우회한다. **현행 함수의 정적 공통화: NORMALIZE159226→12316자, ACCUMULATE61329→15016자·정확 복원 확인**, node7×slot16/LOCATOR235회 반복. 일반 RAG45요청은 이미 축약되어 같은 함수 재적용 이득0. 최종 USE/CONDITIONAL 분기의 동일 제약 병합과 $defs 이름 길이가 후순위다. 생성/전송/서버검증 경계를 유지하고 NOT_USED change_review·필요/claim/gap·복수범위를 줄이지 않는다. GENOS 경로 factor미적용은 코드 확인이며 현장 호환 미검증. 분류 assertion1실패는 advisory별도 정정으로 보존. **제품/MAIN119변경0·실모델0·속도/토큰효과미측정**, JSON-object 전환이나 과거 UNKNOWN 원인 확정 아님.
<!-- /SCHEMA_OPTIMIZATION_AUDIT_20261029 -->

<!-- CUMULATIVE_MAIN119_INPUT_AUDIT -->
**2026-10-29 — 누적 작업 MAIN119·입력 길이 진단:** [반영·진단 TXT](09_ARTIFACTS/AUDITS/20261029-cumulative-main119-input-audit/메인반영과_입력길이_진단.txt) · [ADR1209](04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/README.md). 사용자 요청으로 **MAIN119 / cumulative-contracts-20261029-r1**을 선택했다. 필요ID/거절응답 관찰·감독 복구·목적변경/gap·무손실저장/용량제한·도메인 작성/승인/컴파일 누적 작업 반영, 출처펼치기/accepted-content 유지. **487파일/MAIN118대비96변경(제품설정65+pin31), 작업·후보·선택서비스 동일. 기능348통과·1제외, 동일254회귀228통과/기존26실패·새실패0. 후보34·선택서비스123(OFF/ON미설정/ON빈DB), HEALTH3·모의HTTP3 통과.** 초기검사ROOT/저장API 준비오류 보존·정정. **실제49전송 입력 조사: 도메인최대247213자=system7924/user70323/schema159226, 용어집9후보63983자(detail50151). 일반RAG최대118262자, 연결메뉴/도구/이력 비중 큼.** 신규need선언 전체 복사 성장경로는 모의확인·과거1205주원인 단정금지. 기존 wire축약 유지·입력축약 새적용0·UNKNOWN인과미입증. 미실행1207전송/실패1201검토/병행1208연구는 미채택. **새실모델0·007/009재시험0·GENOS/Git/메일없음·온톨로지기본OFF/데이터유지·법률품질인증없음.** ADR최종통과·graph기존16오류/새0. MAIN118 보존하되 압축기록 생성 후 reader다운그레이드 금지, 새reader+GENOS_JOURNAL_STORAGE=plain 사용.
<!-- /CUMULATIVE_MAIN119_INPUT_AUDIT -->

<!-- DOMAIN_PROFILE_REAL_LIVE_1206_1207 -->
**2026-10-29 — 도메인 프로필 실제 기록 시연 실패:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-domain-profile-live-demo/실험결과.txt) · [ADR1206](04_EXPERIMENTS/ADR/ADR-1206-domain-profile-real-records/README.md) · [ADR1207](04_EXPERIMENTS/ADR/ADR-1207-domain-profile-portable-schema/README.md). 저장1198 C1조건/1200 C3취득기준의 실제2조각·공개원문5unit·기존용어집9후보를483파일 격리 제품에 입력했다. **1206 7.575초·물리3: Parasail429→NearAI1회 전환 뒤 두 응답HTTP200/finish_reason=error/content=null. 구조화0/2·누적/컴파일/승인/게시0·비용미보고.** 원본과실패JOB보존·완성결과대체없음. 엄격schema영향은 가설이다. 후속1207은 같은검증기의 동등schema 반복참조 축약(159226→12287/61329→14563문자)·JSON-object 전송 후보1파일만 추가했으나 **사전호스트스왑+132.516MiB로128기준중단·실모델0**. 후속명령준비도 preflight결속검사로 client/dispatch전에 차단, 오류보존. 두ADR최종검사통과·전역graph기존16오류·새오류0. **작업제품/MAIN118/GENOS유지·추가재시험/Git/메일없음.** 실제누적의미효과 미검증이며 이전47모의검사를 실모델통과로 확대하지 않는다.
<!-- /DOMAIN_PROFILE_REAL_LIVE_1206_1207 -->

<!-- REJECTED_NEED_PRESERVATION_20261029 -->
**2026-10-29 — 거절된 조사 응답의 필요 선언 보존:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261029-rejected-need-preservation/수정과_검증결과.txt). ADR1205의 행동 검증 실패→material_need 유실을 수정했다. 완전한 canonical 응답과 전달 영수증을 받은 뒤, 전체 행동 승인 전에 실제 progress 스키마·쟁점·요청/state·원문 권한/바이트/전달을 독립 검증하여 MN/OPEN과 관찰 영수증을 저장한다. 행동·판단·source_targets·감독 현재 목표/예산은 승인하지 않으며 기존 1회 보완을 유지한다. **제품2+pin31 작업 반영, 현재485파일 고정 사본/작업 해시 동일. 고유196검사 통과(기존169+새24+모의 native API3), 기존 actual007 준비검사1제외.** 저장1205 최초/보완의 행동 오류를 유지하며 같은 필요1개/영수증2개와 최종 입력 연결 확인. 모의 API는 행동2회 거절→OPEN 제한답변·저장/중복조회, 최종 누락1회 보완, 반복 누락422 통과. 최종 요청5개 canonical/wire에 같은 필요ID/문장 존재. 초기 전달영수증 필드 검사1실패와 준비 코드 실패들은 보존·정정했고 성공한 기존 검사는 불필요하게 반복하지 않았다. **새실모델0·007/009 전체 재실행0·MAIN118/GENOS 유지·승격/커밋/메일 없음.** 병행 도메인 프로필 작업 보존. 미선언 필요 발견·법률 의미 정확성·공급자 공백/UNKNOWN 개선으로 확대하지 않는다.
<!-- /REJECTED_NEED_PRESERVATION_20261029 -->

<!-- DOMAIN_PROFILE_IMPLEMENTATION_20261029 -->
**2026-10-29 — 도메인 프로필·판단 누적 로컬 구현:** [구현·검증 TXT](09_ARTIFACTS/AUDITS/20261029-domain-profile-implementation/구현과_검증결과.txt) · [사용 안내](07_DOCS/REFERENCE/OPERATIONS/DOMAIN_PROFILE_WORKFLOW_20261029.txt). 기존 용어집 개념ID/판본을 참조하고 raw 원래 의견·정정→공통 구조화→원문 대조·누적→typed graph 컴파일→내용승인→staged/소비검증/활성전환→RAG ASSESS를 연결했다. 기존 v1과 저장소 재사용, 새DDL0·용어 자동승인0. **신규47검사 통과(계약43/native HTTP3/Streamlit AppTest1), 기존67검사55통과/12실패가 변경 전 ontology 모듈과 동일·해당 범위 새회귀0.** A오판→B정정/2판본→승인게시→C API입력/모의claim/저장답변·중복재조회 확인. 원문/권한/용어집/hash·stale/CAS·UNKNOWN무재시도 유지, runtime 그래프컴파일0. 제품/템플릿24+pin/authority31 작업 반영. 초기 runtime package에 생성schema를 싣던 구조한도 결함 수정·실패 원본 보존. **실모델0·E1/E2/현장Oracle/Dataiku/S3/GENOS미검증·이번MAIN승격0.** 병행ADR1204의MAIN118 선택 보존. AppTest는 실제 브라우저 시각/현장인증 검증이 아니다. instruction resource resolver/256초과 목록/명시참조 후보검색 제한은 사용 안내에 명시했다. 법률 의미 정확성 인증·Git·메일 없음.
<!-- /DOMAIN_PROFILE_IMPLEMENTATION_20261029 -->

<!-- NEED_CONTINUITY_LIVE_1205 -->
**2026-10-29 — 필요 연결 수정본 실제009 미통과:** [실험 TXT](09_ARTIFACTS/AUDITS/20261029-need-continuity-live/실험결과.txt) · [ADR1205](04_EXPERIMENTS/ADR/ADR-1205-need-continuity-live-cm009/README.md). 169계약 통과 사본과 동일471파일·65문서 권한의 격리 native API에서0091회. **294.097초=모델232.676+기타61.421, 물리4=차감4·도구23. Parasail3정상 뒤 최종ASSESS HTTP200헤더/공백60조각660바이트→179.879초 기한 종료·UNKNOWN1·API504/FAILED·최종답변0. 전환0·자원중단0·스왑증가0·통신회수.** 앞서 FOLLOW_CONNECTION의 미제출 새판단 참조가 최초/보완 모두 READ_ACTION_JUDGMENT_REFERENCE로 거절되어 MODEL_DECISION_UNRESOLVED 인계. **두 거절 응답의 material_need는 독립 progress검증2/2통과했지만, 필요 저장이 전체 행동 검증 뒤라 MN등록0·최종 canonical/wire에서 정의 필요 문장이 모두 유실**됐다. GN원문목표3개는 전달됐다. 승인된 필요 연속성/최종 해결·change_review 조건부 필수/ROLE_ONLY 실효는 미검증이며 공집합 검사true를 통과로 해석하지 않는다.31조 마·바8블록 미확보/미전달·자동형제추가0. 원문122·중첩입력183·평면최종61 대조 불일치/권한위반0. 보고비용0.01410652달러(UNKNOWN미보고). **동결471·작업제품7·입력/실행기 동일. 실행 중 별도ADR1204가MAIN118을 선택했으며 이 실험은고정후보 유지·이번승격0.** 실제 최종출력없음으로 COVERED/gaps=[] 변화를 단정하지 않는다. 준비메타9오류·문서helper import1오류·감사집계 해석 정정 보존. 새제품수정/자동재시험/007/GENOS/Git/메일 없음. 후속은 잘못된 행동을 채택하지 않고 독립 검증한 필요를 미해결로 영속화하는 경로다.
<!-- /NEED_CONTINUITY_LIVE_1205 -->

<!-- SOURCE_ACCORDION_MAIN118 -->
**2026-10-29 — 출처 원문 펼치기 MAIN118:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261029-source-accordion-main118/반영과_검증결과.txt) · [ADR1204](04_EXPERIMENTS/ADR/ADR-1204-source-accordion-main-integration/README.md) · [GENOS 반입 안내](08_DEPLOYMENT/GENOS/handoffs/source_accordion_main118_20261029_r1/GUIDE.txt). 사용자 요청으로 **MAIN118 / source-accordion-20261029-r1**을 선택했다. 출처 버튼→출처별 상자→확보 원문 펼침/접힘을 표시하며 추가모델/조회0. MAIN117의466파일 중 workflow1파일만 변경, 다른 작업/동시 변경 보존. 후보29·작업29검사 통과, 기존23검사18통과/3실패/2준비오류 동일·새회귀0. 후보서비스11·실제선택서비스17·반입11조건 통과, 코드ZIP466파일/워크플로우TXT와 선택 MAIN 일치. 초기 검사기 import/임시폴더·메타 오류 보존. ADR최종검사통과·전역graph기존16오류동일. **GENOS 현장 리비전·편집기 배포·화면·Git·메일 미수행**, 법률품질 인증없음. MAIN117 롤백 보존.
<!-- /SOURCE_ACCORDION_MAIN118 -->

<!-- NEED_CONTINUITY_IMPLEMENTATION_20261029 -->
**2026-10-29 — 선언한 필요의 단계 간 연결 계약 구현:** [구현·검증 TXT](09_ARTIFACTS/AUDITS/20261029-need-continuity-implementation/구현과_검증결과.txt). 감독 material_need를 안정 ID와 선언 이력으로 누적하고 원문 목표/구조 선택·실제 확보·최종 claim/판단/gap·명시 제외에 연결한다. ANSWERABLE/FINISH/감독 소진으로 이전 필요를 삭제하지 않으며 최종 누락·부분 원문 해결·OPEN+COVERED를 거절한다. 필요한 NOT_USED의 change_review를 생성 스키마에서도 필수화하고 ROLE_ONLY를 해석 변경과 구분했다. **참조 형제 목표 자동 확장 호출 제거, 필요한 조문·범위 선택은 LLM 유지. 제품7+pin31 작업 반영, 고정 사본 계약/native API169통과·1제외·새실모델0.** 검사 중 별도 온톨로지8파일과 기존 핀 불일치를 발견해 작업 파일은 보존하고 고정 사본만 기존 핀 원본으로 분리 검증했다. 현재 작업 트리 전체 통과가 아니며 상세 결속·초기 실패를 보존했다. **MAIN117·GENOS 유지, 007/009 실제 재시험·승격·Git·메일 없음.** 미선언 필요 자동 발견·법률 의미 정확성 보장으로 확대하지 않는다.
<!-- /NEED_CONTINUITY_IMPLEMENTATION_20261029 -->

<!-- DECISION_CONSISTENCY_AUDIT_20261029 -->
**2026-10-29 — 복수 판단·범위 선택 및 단계 간 상태 감사:** [전수조사 TXT](09_ARTIFACTS/AUDITS/20261029-decision-consistency-audit/전수조사결과.txt). legal_agent162모듈/상태참조57모듈 목록화와 호출 경계 대조, 저장17폴더에서 중복 제거16출력시퀀스·114응답을 조사했다. **복수 판단·READ최대4·구조 열거/범위/전체/제외 지원**, 실제1203 전송 스키마에도 존재한다. source_targets는 응답당4개·항목당 단일좌표로 범위 선택과 계약이 다르다. 실제 저장31조 마·바 해석/8블록 및 부분확보 거절을 오프라인 확인했다. **핵심 결함은 감독 material_need와 최종 needs/gaps 사이 연결 부족**이다.1203은 감독2회 뒤 `TERMINATION_SCOPE_REVIEW:BOUNDED_HANDOFF`, SELECT는 evidence_sufficient=false였고 마지막 필요 문장/독립 필요목록은 최종입력에서 빠졌다. 최종 COVERED/gaps=[]가 이전 필요 해소를 증명하지 않는다. change_review는 생성스키마에서 선택이지만 일부NOT_USED에 서버필수여서 실제422를 일으켰다. 역할 변경과 의미 반전을 구분한다. 기존구조42검사 통과, 진단15개 재현(결함 재현 포함), 별도selector2검사 통과. 기존fixture2실패(policy없음)·감사probe import1오류 보존. **새모델0·제품468파일/MAIN117 유지·후속 구현/실험/배포 없음. 필요 원문·범위 선택은 LLM, 서버는 ID/권한/확보/상태 연결 검증이라는 사용자 지시 유지.** 패턴15응답/9시퀀스를 법률 오류율로 해석하지 않는다.
<!-- /DECISION_CONSISTENCY_AUDIT_20261029 -->

<!-- REFERENCE_PURPOSE_LIVE_1203 -->
**2026-10-29 — 참조·목적 검증 수정본 실제009 미통과:** [실험 TXT](09_ARTIFACTS/AUDITS/20261029-reference-purpose-live/실험결과.txt) · [ADR1203](04_EXPERIMENTS/ADR/ADR-1203-reference-purpose-live-cm009/README.md). 사용자 요청으로1202 rev004와 동일468파일·65문서 권한의 격리 native API/실제 전송기에009를1회 실행했다. **196.368초=모델90.000+기타106.368, 물리11=차감11·도구38. Parasail429→NearAI1회 전환·10정상, UNKNOWN/만료/자원중단0. HTTP422·실행/요청FAILED·최종답변0.** 이번 모델은31조를 목표로 전혀 올리지 않았다. 기존 목표가 있어야 참조 묶음이 활성화되므로 **마목407~409·바목410~414 모두 미확보·최종 최초/보완 미전달**이다.13조의 참조 문장만 전달됐으며 조문root와 하위본문을 구분한다. 대형법인 정의는 이번에 코스닥2조에서 확보·최종입력/초안 반영했다. 직접 종료는 유가2조/유가세칙9조 SUPPORT→NOT_USED의 **change_review 최초·보완 모두 누락→FINAL_REVIEW_PURPOSE_CHANGE**다. 실제 지시문·스키마·이전판단/목적·보완 오류 경로가 전달됐다. 두 이전 finding 자체가 이미 해당 정의/면제가 아니라는 내용이므로 **실제 의미 반전 탐지로 확대하지 않는다.** gaps=[]여서 핵심gap 연결 복구 미발동, 새검토AI0. 원문317·중첩입력775·평면최종입력306 대조 불일치/권한위반0·스왑증가0·통신회수. 보고비용0.020888468달러(429사용량 미보고). 동결/작업468파일·입력/실행기·MAIN포인터 동일. 감사 helper import/인자/임시 상태경로 오류는 보존·읽기전용 정정. ADR최종검사통과·전역graph 기존16오류, **작업제품·MAIN117·GENOS 유지·자동재시험/007/Git/메일 없음**. 후속은 미선언 필요참조 목표 연결과 정상 제외를 구분한 변경 기록/보완이다.
<!-- /REFERENCE_PURPOSE_LIVE_1203 -->

**1203 후속 사용자 지시·종료 판단 정정:** 필요한 참조 조문과 여러 하위 범위를 선택하는 판단은 LLM이 담당한다. 서버의 참조 자동 추가를 해결 방향으로 확대하지 않는다. 서버는 모델이 선택한 목표의 ID/범위·권한·실제 확보·출력 형식과 상태 일치를 검증한다. 실제1203 조사 응답은 FINISH를3회 제안했으나 매번 `evidence_sufficient=false`, `NEEDS_SOURCE`였다. 두 감독 후 코스닥2조 정의를 읽었고 마지막에도 추가 조사 필요를 적은 채 확인 범위에서 종료를 제안했다. 그다음 최초/보완 ASSESS가 `COVERED`, `SATISFIED`, `gaps=[]`로 바뀌었다. 따라서 “13조를 읽고 즉시 충분하다고 종료”가 아니라 **조사에서 부족함을 인정한 종료 제안→최종 판단에서 미확인 소실**이다.31조 마목·바목은 조사 필요 목록에도 없었다. [상세 정정](09_ARTIFACTS/AUDITS/20261029-reference-purpose-live/종료판단_상세정정.txt). 새 모델/제품 변경0.

<!-- REFERENCE_PURPOSE_REVIEW_1202 -->
**2026-10-29 — 참조 묶음·목적별 판단 변경·핵심gap 복구 작업 통합:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261029-reference-bundle-purpose-review/수정과_검증결과.txt) · [ADR1202](04_EXPERIMENTS/ADR/ADR-1202-reference-bundle-purpose-review/README.md). 현재 검증 원문이 명시한 참조 중 한 좌표가 목표로 선택되면 같은 문서의 나머지 참조를 별도 목표로 결속해 기존 서버 선집행으로 확보한다. 파생 목표의 재귀 확장은 막고16목표/기존 시간·도구 예산을 유지한다. CORE/SUPPORT→NOT_USED는 이전 의견·각 조사 목적·현재 원문 또는 실제 주장/핵심gap을 연결해야 하며, 조문root만 있고 필요한 하위 원문이 없으면 완료 근거로 쓸 수 없다. 요구검토의 유일한 오류가 핵심gap 연결 누락이면 주장·gap을 바꾸지 않고 UNRESOLVED 행과 원제안/전후hash 영수증을 남겨 기존 조사/제한 답변 경로로 진행한다. **후보468파일·제품/설정9+pin31, 후보141·작업141검사 통과·기존104 동일/새회귀0.** native API의 형제 원문 확보/최종입력·정상 제외·보완1회·반복오류422·제한답변·저장/중복 재조회 통과. 저장009 조각은 **마목만 선언→마목+바목 목표**, 마목407~409확보/바목410~414미확보 판정, 기존 무근거NOT_USED 거절·핵심gap보존 통과다. **새009전체 실행/답변 통과가 아니며 새모델0·MAIN117/GENOS 유지.** 기존 completion_execution 저장압축 hunk와 다른428파일 보존. 초기 fixture 오류·파생 목표 반복 확장·최상위 영수증 저장스키마 오류를 보존/수정했고 ADR최종검사통과. 원장의root보존1/1은 메타검사에 필요한 기술 기대값이며 하위원문 확보/전달/법률품질 인증이 아니다. 의미적으로 잘못된 재해석까지 자동 보장하지 않는다. Git/메일 없음.
<!-- /REFERENCE_PURPOSE_REVIEW_1202 -->

<!-- FINAL_ORIGINAL_REVIEW_1201 -->
**2026-10-29 — 최종 원문 대조 AI 후보·실제009:** [실험 TXT](09_ARTIFACTS/AUDITS/20261029-final-original-coverage-review/실험결과.txt) · [ADR1201](04_EXPERIMENTS/ADR/ADR-1201-final-original-coverage-review/README.md). 사용자 요청으로 최종 답변과 ASSESS 선택 원문 전체를 대조하는 별도 advisory AI를 격리 후보 rev002에 연결했다. 원문/주장 전수 판정·정확 인용·상태 일치·답변/원문 해시·지속 영수증·중복 방지·물리 예산을 검증하며 자동 답변 수정/추가 보완은 하지 않는다. **후보467파일·제품/설정9+pin31, 고유28검사 통과. 최초 예산 분류 누락2실패는 보존·수정했다. 저장1200의007 새 검토1회(전체007 재실행0)는75.679초·Parasail1응답 뒤 COVERED/누락지적 상충으로 INCOMPLETE. 실제 결함2개 탐지0·이미 있는 내용 오탐2로 검토 효과 미통과.** 최신 사용자 지시에 따라009는 별도로1회 실행했다. **318.430초·모델125.715초·기타192.715초, 물리13=차감13·도구52. Parasail429→NearAI1회 전환·12정상, UNKNOWN/만료/자원중단0. 코스닥13/31 확보·최종 최초/보완 입력 전달, 원문255/입력928 불일치·권한위반0.** 그러나 대형법인 기준 미확인을 핵심gap으로 쓰면서 요구검토 SATISFIED/gap_indices=[]를 최초·보완 모두 유지해 기존 REQUIREMENT_GAP_COVERAGE 거절·HTTP422/FAILED. **최종답변0·새검토AI 도달0이며 corpus에 정의가 없다는 단정은 금지.** 새물리 합계14·보고비용0.035350304달러(429사용량 미보고). ADR최종검사 통과·전역graph 기존16오류 동일/새오류0. **후보만 보존·작업제품/MAIN117/GENOS 유지·자동재시험/Git/메일 없음.** 원문 전달·최종 내용 보존·의미 검토 품질을 구분한다.
**후속 상세감사 정정:** [31조 확보범위 정정](09_ARTIFACTS/AUDITS/20261029-final-original-coverage-review/9번_31조_확보범위_정정.txt). 위 “13/31 확보·전달”은 조문ID 단위 집계였다. 실제009는31조1항3호 **마목+상위문맥6블록만 확보·전달, 바목410~414는DB에 있지만 미확보·미전달, 최종article_complete=false**다. 모델은 마목만 목표로 등록하고 대형법인 정의 탐색 목적을 붙였으며, 읽은 뒤SUPPORT로 인정했다가 최종/보완에서는 “대형법인 정의가 아님”을 이유로NOT_USED 처리했다.13조의 마목·바목 참조 문구는 남았으나 세부근거는 미사용이다. 기존 diagnose/gate의 조문root 존재 검사는 필요하위범위 완전성 검사가 아니며 확보통과 확대금지. 실제 종료원인은 별도의gap/SATISFIED 모순으로 동일하다. 완료ADR·원본실패 보존, 새모델0·제품/MAIN117변경0.
<!-- /FINAL_ORIGINAL_REVIEW_1201 -->

<!-- SUPERVISOR_RECOVERY_LIVE_1200 -->
**2026-10-29 — 조사 복구 후보 실제007·009 미실행:** [실험 TXT](09_ARTIFACTS/AUDITS/20261029-supervisor-recovery-live/실험결과.txt) · [ADR1200](04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/README.md). 사용자 요청으로1199와 동일466파일·65문서 권한을 격리 native API/실제 전송기에 실행했다. **전체262.175초·모델163.694초·기타98.480초, 물리10=차감10·도구39. Parasail2정상 뒤429→NearAI1회 전환·7정상, UNKNOWN/만료/자원중단0.** 실제 CONTINUE_TARGETED+다른 행동 오류를 거절 기록하고 **독립RESEARCH1회 APPLIED→기존 두번째감독 REDIRECT READ→코스닥 시행세칙15 본문 확보·최종인용 통과**. 추가모델보완0·기존감독2회 안에서 동작했다. 두시장13/세칙15·원문257/입력521구간 불일치·권한위반0. 최종3주장2273자·COMPLETE·7단계hash/accepted-content-v1 전체내용 보존, COMPOSE모델0. **그러나 C1은 코스닥 취득 의무를 취득하는 경우로 조건화하고,15(5)의 최근3년주선/상장후2년/환기·관리·폐지사유는 최초·보완 최종프롬프트에 정확히 전달됐는데 claims/답변에서 누락하여 내용미통과·009미실행.** 원문 미확보·조립 손실과 구분한다. 스왑증가0·통신회수·보고비용0.028587200달러(429사용량미보고). 초기 검증 인자오류/실행기 사전정정 기록 보존·ADR최종통과·전역graph기존16오류동일. **MAIN117·작업제품·GENOS 유지·자동재시험/Git/메일 없음. 온톨로지 문서는 정리됐으나 ASSESS 의미 교정 구현은 별도**다.
<!-- /SUPERVISOR_RECOVERY_LIVE_1200 -->

<!-- SUPERVISOR_ROUTE_RECOVERY_1199 -->
**2026-10-29 — 의무/조건 온톨로지 문서·감독 조사 복구 작업 통합:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-supervisor-route-recovery/수정과_검증결과.txt) · [ADR1199](04_EXPERIMENTS/ADR/ADR-1199-supervisor-independent-route-recovery/README.md). 사용자 지시로 [온톨로지 지식 축적](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/CONTROLLED_KNOWLEDGE.md)에 적용 조건·규범 양태·이행 행위/기준·예외·위임의 구분과 원문 판본/span 결속·승인 검토 기준을 반영했다. 도메인 스키마/골드/ASSESS 의미 교정 구현은 별도다. 감독의 CONTINUE_TARGETED+다른 행동은 거절 기록을 유지하고, 현재 메뉴·권한·원문·상태·예산으로 독립 검증한 비종료 조사 행동만 실행한다. 같은 경로 REDIRECT·반복·가짜ID·stale·만료는 복구하지 않는다. 기존 감독2회 안에서 독립 경로 최대2·추가 모델보완0. **후보59·작업59검사 통과, 기존44검사 MAIN117과 동일·새회귀0. 실제 native API 추가 원문 읽기·저장·중복 재조회 통과.** 저장1198 응답4개를 같은65문서/native HTTP에 재생해 변경 없는 감독 제안으로 RESEARCH 실행·15조 후보 도달·다음 조사 선택을 확인했다. 새 판단 전 중단하여 **15조 본문 확보·새007답변/009 미검증**이다. 재생 종료 도구의 portal 정리 오류는 실패 원본 유지, 완료 checkpoint만12조건 영수증으로 확인했다. 초기 fixture2실패·README형식9오류도 원본 보존·정정했다. 제품1+pin31 작업 통합, 다른434서빙파일/기존 hunk 보존·ADR최종검사통과·graph기존16오류동일. **새모델0·MAIN117 선택/GENOS/Git/메일 유지**, ASSESS 의미 오류 해결로 확대하지 않는다.
<!-- /SUPERVISOR_ROUTE_RECOVERY_1199 -->

<!-- MAIN117_LIVE_1198 -->
**2026-10-29 — MAIN117 실제007·009 미실행:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main117-live-test/실험결과.txt) · [ADR1198](04_EXPERIMENTS/ADR/ADR-1198-main117-live-cm007/README.md). 실제 선택service/동일466파일·65문서 권한으로007을1회 실행했다. **전체165.285초·모델96.753초·기타68.532초, 물리7=차감7·도구26. Parasail1정상 뒤429→NearAI1회 전환·5정상, UNKNOWN/기한만료/자원중단0.** 최종2주장·1758자·COMPLETE 저장·7단계 해시 일치, COMPOSE 모델 호출0·accepted-content-v1 전체 내용 보존 통과. 이전 국내소재외국지주회사 분류·최초취득 분모 누락 미재현, 유가 국내/신청후 범위 유지·일반 미확인 문구 없음. **하지만 최초·보완 ASSESS 모두 원문에 있는 코스닥 취득 의무를 “취득하는 경우”라는 적용 조건으로 바꿔 내용미통과. 감독도 FINISH→RESEARCH 변경에 CONTINUE_TARGETED를 보내 계약 거절되고 source_targets=[]여서 코스닥 시행세칙15 미확보·세부 수량/6개월 보유 사유 누락. 009는 미실행.** 두시장13조 확보/인용·원문197/입력305 불일치·권한위반0, 요구검토1회·보완1회·최종 프롬프트7250자 실제 전달. 스왑증가0·통신프로세스회수. 보고비용0.017246310달러(429사용량 미보고). ADR최종검사통과·전역graph기존16오류동일. 마지막 조립의 보존과 앞 단계 의미 판단/조사 복구를 구분하며 공급자·속도 인과효과는 미입증이다. **제품·MAIN117·GENOS 유지, 같은7번자동재시험·Git·메일 미수행.**
<!-- /MAIN117_LIVE_1198 -->

<!-- ACCEPTED_ANSWER_MAIN117 -->
**2026-10-29 — 최종 답변 내용 보존 MAIN117:** [수정·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-accepted-answer-main117/수정과_검증결과.txt) · [ADR1197](04_EXPERIMENTS/ADR/ADR-1197-accepted-answer-release-receipt/README.md). 사용자 후속 수정 요청으로 **MAIN117 / accepted-answer-20261029-r1**을 선택했다. 최종 자유 서술 COMPOSE 호출을 생략하고 ASSESS의 검증된 content/text를 서버가 문단·목록·표로 조립한다. 조건·예외·수치 분모 등 전체 내용을 재컴파일·해시 대조하며 임의 대체문장·누락·중복·변조를 거절한다. 과거 narrative-v1 저장 답변은 호환 유지한다. 후보116·작업116 계약 통과, 동일211회귀189통과/기존9실패/준비오류13·새회귀0. 466파일 중 제품/설정6+pin31변경, 다른429파일·작업 압축읽기 hunk 보존. 실제 선택service OFF/ON미설정/ON빈DB **207확인·HEALTH3·모의HTTP3 통과**. 저장1195의007을 읽기 전용 재조립해1524→2286자·주장4개 전체와 국내소재외국지주회사 분류·최초취득 분모를 보존했다. **새모델0·007 실제 재시험0·0090·GENOS/Git/메일 미수행**, 과거 실패 판정 유지. ASSESS 자체 의미 누락/오판은 해결로 확대하지 않으며 UNREVIEWED 유지. 최초 import 누락·검사 fixture/메타 오류를 보존했다.1196의 조기 완료 상태 오류는 원본 유지하고1197에서 동일 코드9영수증·이전 리더12호환검사 후 정정·승격했다. ADR최종검사통과·전역graph기존16오류동일. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`, MAIN116 롤백 보존.
<!-- /ACCEPTED_ANSWER_MAIN117 -->

<!-- MAIN116_LIVE_1195 -->
**2026-10-29 — MAIN116 실제007·009 미실행:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main116-live-test/핵심결과.txt) · [ADR1195](04_EXPERIMENTS/ADR/ADR-1195-main116-live-cm007/README.md). 실제 선택service/동일466파일·65문서 권한으로0071회 실행했다. **전체433.446초·모델352.369초·기타81.077초, 물리8=차감8·도구30. Parasail 정상6응답 뒤 COMPOSE429→NearAI1회 전환·정상응답, UNKNOWN/기한만료0.** 감독9.850초·ASSESS147.710초, 최종4주장·COMPLETE 저장·7단계 해시 일치. 두시장13조 확보/인용, 원문206·입력333불일치/권한위반0. 최종 프롬프트7250자 실제 전달, 유가 국내/신청후 범위 유지·일반 미확인 문구 제거 확인. **원문·accepted C1·COMPOSE 입력에 있던 국내소재외국지주회사 분류 조건이 마지막 서술형 답변에서 빠져 내용미통과·009미실행.** 외국기업 월별5%의 최초취득 분모도 모호해졌다. 원문 미확보가 아니라 COMPOSE 내용 손실이며 주장ID 포함 검사는 통과했다. 전환 전후 messages/schema 동일·공급자 인과효과 미입증. 자원중단0·스왑증가0·통신프로세스회수. 보고비용0.04362811달러(429사용량 미보고). 준비 메타/리뷰 보조 오류는 보존·정정, ADR최종검사통과·전역graph기존16오류동일. **작업제품·MAIN116·GENOS 유지, 같은7번자동재시험·Git·메일 미수행.**
<!-- /MAIN116_LIVE_1195 -->

<!-- FINAL_ANSWER_MAIN116 -->
**2026-10-29 — 최종 답변 누적 수정 MAIN116 반영:** [반영·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-final-answer-main116/반영과_검증결과.txt) · [ADR1194](04_EXPERIMENTS/ADR/ADR-1194-final-answer-main-integration/README.md). 사용자 요청으로 **MAIN116 / final-answer-20261029-r1**을 선택했다. MAIN115 누적 원문·응답·요구검토·공급자·기한 수정을 유지하고1192 최종 ASSESS/보완 프롬프트2곳과 서버 일반 미확인 문구 제거를 통합했다. material gap·최종 검토 미완료 경고·stop_reason·UNKNOWN 기록 보존. 466서빙파일 중 제품3+pin31변경, 후보 고유130·작업130계약 통과. 211회귀189통과/기존9실패/준비오류13 동일·새회귀0. 저장0072392→2344자로 일반 문구48자만 제거, 주장·원문·조건·중단 이력 동일. 실제 선택service OFF/ON미설정/ON빈DB 총195확인·HEALTH3·모의HTTP3 통과. 초기 검사 준비 오류는 원본 보존 후 동일제품으로 정정 검증했다. 작업의 저장압축 읽기와 다른432파일 보존. ADR최종검사통과·전역graph기존16오류동일. **새모델0·감독공백/UNKNOWN 미해결·007전체미통과/009미실행 기록 유지·GENOS/Git/메일 미수행**. 모델·데이터·예산·출력상한없음·온톨로지기본OFF 동일. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. MAIN115 롤백 보존.
<!-- /FINAL_ANSWER_MAIN116 -->

<!-- FINAL_SCOPE_PROMPT_LIVE_1193 -->
**2026-10-29 — 최종 프롬프트 실제007·009 미실행:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-final-scope-prompt-live/핵심결과.txt) · [ADR1193](04_EXPERIMENTS/ADR/ADR-1193-final-scope-prompt-live-cm007/README.md). 사용자 요청으로1192와 동일466파일을 격리 native API/실제 서빙 전송기로0071회 실행했다. **Parasail 물리8=차감8, 정상7응답/UNKNOWN1·전환0. 전체448.401초·모델365.856초·기타82.545초, 도구30.** 감독6번째 호출은 HTTP200 뒤60조각660바이트 공백만 수신해179.859초에 절대기한 종료·프로세스 회수됐고, 기존 확보 원문 답변 경로의 최종ASSESS/보완이 각각50.289/47.738초에 완료됐다. 수정 지시문7250자가 두 최종 호출에 실제 전달됐으며 **이전 누락인 ‘예비심사 신청 후 국내 모집·매출분’ 조건을 최초·보완·실제 답변에 모두 유지**했다. 두시장13조/시행세칙 등 핵심 수량·기간·범위 대조 통과, 주장5·2392자·COMPLETE 저장, 원문206/입력472불일치·권한위반0. 요구검토 근거연결 보완1회, 자원중단0·스왑증가0. **COVERED/gaps=[]에도 서버 일반 미확인 문구가 남고 감독UNKNOWN으로 전체기준미통과·009미실행.** 보고비용0.05805792달러(UNKNOWN비용미확인). 이전1191은NearAI·다른조사입력이므로 프롬프트 인과효과/속도인증 아님. 완료 전 감사시도는 원본 보존하고 최종저장감사를 다시 확인했다. ADR최종검사통과·전역graph기존16오류동일. **작업제품·MAIN115·GENOS 유지, 같은7번자동재시험·Git·메일 미수행**.
<!-- /FINAL_SCOPE_PROMPT_LIVE_1193 -->

<!-- FINAL_SCOPE_PROMPT_1192 -->
**2026-10-29 — 최종 답변 조건 보존 프롬프트 후보:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261029-final-answer-scope-prompt/수정과_검증결과.txt) · [전체 시스템 지시문](09_ARTIFACTS/AUDITS/20261029-final-answer-scope-prompt/최종_시스템_프롬프트.txt) · [ADR1192](04_EXPERIMENTS/ADR/ADR-1192-final-answer-scope-prompt/README.md). MAIN115 기반 격리 scoped/rev-001에서 최종 ASSESS·보완 프롬프트2곳만 수정했다. 주체·대상·지역·시점, 산정 기준·단위·상한·기한, 조건·예외를 실제 claims에 쓰고 원문과 역대조하도록 명시한다. 읽은 원문의 답변 누락과 원문 미확보를 구분하며 보완 때도 내용 대조를 반복한다. 특정 조문·문서·정답 하드코딩없음, 새 모델 단계·출력 필드·재시도 추가0. 466파일·프롬프트2+pin31변경, 고유75계약 통과(최초63통과/검사ROOT오류12보존 후 동일후보 재검사12통과). 저장007 최종11·12요청의 질문·원문·스키마·라우팅 동일, system만5762→7250자로 재구성·미전송. **새모델0·효과/속도미검증·작업제품/MAIN115/GENOS미변경·서버 일반 제한문구 결함 미수정**. 인샘플 Proposed·decision_eligible=false. ADR최종검사통과, 전역graph기존16오류동일.
<!-- /FINAL_SCOPE_PROMPT_1192 -->

<!-- MAIN115_PARASAIL_LIVE_1191 -->
**2026-10-29 — MAIN115 Parasail 실제007 시험·009 미실행:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main115-parasail-test/실험결과.txt) · [ADR1191](04_EXPERIMENTS/ADR/ADR-1191-main115-parasail-cm007/README.md). 사용자 실험 요청으로 실제 선택service/466파일·동일65문서 권한에서007을1회 실행했다. **Parasail 첫 요청은 공유풀429, 규칙대로 Near AI1회 전환 후11응답·최종답변·COMPLETE 저장을 완료**했다. 전체337.624초·모델208.867초·기타128.756초, 물리12=차감12·도구44. 두시장13조 확보/인용, 원문359·입력922구간 불일치/권한위반0. 요구검토1회 저장·기존ASSESS보완1회·UNKNOWN/기한만료/자원중단0. **내용검토에서 유가 의무인수 수량의 국내 모집·매출 범위 누락과 COVERED에도 서버가 덧붙인 일반 미확인 문구를 확인해7번 내용미통과·9번 미실행**. 원문 미확보가 아니다. 정상11응답 보고비용0.026090240달러,429사용량정보없음. Parasail 생성 성능·NearAI 일반성능/법률품질 인증이 아니다. 준비문서19오류·중앙값집계1오류를 원본보존·정정, ADR최종검사통과·전역graph기존16오류동일. **MAIN115·제품·자원기준 유지, 자동재시험·GENOS·Git·메일 미수행**.
<!-- /MAIN115_PARASAIL_LIVE_1191 -->

<!-- PARASAIL_PRIMARY_MAIN115 -->
**2026-10-29 — 기본 공급자 Parasail 복귀·MAIN115 반영:** [반영·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-parasail-primary-main115/반영과_검증결과.txt) · [ADR1190](04_EXPERIMENTS/ADR/ADR-1190-parasail-primary-routing/README.md). 사용자 요청으로 **신규 외부 실험·로컬 서빙 기본을 Parasail FP8**로 변경했다. **MAIN115 / parasail-primary-20261029-r1**, 확정429만 Near AI FP8 1회·물리별 차감 유지. 466서빙파일 중 설정1+pin25변경, 애플리케이션 코드·데이터·모델·40/1024/1800·개별180초·출력상한없음·온톨로지기본OFF 동일. 후보41·작업41검사 및 실제 선택service59확인(HEALTH1·모의HTTP1) 통과. 초기 승격 arm 오기재 거절은 보존하고 같은 검증 결과의 올바른 arm으로 정정·승격했다. ADR1190 최종검사 통과, 전역graph 기존16오류 동일. **새모델0·속도/안정성 개선 미검증·CM007/009 재실행0·GENOS/Git/메일 미수행**. MAIN114는 롤백 보존. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`.
<!-- /PARASAIL_PRIMARY_MAIN115 -->

<!-- MAIN114_CM007_RETEST_1189 -->
**2026-10-29 — MAIN114 실제007 재시험·009 미실행:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main114-cm007-retest/7번_실제시험_결과.txt) · [ADR1189](04_EXPERIMENTS/ADR/ADR-1189-main114-cm007-conditional009/README.md). 명시적 외부 전송 승인 후 실제 선택service/MAIN114의466파일·같은65문서 권한으로007을1회 실행했다. 첫 모델8.657초 정상 뒤 서버가 두시장13조와 유가시행세칙9조를 확보했다. **두 번째 조사 판단은 HTTP200헤더 뒤58조각660바이트 공백만 수신해179.699초에 절대기한 종료·UNKNOWN/FAILED·HTTP504를 기록했다. 전체238.503초·물리2=차감2·도구26, 최종답변없음·009미실행**. 확보73/모델입력view61구간 불일치·권한위반0. 통신 프로세스 종료/회수 확인, 원격취소·두번째비용·공급자 내부 원인은 미확인. 자원중단0·최소가용RAM8.100GiB·스왑증가0MiB. **새 requirement_review/ASSESS 도달0회이므로4번 수정의 실제 효과는 미검증**.1~3번 로컬 자원 수정·기준 완화·자동재시험·모델비교·GENOS·Git·메일 미수행, MAIN114 유지. 준비 메타검사2오류와 승인검토2거절은 보존하고 각각 호출 전 정정·사용자 추가 승인으로 진행했다.
<!-- /MAIN114_CM007_RETEST_1189 -->


<!-- REQUIREMENT_COVERAGE_MAIN114 -->
**2026-10-29 — 질문 요구별 충족 검토 MAIN114 반영 완료:** [반영·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-requirement-coverage-main114/반영과_검증결과.txt) · [ADR1188](04_EXPERIMENTS/ADR/ADR-1188-requirement-coverage-review/README.md). 사용자 요청4번만 구현해 **로컬 MAIN114 / requirement-coverage-20261029-r1**에 반영했다. 기존 ASSESS에서 질문 전체 위치·기존 쟁점을 충족/제외/미해결로 검토하고 실제 주장·현재 원문·사용자 범위 인용·핵심 gap에 연결한다. 누락·가짜ID·다른 쟁점 근거·이유만 있는 제외를 거절하며 기존 보완·추가 조사·제한 답변 경로를 사용한다. 별도 모델 단계 추가0, 특정 조문 하드코딩없음. 466서빙파일·MAIN113대비37변경(제품/설정6+pin31), 후보78·작업58검사 통과, 동일211회귀189통과/기존9실패/준비오류13·새회귀0. 실제 선택service OFF/ON미설정/ON빈DB 각57·총171확인 통과(HEALTH3·모의HTTP3·새모델0). 작업 코드의 기존 저장 압축 읽기는 병합 보존했다. ADR1188 최종검사 통과, 전역 graph는 다른 ADR의16오류로 미통과다. **1~3번 로컬 자원 문제는 보류 유지, CM007/009 실제 재실행·GENOS 배포·모델비교·Git·메일 미수행**. 질문 위치의 연결 검증을 의미적 완전성 보장으로 확대하지 않는다. 데이터·모델·40/1024/1800·출력상한없음·온톨로지 기본OFF 유지. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`.
<!-- /REQUIREMENT_COVERAGE_MAIN114 -->

<!-- SOURCE_CONTRACT_MAIN113 -->
**2026-10-28 — 누적 원문·응답·기한 수정 MAIN113 반영 완료:** [반영·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261028-source-contract-main113/반영과_검증결과.txt) · [ADR1186](04_EXPERIMENTS/ADR/ADR-1186-required-source-main-integration/README.md). 사용자 요청으로1173~1184의 확정 원문 선집행·형식 보완·독립 읽기 복구·목표 종료/포함 판정·표제 기반 미선언 목표·판단/답변 일치·429 전환·절대 기한을 작업 코드와 **로컬 MAIN113 / source-contract-20261028-r1**에 통합했다. 465서빙파일·MAIN112대비58변경(제품/설정27+pin31), 별도 연구클라이언트도 작업 통합했다. 겹친2파일의 기존 저장 압축 수정은 보존했으며 저장 압축 전체 기능을 이번 릴리스에 승격한 것은 아니다. 기술308조건(동일제품307+참조보완1재검사), 최종서빙19·작업58 통과. 211회귀189통과/기존9실패/준비오류13이 MAIN112와 항목별 동일·새회귀0. 실제 선택service OFF/ON미설정/ON빈DB 각55·총165확인 통과(HEALTH3·모의HTTP3·새모델0). 초기 공급자 설정 포장 누락과 제한 환경 HEALTH 대기 중단은 보존했고 최종 묶음·일반 로컬 실행은 통과했다. 모델·데이터·40/1024/1800·출력 상한 없음·온톨로지 기본OFF 유지, 로컬 외부전송 Chutes FP8/확정429만 NearAI1회 연결. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. **007 최종답변 미완료·009 미실행은 그대로이며 이번 새 실모델0, GENOS 현장 배포·모델비교·Git·메일 미수행**. 아래 MAIN112 유지 기록은 각 실험 당시 상태다.
<!-- /SOURCE_CONTRACT_MAIN113 -->

<!-- MODEL_DEADLINE_1184 -->
**2026-10-28 — 모델 절대 기한 수정·007 재시험:** [결과 TXT](09_ARTIFACTS/AUDITS/20261028-model-absolute-deadline/수정과_7번_재시험결과.txt) · [ADR1184](04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline/README.md). 이전1179의3번째호출은원문확보후후속판단중응답미완료였으며원격원인은미확인이다. 작업별httpx timeout만있던경로에절대기한·요청수명통신프로세스종료/회수·늦은결과거절·UNKNOWN/504무재시도를서빙gateway/공통클라이언트에연결했다. 격리rev002466파일·제품4/pin31변경·기술308조건·211회귀189통과/기존9실패/준비오류13동일·새회귀0. 기록식별자/경로오류는보존·정정했다. **실제007은1호출/차감1·정상응답14.502초뒤원문조사중호스트스왑증가129.5MiB가사전128MiB기준을넘겨46.193초에종료코드125로중단**. 당시가용RAM8.197GiB로OOM단정금지. 원문57구간불일치/권한위반0·원문전달0구간. 코스닥13확보·유가13미확보·최종답변없음·009미실행. 이번실제만료호출관찰없음,만료경로는오류주입/native API검증이다. 작업제품통합·MAIN승격·GENOS·강한모델비교미수행, **MAIN112유지**.
<!-- /MODEL_DEADLINE_1184 -->


<!-- GENOS_STORAGE_20261028 -->
**2026-10-28 — GENOS 기록 중복·보관 한도 수정:** [결과](09_ARTIFACTS/AUDITS/20261028-genos-storage/결과.txt) · [반입·설정](08_DEPLOYMENT/GENOS/handoffs/storage_compact_20261028_r1/GUIDE.txt). 요청/사건 DB의 긴 본문을 내용 해시·무손실 압축으로 공유하며 판단·실패·원문 좌표·기존 논리 해시를 보존한다. 모델 입력 안에 중첩된 JSON 원문도 분해한다. GENOS runtime/state 합계 기본20GiB의 진입 제한·추가 실행 점검을 연결했으며 강제 파일시스템 quota나 과거 기록 삭제가 아니다. 압축 필드의 직접 조회는 `semantic_runtime.legal_agent.journal_storage.connect`를 사용한다. 기존 `sqlite3.connect`는 BLOB 참조만 돌려줄 수 있으므로 새 소비자는 공통 리더와 실제 권한/내용 검증을 유지한다. 새22검사 통과·기존107검사90통과/기존17실패 동일·반입37검사 통과. **선택 MAIN112 유지, 현장 GENOS 배포·Dataiku 자동 보관 이관 미수행**. 압축 쓰기만 중단할 때는 새 리더를 유지하고 `GENOS_JOURNAL_STORAGE=plain`을 설정한다.
<!-- /GENOS_STORAGE_20261028 -->

<!-- SOURCE_SCOPE_1179 -->
**2026-10-28 — 미선언 원문 목표 발견·007 재시험:** [결과 TXT](09_ARTIFACTS/AUDITS/20261028-source-scope-completion/수정과_재시험결과.txt) · [ADR1179](04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/README.md). 격리1178에서 질문과 직접 맞는 저장 표제를 서버가 목표로 등록·선집행하고, 다른 원문/설명만으로 제외하지 못하게 수정했다. 특정13조·문서명·ID 하드코딩없음. rev002465파일·293기술조건·211회귀189통과/기존9실패/준비오류13동일·새회귀0. 실제007은 최초모델뒤선택모델추가0/도구5회로 두시장13조와유가시행세칙9조를모두확보했다. 원문72/입력122불일치·권한위반0,물리3=차감3. **3번째모델호출이단계기한을넘겨도응답미완료하여제어측중단(전체기록475.648초),2응답/1결과불명·최종답변미통과·009미실행**. 확정429없어공급자전환/자동재요청0. 원격취소·미응답비용미확인. OFF설정/검사보조/기록경로실패·동시작업변경에따른추가freeze중단을보존했다. 직접표제일치범위의발견효과이며전체의미추론·최종답변·기한종료해결로확대하지않는다. 작업제품통합·MAIN승격·GENOS·강한모델비교미수행, **MAIN112유지**.
**기록 정정1182:** 1179의 단계계획이 문자열3개여서 최종 메타검사6오류가 발생한 원본은 보존했다. [ADR1182](04_EXPERIMENTS/ADR/ADR-1182-source-scope-validation-receipt/README.md)가 같은 단계·원장·465코드·실제결과를 유지한 형식 정정 영수증4조건과 최종 ADR검사를 통과했다. 새모델0. [최종 TXT](09_ARTIFACTS/AUDITS/20261028-source-scope-completion/최종결과.txt).
<!-- /SOURCE_SCOPE_1179 -->


<!-- RESPONSE_RECOVERY_1178 -->
**2026-10-28 — 응답 형식·보완·원문 조사 복구 수정:** [결과 TXT](09_ARTIFACTS/AUDITS/20261028-response-contract-recovery/수정과_재시험결과.txt) · [ADR1178](04_EXPERIMENTS/ADR/ADR-1178-source-goal-contained-original/README.md). 1176에서 분기별 오류/허용값·동일화면1회보완·가짜ID등록차단·정확조회후다른탐색재개·구체중단사유를 구현했다. 실제0018호출/146.752초는 완료조건통과,00711호출/360.868초는 두시장13조 미확보로 실패하여009미실행. 확보370/전달894구간불일치·권한위반0,물리19=차감19.1176의저장enum검사오류(COMPLETED/실제COMPLETE)는원본보존·1177정정,001재호출0.007에서상위9조전체를읽고도하위14항미확보로남는결함을1178에서추가수정했다. 최종rev002464파일·263기술검사통과·211회귀189통과/기존9실패/준비오류13동일·새회귀0. 실제원문검증기로하위4블록충족/누락/변조를검사했으며추가모델0. **최종포함판정수정뒤실모델·작업제품통합·MAIN승격·선택서비스·GENOS·더좋은모델비교미수행,MAIN112유지**.007필요문서선택·제외판단실패를해결로확대하지않는다.
<!-- /RESPONSE_RECOVERY_1178 -->

<!-- ASSESSMENT_CONSISTENCY_1175 -->
**2026-10-28 — 판단·답변 일치 수정과 001/007/009 재시험:** [최종 TXT](09_ARTIFACTS/AUDITS/20261028-assessment-scope-fix/수정과_재시험결과.txt) · [ADR1175](04_EXPERIMENTS/ADR/ADR-1175-source-goal-scope-contract/README.md). 격리1174에서 PARTIAL/INSUFFICIENT의 빈 핵심gap 거절과 미해결 답변의 결정적 조립을 구현했다. 실제0016호출/130.172초·0079호출/332.028초·0096호출/132.327초, 총21호출. 반환/저장 일치·원문262/전달459구간 불일치와 권한위반0. **007은 유가증권시장13 누락,009는 필요한13/31 미확보로 답변 완성 실패**다.009에서 coordinate_scope=조를 허용한 서버 결함을1175에 추가 수정, 최종rev002464파일·177기술검사 통과·추가모델0. 이전 실모델을 최종scope수정본의 실모델 통과로 확대하지 않는다. 작업 제품통합·MAIN승격·GENOS현장·더좋은모델비교·Git·메일 미수행, **MAIN112 유지**.1174final메타검증의p95/검증로그hash실패는원본보존·1175정정영수증으로구분한다.
<!-- /ASSESSMENT_CONSISTENCY_1175 -->

<!-- REQUIRED_SOURCE_1173 -->
**2026-10-28 — 확정 원문 선집행 후보 구현·실행:** [결과 TXT](09_ARTIFACTS/AUDITS/20261028-required-source-execution/구현과_검증결과.txt) · [ADR1173](04_EXPERIMENTS/ADR/ADR-1173-required-source-server-execution/README.md). 격리 rev012에 확정 목표의 모델 선택 전 집행·판단 보완 분리·목표 종료 계약·문서/목표 번호 결속·서빙 gateway의 요청당 확정429 1회 전환을 구현했다. 기술130검사 통과, 동일71회귀54통과/17기존실패·새회귀0. 저장001/007 재생은 세칙23/상장규정13 원문을 추가 선택모델0회로 확보·재개 검증했다. 실제001은 Chutes8호출·161.844초·HTTP200/READY·주장1·저장완료지만 LIMITED_ANSWER/PARTIAL과 단정적 답변의 불일치로 내용 게이트 실패다. 이번 새 실행은26조만 목표로 선언했으므로 세칙23 선집행이 발동했다고 확대하지 않는다. 원문34/전달60구간 불일치0·권한위반0·물리8=차감8. **007/009·작업 제품 통합·MAIN 승격·선택서비스 재검증은 미실행, MAIN112 유지**. 실제 Near AI·GENOS 현장·더 좋은 모델 비교·메일·Git 미수행. 과거 실패와 중간 검증 실패를 보존한다.
<!-- /REQUIRED_SOURCE_1173 -->

<!-- MAIN104_SQL_FOLLOWUP -->
**2026-10-27 — MAIN105 반영·실제 서비스 확인 완료:** [전체 반영·실제 실행·온톨로지 후속](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md). 최초211초 원인의 MAIN104 SQL 수정에 반복 원문 확인 재사용과 네 연결 TEMP VIEW의 ID 점조회를 더했다. 보관응답1회 재생의 동일 계측35화면736.500→93.718초(87.275% 감소), 원문·행동·최종 답변 동일, 새 모델 호출0회다. 신규237조건·관측보조1,345조건을 구분한 ADR1081 검증 후 MAIN105 `navigation-validation-20261027-r1`을 선택했고 실제 서비스19확인(HEALTH·모의 HTTP1회·새 모델0회)이 통과했다. 작업 코드 통합에서 새4검사 통과, 기존7실패는 변경 전후 동일하다. 온톨로지는1074 부분실패→1077 상태 전환 수리→MAIN105 결합1079 실모델1셀/10호출을 완료했다. 두 원문의 판단 보존을 확인했지만 근거 연결 보완1회·제한 답변으로 품질 효과는 미인증이다. MAIN105 최종 누적본433파일·첨부4개를 삼성메일 SENT `1a17ae4c6976a0f7`로 발송·확인했다. 설치144명령·SQL18·상태13쌍을 통과했으며 MAIN104 첨부를 대체한다. P0~P4 전체 구현·전체 응답시간 개선·법률 품질·온톨로지 MAIN·GENOS 현장 배포 완료로 확대하지 않는다. 아래 이전 상태 기록과 구분한다.
**추가 실제 질문1082:** 같은 질문·데이터·프로필의 MAIN105 새 실행31호출에서 모델 밖166.596초·30화면80.792초를 관찰했으나, 제공자 문맥 한도400으로 최종 답변 전에 실패했다. 실제 출력상한 필드0개, 원문79단위 불일치·권한 위반0이며 전체 응답시간 개선율로 사용하지 않는다. [관찰·중단 원인](04_EXPERIMENTS/ADR/ADR-1082-main105-live-latency/artifacts/run-001/COMPARISON.md).
<!-- /MAIN104_SQL_FOLLOWUP -->

**2026-10-27 — 211초 원인·최적화 확인:** [상세 측정과 결과](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NAVIGATION_211S_ROOT_CAUSE_20261027.md). 정의 연결 조회의 전체 참조 VIEW 조립과 권한 ID 목록 반복이 원인이었다. 동일 계측의8개 대응 구간236.744→19.891초(91.598% 감소), 원래 화면·행동·전달 원문8/8 일치, 신규 모델 호출0회. 당시 SQL 두 수정은 작업 코드에 통합했고 선택 MAIN103·GENOS 배포는 유지했다. 이후 MAIN 반영 상태는 문서 상단 최신 기록을 따른다. 초기 준비·전체 응답시간·온톨로지 품질·GENOS 속도와 구분한다. 아래2026-10-26 상태는 선행 단계 기록이다.

**2026-10-26 성능 구현·실험 상태:** [상세 결과](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NON_MODEL_LATENCY_IMPLEMENTATION_RESULT_20261026.md) · [전체 계획](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NON_MODEL_LATENCY_OPTIMIZATION_PLAN_20261026.md). 격리 후보에 P0 계측·P1 일부와 온톨로지 재표시 오류 수정을 구현했다. 반복 스키마 검사96.17% 감소는 국소 비교이며 전체 서비스 개선율이 아니다. 초기 준비17.605초의98.266%를 이름 있는 구간에 귀속했고 연결 매칭·구조 결속10.676초가 가장 컸다. 실모델1회는 불완전 출력/연속 공백으로 중단, 온톨로지 효과와 전체 최적화는 미확인이다. P2/P3/P4·기본 작업 코드 통합·MAIN103·GENOS 반영은 미완료다. 과거 실험과 실패는 보존한다.

**MAIN = 용어집 구축·갱신을 공통 기반으로, Document Ingestion(데이터 입력 → 구조화) → 문서–용어 연결 → 용어·정의·명시 참조 색인 → 용어 기반 RAG → 피드백 루프**다.
전체 단계의 책임·계약·현재 연결 상태는 [ARCHITECTURE.md](00_SYSTEM/ARCHITECTURE.md)의 MAIN 정의를 따른다. 로컬 RAG 릴리스와 그 활성 포인터는 MAIN의 서빙 부분이며 전체 MAIN을 대신하지 않는다.
목표는 **재현 가능한 전체 파이프라인에서 실험을 분기하고, 검증한 결과를 MAIN에 반영하는 것**이다. 최종 서빙 환경은 망분리 GENOS다.

## 전체 인프라 기준 — 사용자 확인 2026-10-16

- **사용자 정정(2026-11-02, 개발계부터 Gold 구조 적용): 운영계 SQL 데이터는 최종 Gold로 이관하므로, 개발계 적재부터 확정 Gold R19의 13테이블·60컬럼 계약에 맞춘다.** 기준은 [R19 최종 통합 정의서 안내](07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_TABLE_APPLICATION_20261030_R19/골드테이블_R19_반영사항과_사용안내.txt)와 `mapping_r18_registration.json`이다. 개발계의 접근 가능한 스키마·환경별 물리명과 데이터 구조를 구분하며, 개발용 Silver 위치를 이유로 별도 컬럼/타입/키/게시 구조로 적재한 뒤 운영에서 다시 재구조화하는 경로를 목표로 삼지 않는다. 원문·검색·승인 온톨로지·벡터의 적재와 조회를 같은 Gold 계약에 연결하고, 질의·판단·로그와 승인 전 작업/파일 보관은 해당 책임 영역에 유지한다. 현재 R11의 개발용9표·46컬럼 및 R12의 벡터2표 전달본은 이 요구를 반영한 완료본이 아니다. 기존 적재·재개 영수증을 보존하고 대상 계약·판본·내용을 대조해 재사용 가능 범위를 정한다. 이 정정은 요구사항 반영이며 현장 DDL 변경·재적재·Gold 전환 완료를 뜻하지 않는다. 아래 10월27일 물리 배치 기록은 당시 상태로 보존한다.

- 사용자 후속 정정(2026-10-27): **GENOS는 계산 리소스이며 작업·재시도·진행·로그·결과 저장은 Dataiku가 관리**한다. 취소는 Dataiku에서 요청하고 GENOS의 현재 프로세스 종료를 확인한다. GENOS→S3 직접 접속을 전제로 만들지 않는다. 비동기 HTTP로 입력/진행/결과를 주고받고 Dataiku가 S3에 적재한다. 취소·전송에 필요한 임시 핸들과 파일은 계산 수명에 한정하며 영속 GENOS job registry/지난 작업 로그 조사·ACK 해제 운영을 새 구조에 넣지 않는다. [수정본·설치·취소](08_DEPLOYMENT/DATAIKU/pipeline_stateless_20261027_r1/GUIDE.txt). 로컬 검증과 실제 리비전 배포는 구분한다.

- 사용자 후속(2026-10-27): 원문 파이프라인은 **Dataiku Python 레시피 Flow**로 구성하고, 구조화는 이미 만든 GENOS `legal_pipeline_serving`을 사용한다. 업로드 폴더는 `LEGAL_RAG/ehA8dpVm`, 연결 주소·토큰은 프로젝트 변수에 설정되어 있다. [레시피 설치·원문 위치·연결 확인](08_DEPLOYMENT/DATAIKU/pipeline_recipes_20261027_r1/GUIDE.txt). 신규 전달본은 S3 원문 압축 해제 보관 → 기존 GENOS 처리 → S3 반환 결과 → 실버 적재를 분리한다. 로컬 SDK/모의 원문/Oracle 검증과 현장 Flow 설치·실제 접속은 별도다. 사진의 관리 화면 URL을 API 호출 URL로 추정하지 않는다.

- 사용자 정정(2026-10-27, 개발계): 실버 레이어는 **`SIDDS` 스키마 / 테이블 접미사 `_S`**, 에이전트 레이어는 **`SIDDA` 스키마 / 접미사 `_A`**다. 개발계 GENOS의 Dataiku 지식 조회는 실버만 접근 가능하므로 조회할 원문·구조화·검색·게시 데이터를 `SIDDS.*_S`에 둔다. 온톨로지·숏컷·에이전트 기록은 `SIDDA.*_A`에 둔다. S3 작업 JSON 보관·검토 절차와 운영 골드 승인 절차는 별도다. 이전 `AIDP/SIDDA=dev_silver` 표시는 잘못된 개발계 물리 매핑이며 과거 기록으로 보존한다. 연결 이름 `AIDP`와 owner를 구분한다. [새 적재 SQL·실행 안내](08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1/GUIDE.txt). SIDDA의 온톨로지·숏컷 소비자 접근과 GENOS 조회 매핑 전환은 실제 배선을 확인하며 문서·적재 완료만으로 연결 완료라 하지 않는다.

- 사용자 → GENOS 채팅 앱 → GENOS 백엔드 에이전트 → Oracle 조회 기반 RAG → 채팅 응답이다.
- 데이터플랫폼의 Dataiku에 연결된 Oracle RDB 테이블에 법령·용어 등의 지식그래프와 온톨로지를 그래프 형태로 저장한다.
- 사용자 명시(2026-10-22): Dataiku의 **에이전트 레이어**에는 LLM 질의·에이전트 판단·실행 로그를 저장하고, **골드 레이어**에는 구조화 데이터·온톨로지·LLM Wiki(`llm_wiki`)를 저장한다. 향후 데이터·DB 설계와 구현은 이 저장 책임 구분을 따른다. 상세 기준은 [Dataiku 데이터 레이어](00_SYSTEM/ARCHITECTURE.md#dataiku-data-layers)다.
- 사용자 제공(2026-10-22, 사진 4장): 골드 테이블·컬럼 설계는 [골드 레이어 스키마·메타데이터 규약](00_SYSTEM/ARCHITECTURE.md#dataiku-gold-schema-convention)을 따른다. 메타마이너 표준용어·도메인·인포타입, 논리명·물리명, `NVARCHAR`→`VARCHAR` 및 해당 ADB의 한글 길이 규약, 테이블·컬럼 Description 항목, 운영 골드의 메타 등록·DBA 생성 신청을 설계에 반영한다. 규약 기록과 실제 DDL·등록·현장 적용 완료는 구분한다.
- 사용자 추가 제공(2026-10-22, 가이드 사진 9장+7장): [메타마이너 명명·신청 절차와 원본 사진](07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/README.md)을 함께 따른다. 표준단어·동의어·금칙어와 `수식어 + 도메인` 구성, 물리명·용어명 30바이트 규약, 유형별 용어·ID 예외·표준도메인·코드값 규칙, 업무별 표준사전과 미등록 표준의 신청·승인 절차를 확인한다. 원본은 골드 안내4장·가이드9장·후속7장 총20장을 구분해 보관하며, 가이드 내 표기 불일치는 임의 확정하지 않는다.
- 사용자 추가 제공(2026-10-22, 엑셀 화면 사진 7장): 골드 스키마 설계·변경 시 [테이블 목록·Bizmeta·등록 대상·컬럼 정의 작성 기준과 이미지](07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/TABLE_SCHEMA_WORKBOOK.md)를 함께 따른다. 에이전트번호·스키마·테이블명·골드 후보, 데이터논리명·출처·유형·가공 과정·생성시각, 등록 대상/추가 검토/제외 요청, 컬럼 순번·물리명·논리명·타입과 표준 매핑을 작성한다. 후보·신청·승인·생성을 구분하며 사진의 예시 테이블·타입 대조를 확정 DDL로 사용하지 않는다. 기존20장과 추가7장 총27장의 원본을 묶음별로 보존한다.
- 사용자 명시(2026-10-24): 온톨로지 작업 단위(개념 묶음·LLM 제안 스키마)는 **JSON으로 Dataiku S3 관리 폴더**에 둔다. 에이전트 레이어는 사용자 로그·LLM 판단, 골드는 사람이 승인·신청한 뒤 SQL로 적재된 온톨로지다. 승인한 **용어·별칭도 같은 절차로 골드**에 들어간 뒤부터 쓴다(용어집은 온톨로지와 별개인 바꿔 넣기 도구, [랜딩](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/LANDING.md)). 승인만으로는 쓰이지 않는다. 상세는 [온톨로지 v4 저장 위치](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/CONTROLLED_KNOWLEDGE.md#저장-위치).
- 사용자 명시(2026-10-22): 재사용 지식의 **일차 저장 단위는 질문이 아니라 원문**이다. 질문을 통해 발견한 개념·검토 사항·연결 근거를 원문의 문서 판본·조항·span에 연결한다. 질문은 발견 이력과 조회 입력으로 보존한다. 다른 질문으로 같은 원문·개념에 도달해도 해당 검토 사항과 연결 근거를 사용할 수 있어야 하며, 질문별 답변 묶음을 원문 중심 온톨로지로 설명하지 않는다.
- 사용자 명시(2026-10-19): GENOS 코드서빙 쪽에는 데이터를 저장하지 않는다. 원문·색인 전체를 내려받아 로컬 SQLite/파일/영속 볼륨에 복원하는 방식을 목표 구조로 안내하지 않는다. 서빙은 필요한 데이터만 Oracle/조회 API에서 받아 요청 처리 중 일시적으로 사용한다. 캐시는 우선 DB 내부에서 관리하고, 별도 공유 결과 캐시가 필요하면 서빙 밖의 데이터 계층에서 버전·권한 범위를 관리한다. 현재 `oracle_dp`의 전체 로컬 복원 경로는 이 조건에 미준수이며, 문서 정정만으로 런타임 전환이 완료된 것으로 보고하지 않는다.
- 외규는 Dataiku의 매일 배치가 API 중계서버를 통해 법제처의 신규·갱신 자료를 확인·수집하고, 구조적 파싱·VLM 파싱 → 구조 분해 → 색인 → 지식그래프 적재·갱신으로 연결한다.
- 사용자 정정(2026-10-27): 법제처 수집 호출은 **Dataiku 배치 → API 중계서버 → 법제처**로 계획한다. GENOS를 수집 호출 주체나 중간 실행 단계로 넣지 않는다. 10월23일의 GENOS 수집 코드서빙 계획·진단 자료는 과거 기록으로 보존한다. 이번 정정은 계획·인계 문서 기준이며 배치 구현·현장 실행 완료를 뜻하지 않는다.
- 내규는 현업의 데이터 포탈 업로드 → Dataiku 연결·수집 → 구조적 파싱·색인 → 지식그래프 적재로 연결한다.
- 상세 기준은 [전체 인프라](00_SYSTEM/ARCHITECTURE.md#전체-인프라--사용자-확인-2026-10-16)다. 로컬 SQLite·NFS 세대 및 반입 기록과 구분하며, 사용자 확인 아키텍처를 코드 연동·현장 배포 검증 완료로 바꾸어 보고하지 않는다.

## 신규 외부 실험 모델

2026-09-30 사용자 변경에 따라 ADR-0583 이후 신규 외부 실험의 기본값은
**Qwen3.8 / qwen/qwen3.8-27b**다. 2026-10-28 Chutes FP8 전환 후, **2026-10-29 사용자 요청으로 현재 기본 공급자를 Parasail FP8로 변경했다(ADR1190)**. 확정 HTTP429에만 **Near AI FP8로 클라이언트 수명 동안 한 번** 전환하며 두 요청 모두 기존 물리 호출 예산에 센다. 모델 fallback·동일 공급자 자동 재시도는 없고, 응답 불명·다른 HTTP 오류·형식 오류에는 전환하지 않는다. reasoning effort none·출력 상한 없음은 유지한다. 모델 정본은 `00_SYSTEM/EXPERIMENT_MODEL_POLICY.json`, 공급자 추가 설정은 `00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json`, 공통 호출은 `lawrag.research.experiment_client.ExperimentClient`다. 공급자 설정이 없는 과거 환경은 Parasail 단독이다. **ADR1172 당시 MAIN112의 내장 전송기는 변경 대상이 아니었다. MAIN113부터 ADR1186의 공급자 정책을 로컬 외부 서빙에도 연결했고, 현재 MAIN116은 ADR1190의 Parasail 우선 정책을 그대로 사용한다. GENOS 내부 전송의 현장 변경은 미수행이다.** [ADR1172 검증과 범위](04_EXPERIMENTS/ADR/ADR-1172-qwen38-provider-switch/README.md). 이전 Gemma 기본 정책과
완료된 기록은 역사적 정본으로 보존한다.

<!-- CURRENT_LOCAL_RAG_RELEASE -->

**2026-10-29 — 최종 답변 누적 수정 MAIN116 반영:** [반영·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-final-answer-main116/반영과_검증결과.txt) · [ADR1194](04_EXPERIMENTS/ADR/ADR-1194-final-answer-main-integration/README.md). 사용자 요청으로 **MAIN116 / final-answer-20261029-r1**을 선택했다. MAIN115 누적 원문·응답·요구검토·공급자·기한 수정을 유지하고1192 최종 ASSESS/보완 프롬프트2곳과 서버 일반 미확인 문구 제거를 통합했다. material gap·최종 검토 미완료 경고·stop_reason·UNKNOWN 기록 보존. 466서빙파일 중 제품3+pin31변경, 후보 고유130·작업130계약 통과. 211회귀189통과/기존9실패/준비오류13 동일·새회귀0. 저장0072392→2344자로 일반 문구48자만 제거, 주장·원문·조건·중단 이력 동일. 실제 선택service OFF/ON미설정/ON빈DB 총195확인·HEALTH3·모의HTTP3 통과. 초기 검사 준비 오류는 원본 보존 후 동일제품으로 정정 검증했다. 작업의 저장압축 읽기와 다른432파일 보존. ADR최종검사통과·전역graph기존16오류동일. **새모델0·감독공백/UNKNOWN 미해결·007전체미통과/009미실행 기록 유지·GENOS/Git/메일 미수행**. 모델·데이터·예산·출력상한없음·온톨로지기본OFF 동일. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. MAIN115 롤백 보존.

직전 MAIN115 단계의 보존 기록:

2026-10-29 사용자 요청으로 **로컬 RAG MAIN115 / workflow1.20.8** `parasail-primary-20261029-r1`을 선택했다. MAIN114의 모든 애플리케이션 코드·데이터를 유지하고 기본 공급자만 **Parasail FP8**로 변경했다. 확정429만 Near AI FP8 1회 전환·물리별 차감 유지. 466파일·설정1+pin25변경, 후보41·작업41검사·실제 선택service59확인 통과(HEALTH1·모의HTTP1·새모델0). 속도·안정성 개선 및 CM007/009 성공은 미검증이다. 모델·예산·개별180초·출력상한없음·온톨로지기본OFF 유지. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. [반영·검증·롤백](09_ARTIFACTS/AUDITS/20261029-parasail-primary-main115/반영과_검증결과.txt). 직전 MAIN114 릴리스 보존.

후속 실제 시험1191에서 Parasail 공유풀429→NearAI11응답으로007 최종 답변·저장은 완료했으나, 내용 범위 누락/제한 문구 불일치로 내용미통과·009미실행이다. 제품 수정은 하지 않았다. [실제 결과](09_ARTIFACTS/AUDITS/20261029-main115-parasail-test/실험결과.txt).

직전 MAIN114 단계의 보존 기록:

2026-10-29 사용자 요청4번을 구현해 **로컬 RAG MAIN114 / workflow1.20.8** `requirement-coverage-20261029-r1`을 선택했다. 기존 ASSESS에 질문 전체와 쟁점별 충족·제외·미해결 검토를 추가하고, 실제 주장·원문·사용자 범위·핵심 gap과의 연결을 서버가 검증한다. 기존 보완·추가 조사·제한 답변을 사용하며 별도 모델 단계 추가0이다. 466서빙파일·MAIN113대비37변경(제품/설정6+pin31), 후보78·작업58검사 통과. 동일211회귀189통과/기존9실패/준비오류13·새회귀0, 실제 선택service OFF/ON미설정/ON빈DB 각57·총171확인·모의HTTP3 통과·새모델0. 데이터·모델·40/1024/1800·출력상한없음·온톨로지 기본OFF 유지. 온톨로지 선택만으로 검토를 우회하지 않도록 기존 ASSESS를 거치며 실제 모델 비용·속도 영향은 미측정이다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. **1~3번 로컬 자원 문제 보류·의미 품질 미인증·GENOS 배포 미수행**. 후속 ADR1189의 실제007은 두13조 확보 뒤 두번째 모델 절대기한으로504 종료했고009는 미실행이다. 새 요구 검토 단계에는 도달하지 못했다. 이전 MAIN113 릴리스는 롤백용으로 보존했다. [반영·검증·재시작·롤백](09_ARTIFACTS/AUDITS/20261029-requirement-coverage-main114/반영과_검증결과.txt), [완료 영수증](09_ARTIFACTS/AUDITS/20261029-requirement-coverage-main114/completion.json).

직전 MAIN113 단계의 보존 기록:

2026-10-28 사용자 요청으로 **로컬 RAG MAIN113 / workflow1.20.8** `source-contract-20261028-r1`을 선택했다. 누적 원문 선집행·응답 복구·목표/판단 계약·공급자429전환·절대기한을 작업 코드에 통합하고, 검증한465서빙파일을 공식 승격했다. MAIN112 대비58파일 변경, 기술308·최종서빙19·작업58조건 통과, 211회귀 항목별 동일·새회귀0. 실제 선택service OFF/ON미설정/ON빈DB 각55·총165확인과 모의HTTP3 통과·새모델0. 데이터·모델·온톨로지/초기벡터·출력상한없음·40/1024/1800예산 유지. 로컬 외부 전송은 Chutes FP8, 확정429에만 Near AI FP8 1회이며 두 요청 모두 차감한다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. **007/009 의미 품질 미인증·GENOS 현장 배포 미수행**. 이전 MAIN112는 롤백용으로 보존했다. [반영·검증·재시작·롤백](09_ARTIFACTS/AUDITS/20261028-source-contract-main113/반영과_검증결과.txt), [완료 영수증](09_ARTIFACTS/AUDITS/20261028-source-contract-main113/completion.json).

직전 MAIN112 단계의 보존 기록:

2026-10-28 사용자 요청으로 **로컬 RAG MAIN112 / workflow1.20.8** `vector-initial-20261028-r1`을 선택했다. 최신 MAIN111 보존, Oracle 초기 벡터 검색→기존 원문 조사 연결과 Dataiku `LEGAL_04_VECTOR_INITIAL_R1` 적재/재개/READY 게시를 추가했다. 458서빙파일·43변경, ADR1165 기술44조건+동일서빙4재검사+전달TXT8 통과. 기존110검사109통과1실패 전후동일·새회귀0. 실제선택service OFF/ON/빈DB 각45·총135확인·모의HTTP3,새모델0. ADR1164 READ법령상태누락 실패·기존graph9오류 보존. 온톨로지기본OFF·데이터·모델·40/1024/1800·출력상한없음 유지. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. 벡터는 Oracle 요청 경로에 연결하며 로컬SQLite 전체가 자동벡터화된 것은 아니다. **현장 GENOS 배포·실제임베딩·전체데이터 적재·1초/법률품질 미인증**. 삼성메일 SENT `1a18027f90e18fe5`에 ZIP+실행TXT2+GUIDE4첨부,수신처/크기/MIME 재확인. [반영·검증·사용·롤백](09_ARTIFACTS/AUDITS/20261028-vector-initial-main112/반영과_실행안내.txt) · [전달안내](08_DEPLOYMENT/GENOS/handoffs/vector_initial_20261028_r1/GUIDE.txt).


2026-10-28 사용자 지시에 따라 **로컬 RAG MAIN111 / workflow1.20.8**을 선택했다. 릴리스 `ontology-workflow-20261028-r1`, 정본 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`. MAIN110의 SQL·최소입력·고정번호·독립 원문조사 복구·365자 복수선택 지침을 유지하고, 누락된 bundle 스키마를 서빙 목록에 복원했다. **에이전트 판단 수집 → Dataiku 작업 JSON → 기존 화면 생성·검토·승인 → DB 게시 → 원문 도착 시 RAG 조회**의 공통 구현을 연결했다. 개발계 온톨로지 테이블은 `SIDDA.LGL_ONT_{WORK,EVT,PUB,HEAD,ANC}_A` 5개이며 원문은 `SIDDS.*_S`에서 검증한다. 승인만으로 노출하지 않고, 사전 조립본·원문 좌표·활성 포인터·감사 기록을 함께 게시한다. **ON/OFF 유지·기본 OFF·온톨로지 데이터 미포함**, ON+미설정/빈DB는 기존 RAG다. 최종 ADR1160 기술254조건(244테스트+실제 로컬 Oracle10)을 통과했고 검증·선택 서빙453파일이 일치한다. MAIN110 대비50파일을 선택 통합하고 기존 화면·CLI·Dataiku 레시피를 작업 코드에 연결했다. 실제 선택service OFF/ON미설정/ON빈DB 각42·총126확인, 모의HTTP3·새모델0. 이전1156~1159 실패·최종화 목록 보완·기존graph9오류를 보존했다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. 데이터·모델·출력상한 없음·40/1024/1800예산 유지. **현장 Dataiku S3/Flow·에이전트 이벤트 입력 배선·SIDDA 접근 권한·GENOS 생성 모델·리비전 배포는 미확인**이며 법률 품질·속도 개선 인증이 아니다. Git commit/push·메일 미수행. [최신 MVP·테이블·설치 범위](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/WORKFLOW_CONNECTED_20261028.md) · [결과·설정·롤백](09_ARTIFACTS/AUDITS/20261028-ontology-workflow-main/결과.txt).

직전 MAIN110 단계의 보존 기록:

2026-10-28 사용자 지시에 따라 **로컬 RAG MAIN110 / workflow1.20.8**을 선택했다. 릴리스 `ontology-selection-20261028-r1`, 정본 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`. 최신 MAIN109의 SQL·최소입력·고정번호·독립 원문조사 복구를 유지하고 온톨로지 선택 지침 한 곳만 374→365자로 교체했다. 일반 성립·적용 요건에서 성립과 제외·예외 경로를 함께 선택하도록 안내하며 두 개를 서버가 강제하지 않는다. **ON/OFF 유지·기본 OFF·온톨로지 데이터 미포함**, ON+빈 데이터는 기존 RAG다. 제품1+종속pin31 변경, 작업·검증·선택440파일 일치. 기술226조건(1152의216+1153 재실행10)을1154가 동일 코드로 상속하고 영수증12조건을 확인했다. 실제 선택service OFF/ON빈데이터 각37·총74확인, 모의HTTP2·새모델0. 앞선1150의 알려진8질문11반복11/11은 인샘플이며 이번 기술승격을 새 법률 품질 인증으로 확대하지 않는다. 1152 검사 경로 실패·1153 영수증 누락과 기존graph9오류를 보존했다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. 데이터·모델·출력상한 없음·40/1024/1800예산 유지. GENOS 현장·데이터 게시·Git commit/push·메일 미수행. [반영·설정·검증·롤백](09_ARTIFACTS/AUDITS/20261028-ontology-selection-main110/반영과_사용방법.txt).

직전 선택 단계의 보존 기록:

2026-10-27 사용자 지시에 따라 **로컬 RAG MAIN109 / workflow1.20.8**을 선택했다. 릴리스 `source-recovery-20261027-r1`, 정본 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`. 본문/부칙 조항 혼동과 최종판단 오류 뒤 독립 원문조사가 막히던 경로를 수정하고, 법령명 전용 조회·검증기 재사용·원문 배치/길이 계산·검색 재사용·현재20개 상세준비·고정번호·새판단/수정분리·구체오류·독립읽기 복구를 통합했다. MAIN107 모드와 MAIN108 온톨로지 프레임워크(기본OFF·데이터미이행)를 보존했다. ADR1146 동일440서빙파일·56변경(제품/설정25+pin31), 기술검사 실행647회(일부묶음중복), 기존236검사151통과85실패는 MAIN108과 동일·신규회귀0. 실제service의 OFF/ON빈데이터 각36확인 통과(모의HTTP2·외부모델0). ADR1149 실제 선택서비스 공개질문1회/새모델8호출에서 본문제2조 원문→실제C1→USE/C1→최종답변 HTTP200/READY·저장COMPLETED를 확인했다. 원문비교56·전달본문23회 불일치0,권한/번호위반0,출력상한필드0. 내부상태는LIMITED_ANSWER/PARTIAL이며 충분성설명과상태의불일치는 남는다. 실제475.223초에는 실험대기408.410초·모델29.952초가 포함된다. 용어집만제외 비LLM442.756초, 실험대기도별도제외하면34.346초(초기앱준비2.849초별도); **1초미달·품질미인증**. 실패1138/1140/1141/1142/1143/1144/1147을 보존하고 자연실행에서 오류복구가 발동했다고 확대하지 않는다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`;모델·원문·40/1024/1800예산·출력상한없음 유지. GENOS현장·온톨로지데이터게시·Git commit/push·메일 미수행. [반영·실제실행·한계](09_ARTIFACTS/AUDITS/20261027-source-recovery-main109/반영과_실제실행_결과.txt).

직전 MAIN108 단계의 보존 기록:

2026-10-27 사용자 지시에 따라 **로컬 RAG MAIN108 / workflow1.20.8**을 선택했다. 릴리스 `ontology-framework-20261027-r1`. 온톨로지 사전 시나리오 조립·원문 결속·복수 선택·충분성/재선택·기존 탐색 복귀의 공통 코드만 반영하고 **데이터는 미이행, 기본 OFF**다. `GENOS_RAG_ONTOLOGY_ENABLED=on/off` 설정 후 프로세스를 재시작한다. ON이어도 연결된 데이터가 없으면 일반 RAG로 동작한다. ADR1139의 총216기술 계약 통과, 기존236검사151통과·85실패는 MAIN107과 항목별 동일하여 새 회귀0.437서빙파일·46변경을 공식 승격으로 결속했다. 실제 선택 서비스의 OFF/ON-빈데이터 각34개, 총68확인과 모의 HTTP2회가 통과했다(실제 모델0회).1136 실행기 오류·1137 제한 환경의 TestClient 대기는 보존했다.1135의 선택 누락/충분성 판단 실패는 남으며 법률 품질 인증이 아니다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. 기존 원문·색인·모델·출력상한 없음·40/1024/1800예산 유지. GENOS 현장·온톨로지 데이터 게시·Git commit/push·메일은 미수행. [설정·범위·검증](09_ARTIFACTS/AUDITS/20261027-ontology-framework-main108/사용과_반영결과.txt).

직전 선택의 보존 기록:


2026-10-27 사용자 지시에 따라 **로컬 RAG MAIN107 / workflow1.20.8**을 선택했다. 릴리스 `genos-mode-20261027-r1`, 정본 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`. GENOS 드롭다운 `applied_fields.mode`의 **전체 법령·내규·외규·대사**를 기존 검색/대사 경로에 연결했다. 전체 법령은 허용된 전체 분류를 검색하고, 문서 필터·권한을 보존한다. 같은 대화의 내규→외규→전체 범위를 명령 검증 전 결속하고 후속 검색을 갱신한다. 실패1108·검사 기대값 오류1109를 보존한 ADR1111 신규51계약 통과, 기존145검사66통과79실패는 MAIN106과 동일하여 신규 회귀0. 제품7파일·pin31파일을 변경한429서빙파일과 실제 service28확인(HEALTH·모의 HTTP1·실제 모델0)을 통과했다. 데이터·모델·프로필·출력상한 없음·40/1024/1800예산은 유지한다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. **GENOS 현장 리비전·화면 저장·실제 플랫폼 입력은 미확인**, Git commit/push·메일 미수행. [화면 설정과 검증](09_ARTIFACTS/AUDITS/20261027-genos-mode-main107/GENOS_화면설정.txt), [선택 서비스](09_ARTIFACTS/AUDITS/20261027-genos-mode-main107/consumer-active.json).

직전 MAIN106 단계의 보존 기록:

2026-10-27 사용자 지시에 따라 **로컬 RAG MAIN106 / workflow1.20.8**을 선택했다. 릴리스 `compact-input-20261027-r1`, 정본 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`. 공통 최소입력·읽기 후보20개 페이지·요청 원장 SQL배치를 반영했다. 완료1086rev004 제품을 신규272기계조건·관측127검사(ADR1090)와 공식429서빙파일 결속(ADR1092)으로 검증했고 실제 service 진입점20확인(HEALTH·모의 HTTP1회·새 모델0회)을 통과했다. MAIN105대비65파일 차이에 기존 작업 코드의 판단·연결범위·구조/별표 기능을 명시적으로 포함했으며 작업 코드를 통째로 덮어쓰지 않았다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. 데이터·모델·출력상한 없음·40호출/1024도구/1800초 예산은 유지한다. 앞선1086 실모델은9호출·191.593초·제한답변: 모델 밖82.254초에서 첫화면32.281초를 뺀49.973초는 자원준비18.054·후속화면8.988·기타미계측22.930초다. 판단번호-원문 연결 오류를 보완1회 후에도 반복해 추가조사 행동0회로 끝났으며 토큰 오류는 없었다. 판단품질·전체속도 개선 인증과 구분한다. 온톨로지1088/1091 결합·GENOS 현장·새 메일·Git commit/push는 미수행. [확인·진단 TXT](09_ARTIFACTS/AUDITS/20261027-compact-main106/반영과_시간_답변실패.txt), [선택 영수증](09_ARTIFACTS/AUDITS/20261027-compact-main106/completion.json).

직전 MAIN105 단계의 보존 기록:

2026-10-27 사용자 지시에 따라 **로컬 RAG MAIN105 / workflow1.20.8**을 선택했다. 릴리스 `navigation-validation-20261027-r1`, 정본 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`. MAIN104의420파일 중 반복 원문 검증 재사용·네 연결 권한 VIEW 점조회의 제품3파일과pin31파일만 변경하고 기존 정의 조회 수정을 유지했다. 신규237조건·관측보조1,345조건, 원래38응답/35화면/최종답변 동등성, 실제 선택 서비스19확인(HEALTH·모의 HTTP1회·새 모델0회)을 통과했다. 보관응답1회 재생의 동일35화면736.500→93.718초(87.275% 감소), 모델호출0이며 전체 서비스 개선율이 아니다. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. 데이터·검색·모델·출력상한 없음·40호출/1024도구/1800초 예산 동일. 작업 코드의 기존directory/별표 기능을 보존해3hunk 통합했고100검사통과·기존7실패 동일이다. 온톨로지 MVP는 별도1079 후보이며 MAIN 기능 전체에 포함하지 않았다. 반영 후1079 실모델1셀/10호출에서 상태 전환 수리는 확인했지만 제한 답변으로 품질 효과는 미인증이다. MAIN105 누적본433파일·첨부4개를 삼성메일 SENT `1a17ae4c6976a0f7`로 발송·확인했고 MAIN104 첨부를 대체한다. GENOS 현장 배포·Git commit/push 미수행. [승격·실행·인계·남은 상태](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MAIN_SQL_AND_ONTOLOGY_FOLLOWUP_20261027.md). 과거 실행·실패·MAIN103/104·인계본은 보존한다.
<!-- /CURRENT_LOCAL_RAG_RELEASE -->

2026-10-23 사용자 지시에 따라 로컬 MAIN과 **신규 외부 실험의 출력 토큰 상한은 없다**. 현행 정책의 `max_output_tokens=null`을 유지하고, 새 실험 동결 시 과거 `6400`/`12800` 상한을 다시 지정하지 않는다. 공통 클라이언트는 현행 정책에서 호출자가 넘긴 출력 상한도 실제 요청에서 제거한다. 총 호출·도구·시간 예산과 불완전 출력 검증은 유지하며 모델 서버 자체 한도는 별도다. 완료된 과거 실험의 동결 정책·요청·결과는 재현을 위해 변경하지 않는다.

### 이전 정책 기록

2026-09-23 사용자 지시에 따라 ADR-0538~0581 신규 외부 실험의 기본값은 **Gemma / google/gemma-4-31b-it**였다.
ADR-0582는 예약 후 사용자 변경으로 실제 공개 사례 호출에 Qwen3.8을 명시적으로 사용한 전환 사례다.
정본은 [EXPERIMENT_MODEL_POLICY.json](00_SYSTEM/EXPERIMENT_MODEL_POLICY.json), 공통 호출은
`lawrag.research.experiment_client.ExperimentClient`다. OpenRouter Parasail FP8과 thinking off를
고정하며 `.env`의 `OPEN_ROUTER`를 읽되 키는 출력·기록하지 않는다. 생성·VLM·중간처리·평가에
적용하며 다른 모델/provider 자동 fallback은 없다. 이전 Qwen·Gemini·Haiku 완료 기록은 보존한다.
GENOS 내부 모델·활성 MAIN 릴리스는 별도이며 외부 Gemma 결과를 현장 성능으로 간주하지 않는다.

2026-10-26 ADR1066 실모델 후속 관찰: 계획9셀 중 A0/A1 제한 답변2·A2 재표시 receipt 충돌1로 중단,6미실행. 행동 필수항목 누락은 관찰19응답에서 재현되지 않았지만 source 카드의 표시ID를 불변 내용 hash에 섞은 결함과 선택 목적/대상 불일치가 남았다. 제품27호출, 평가0회; MAIN103/GENOS 불변. [진단과 후속 경계](04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/POST_RUN_DIAGNOSIS.md). 이 실패 후보를 MAIN 기능이나 완료 부모로 간주하지 않는다.

## 작업을 시작할 때

- 2026-10-26 사용자 후속 지시: 온톨로지 MVP의 조사 선택은 [행동별 최소 응답 계약](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/ACTION_CHOICE_CONTRACT_20261026.md)을 따른다. 모델에는 현재 행동·대상과 실제 필요한 이유/검색/판단만 요구하고, 스키마의 고정값·빈 검토·검증된 출발 목적은 서버가 복원한다. 정상·preview·전체 보완은 같은 계약과 메뉴를 사용한다. 미제출 판단은 pending으로 보존하며 법률 의미·근거를 자동 생성하지 않는다. 입력 문자 hard-stop 해제는 ADR1066 후보 설정이며, 구현·합성 검사·실모델·선택 MAIN 상태는 [최신 기록](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MVP_EXECUTION_REPAIR_STATUS_20261026.md)에서 구분한다.

- 요청과 관련된 아래 진입점부터 읽고, 필요한 문서·코드만 따라간다. 파일명·날짜·검색 결과만으로 현행 구현을 정하지 않는다.
- 대상 환경, 실제 실행 명령/API, 선택된 코드·데이터 세대, 호출되는 함수와 산출물의 소비자를 확인한 뒤 수정한다.
- 설계상 목표, 현재 작업 코드, 선택된 릴리스, 현장 검증 결과를 구분한다. 작업 코드 수정만으로 실행 중인 릴리스가 바뀌었다고 보고하지 않는다.
- 문서와 구현이 다르면 실제 연결 상태와 차이를 밝힌다. 미연결 기능·과거 실험을 현행 기능으로 설명하지 않는다. `research`·보관 경로도 실제 의존성이 있으면 사용 중이므로 이름만 보고 삭제하지 않는다.

| 작업 | 먼저 볼 곳 |
|---|---|
| 전체 MAIN·단계 책임·엔진 연결 | [ARCHITECTURE.md](00_SYSTEM/ARCHITECTURE.md) → [PIPELINE.json](00_SYSTEM/PIPELINE.json), [WORKSPACE.json](00_SYSTEM/WORKSPACE.json) |
| 실행·서빙 경로 | [service.py](service.py), [파이프라인 CLI](06_TOOLS/pipeline.py); 선택된 릴리스/세대의 manifest와 코드까지 확인 |
| 에이전트 실패·판단 충돌·스키마 오류·재시도·복구 | [필수 코딩 지침](07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md); 수정 전 실패 분류·복구 담당·한도·최종 상태·필수 검사를 정하기 |
| 데이터 추가·재구축 | [데이터 안내](01_DATA/README.md), [DATA_MODEL.md](00_SYSTEM/DATA_MODEL.md), [LEGAL_SCHEMA.json](00_SYSTEM/LEGAL_SCHEMA.json) |
| 실험·품질 비교·MAIN 승격 | 아래 실험 절차와 연결된 두 표준 문서 |
| 용어집 구축·정의·관계·수집 재개 | [용어집 파이프라인](07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md) → `pipeline.py glossary`; 목록 완료와 정의·관계 수집 완료를 구분 |
| 후속 작업·실험 아이디어 | [백로그](07_DOCS/BACKLOG.md); 등록과 실제 실행을 구분 |
| GENOS 관련 모든 질문·작업 | [GENOS.md](GENOS.md)를 먼저 읽고, 질문별 출처만 추가로 읽기 |
| 법령 해석·규정 적용 | [위키 인덱스](01_DATA/wiki/wiki/index.md)로 해석 지식을 찾고, 적용 대상의 원문·버전으로 검증 |

## 파이프라인과 구조 변경

- 전체 흐름의 단계별 입력·출력·스키마·실행 순서를 명시한다. 모듈은 나누되, 한 실행 명세로 어떤 경로를 재현하는지 추적할 수 있게 한다.
- 새 기능은 담당 단계, 호출 진입점, 산출물 소비자, 필요한 설정과 검증 방법을 함께 연결한다. 기존 연결을 확인하지 않고 별도 실행기·중복 파이프라인을 늘리지 않는다.
- `PIPELINE.json`의 선언과 실제 CLI/API 배선을 대조한다. 비어 있거나 이행 중인 단계는 미구현/미연결 상태로 표시하고, 파일이나 문서가 있다는 이유로 완료 처리하지 않는다.
- 단계 내부 구현은 입력·출력 계약을 유지하며 교체한다. 계약 변경 시 소비자·스키마 버전·데이터 이행·영향받는 하위 단계의 재구축 범위를 함께 다룬다.
- 현행 원문·용어 RAG 계약은 `DATA_MODEL.md`와 `term-runtime-v1.schema.json`을 따른다. `LEGAL_SCHEMA.json`의 구 의미 스키마는 폐기 이력이며 신규 생성·RAG에서 사용하지 않는다. 용어집 검토는 `GLOSSARY_SCHEMA.json`을 따른다.
- 경로는 `lawrag.platform.workspace`의 논리 root ID로 해결한다. 새 최상위 디렉터리는 `NN_UPPERCASE` 형식을 따른다. 활성화·이행은 workspace의 receipt와 선택 세대를 확인한다.
- 원문 근거·버전·감사·롤백·접근권한을 보존한다. 기존 작업 변경과 완료된 실험·릴리스 이력은 덮어쓰지 않는다.

## 실험 → 검증 → MAIN

Risk팀 관련 실험의 사용자 등록 질문 묶음은 **`risk_cm`**이다.
[질문·외규 마킹·전사 상태](01_DATA/GOLDEN/risk_cm/README.md)와
[공통 등록부](01_DATA/GOLDEN/registry-v2-risk_cm.json)를 먼저 확인한다.
사용자 승인(2026-10-24): risk_cm 105문항(질문·판정 주석·근거 색인·Excel·사진)과 CM 51문항(질문·기준답변·근거 좌표)은 외부 실험 모델로 전송할 수 있다.
`v1/dataset.json`의 반출 false, `PIPELINE.json`의 "internal CM excluded", `cm_shortcut_package.py`의 `NOT_AUTHORIZED_FOR_EXTERNAL_MODEL`은 이전 표시이며 [risk_cm 승인](01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json)·[CM 승인](01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json) 기록이 우선한다. 기준답변·판정은 반출과 별개로 제품 모델 입력에 넣지 않는다. 105문항은
정답·필수근거 승인 전 `question_only`이며 외규 단독 후보는 027·029·078이다.
판정·정답 후보는 제품 입력과 분리하고, 외규 표시를 미사용 holdout의 증명으로
취급하지 않는다. 실제 실행은 아래 ADR 절차로 별도 동결한다.

실험·평가·A/B·ablation·probe·holdout·replay·regrade 또는 모델/프롬프트/검색 효과 비교를 할 때만 다음 두 문서를 **끝까지 읽고** 따른다.
단순 문서 정리, 읽기 전용 진단, 일반 단위 테스트는 새 실험으로 취급하지 않는다.

- [EXPERIMENT_AGENT_PROMPT.md](04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md)
- [STANDARD.md](04_EXPERIMENTS/LEGACY_ADR/STANDARD.md)

1. 진행 중인 동일 scope의 reservation을 먼저 확인한다. 실험을 위한 구현 수정·첫 호출 전에 `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py new --adr-root 04_EXPERIMENTS/ADR`로 ADR을 선점한다. 생성된 owner·task/session·시각·상태·append-only 이벤트를 보존한다.
2. 기준 전체 파이프라인과 정확한 부모 `experiment_id/arm_id`를 정한다. 가설·성공 기준·허용 회귀·평가 데이터·arm·run과 코드/데이터/스키마/프롬프트/모델/설정 버전을 결과 확인 전에 동결한다.
3. 후보는 표준의 snapshot·register·freeze 절차로 격리한다. 변경하지 않은 단계도 기준 버전에 결속하고, 후보가 운영 registry나 기본 경로에서 자동 선택되지 않게 한다. Git 브랜치만으로 데이터·모델·실행 계보가 고정되었다고 보지 않는다.
4. 같은 조건에서 기준과 후보를 비교하고 변경 단계의 계약·하위 단계 연결·전체 결과를 확인한다. 실제 backend/model ID·입출력·사용량·지연·산출물 경로를 남긴다. offline evaluator는 표준의 역할별 allowlist를 따르며 제품 context나 답변을 바꾸지 않는다.
5. 결과를 본 뒤 만든 후속 후보·재실행·재채점은 새 ADR로 남긴다. 완료된 arm만 부모로 쓰고, 여러 결과를 합치면 새 ADR의 `merged_from`에 정확한 부모와 채택/제외·충돌 해결·롤백 기준을 기록한다. 단순 의존 관계는 `relationships`로 남긴다.
6. 완료 전 stable runner의 `adr_structure.py validate --final`과 `graph` 검사를 수행한다. 표준의 과거 `scripts/`·`docs/adr` 예시는 현행 runner·ADR 경로로 해석하며 옛 디렉터리를 재생성하지 않는다.
7. Accepted·out-of-sample·`decision_eligible=true`·complete인 arm만 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py`의 hash 고정 plan과 명시적 `--confirm-main` 절차로 승격한다. 코드·데이터 세대와 apply/rollback receipt를 보존하고 롤백 경로를 둔다. 기존 품질 우회를 새 실험의 통과 근거로 재사용하지 않는다.

Git main 병합, ADR merge, 데이터 CURRENT 변경, 제품 MAIN 승격, GENOS 리비전 배포는 각각 별도 상태다. 어느 상태까지 완료했는지 정확히 보고한다.

### 개발 연속성과 실제 MAIN 배선 — 사용자 지시 2026-10-06

- 기존에 개발한 기능 위에서 이어서 개발한다. 실험 후보에만 있는 수정과 현재 MAIN 작업 코드의 차이를 먼저 대조하고, 필요한 수정은 기존 개발 경로에 통합한다. 후보 snapshot 전체를 작업 코드에 덮어써 다른 최신 수정들을 잃지 않는다.
- 후보에서 성공한 기능을 작업 코드·활성 릴리스의 기능으로 설명하지 않는다. 특히 검색/정렬 정책, 선택 도구, 행동·이유 체인, 복귀/재개, 답변 소비자의 실제 배선을 코드와 해시로 확인한다.
- 사용자가 전체 구현과 MAIN 반영을 요청한 작업의 완료 범위는 통합 코드 작성 → 동일 코드 검증 → MAIN 배선/승격 → 선택 포인터 확인 → 실제 로컬 서비스 진입점 확인까지다. 설계 요청에서는 이 전 과정을 설계에 포함한다. 실험 격리·품질 기준·승격 계약은 유지하며, 미충족 단계는 완료로 보고하지 않는다.
- 완료 기록에는 작업 코드, 검증 후보, 선택 릴리스의 코드/프로필/데이터/검색 정책 지문을 연결하고 실제 서비스에서 선택한 실행 binding을 남긴다. 로컬 MAIN 반영과 GENOS 현장 반입·배포·검증은 별도로 기록한다.

### 판단 오류와 저장공간 — 사용자 지시 2026-10-07

- 실험 질문의 세부 답변이 전부 맞아야 MAIN에 반영하는 것은 아니다. 일반화 부족과 판단 미스는 별도 기록하고 후속 실험으로 개선한다. 세부 의미 채점 실패만으로 MAIN 반영을 자동 차단하지 않는다.
- 인용·권한·코드/데이터 해시·상태 보존·실제 서빙 연결의 심각한 문제는 계속 검증한다. 새 판정 기준은 후속 ADR의 호출 전에 동결하며, 이전 실험의 기준과 결과를 소급 변경하지 않는다.
- 저장공간 사용을 최소화한다. 같은 해시의 읽기 전용 원문·캐시는 공유하고, 원시 기록은 무손실 압축과 해시·복원 방법으로 보존한다. 본문·모델 입출력·전체 회수 목록을 보고서마다 반복 복사하지 않는다. 원본 데이터와 실패 이력은 임의 삭제하지 않는다.

- 2026-10-28 실험 기록 보관: 신규 실험은 요약/판정/집계 JSON과 대형 원시 기록을 분리한다. 요약에는 원시 기록의 경로·SHA256·개수·용량을 참조하고, 탐색 노드/연결/원문 전체를 시작점·보고서마다 중복 삽입하지 않는다. 큰 원시 기록은 스트리밍 무손실 gzip으로 보관하며 압축 전 내용 해시와 압축 파일 해시를 구분한다. 동결된 과거 JSON의 필드·판정·실패 이력은 축약/재작성하지 않는다. `09_ARTIFACTS/AUDITS/20261028-experiment-storage-cleanup/archive-plan.json`에 든 보관 대상은 파일 옆의 `.gz.archive-receipt.json` 상태로 확인한다. 원래 경로를 직접 읽는 과거 검증기·재생기를 실행하기 전에 `06_TOOLS/maintenance/experiment_record_archive.py restore --path <원래상대경로>` 또는 `restore --adr ADR-번호`로 필요한 원본만 복원한다. 복원 없이 발생한 파일 부재를 실험 자체의 실패로 오인하지 않는다. 압축 도구는 진행 중인 프로세스/열린 파일·최근7일 기록·기존다중링크·작은 요약/manifest를 제외한다. 저장 형식 변경으로 과거 미완료 실험을 완료 처리하지 않는다.
- 신규 실험 실행기의 기록 작성에는 `06_TOOLS/maintenance/experiment_json.py`의 `write_summary`와 `write_raw_json`을 사용한다. 요약은1MiB를 초과하면 자르지 않고 거절하며, 대형 원시는 처음부터 `.json.gz`로 기록·복원해시 검증 후 작은 참조를 반환한다. 이미 동결한 과거 실행기를 소급 변경하지 않는다. 이 도구는 신규 작성용이며 기존 모든 실행기의 자동 전환이나 GENOS 저장 정책 반영을 뜻하지 않는다.

### 저장공간·RAM 제약 — 사용자 지시 2026-10-18

- 2026-10-28 저장공간 정리: `09_ARTIFACTS/AUDITS/20261028-storage-cleanup/dedup-plan.json`의 과거 데이터 35경로는 SHA256이 같은 9묶음으로 공유하며 읽기 전용이다. 26개 독립 사본의 12.0817GiB를 회수했고 기존 경로·내용·MAIN112 선택을 보존했다. 해당 과거 데이터를 수정하려면 공유 파일에 직접 쓰거나 chmod하지 말고, 별도 새 파일로 복사·검증한 뒤 교체해야 한다. 결과·검증·복원 방법은 같은 폴더의 `정리결과와_복원안내.txt`를 따른다. WSL 내부 가용량 외에 `/mnt/c`의 실제 여유도 확인한다. 이 기록은 GENOS 보관 정책 수정이나 Windows VHDX 압축 완료를 뜻하지 않는다.

- 이 작업 환경은 저장공간과 RAM이 제한적이다. 작업 시작·무거운 실행 전에 가용 디스크, RAM, swap, 기존 작업 프로세스를 확인하고 사용량을 줄이는 실행 방식을 기본으로 한다.
- 실제 데이터 로딩·fulltext 전체 흐름·대형 테스트·모델 검증은 무거운 프로세스 하나씩 순차 실행한다. 같은 데이터나 인덱스를 여러 프로세스가 동시에 메모리에 적재하지 않는다. 제한된 환경에서 병렬화로 속도를 높이려 하지 않는다.
- 데이터·로그는 가능한 범위에서 스트리밍·작은 배치로 처리한다. 전체 파일을 한꺼번에 읽거나 동일 본문·인덱스·대형 객체를 중복 복사하지 않는다. 실행에 필요한 파일만 snapshot/복사하며 동일 해시의 불변 데이터는 공유한다.
- 실행별 메모리·디스크 사용량을 관찰하고 운영체제와 다른 작업에 필요한 여유를 남긴다. 메모리 한도·중단 기준을 먼저 정하고, RAM/swap 압박이 커지면 추가 실행을 시작하지 않고 원인을 기록한 뒤 실행 범위를 줄인다. 재실행은 중단·부분 완료 기록과 기존 예산을 확인한 뒤 진행한다.
- 완료된 임시 산출물·실험 runtime은 프로세스 종료를 확인한 뒤 무손실 압축과 원본 해시·복원 방법으로 보존한다. 확인된 작업용 중복·재생성 가능 임시 파일만 정리하고, 원본 데이터·완료 실험·실패 이력·활성 릴리스·사용자 파일을 임의 삭제하지 않는다.

### 대사 의미 판단 — 사용자 지시 2026-10-16

- 비교의 충분성·적용성·예외·차이·충돌은 LLM이 원문을 보고 판단한다. 사용자가 결과를 검토하고 수정을 요청할 수 있게 의견·이유·인용·미확보 내용을 함께 보여준다.
- 미확보 설명, 표현 차이, 의미 상태값 조합, 수치 차원 목록 미완성만으로 결과를 버리거나 반복 수정시키지 않는다. 모델에게 위치·근거 ID·도구명·중복 상태를 재작성시키지 않고 시스템이 확정 가능한 값은 조립한다.
- 실제 선택한 인용의 원문 일치, 내규·외규 구분, 문서 접근권한, 코드·데이터·상태 해시와 재개·중복·예산 검사는 유지한다. LLM 의견을 검증된 법률 정답이나 원문 부재의 증명으로 승격하지 않는다.
- 사용자 재강조: 오류 수준이 아닌 불확실성은 실행 중단 조건으로 삼지 않는다. 이 원칙은 대사 부모뿐 아니라 내규·외규 자식 RAG의 조사 종료 검사에도 적용한다. 조사 대상의 구체화·근거 충분성·의미 판단 차이는 설명과 미확인 사항으로 남기며, 이미 읽은 원문의 전달을 막는 이유로 쓰지 않는다. 원문 전달과 자식의 판단 완료를 분리한다.

### 내규 기반 대사와 표 출처 — 사용자 지시 2026-10-20

- 대사는 사용자 질문 → 찾은 내규 → 내규의 개념·조항 범위 → 연결된 외규 → 대사 해석 순서로 구성한다. 질문만으로 내규·외규를 각각 독립 조사한 것을 내규 기반 연결로 설명하지 않는다.
- 개념 이름·정의·어느 장/절/조/항/호까지 묶을지는 LLM이 실제 내규 원문을 보고 판단한다. 시스템은 선택한 원문·문서명·조항·버전·권한을 결속하고, 확보하지 않은 범위를 채워 넣지 않는다.
- 대사표의 왼쪽에는 내규 출처 조항을 두고 개념·확인 내용, 실제 내규 원문, 대응 외규의 문서·조항·실제 원문, 해석·미확인을 같은 행에서 연결한다. 출처 번호만 표시하거나 본문 요약으로 원문을 대신하지 않는다.
- 연결 외규 미확보를 외규 부재로 단정하지 않는다. 구현·모의 계약 검증·선택 MAIN·GENOS 적용 상태는 각각 구분한다.

## 데이터와 법률 근거

- 새 데이터는 데이터 안내의 RAW 반입·검증 경로로 넣는다. 출처·문서 ID·버전·해시·공개/내부 구분·실제/모의 구분을 남기고, 임의 폴더의 최신 파일을 자동 선택하지 않는다.
- 외부·GENOS 내부 생성 데이터는 같은 `DatasetPackage` 계약을 사용하고 `SourceSet`이 명시적으로 조합한다. 원문·완료 세대는 보존하고 변경은 새 세대와 계보로 남긴다.
- 규칙 기반 hint는 원문의 단서·span·명시 참조를 다룬다. LLM의 의미 추출은 검증·검토를 거칠 observation이며 추출 성공만으로 정본으로 승인하지 않는다. 근거가 부족하면 미확인 상태를 보존한다.
- 법령 원문과 해석 위키를 구분한다. 수치·인용은 해당 원문에서 확인해 원문 표기대로 쓴다. 위키 수정 시 index·log를 갱신하고 원문 불변층을 보존한다. 낡은 해석은 Outdated/Disputed로 표시한다.
- 피드백은 근거와 세대에 연결된 수정 후보로 만든다. 검증한 검색 경로를 재사용하되 과거 답변을 정답 데이터로 자동 승격하지 않는다.

## GENOS와 외부 개발 환경

- 사용자 확인(2026-10-01): GENOS 현장 실행 명령은 `python3`를 사용한다. 현장 인계 TXT에 로컬 저장소 전용 `.venv/bin/python` 경로를 넣지 않는다. 실제 `sys.executable`과 Python 버전은 현장 로그로 확인한다. 아래 WSL 로컬 개발·테스트의 `.venv/bin/python` 규칙과 구분한다.

- 현장 질의·warmup 검증은 **워크플로우 테스트 화면에서만 가능**하다. 코드서빙 직접 테스트 UI/API 실행을 요구하지 않는다. 워크플로우 Python 단계 변경은 코드 ZIP 적용·Git push와 별도로 편집기에 반영해야 한다.

- GENOS 코드 ZIP을 현장에 인계할 때 코드 적용 대상은 기존 Git checkout인 `~/DEV`다. 검증한 파일을 백업 후 적용하며, 별도 후보 코드 폴더에만 설치하는 방식은 사용자가 명시적으로 요청한 경우에 쓴다. 패키지를 풀고 설치기를 실행하는 위치와 코드 적용 대상을 구분한다. 실행 TXT는 첫 단계부터 지속 로그와 실패 상태를 남기고, 재실행 시 이미 적용된 파일을 안전하게 확인한다. 코드 적용과 NFS generation 생성, Git push, 코드서빙 리비전 배포는 각각 별도 상태로 확인한다.

- 사용자 정정(2026-10-14): ZIP/실행 TXT는 사용자가 실제 업로드한 `TRANSFER` 폴더에서 실행한다. 그 폴더를 현재 작업 위치로 두고 `./정확한첨부파일명.zip`, `./정확한실행파일명.txt`처럼 상대경로로 안내한다. `TRANSFER`의 절대 위치를 `~/TRANSFER`나 `~/DEV/TRANSFER`로 추정하지 않고, 압축 해제·설치기 실행을 위해 먼저 `DEV`로 이동하도록 안내하지 않는다. ZIP은 `python3 -m zipfile -e ./정확한첨부파일명.zip ./패키지폴더`로 풀고 `bash ./패키지폴더/정확한실행파일명.txt check` 및 `apply`를 연결한다. 설치기의 기존 checkout 적용 대상 및 이후 Git commit·generation 검증 위치는 별도로 명시한다.

- 환경별 사용법·모델 설정·배포 절차의 진입점은 [GENOS.md](GENOS.md)다. **현재 Codex 세션에서는 망분리 GENOS 세션·코드스페이스·서빙·내부 모델에 접근할 수 없다.** 현장 연결 확인을 재시도하지 않고 코드·반입 자료·사용자가 제공한 현장 기록으로 확인한다. 최종 GENOS 실행은 내부 LLM·임베딩을 사용한다.
- `localhost`/WSL의 로컬 개발 서버와 GENOS 현장 서버를 명시적으로 구분한다. 로컬 응답·실패로 GENOS 상태를 판단하거나 환경을 밝히지 않은 “상주 서버” 표현을 쓰지 않는다.
- 외부 모델 실험 결과와 GENOS 내부 모델의 현장 성능은 구분해 보고한다.
- 현장 인계에는 코드 리비전·의존성·설정 이름·입출력 계약·실행/재개/검증/롤백 방법을 포함한다. 외부 테스트 성공과 현장 배포 성공을 구분한다.

## 개발과 완료 확인

- Git·Python·테스트·저장소 스크립트는 WSL의 `/home/jin/8-AGENT`에서 Linux 도구로 실행한다. Windows Git/PowerShell로 UNC 경로를 조작하거나 `safe.directory`로 우회하지 않는다.
- 환경 관련 작업 전에 `06_TOOLS/check_wsl_dev_environment.sh`를 실행한다. Python은 저장소 `.venv/bin/python`을 사용한다.
- 변경 범위에 맞는 계약·회귀·연결 검사를 수행한다. 완료 보고에는 무엇을 바꿨는지, 실제 확인 결과, 영향받는 실행 경로와 남은 미확인 사항을 짧게 남긴다.

### 에이전트 실패와 충돌 처리 — 사용자 지시 2026-10-13

에이전트·도구·모델 어댑터·스키마·검증기·상태 저장·답변 표시를 수정할 때는
[AGENT_FAILURE_RECOVERY_POLICY.md](07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md)를 먼저 읽고 따른다.
이 지침은 코드 작성·검토·테스트의 필수 기준이며, 문서 작성만으로 런타임 구현이나 현장 반영이 완료된 것은 아니다.

- 정상 경로와 함께 실패 경로를 설계한다. 오류 종류, 실제 원인, 복구 담당 한 곳, 허용 보정, 재시도/시간/호출 한도, 상태 보존, 최종 응답을 먼저 정한다. `raise`만 추가하거나 포괄 `except`로 성공 처리하는 구현은 완료로 보지 않는다.
- 모델 출력은 제안이다. JSON 구문·스키마 → 필드 간 일관성 → 제시된 근거/권한/버전 → 상태 revision/소비자 계약을 각각 검증하고, 스키마 통과를 의미·근거 검증 통과로 간주하지 않는다.
- 자동 보정은 의미를 추정하지 않는 사전 허용 규칙만 사용한다. 원래 제안과 변경 사유를 기록하고 전체 검증을 다시 한다. `MISSING_SOURCE + REQUEST_FACT`는 부족을 보존한 채 원문 조사로 연결할 수 있지만, 근거·사용자 사실·법률 결론을 만들거나 부족을 삭제해 통과시키지 않는다.
- 스키마/판단 수정 요청에는 같은 요청·근거 범위와 구체 오류를 전달한다. 같은 실패의 재시도를 gateway·단계·상위 실행기가 중복 수행하지 않는다. 원인/판단 단위별 담당과 총 예산을 명시하고, 재개해도 사용량·deadline·실패 이력을 초기화하지 않는다.
- 같은 자료·같은 상태에서 같은 충돌이 반복되면 맹목 재호출하지 않는다. 허용된 별도 조사 경로, 확인된 근거만의 제한 답변, 필요한 사용자 사실 질문, 또는 사유가 기록된 중단으로 끝낸다. 미확보 원문은 사용자의 사실 부족으로 떠넘기지 않는다.
- 법률 의미 충돌은 양쪽 근거·적용 범위·버전을 유지해 재검토한다. 권한 위반·해시 불일치·변조·stale 상태·출처 불명은 일반 모델 수정으로 우회하지 않는다. 실패한 도구 실행을 근거 확보/부재 확인으로 기록하지 않는다.
- 실패·부분 성공·성공·중단·재개 가능을 구분한다. 검증된 주장만 제한 답변에 쓸 수 있다. 전송 중 일부가 표시된 뒤 실패하면 완성 답변으로 확정하거나 다른 생성 결과를 이어 붙이지 않는다. 실패 이력을 성공한 숏컷·위키·정답으로 승격하지 않는다.
- 수정 후 정상/복구 성공/복구 실패/반복 충돌/예산 소진/재개/중복 요청/권한·해시·상태 회귀/표시·저장 소비자 연결을 변경 범위에 맞게 검사한다. 공통 검증기는 사용하는 현행 버전별로 확인하고, 최소 한 검사는 실제 API 또는 서비스 진입점과 같은 코드·pin으로 실행한다. 재현 가능한 결함만 일반 단위 검사로 수정하며 모델·프롬프트·검색 효과 비교는 기존 ADR 절차를 따른다.
- 완료 기록에는 남은 미구현·미검증 복구 경로, 실제 테스트 결과, 작업 코드/선택 릴리스/GENOS 적용 상태를 남긴다. 오류 문구를 숨기거나 HTTP 상태만 바꾼 것을 오류 해결로 보고하지 않는다.

<!-- NONMODEL_RECOVERY_CANDIDATE_20261027 -->
**2026-10-27 비LLM·입력·복구 후보:** [구현·검증·남은 문제](07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NON_MODEL_1S_AND_RECOVERY_IMPLEMENTATION_20261027.txt). ADR1129 격리후보의 새52·관측350검사 총402통과. A-C만의 보관응답 재생은 전체 비LLM(용어집 제외)80.255→46.539초이며1초미달. 새 공개질문은HTTP200/CLARIFY로 원문조사0회여서 통합 검증 미충족, 승격거절. 이전1120의 추가원문조사12기록과 최종claim연결실패를 구분한다. 최종후보433파일(제품432)이며 작업제품코드·선택MAIN107·GENOS에 반영하지 않았다. 문서번호는 카탈로그 기준·원장결속, 새판단/독립읽기 복구는후보구현이고 활성MAIN기능으로 설명하지 않는다.
<!-- /NONMODEL_RECOVERY_CANDIDATE_20261027 -->
