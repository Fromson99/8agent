골드 연결 R12 — 별도 폴더 가능성 확인 및 로컬 예시
2026-10-29

결론
기존 제품 파일을 수정하지 않고 이 폴더의 설정과 실행기로 골드 테이블을 선택하는 방식이 가능하다.
B03/B05 각각 실제 로컬 Oracle에 R12 13테이블·60컬럼을 만들고, 합성 데이터 39행으로 확인했다.
Oracle 검사 29개씩 총58개, 새 연결층 경계 단위검사11개가 통과했다.
현행 서비스 전체의 골드 전환이나 실제 Dataiku/GENOS 운영 연결 완료를 뜻하지 않는다.

구성
- config_b03.json / config_b05.json: owner, B03/B05 명명안, R12 모델 경로·해시.
- gold_connection.py: 골드 물리 컬럼→기존 논리 행 변환, 요청 연결, 벡터 읽기, 선택 CAS.
- example_data.py: 외부 모델을 사용하지 않는 합성 예시 원문·색인·벡터·온톨로지 행.
- run.py: DDL 출력 또는 자원 제한이 있는 로컬 Oracle 예시 생성·검사·정리.
- test_connector.py: 설정·식별자·JSON·SQL 문법 보존 경계 검사.
- results/: 최초 실패와 정정 후 성공 원본, 예시 DDL·데이터, 해시·용량 기록.

연결 방식
새 실행기 --config → GoldConfig → 별도 읽기 연결 → 골드 테이블 → 기존 원문/검색 소비자.
실제 검사는 선택 MAIN117(accepted-answer-20261029-r1)의 변경 없는 원문/해시/권한/전문검색
코드를 가져와 수행했다. 선택 리비전466파일의 해시를 실행 전후 대조했다.
기존 서비스의 기본 매핑, 환경변수, MAIN 포인터는 이 작업에서 변경하지 않았다.
기존 서비스에 새 파라미터만 주면 자동 활성화되는 상태는 아니다. 현재는 새 실행기/연결 함수가 진입점이다.

읽기 연결은 DB VIEW를 추가하지 않고 요청 SQL의 인라인 SELECT로 논리 컬럼명을 제공한다.
문서명 VARCHAR2→CLOB과 본문생략 Y/N→1/0 변환을 새 어댑터에서 수행한다.
NULL은 유지하고 잘못된 생략 값은 기존 검증기가 거절하도록 한다. 문자열을 조용히 자르지 않는다.
기존 읽기 API의 ID 512 BYTE 제한은 유지되므로, R12의 1000 BYTE 컬럼을 전부 소비한다고 주장하지 않는다.

최초 연결에서 기존 SQL 파서가 Oracle JSON_TABLE의 ERROR ON ERROR 문법을 거절했다.
새 어댑터는 문자열·주석·bind·JSON 문법을 그대로 보존하고 등록된 FROM/JOIN 테이블 토큰만 치환한다.
기존 제품 파일이나 전역 함수의 교체/monkeypatch는 하지 않는다.
현재 SQL 경로에서 필요한 표만 지원하며 Agent 상태/자산 저장 포트를 골드로 임의 연결하지 않는다.

로컬에서 사용
저장소 루트 /home/jin/8-AGENT 기준이다. GENOS 현장 실행 지시가 아니다.

1. DB 실행 없이 B03의 생성 SQL 확인
   PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_r12/run.py plan --config 08_DEPLOYMENT/LOCAL/gold_connection_r12/config_b03.json

2. B03/B05 로컬 예시 재생성·검사
   PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 08_DEPLOYMENT/LOCAL/gold_connection_r12/run.py verify-local --config 08_DEPLOYMENT/LOCAL/gold_connection_r12/config_b03.json --config 08_DEPLOYMENT/LOCAL/gold_connection_r12/config_b05.json

이 명령은 기존 로컬 테스트 컨테이너 a8-legal-mapped-20261023의 작업 라벨·localhost 바인딩을 검사한다.
새 이미지 다운로드나 새 Oracle 컨테이너 복제는 하지 않는다. 실행 중 시스템 비밀번호는 메모리에서만 쓴다.
매번 임의 이름의 별도 예시 스키마에 최대64MiB quota를 주고 두 명명안을 순서대로 검사한다.
설정의 owner는 이 로컬 검사에서 임시 owner로 대체한다. 기존 SIDDS/SIDDA 테이블은 대상이 아니다.
성공/실패 모두 자신이 생성한 예시 스키마만 삭제하며, 원래 정지 상태였던 컨테이너는 다시 정지시킨다.
예시 테이블을 계속 남기지 않는다. 정확한 DDL과 합성 데이터를 결과 폴더에 남기므로 재생성할 수 있다.

확인한 범위
- 실제 Oracle 23.26.3.0.0, R12 테이블13/컬럼60/PK13/일반 인덱스11/native VECTOR1.
- B03·B05 각각39행. 문서2, 구조2, 본문3, 원문게시1, 조회게시1, 검색행20,
  채널1, 온톨로지 게시/선택/연결 각1, 벡터게시1, 벡터구간4, 벡터선택1.
- 기존 원문 소비자의 문서명·Y/N 복원·순서·원문 해시·권한 거절·변조 탐지.
- 기존 SRCH_ROW의 문구 검색·문서 그룹·페이지·total·cursor 결속·빈 검색.
- 실제 VECTOR_DISTANCE와 문서 권한 필터, 원문 단위 MIN 거리 집계 후 순위.
- 미완료 벡터 미선택, 잘못된 profile/권한/숫자 거절, 활성화/해제·stale·A→비활성→A CAS.
- 온톨로지 예시의 저장 및 원문 구조와의 JOIN. 실제 시나리오 생성·승인·RAG 해석 검증은 아니다.
- 실제 임베딩 호출0, LLM 호출0, 실제 원문/색인 복사0.

용량과 실행 경계
검사 전후 WSL 표시 여유 약208GiB, Windows C: 실제 여유 약34.35GiB였다.
WSL 내부 여유만 보고 대량 복사를 결정하면 안 된다. 호스트 C: 여유를 함께 본다.
선택 데이터의 SQLite 9파일 논리 크기는 약4.726GiB이며 이번에는 복사하지 않았다.
이 값은 Oracle 이관 용량 예상치가 아니다. JSON/CLOB·일반 인덱스·벡터·UNDO/REDO를 더 확인해야 한다.
예시 스키마의 Oracle 할당량은 명명안당5.75MiB이며 순차로 생성 후 삭제했다.
성공 실행의 채집 시점 최소 가용 RAM은9.32GiB, 관측 swap 증가는1.25MiB였다.
짧은 간격 전체의 연속 최고 사용량 측정이나 성능 인증은 아니다. 폴더 자체는 약0.5MiB다.
가드: C:20GiB 미만, WSL10GiB 미만, 가용 RAM4GiB 미만, swap128MiB 초과 증가,
또는 실행 중 C: 여유256MiB 초과 감소 시 다음 검사 진행을 중단하고 정리한다.
Oracle 기존 컨테이너 메모리 상한은2,621,440,000바이트다. 다른 컨테이너·기존 데이터는 정리하지 않았다.

실패·원본 보존
results/run-20261029-162300-440701/: 최초 Oracle 문법 변환 실패 및 정리 기록.
results/run-20261029-162545-185589/: 수정 후 B03/B05 성공, 예시 SQL·JSON, 실제 조회 결과.
results/unit_tests.log: 11통과. cacheprovider 비활성화에 따른 기존 cache_dir 설정 경고1.
results/original_files_before.json: 작업 초기 기존 파일1178개의 지문.
성공 실행 종료 시 이 새 폴더 밖에서 PIPELINE.json, law_navigation.py, need_continuity.py,
ontology_work/repository.py의 변경이 관측됐다. 이 작업의 쓰기 대상은 새 폴더뿐이며 이들 파일은 수정/복원하지 않았다.
동시에 진행 중인 작업 변경 가능성을 구분하기 위해 관측 결과를 그대로 남겼다.
이번 검사가 실제 가져온 선택 릴리스466파일과 MAIN117 포인터는 실행 전후 동일했다.

전체 연결 전에 남은 구현
1. 새 서비스 진입점에서 골드 읽기 연결과 기존 인증/권한·Agent 저널을 연결하는 작업.
2. Dataiku 실데이터 적재기: 전체 원문·검색행·JSON 관계의 배치 검증, 재개, 중복 처리.
3. 벡터 게시의 실제 모델/profile·전체 구간 해시/건수 검증, writer lease/fencing과 봉인 연결.
   이번 예시 적재기는 단일 작성자용이다. HEAD CAS 성공을 동시 적재 전체 안전성으로 확대하지 않는다.
4. 온톨로지 Gold/Agent 트랜잭션, 실제 운영 owner/권한·ORDS 연결 검증.
5. 기존512 BYTE ID 제한과 R12 컬럼 길이 차이, 문서명2250 BYTE 초과 데이터의 사전 검사.
6. 전체 이관 전 작은 실제 문서 범위로 Oracle 할당량·행 수·인덱스 크기·로그 증가를 측정.
   그 결과와 원본 보존·롤백 공간을 합산한 뒤 전체 이관 가능량을 정한다.

전문검색 페이지별 점수 재계산은 기존 구현 그대로다. 이번 연결 검증을 속도 개선으로 해석하지 않는다.
전체 데이터 이관, MAIN 승격, GENOS 배포, Git commit/push, 메일은 이번 작업에 포함하지 않았다.
