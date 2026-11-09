Oracle 규모 점검 (oracle_scale_guard) — 2026-11-06

왜 필요한가
  현장 Oracle 오류는 대부분 SQL 문장이 아니라 "범위 전체·문서 전체를 펼치는 코드"에서 났다.
  Oracle 경로는 한 번의 나열이 1만 행을 넘으면 멈추고(QUERY_NAV_BUDGET / QUERY_SQL_RESULT_BUDGET),
  키 조회 전용 목록을 통째로 돌면 거절한다(QUERY_FULL_CATALOGUE). 요청당 SQL 한도는 1만 회다.
  SQLite에서는 같은 코드가 메모리 사전이라 통과하고, 로컬 소형 시험도 1만 행에 안 닿아 통과한다.
  그래서 현장에서 하나씩 터졌다(RECALL corpus_ids, 별표 색인, 구조 목록, 가이드 원문 메뉴 …).

무엇을 하나
  1. inventory.py — 이 코드가 Oracle로 보낼 수 있는 SQL 전부(계획 642개 중 Oracle 대상 215문장)와 손으로 쓴 Oracle SQL 목록.
  2. test_guard_oracle.py — 로컬 Oracle 컨테이너(a8-legal-mapped-20261023)에 개발계 실버 17표를 임시 소유자로 만들고
     작은 자료(범위 원문 ~150, 한 문서 ~250단위, 장 4개 아래 조문, 벡터 3차원 항목)를 게시한 뒤, 배포 프로필(가이드 모드)
     질문 17개(키워드·벡터 초기검색·후속 질문·조문 번호 검색어, 문서 이름+조문 번호 검색어의 키워드 S11·벡터 V4)를 모의 모델로 끝까지 실행.
     test_guard_comparison_oracle.py — 같은 방식으로 대사(모의내규↔모의승인규정 + 부속 문서) 1건.
     현장 1만 행 한도를 자료 크기에 맞춰 40행으로 줄이고, 제품의 묶음 크기 상수(제목 묶음 1,000행, 단위 1,000개 묶음,
     문서 전체 4,096단위, 블록 5,000개 창)도 같은 비율로 줄여 그 코드 경로가 작은 자료에서도 실제로 실행되게 한다.
     서빙 Factory처럼 프로세스 캐시(GENOS_ORACLE_SHARED_CACHE)를 붙여 현장과 같은 조건으로 SQL 수를 센다(GUARD_SHARED_CACHE=off로 끔).
     기록: 40행 넘는 한 번의 읽기, 한 질문에서 한 문서를 한 건씩 40회 넘게 조회, 전체 목록 거절, SQL·시간.
     모의 모델은 guard_transport.py(05_TESTS 공유 시험 파일의 고정본)라 다른 세션의 시험 수정에 흔들리지 않는다.
     이어서 Oracle 대상 SQL 전부를 값 9종 × 열 크기 2종(시험 / 로컬 1,547문서 실측)으로 실행.
  3. judge.py — 질문 실패, 한도 초과 읽기, 전체 목록 거절, ORA-22806 모양(WITH+NUMBER 바인드), SQL 오류,
     한 질문당 SQL 수와 많이 부르는 곳을 보고서.txt / report.json으로 정리. 하나라도 있으면 실패(exit 1).

실행 (무거운 실모델 셀이 돌고 있지 않을 때, 약 4~5분, 외부 모델 0)
  .venv/bin/python 06_TOOLS/maintenance/oracle_scale_guard/run.py --code-root <릴리스 또는 후보 code 폴더> --out <새 폴더>
  예: --code-root 08_DEPLOYMENT/RELEASES/<release>/code --out 09_ARTIFACTS/AUDITS/<날짜-작업>/pytest-guard
  (출력 폴더 이름에 pytest를 넣으면 다른 세션의 실모델 대기 스크립트가 바쁜 것으로 본다)
  저장된 결과만 다시 판정: .venv/bin/python 06_TOOLS/maintenance/oracle_scale_guard/judge.py <out>
  일부만: --parts scenarios  /  --scenarios S2,S3

예외 기록: accepted.json — 자료 크기와 무관하게 묶인 읽기만, 코드에서 확인할 수 있는 이유와 함께. 가능하면 상수 축소로 해결.

판정 읽는 법
  [scope]    요청 범위 전체를 읽음 → 현장 범위(원문 약 4만)에서 멈춤
  [document] 문서 하나 전체를 읽음 → 1만 단위 넘는 문서(로컬 실데이터 7개: 조세특례제한법 시행규칙 29,428 등)에서 멈춤
  [statement] 한 SQL 결과를 끝까지 스트리밍 → 위와 같음
  한 문서를 한 건씩 조회 → 문서 단위 수만큼 SQL(현장 큰 문서면 요청당 SQL 1만 회 한도 초과)
  허용: 문서 하나 전체 나열 — 그 문서의 게시 단위 수만큼 한도를 주고 요청 안에서 재사용하는 읽기(정보로만 표시)
  한 질문 SQL 수: 현장 한도 10,000, SQL 1회 수 ms~수십 ms → 수천 회면 수십 초.
  "점검 도구 자체 오류"가 있으면 결과를 믿지 말고 도구를 먼저 고친다(제품 오류로 보고하지 않는다).

한계
  운영 Gold(packed) 경로, 실제 ORDS HTTP, 현장 자료·현장 색인 유무는 시나리오에 없다. 4MB 요청 캐시에 가려지는 경우는
  작은 자료로 드러나지 않을 수 있어, 큰 변경은 09_ARTIFACTS/AUDITS/20261106-oracle-query-survey/run.py의 실제 크기
  시험(원문 1만 초과 범위 --filler-documents 6, 1만 단위 문서 --big-doc-articles 2600)도 함께 돌린다.
  모의 모델이 고르는 경로만 지난다 — 통과가 모든 경로의 안전을 뜻하지 않는다. 새 기능은 그 경로를 지나는 시나리오를 추가한다.
  ORA-22806은 현장 ORDS에서만 재현됐다(로컬 Oracle은 통과). 그래서 그 모양(WITH 안 NUMBER 바인드)을 금지 규칙으로 본다.
