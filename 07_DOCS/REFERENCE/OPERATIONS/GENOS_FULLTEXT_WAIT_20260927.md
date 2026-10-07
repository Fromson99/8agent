# Fulltext SQL 중단 제한 해제와 GENOS 대기시간

2026-09-27 사용자 요청으로 fulltext의 별도 20초 중단을 제거하고 연결·응답 대기를
늘린 작업 코드다. 실제 GENOS 플랫폼 설정·배포 상태는 이 세션에서 접근할 수 없다.

## 실행 경로와 시간

`service.py` → GENOS generation 선택 → v5 profile의 실제 실행 시간 결속 →
`RequestContext` → `workflow_relations_tools.search(fulltext)` → FTS5 `rank`.
기존 20초 SQL callback 대신 요청 전체 deadline을 사용한다. 순위·검색 범위·
결과 수·인덱스 내용·실제 SQL 오류의 보고는 유지한다. 시간 초과 외의 DB 오류를
성공이나 검색 0건으로 바꾸지 않는다. 별도의 관계 탐색 시간/횟수는 이 변경 대상이 아니다.

|설정·대상|이전|변경 후|
|---|---|---|
|v5 fulltext SQL 별도 중단|20초|삭제. 요청 전체 deadline 사용|
|GENOS v5 전체 요청|기본 300초|기본 1800초, `GENOS_RAG_WALL_SECONDS`로 지정|
|워크플로우 → 코드서빙 대기|기본 360초|기본 2100초, `GENOS_CODESERVING_TIMEOUT_SECONDS`|
|내부 LLM 연결 수립|5초 고정|기본 60초, `GENOS_LLM_CONNECT_TIMEOUT`|
|내부 LLM 모델 확인 `/models`|총 15초|endpoint 읽기 설정 사용, 기본 120초|

v5 모델 호출의 전체 HTTP 시간은 남은 요청 시간이고, 연결 시간은 지정값과 남은
시간 중 작은 값이다. POST는 물리 호출 1회이며 연결 실패 시 무제한 재시도하지 않는다.
GENOS 환경 결속과 별도 파일로 고정한 v5 profile 모두 실제 실행 profile에 시간
설정을 반영한다. 원본 profile 파일과 로컬 frozen release는 수정하지 않으며 실행
profile의 해시에 변경 시간이 포함된다. 기존 1800초보다 긴 profile은 기본 설정으로
줄이지 않는다. 명시 `GENOS_RAG_WALL_SECONDS`는 해당 값을 사용한다.

## 현장에서 저장할 설정

코드서빙 리비전 환경 설정:

```text
GENOS_RAG_WALL_SECONDS=1800
GENOS_LLM_CONNECT_TIMEOUT=60
```

워크플로우 리비전 환경 설정 (코드서빙 환경과 별개):

```text
GENOS_CODESERVING_TIMEOUT_SECONDS=2100
```

기존 360초 값이 남으면 새 Python 코드를 붙여넣어도 해당 값이 우선한다.
실제 GENOS 플랫폼에 별도의 게이트웨이/코드서빙 요청/워크플로우 실행 시간 설정이
있으면 이 요청을 끝까지 기다릴 수 있는 값(최소 2100초)으로 맞춰야 한다.
해당 설정의 명칭·변경 권한·플랫폼 최대값은 현장 미확인이다. Python 환경변수나
Git push만으로 플랫폼 자체 제한이 변경됐다고 판단하지 않는다.

## 배포·검증·원복

이전 SQL 검사 R1과 최종 검토 advisory R1의 두 상태를 인식하는 누적 패치로
인계한다. advisory 변경도 포함하므로 앞 패치를 아직 적용하지 않았어도 SQL R1
위에 이번 묶음을 적용할 수 있다. 이후 이전 패치를 덮어 적용하지 않는다.
기존 `~/DEV`를 백업 후 적용하고 엔진 pin·ZIP/commit 검증을 수행한다.
동일 generation으로 코드서빙 새 리비전을 배포하고 워크플로우 Python 전체 교체와
위 환경 설정을 각각 적용한다. 새 NFS generation과 재색인은 필요하지 않다.

모의 회귀 검사에서는 SQLite의 실제 progress callback을 사용해 시계를 25초 뒤로
이동시켜도 조회가 끝나는지, 전체 요청 deadline에서는 중단하는지 확인한다.
모델 HTTP 연결 설정과 전체 deadline, 실제 GENOS generation 진입 경로의 시간
결속, 워크플로우의 기본값/기존 설정 우선순위를 검사한다. 내부 모델 호출이나
실제 NFS 성능 측정은 아니다. 현장 질의는 워크플로우 테스트 화면에서만 확인한다.

원복은 설치 백업과 이전 코드서빙·워크플로우 리비전으로 한다. 시간 설정도 별도로
이전 값으로 되돌린다. 현재 코드에서 `GENOS_RAG_WALL_SECONDS=300`은 전체 요청을
5분으로 되돌리지만 fulltext의 별도 20초 중단을 복원하지는 않는다.
