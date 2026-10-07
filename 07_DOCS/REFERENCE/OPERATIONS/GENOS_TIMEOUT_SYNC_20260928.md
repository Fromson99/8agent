# GENOS 시간 설정 전수 확인과 전체 코드 갱신

## 확인 범위와 사실

현재 인계본은 `timeout-sync-20260928-r3`다. R3 인계 README의 자동 적용 순서가 아래 R2 수동 절차를 대체한다. R1은 용어집 컴파일러 캐시 결속을 바꿨으므로 반복 적용하지 않는다. 저장소 현재 코드·설정·운영 도구를 대상으로
timeout/deadline/wall_seconds/time_limit/time_budget을 전수 검색했다.
정확한 파일별 원문 위치와 해시는 `08_DEPLOYMENT/GENOS/handoffs/timeout_20260928_r1/`
아래 BEFORE/AFTER 감사 목록에 기록한다. 완료된 실험/릴리스, 고정 generation,
실제 데이터·환경·가상환경은 현행 시간 설정과 구분한다.

사용자 사진의 `profile-tools-v4.json`은 `.Trash-1001/files/...20260921` 아래에
있다. 이 경로의 300초는 실제 실행 선택을 입증하지 않는다. 앞 사진에서는
약 300초에 코드서빙 HTTP 500을 받은 워크플로우가 `answer_status=failed`인
dict를 반환했고, 플랫폼 바깥에는 `code=0, errMsg=success`가 표시됐다.
환경변수 목록에는 같은 대기시간 이름이 600/2100으로 중복 등록돼 있었다.
실제 프로세스가 받은 값과 500을 만든 구성요소는 사진만으로 확정하지 않는다.

## 수정과 보존

|현재 경로|적용 기본값|
|---|---|
|LEGAL_AGENT 프로필 5개와 PIPELINE 요청 설정 7곳|1800초|
|법률 에이전트 v1~v5 기본 프로필|1800초|
|실제 연결된 navigation/document/term/task 요청|1800초|
|참조 해소 기본 요청, GENOS build/authoring의 기존 300초 모델 대기|1800초|
|워크플로우 `/json`, `/stream`|2100초, 같은 `GENOS_CODESERVING_TIMEOUT_SECONDS`|
|GENOS 호출 셸 도구|2100초, `GENOS_CALL_TIMEOUT`|
|DOC 변환 시간 진단|900초, 기존 변환 경로와 동일|

명시적으로 더 짧은 실행 옵션이나 환경변수를 주면 그 값이 적용된다.
GENOS v5의 기존 `GENOS_RAG_WALL_SECONDS` 동작과 설정 검증은 유지한다.
모델 연결 60초, 모델 ID 확인/embedding HTTP 대기, 전처리·변환 대기,
SQLite 잠금 대기, 원문 회수 단계 자체 예산, heartbeat/worker 종료 대기는
전체 요청의 300초 제한과 다른 책임이므로 일괄 연장하지 않는다.
현재 모델 ID·원문 범위·출력 토큰·동시 요청 무제한 정책·FINAL 검토·출처 계약은 유지한다.
프로필 SHA256 소비자와 엔진 manifest/PIPELINE pin은 변경 코드에 맞춰 갱신한다.
데이터 manifest/세대/CURRENT와 frozen release는 바꾸지 않는다.

## 현장 적용 순서

1. 메일의 `8agent-genos-timeout-sync-20260928-r2.zip`, `..._APPLY.txt`를 같은
   폴더에 두고 `bash 8agent-genos-timeout-sync-20260928-r2_APPLY.txt`를 실행한다.
   기본 대상은 기존 Git checkout `~/DEV`다. 모든 실행은 첫 단계부터 지속 로그를
   남긴다. 전체 ZIP SHA256·파일 목록·개별 SHA256·Python 문법을 확인하고,
   적용 전 파일을 백업한 뒤 현재 코드 파일을 갱신한다. 로그의 BACKUP/RECOVERY
   경로와 적용 receipt를 보존한다. 이미 적용된 동일 ZIP은 상태를 확인하고 재사용한다.
   다른 프로젝트는 `DEPLOY_ROOT=/실제/Git/checkout`을 지정한다.
2. ZIP의 고정 과거 코드 세대는 이력으로 보존한다. 현재 Python은 현장 인터프리터로
   문법 검사한다. 기존 고정 코드의 알려진 Python 3.11 비호환 모듈은 현재 서비스의
   실행 검증 대상이 아니며, 고정 세대 전체의 실행 가능성을 인증하지 않는다.
3. `~/DEV`에서 변경 파일을 검토해 commit한다. `MODE=verify`와 실제
   `GENOS_GENERATION=/선택한/절대/generation`으로 같은 TXT를 실행한다.
   ZIP의 모든 파일을 해당 clean commit과 대조하고 그 checkout으로 generation
   E2E와 verify_assets를 실행한다. 통과한 commit을 push하고 코드서빙 새 리비전이
   바로 그 commit과 generation을 선택하도록 한다. TXT는 자동 push/deploy하지 않는다.
4. 별도 첨부 `..._WORKFLOW_PASTE_ALL.txt` 전체를 워크플로우 Python 단계에
   붙여넣고 저장·배포한다. 시간 변수는 `GENOS_CODESERVING_TIMEOUT_SECONDS=2100`
   한 항목만 남긴다. 코드서빙 변수 `GENOS_RAG_WALL_SECONDS=1800`은 코드서빙
   리비전에 설정하며 워크플로우와 공유되지 않는다. 현재 기본값이면 두 시간 변수는
   생략할 수 있지만 이전 명시 값이 남아 있으면 바꿔야 한다.
5. 워크플로우 테스트 화면에서 `{"API_TYPE":"WORKFLOW_SETTINGS"}`를 실행한다.
   모델/HTTP 호출 없이 리비전 `timeout-sync-20260928-r1`과 두 경로의 실제
   `2100` 값을 확인한다. 채팅 앱도 해당 워크플로우 리비전을 선택해야 한다.
6. 같은 테스트 화면에서 실제 질문을 실행한다. 코드서빙 로그의
   `binding.resolved`/`runtime.request_budget`(1800), `request.returning`과
   워크플로우 `code_serving.*`를 같은 request_id로 대조한다.
   HTTP 500은 `failure_kind=http_error`, `http_status=500`, `tm_total`,
   클라이언트 자체 오류는 `failure_kind=client_exception`, `error_type`을 남긴다.
   새 코드에서도 실제 적용 대기값보다 빨리 HTTP 500이 도착하면 해당 요청의
   응답 detail/코드서빙 상태/중계 호출 로그로 500의 발생 지점을 확인한다.

## 원복과 확인 한계

`MODE=rollback ROLLBACK_FROM=/로그의/백업경로 bash ..._APPLY.txt`로 파일을 복구한다.
적용 뒤 바뀐 사용자 파일이나 변조된 백업은 덮어쓰지 않고 거절한다.
코드서빙·워크플로우 리비전과 환경변수는 각각 이전 값으로 복귀한다.
새 데이터 generation은 필요 없다. 이전 코드/환경/원문은 보존된다.

로컬 검증은 모의 데이터의 계약·호출 시간 전달·오류 분류·설치기 및 코드 ZIP 결속이다.
외부 모델 호출이나 성능 비교 실험을 하지 않았다. GENOS 배포·실제 내부 데이터
응답과 300초 HTTP 500 해소는 현장 기록이 돌아오기 전까지 미확인이다.

## 로컬 검증 기록

관련 검사 153개 통과. 확대 검사에서 남은 5개 실패는 시간 기본값을 변경 전으로
되돌리고 엔진 pin을 대조한 격리 복사본에서도 같은 원인으로 재현됐다.
문서/후보 순위, 테스트 단독 import, task max_actions 계약, 참조 적용의
fulltext/navigation 결속이며 상세 출력은 감사 폴더에 보존한다.
이 경로 전체의 통과나 GENOS 현장 성공을 인증하지 않는다.
현재 `run_tool.py genos_call.sh`도 현재 도구로 연결해 과거 고정 세대의 300초 기본값을 피한다.

## 현장 사진의 용어집 결속 오류 — 2026-09-28

사용자 사진에서 `resources.glossary` 준비 중 `glossary compiler/cache binding mismatch`,
그 뒤 `legal-agent internal contract failed`와 HTTP 500을 확인했다.
이 요청은 용어집 준비 단계에서 중단됐으며 사진은 해당 요청의 모델 호출 성공을 입증하지 않는다.

시간 통합 변경은 `full_glossary.py`의 FullGlossaryAgent 기본값·상한을 150에서 1800으로
바꾸면서 전체 파일 SHA256을 `ba2c6ced8da72307934e627a7a7508fb29da45e35d09fc3e0a116884a0a5d058`
에서 `5b3e117aa1e8877568f4ff9c9efcad08c1cace071d7a8915b44d4d562b9b177b`로 바꿨다.
`glossary_assets`는 캐시 receipt의 `compiler_sha256`과 이 파일 전체 해시를 비교한다.
변경 전 해시에 결속된 모의 receipt와 현재 코드로 사진과 같은 오류를 로컬 재현했다.
사진만으로 현장 receipt 해시·배포 커밋·실제 선택 generation은 확정하지 않는다.

위의 “새 데이터 generation은 필요 없다”는 설명은 기존 용어집 캐시와 컴파일러가
일치하는 경우에만 적용한다. 엔진 rehash는 이 캐시 결속을 갱신하지 않는다.
[읽기 전용 진단 TXT](../../../08_DEPLOYMENT/GENOS/diagnostics/GENOS_GLOSSARY_COMPILER_CHECK_20260928.txt)로
코드서빙이 선택한 정확한 generation과 배포 checkout의 두 해시를 확인한다.
불일치가 확인되면 검증한 백업의 정확한 컴파일러 바이트로 복구하거나 새로운 결속 세대를
만들고 release gate를 통과해야 한다. 기존 manifest·receipt의 해시를 수동 덮어쓰지 않는다.
컴파일러 복구 시 다른 실행 경로의 시간 설정도 다시 확인한다.

진단 도구의 모의 일치·컴파일러 불일치·receipt 변조 세 경우를 확인했다.
이번 진단에서 서빙 코드·데이터·CURRENT·배포 리비전은 변경하지 않았다. 현장 복구는 미확인이다.

## R2 캐시 호환 복구와 generation 경로 설명

R2는 `full_glossary.py`를 변경 전 정확한 바이트/해시로 복구한다. 현재 Pipeline에는
옛 FullGlossaryAgent 구현 선택이 없으므로 해당 클래스의 150초 숫자는 실제 v5 요청의
1800초 예산에 관여하지 않는다. 캐시/manifest/CURRENT 검증은 유지한다.
기존 compiler 해시에 결속된 모의 캐시와1800초 v5를 함께 열어HTTP200 및 데이터 불변을 확인했다.
관련154개 검사 통과이며 현장 해시/질문 성공은 별도다.

`generation`은 서빙 데이터 폴더이며 새로 생성하라는 의미가 아니다. 코드서빙 환경의
GENOS_GENERATION 값을 그대로 사용한다. 없으면 GENOS_DATA_ROOT/generations/CURRENT.json의
path를 읽는다. 실제 선택은 binding.resolved의 generation_path에서 확인한다.
워크플로우 환경과 코드스페이스 셸은 코드서빙 환경과 자동 공유되지 않는다.
로그 저장 rag-request-reports 경로와 ~/DEV 코드 루트는 generation이 아니다.
상세 설명과 실행 순서는 [R2 인계 설명](../../../08_DEPLOYMENT/GENOS/handoffs/timeout_20260928_r2/README.txt)을 따른다.

## R3 자동 적용과 검사

[자동 적용 설명](../../../08_DEPLOYMENT/GENOS/handoffs/timeout_20260928_r3/README.txt)을 따른다.
`bash 8agent-genos-timeout-sync-20260928-r3_APPLY.txt` 한 실행에서 기존 checkout 백업 적용,
기존 데이터 선택값 확인, 용어집 코드 해시 검사, generation E2E/verify_assets를 수행한다.
배포 gate도 generation 인자가 없으면 동일 자동 확인을 사용한다.
서빙의 기존 세대 선택과 환경값은 유지한다. 코드스페이스에 설정/포인터/검증 자료가 없을 때는
코드 적용 완료와 데이터 미확인을 분리하며 임의 세대를 선택하거나 PASS를 만들지 않는다.
날짜순 탐색, 캐시 삭제/자동 빌드, 데이터 manifest/CURRENT 갱신, 모델 호출은 하지 않는다.
