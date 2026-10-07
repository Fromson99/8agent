GENOS 요청별 실행 기록 검사 도구 — 2026-09-23

2026-09-28 추가: 초반 로딩 / FULLTEXT 전용 TXT 분리
- GENOS_BOTTLENECK_20260928_R1.txt 한 개를 ~/DEV/TRANSFER에 둡니다.
- cd -P ~/DEV && bash TRANSFER/GENOS_BOTTLENECK_20260928_R1.txt
- TRANSFER/bottleneck-reports/<시각-고유번호>/요약.txt와 요청별 로딩.txt/FULLTEXT.txt를 봅니다.
- 특정 로그는 --input /실제/요청.json, 팀은 --team risk_team으로 고릅니다.
- 기존 JSON/LOG/TXT/컨테이너 JSONL을 읽습니다. 코드서빙 재배포와 데이터 재구축은 없습니다.
- WARMUP은 공유 요청 기록이 없어 저장한 컨테이너 로그를 --input으로 지정합니다.
- 세부 계측이 없는 항목은 미확인이며 중첩 구간을 합산하지 않습니다.
- 구현: 06_bottleneck_report.py. 실행 TXT에는 같은 코드를 포함합니다.

목적
- 코드서빙에서 공유 NFS에 쓴 genos-request-report-v1 JSON을 코드스페이스에서 읽습니다.
- 모델 호출, 색인, 코드서빙 설정 변경을 하지 않습니다. Python 표준 라이브러리만 사용합니다.
- 기본 출력에는 질문, 원문, 시스템/사용자 프롬프트, 모델 답변, 인증키를 넣지 않습니다.

설치
1. genos-request-report-diagnostics-20260923-r3.zip을 ~/DEV/TRANSFER에 올립니다.
2. GENOS 코드스페이스 터미널에서 다음을 실행합니다.

   cd -P ~/DEV
   python3 -m zipfile -e TRANSFER/genos-request-report-diagnostics-20260923-r3.zip TRANSFER

검사 명령

   python3 TRANSFER/request-report-diagnostics/04_shared_storage.py
   python3 TRANSFER/request-report-diagnostics/01_latest_status.py --limit 5
   python3 TRANSFER/request-report-diagnostics/02_model_rejection.py
   python3 TRANSFER/request-report-diagnostics/03_agent_flow.py
   python3 TRANSFER/request-report-diagnostics/05_team_data_access.py

특정 요청은 --run-id <32자리 run_id>를 02/03에 추가합니다.
요청 파일 경로가 다르면 모든 명령에 --root <공유 JSON 상위 디렉터리>를 추가합니다.

02_model_rejection.py는 기본으로 가장 최근의 실제 모델 실패 요청을 찾습니다.
--newest를 붙이면 실패 여부와 관계없이 가장 최근 요청을 선택합니다.
기본 출력: HTTP 상태, 오류 type/code/param, 메시지 해시와 길이,
요청 모델/토큰/JSON schema 설정, 프롬프트 글자 수만 표시합니다.
실제 모델 오류 문구가 필요하면 현장 화면에서만 아래 옵션을 사용합니다.

   python3 TRANSFER/request-report-diagnostics/02_model_rejection.py --show-message

오류 문구에 내부 질문·원문이나 키가 포함됐는지 확인한 뒤 외부 공유 전에 가리십시오.
보고서 JSON 원본에는 내부 질문·원문·프롬프트·모델 응답이 들어 있으므로 외부 반출하지 않습니다.

검사 결과 해석
- 400/BadRequestError: 모델이 요청을 거절했습니다. 연결 성공이나 답변 품질 성공이 아닙니다.
- journal.status=NOT_FOUND: 실행 journal을 보고서 생성 시점에 찾지 못했습니다.
- 04 결과는 코드스페이스의 읽기 권한만 확인합니다. 코드서빙의 쓰기 권한은
  코드서빙 컨테이너 로그의 shared_report.written 또는 shared_report.failed로 확인합니다.
- 02에서 모델 오류 문구 없이 원인을 특정하지 않습니다. max_tokens나 JSON schema를
  추측으로 바꾸지 말고 실제 오류 type/code/param/message와 요청 설정을 대조합니다.

팀·데이터 접근 확인
- 05는 가장 최근의 성공적인 LEGAL_AGENT 요청을 고릅니다. request의 team_id,
  실제 query 문서 범위, 원문 evidence가 저장된 문서, 사용한 도구 상태를 구분합니다.
- team_id가 없으면 NO_TEAM_FILTER입니다. 워크플로우 TEAM_ID가 설정돼 있으면
  코드서빙에 전달된 최종 team_id가 요청 기록에 들어 있어야 합니다.
- 보고서의 generation_id/store_sha256와 일치하는
  /nfs-root/diamo/8-agent/term-releases/*/*/generation을 찾으면 읽기 전용으로
  store.sqlite의 팀별 문서 수·이름을 보여줍니다. 자동 탐색 후보가 없거나 여러 개면
  코드서빙 환경의 정확한 GENOS_GENERATION을 --generation에 지정합니다.

   python3 TRANSFER/request-report-diagnostics/05_team_data_access.py \
     --generation /nfs-root/diamo/8-agent/term-releases/<run>/<reviewed-or-unreviewed>/generation

- 출력의 generation_catalogue.store_sqlite_read는 코드스페이스의 파일 읽기 확인입니다.
  source_text_evidence_count는 해당 코드서빙 요청에서 실제 원문 조각을 저장한 수입니다.
  팀 선택은 검색 범위이며 사용자의 접근권한 부여가 아닙니다.
- 현장 코드서빙의 /v1/rag/teams 및 /v1/rag/documents?team_id=<팀명>도
  선택된 세대의 현재 목록을 반환합니다. 공유 NFS 경로만으로 팀 필터가 켜지지 않습니다.

이 도구는 기록된 실행을 읽을 뿐, 모델의 숨은 사고 과정이나 현장 정답률을 인증하지 않습니다.
