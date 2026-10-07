# 초반 로딩·FULLTEXT 로그 분리 — 2026-09-28 R1

기존 요청 JSON/실시간 LOG/읽기용 TXT/컨테이너 JSONL에서 로딩과 FULLTEXT 계측만
분리한다. 새 검색·모델 호출·성능 비교 실험은 수행하지 않는다. 기존 코드서빙,
PIPELINE/엔진 pin, generation, CURRENT, 로그 원본을 변경하지 않는다.

구현은 `08_DEPLOYMENT/GENOS/diagnostics/06_bottleneck_report.py`이며 배포되는
파일은 이 소스를 포함한 `GENOS_BOTTLENECK_20260928_R1.txt` 한 개다.
표준 라이브러리만 사용하고 기존 파이프라인을 import하거나 우회 실행하지 않는다.

GENOS 코드스페이스의 기존 checkout에서 실행한다.

```bash
cd -P ~/DEV
bash TRANSFER/GENOS_BOTTLENECK_20260928_R1.txt
```

기본 입력은 `GENOS_SHARED_LOG_DIR` 또는 기존 공유 경로
`/nfs-root/diamo/8-agent/rag-request-reports`다. 한국 날짜/팀 폴더와 과거 날짜
폴더를 모두 읽으며 최근 입력 10개를 고른다. JSON과 같은 이름의 LOG/TXT는
중복 집계하지 않는다. 팀·날짜·요청 또는 특정 입력을 명시할 수 있다.

```bash
bash TRANSFER/GENOS_BOTTLENECK_20260928_R1.txt --team risk_team --limit 5
bash TRANSFER/GENOS_BOTTLENECK_20260928_R1.txt --day 2026-09-28 --request-id REQUEST_ID
bash TRANSFER/GENOS_BOTTLENECK_20260928_R1.txt --input /실제/요청.json
bash TRANSFER/GENOS_BOTTLENECK_20260928_R1.txt --input /실제/컨테이너.jsonl
```

출력은 `~/DEV/TRANSFER/bottleneck-reports/<UTC시각-고유번호>/`의 `요약.txt`와
요청별 `로딩.txt`, `FULLTEXT.txt`다. `--output`으로 결과 상위 경로를 지정할 수 있다.
별도 `execution/EXTRACT_*.txt`에는 시작부터 실행 상태·결과 위치·exit_status가
남는다. 재실행은 기존 결과를 덮어쓰지 않는다. 입력 선택·계측 부재 시 실패 요약과
종료 코드 2를 남긴다. 질문·본문·프롬프트·모델 답변은 출력하지 않는다.

로딩 순위는 첫 모델 시작 이전의 기존 완료 계측을 사용하며 이후 준비는 별도
목록에 둔다. request.started와 session.resources.ready가 같은 요청에서 확인될
때만 그 사이 시간을 표시한다. 이 값은 서버 최초 기동 전체 시간이 아니다.
구간·내부 계측이 중첩되므로 합계를 만들지 않는다. 캐시 상태는 자원별 관측이며
서로 다른 worker의 준비 완료를 합치지 않는다.

FULLTEXT는 tokenize/scope/rank/SQL fetch/위치 SQL/JSON 변환/preview와 CPU,
프로세스 동시 검색 수를 구분한다. 누락된 항목은 미확인으로 표시한다.
벽시계-CPU 차이를 NFS 원인으로 확정하지 않으며 fulltext.cached를 검색 결과
캐시 적중으로 표시하지 않는다. 요청 ID가 없는 컨테이너 로그는 프로세스/스레드
미결속 기록으로 분리하며 동일 요청으로 추정하지 않는다.

현행 `service.py`는 WARMUP에 공유 보고서 쓰기를 하지 않는다. 해당 준비 작업을
분리하려면 저장한 컨테이너 로그를 `--input`으로 읽는다. 세부 step 로그는 기존
`GENOS_LOG_LEVEL=DEBUG`에서 기록되므로 INFO뿐인 로그로 내부 시간을 복원하지 않는다.
새 현장 질의가 필요할 때는 기존 워크플로우 테스트 화면만 사용한다.

완료 이벤트가 없는 step과 SQL 검색은 별도로 표시한다. 마지막 기록 시각까지의
관측 간격만 표시하며 현재 실행 중인지, 종료 로그가 누락됐는지는 확정하지 않는다.

WSL 환경 검사, 독립 실행 TXT의 bash 문법 검사, JSON/LOG/TXT/JSONL 입력과
요청/팀 분리·중첩·원본 보존·민감 본문 제외·실패 상태·독립 TXT 실행 계약을 확인했다.
GENOS 현장에서 실행한 결과나 병목 해소는 아직 미확인이다. 이 전달은 읽기 전용
검사 도구이므로 Git push·코드서빙 리비전 배포·세대 gate를 요구하지 않는다.

이번 독립 도구 계약 12개 통과. 기존 `test_genos_diagnostics_bundle.py`도 확인해
3개 통과/1개 실패를 기록했다. 실패는 기존 `format_readable_report`의 검색 행동
문자열이 예전 `tool=search ...` 기대값과 다른 것으로, 해당 formatter와 테스트는
이번 변경에서 수정하지 않았다. 저장소 전체 회귀 통과로 보고하지 않는다.
