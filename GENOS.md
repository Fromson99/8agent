# GENOS — 질문과 작업의 진입점

2026-10-14 사용자 경로 정정: 현장 업로드 폴더는 사용자가 열어 둔 **`TRANSFER`**이며,
그 폴더에서 `./GENOS_URLLIB_TLS_20261014_R1.zip`처럼 **현재 위치 기준 상대경로**로 실행해야 한다.
이 폴더의 절대 위치를 `~/TRANSFER`로 가정한 기존 안내 때문에 사진의 FileNotFoundError가 발생했다.
사용자는 경로를 직접 수정해 실행했다고 보고했다. 앞으로 압축 해제·설치기 실행을 위해 `DEV`로
이동시키지 않으며, 설치기의 실제 코드 적용 대상인 기존 Git checkout과 실행 위치를 구분한다.
예시는 `python3 -m zipfile -e ./GENOS_URLLIB_TLS_20261014_R1.zip ./urllib-tls-r1-package`와
`bash ./urllib-tls-r1-package/GENOS_URLLIB_TLS_20261014_R1_RUN.txt check`/`apply`다.
재실행 요청은 없으며 기존 봉인 ZIP·메일 첨부·가이드는 발송 당시 이력으로 보존한다.
실행 로그/적용 receipt·commit·코드서빙 리비전·내부 모델 성공은 이 보고에 포함되지 않았다.
[현장 보고 기록](08_DEPLOYMENT/GENOS/handoffs/urllib_tls_20261014_r1/FIELD_PATH_CORRECTION_20261014.json).

2026-10-14 사용자 요청으로 승호 최신 `integration` `6b3ec4789`와 10월8일 `2e33171ac`의
모델 전송을 대조하고 [urllib 전환 R1](08_DEPLOYMENT/GENOS/handoffs/urllib_tls_20261014_r1/GUIDE_UTF8.txt)을 완성했다.
작업 코드에는 있던 urllib 전환이 기존 GENOS 인계본에 빠져 있었으며, 이번에는 공통 모델 목록/JSON/임베딩과
에이전트/AD/답변 SSE의 전송 3파일을 동일 검증 바이트로 결합했다. Python 기본 CA 및 `SSL_CERT_FILE`/`SSL_CERT_DIR`,
인증서·호스트명 검증을 사용하고 기존 deadline·단일 전송·스트림 종료·오류 원장·입력 계측·예산·캐시를 보존한다.
AD_REQUEST_LOGS R2+GAP_ACTION R2 이후2640종(성공 shortcut/공개 안내/입력 계측 유무)의 inventory와 helper pin30개를 결속했다.
설치본224계약·실제 RUN100명령/4조합·원복4회/변조거부8회·동일 committed checkout 모의 generation gate4회 통과.
기존 모의 부팅4회와 실제 localhost TLS `service.service` 부팅 성공4회/미신뢰 인증서 거부4회를 확인했다.
작업 확대70개 중66통과/4실패는 변경하지 않은 워크플로우의 공개 오류 표시 기대 불일치이며 기록을 보존한다.
검사 fixture의 생성용 스키마/모듈 누락도 보완하고 초기 실패를 보존했다. 실제 GENOS/외부망/모델 추론0회다.
3파일은 작업/선택 MAIN61/인계 설치본 해시가 같고 로컬 MAIN61 포인터 및 외부 Qwen adapter는 유지했다.
**이전 패치들과 함께 적용할 때 이번 URLLIB_TLS R1을 마지막에 기존 ~/DEV에 적용하고 새 리비전 배포·SSE 재시작이 필요하다.**
원문 재구축·워크플로우 편집기 교체는 없다. 현장 CA 설치/실행 환경·반입·배포·내부 모델 성공은 미확인이다.
[검증](08_DEPLOYMENT/GENOS/handoffs/urllib_tls_20261014_r1/VALIDATION.json) · [승호/MAIN 비교](08_DEPLOYMENT/GENOS/handoffs/urllib_tls_20261014_r1/COMPARISON.json).
삼성메일 SENT `1a138af52daf4d34`로 ZIP/독립 RUN/적용 안내/검증 요약/상세 검증/해시6첨부를 발송하고 수신자·제목·파일명·정확한 크기를 재확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/urllib_tls_20261014_r1/EMAIL_SENT.json).

2026-10-14 사용자 사진의 `source-law-navigation-2 / finish_reason=length`와 최종 실패 로그 누락을 조사하고 [입력 계측·실패 로그 R1](08_DEPLOYMENT/GENOS/handoffs/model_input_metrics_20261014_r1/GUIDE_UTF8.txt)을 준비했다. 사진은 조사 제안의 길이 종료이며 실제 입력 컨텍스트 초과와 수정 요청 이후 최종 중단 위치는 미확정이다. 호출별 메시지 문자/UTF-8·스키마 크기·실제 usage·출력 상한 대조를 연결했다. `FINAL RESPONSE / ANSWER`가 공개 실패의 `message/answer_status/failure_reason`을 누락하던 문제와 공개 응답에서 사라진 `run_id` 때문에 상세 보고서가 원장을 찾지 못하던 연결을 수정했다. 같은 요청 이벤트로만 원장을 찾고 비동기 `SERVICE OUTCOME`을 기록한다. 출력 한도·모델·재시도·근거 검증·답변 정책은 유지한다. 작업 확대157통과/9실패이며 수정 전 격리 코드에서도 같은9실패를 재현했다. 설치본80계약·실제 RUN94명령/설치·재실행·변조거부·원복4조합·서비스부팅8회·같은 committed checkout 모의 generation gate4회를 통과했다. AD_REQUEST_LOGS R2와 GAP_ACTION R2 이후1320종 선행 inventory(성공 shortcut/공개오류안내 유무 포함)를 지원한다. **기존 ~/DEV 적용, 새 코드서빙 리비전 및 SSE 재시작이 필요하며 원문 재구축·편집기 교체는 없다.** [원인과 한계](08_DEPLOYMENT/GENOS/handoffs/model_input_metrics_20261014_r1/FINDINGS_UTF8.txt) · [검증](08_DEPLOYMENT/GENOS/handoffs/model_input_metrics_20261014_r1/VALIDATION.json). 작업 코드/인계본 상태이며 로컬 선택 MAIN61은 유지했다. 삼성메일 SENT `1a1388513820ee7a`에서 ZIP/독립 실행TXT/패치노트/적용 안내/검증/해시6첨부의 수신자·제목·파일명·크기를 확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/model_input_metrics_20261014_r1/EMAIL_SENT.json). GENOS 반입·배포·내부모델 재질의 성공은 미확인이다.

2026-10-14 사용자 현장 확인으로 **Jupyter ORDS 연결 오류를 해결**했다. 사용자는 인증값 철자 오류를 수정했다고 보고했고, R6 노트북의 04 연결 확인(화면 시각 10:54:27)에서 `PASS`, `OK=1`, `LOGIN_USER=CURRENT_SCHEMA=BAIP04APP`, `address_mode=SDK_DEFAULT`를 확인했다. ORDS 별칭은 `b04`이며, 세션 환경변수와 SDK 실제 주소는 모두 `http://172.27.43.141:8080/ords/`다. 제공된 담당자 안내의 토큰 URL과 SQL URL도 이 서버의 `b04` 경로다. 이전 `HTTP 401 / invalid_client`는 사용자 보고상 인증값 오타로 해결됐으며, 주소 변경은 해결 근거가 아니다. 정확히 수정한 문자와 인증키 원문은 기록하지 않았다. `.http` 속성 오류는 별도로 잘못 안내한 진단 경로이며 실제 경로는 `dw_client.sql._http._client.base_url`이다. **현재 확인 범위는 R6 연결 및 SELECT 성공**이고 테이블 생성·쓰기·VDB·배치 성공은 아직 미확인이다. 기존 인증값을 다시 로드하지 않고 연결에 성공한 `desk`를 사용해 R6의 09 생성·검증 셀을 실행하는 [현장 절차](09_ARTIFACTS/AUDITS/20261014-dongwoo-ords-latest/TABLE_CREATE_STEPS_20261014.txt)를 정리했다. [해결 기록](09_ARTIFACTS/AUDITS/20261014-dongwoo-ords-latest/AUTH_RESOLUTION_20261014.json). 이 기록은 사용자 제공 화면 근거이며 Codex가 내부망에 접속한 결과가 아니다.

2026-10-14 예외 안내 통합을 **로컬 MAIN61 `public-failure-guidance-20261014-r1`**에 반영했다. 권한·상태 충돌·입력 분량·요청 제한·서버/전송·시간 초과·처리 한도·사전 점검/표시 예외를 공통 법률 검토 안내와 짧은 오류 코드로 표시하고 실패 상태와 내부 진단을 보존한다. 합성2400조합·관련298계약, 작업/검증/선택301파일 및 실제 WSL `service.service` 정상조회와503/timeout/limit를 확인했다. [GENOS 인계 R1](08_DEPLOYMENT/GENOS/handoffs/public_failure_guidance_20261014_r1/GUIDE_UTF8.txt)은 GAP_ACTION R2 이후990종 선행 inventory를 지원하며, 설치본337계약·독립 편집기15검사·설치/원복6상태·서비스 부팅12회·동일 committed checkout 모의 generation gate6회를 통과했다. 기존 캐시/예산/로그 설정을 보존한다. **새 코드서빙 리비전·SSE 재시작과 워크플로우 PASTE_ALL 편집기 저장이 모두 필요하다.** 원문 재구축은 없다. 삼성메일 SENT `1a137d9a5f150ea7`에서 ZIP/실행TXT/편집기TXT/안내/검증요약/해시6첨부를 재확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/public_failure_guidance_20261014_r1/EMAIL_SENT.json), [MAIN 반영 기록](04_EXPERIMENTS/ADR/ADR-0775-public-failure-main/MAIN_RESULT.txt). 오류 발생 원인 해결·GENOS 현장 배포/내부모델 검증은 별도이며 기존5회귀·전역graph8오류(추가0)·구엔진6종 stale pin은 남아 있다.

2026-10-13 후속 사용자 승인으로 원문 gap 행동 충돌 수정을 **로컬 MAIN60 `assessment-gap-action-20261013-r1`**에 반영했다. 고정952조합·관련353계약과 실제 선택301파일/로컬 service.service HEALTH·검색200을 확인했다. [GENOS R2](08_DEPLOYMENT/GENOS/handoffs/assessment_gap_action_20261013_r2/GUIDE_UTF8.txt)는 R1과 같은3파일 수정에 최근 SUCCESSFUL_SHORTCUT R1 선행 상태를 추가 지원한다. 두 패치를 함께 설치할 때는 shortcut R1 다음에 gap R2를 적용한다. 기존660종과 추가330종의 정확한 선행 inventory를 연결하며 원문 재구축·편집기 교체는 없다. [MAIN 반영 기록](04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main/MAIN_RESULT.txt). 전역 복구 구현·기존4실패·GENOS 현장 적용은 미완료/미확인이다. 삼성메일 SENT `1a1347c3bd4716f6`에서 R2 ZIP/독립 실행TXT/안내/검증요약/해시5첨부를 재확인했다. ZIP에 실패 코딩 지침과 MAIN 결과도 포함했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/assessment_gap_action_20261013_r2/EMAIL_SENT.json).

2026-10-13 사용자 사진에서 ASSESS의 `A legal source gap requires source research, not REQUEST_FACT.`를 확인했다. 원문 gap의 종류/대상/사유를 보존하며 잘못된 행동만 기존 원문 조사로 연결하는 [수정 R1](08_DEPLOYMENT/GENOS/handoffs/assessment_gap_action_20261013_r1/GUIDE_UTF8.txt)을 준비했다. 모델의 두 번째 거절 상세는 사진에 없으므로 모든 422의 해결로 보지 않는다. 작업 신규63계약·API, 설치본342계약, 설치4상태/부팅8회/같은 committed checkout 모의 generation gate4회와 알려진 선행660 inventory를 확인했다. 확대276통과/복구4실패는 수정 전 3파일 복원 코드에서도 동일하며 별도 후속으로 남겼다. [검증](08_DEPLOYMENT/GENOS/handoffs/assessment_gap_action_20261013_r1/VALIDATION.json). 기존 MODEL_STREAM_FIX R1 또는 AD_REQUEST_LOGS R2가 적용된 `~/DEV`에 적용하며, 새 코드서빙 리비전과 별도 SSE 재시작이 필요하다. 원문 재구축·편집기 교체는 없다. **사용자 요청의 [에이전트 실패·충돌·스키마 코딩 지침](07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md)을 AGENTS.md에 필수 기준으로 연결**했다. 전역 복구 체계 전체의 구현 완료는 아니며 남은 항목은 BL-010이다. 선택된 로컬 MAIN59의 3파일에는 이 수정이 없음을 해시로 확인했고 본 작업에서 승격하지 않았다. 메일 발송·GENOS 반입·배포·워크플로우 성공은 미실행/미확인이다.

2026-10-13 정상 완료 shortcut 정책과 공통 AD 페이지 이동을 **로컬 MAIN59 `successful-shortcut-20261013-r1`**에 반영했다. 최종 답변 게시 성공·현재 route/revision·비어 있지 않은 근거 답변을 확인하고, 실패 원장은 보존한다. 위키 컴파일/재사용도 성공 기록에 결속하며 의미적 정답 자동 승격은 없다. 36상태 조합, 후보/작업 각각169계약, 선택301파일과 실제 service.service HEALTH/RAG_SEARCH200을 확인했다. GENOS 현장 배포는 별도이며 [전체 실행 안내](08_DEPLOYMENT/GENOS/handoffs/successful_shortcut_20261013_r1/GUIDE_UTF8.txt)를 따른다. [MAIN 결과](04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication/MAIN_RESULT.txt).

삼성메일 SENT `1a13476887c28e71`로 SUCCESSFUL_SHORTCUT R1 ZIP·독립 RUN·가이드·검증요약·해시5첨부를 발송하고 수신자/제목/첨부 이름·크기를 확인했다. 실제 인계 RUN으로 설치6상태/서비스12회/동일 committed checkout 모의 generation gate6회, 설치 코드278계약을 통과했다. **AD_REQUEST_LOGS R2가 성공한 기존 ~/DEV에 추가 적용**하고 새 commit/push·코드서빙 리비전·SSE 재시작이 필요하다. 원문 재구축·워크플로우 편집기 교체는 없다. 과거 성공 기록은 안내의 명시적 backfill 검증 후에만 복원한다. [검증](08_DEPLOYMENT/GENOS/handoffs/successful_shortcut_20261013_r1/VALIDATION.json) · [발송](08_DEPLOYMENT/GENOS/handoffs/successful_shortcut_20261013_r1/EMAIL_SENT.json).

2026-10-13 사진의 `AD_REQUEST_LOGS R1 / Unknown code bytes; preserved: service.py`를 기존 조사 예산 R1이 적용된 코드에서 재현했다. 전체 inventory는 승인된 예산 코드를 정규화하지만 개별 service.py 비교는 원본 바이트를 사용한 **R1 설치기 결함**이다. 사진은 코드 교체 전 실패이며 두 팀으로 재시도한 push 성공과 구분한다. [설치기 수정 R2](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r2/GUIDE_UTF8.txt)는 정확히 검증한 예산 코드만 비교 시 정규화하고 결과에는 보존하며, 실제 출력 해시를 기록한다. 제품 코드 payload는 R1과 동일하고 미확인 수정 거부는 유지한다. 경계 검사8개, 예산 유무를 포함한 설치6상태/119명령·서비스 초기화12회·동일 committed checkout 모의 generation gate6회, 예산 코드가 있는 설치본 계약416개 통과. R1 실패3회와 변조 거부12회를 포함하며 실제 모델 추론0회다. 삼성메일 SENT `1a13416c503e1958`의 ZIP/독립 RUN/안내/검증요약/해시5첨부를 확인했다. **사진처럼 R1이 실패한 기존 ~/DEV에는 AD_REQUEST_LOGS R1 대신 R2 설치 파일을 사용**한다. 별도 R1 undo는 불필요하며 적용 후 새 commit/push·코드서빙 리비전·SSE 재시작이 필요하다. 원문 재구축·편집기 교체는 없다. 로컬 MAIN/제품 작업 코드 변경은 없고 GENOS R2 반입·배포·화면 및 원래 AD 모델 HTTP 오류 해결은 미확인이다. [재현](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r2/REPRODUCTION.json) · [검증](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r2/VALIDATION.json) · [발송](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r2/EMAIL_SENT.json).

2026-10-13 후속 요청으로 [팀별 실행 로그·AD 모델 계약 R1](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r1/GUIDE_UTF8.txt)을 작성·검증하고 삼성메일 SENT `1a133ea1f1b744cc`로 수정 ZIP/독립 RUN/안내/검증요약/해시 첨부5개를 발송했다. 공유 로그는 기존 날짜/팀 아래 `legal_agent/`와 `ad_mode/`로 나누며 AD의 실제 전송 요청·HTTP 오류 원문·해석/변경 기록을 같은 요청 보고서로 내보낸다. AD SQL은 실행 중 원장으로 유지하고 공유 파일은 완료 후 비동기로 생성한다. legal_agent에만 있던 전송 스키마 `uniqueItems` 제거를 공통 모듈로 옮겨 AD에도 적용했고, 원래 스키마 검증은 유지한다. 사진의 HTTP 오류 원인 자체는 아직 미확정이다. 작업 계약116개·설치 코드 계약416개, 대표3상태/58명령·초기화6회·동일 committed checkout 모의 generation gate3회 통과, 실제 모델 추론0회다. 별도 숫자 인용 schema-repair 검사1개는 수정 전후 동일 실패로 기록했다. **MODEL_STREAM_FIX R1이 적용된 기존 ~/DEV에 추가 적용**하고 새 코드서빙 리비전과 별도 SSE 재시작이 필요하다. 원문 재구축·편집기 교체는 없다. 작업 코드·인계본 반영이며 로컬 MAIN58 선택 릴리스에 이 패치를 승격하지 않았고, GENOS 실제 반입·배포·화면 성공은 미확인이다. [검증](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r1/VALIDATION.json) · [발송](08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r1/EMAIL_SENT.json).

2026-10-13 사진 후속 수정으로 [기관별 표시 R2](08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2/GUIDE_UTF8.txt)를 완성했다. 용어집에서 확인한 한국어 기관명 아래 번호 목록으로 모으고 `internal`은 **내부 규정**으로 표시한다. R1에 남아 있던 전체 오류 표시를 공개 이벤트 필터로 차단하며 진단 원장은 유지한다. 로컬 MAIN58 `source-provider-20261013-r2` 선택과 실제 service.service HEALTH/RAG_SEARCH200·원문12개/카드1개를 확인했다. 후보/작업 각각97계약·24조합 통과, 검증후보/선택297파일 동일. 삼성메일 SENT `1a133d8e5a42035e`의 ZIP/전체 교체TXT/안내/검증요약/해시5첨부를 재확인했다. **현장은 기존 워크플로우 편집기를 R2 TXT 전체로 교체**하며 저장/실제 화면은 미확인이다. 아래 MODEL_STREAM_FIX R1은 backend 전송 수정으로 별도 유지한다. [로컬 반영·롤백](04_EXPERIMENTS/ADR/ADR-0772-source-provider-display/MAIN_RESULT.md) · [발송](08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2/EMAIL_SENT.json).

2026-10-13 사용자 정정에 따라 설계 자료 대신 실제
[모델 스트림 종료 수정 R1](08_DEPLOYMENT/GENOS/handoffs/model_stream_fix_20261013_r1/GUIDE_UTF8.txt)을
작성·검증하고 삼성메일 SENT `1a133bf3bce67c71`로 ZIP/독립 RUN/안내/검증요약/해시 첨부5개를 발송했다.
작업 urllib와 현장 httpx에 같은 SSE 파서를 연결해 DONE 수신 시 finish_reason 누락을 허용하고,
정상 EOF의 완전한 마지막 프레임을 처리한다. DONE 없는 EOF·실제 중단·length/content_filter·
원격 오류는 실패로 유지하며 종료 진단을 원장에 저장한다. 기존 JSON/근거/본문 일치 검증은 유지한다.
로컬 계약115개, 현장 설치 코드 계약284개, 대표3상태/55명령·부팅6회·동일 committed checkout의
모의 generation gate3회와 알려진 narrative R2 inventory330종을 확인했다. 실제 모델 호출0회다.
기존 R2가 적용된 ~/DEV에 백업 후 적용하며 원문 재구축·편집기 교체는 없고 새 코드서빙 리비전과
별도 SSE 서버 재시작이 필요하다. 작업 코드와 인계본은 수정됐지만 현장 반입·배포·화면은 미확인이다.
이 작업은 로컬 선택 포인터를 바꾸지 않았다. 발송 전 확인한 별도 작업의 MAIN57
`source-cards-20261013-r1`에는 이번 전송 수정이 포함되지 않았다.
[검증](08_DEPLOYMENT/GENOS/handoffs/model_stream_fix_20261013_r1/VALIDATION.json) ·
[발송 확인](08_DEPLOYMENT/GENOS/handoffs/model_stream_fix_20261013_r1/EMAIL_SENT.json).

2026-10-13 후속 요청으로 법령 경로·원문 로그 묶음의 **로컬 MAIN57** 연결까지 완료했다.
MAIN56의 일반5단계 요약에서 사라지던 source activity를 표시 소비자에 전달한다.
합성24조합·후보/작업 각각48계약, 검증/작업/선택297파일과 실제 service.service
HEALTH/RAG_SEARCH200·선택 모듈의 원문12개/카드1개를 확인했다.
[전체 반영·한계·원복](04_EXPERIMENTS/ADR/ADR-0771-source-cards-main-wiring/MAIN_RESULT.md).
기존 [편집기 표시 R1](08_DEPLOYMENT/GENOS/handoffs/workflow_source_cards_20261013_r1/GUIDE_UTF8.txt)의
ZIP·전체 교체 TXT·안내·검증요약·해시 첨부5개를 삼성메일 SENT `1a133ae1626ae56b`로 발송하고
수신자·제목·첨부 이름/크기를 확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/workflow_source_cards_20261013_r1/EMAIL_SENT.json).
메일 발송 당시 MAIN56 미반영 설명과 아래 미발송 기록은 당시 상태다. 봉인 R1 파일은 유지한다.
GENOS는 기존 R4 편집기를 R1 TXT 전체로 교체해야 하며 현장 저장/화면은 아직 미확인이다.

2026-10-13 사진의 검색 path 줄바꿈과 원문 확인 카드 과다를 수정한
[편집기 표시 R1](08_DEPLOYMENT/GENOS/handoffs/workflow_source_cards_20261013_r1/GUIDE_UTF8.txt)을 준비했다.
발송된 R4 편집기를 기반으로 경로를 Markdown 목록으로 분리하고 중복 제목을 없앴다.
연속된 `UNIT_READ_STARTED` 알림은 하나의 카드로 모아 다음 진행 단계 또는 답변/종료 전에
한 번 송신한다. 수신 이벤트에는 모델 호출 ID가 없어 이는 화면 알림의 묶음이며
동일 LLM 호출이나 모델 입력 완료를 증명하지 않는다. 작업 워크플로우와 인계 TXT는
같은 표시 메서드를 사용한다. 신규/연결/답변 계약60개와 정확한 편집기 계약12개 통과.
별도로 실행한 구 진행 표시 검사7개는 기존 MAIN56 파일에서도 동일하게 실패함을 확인했다.
적용은 기존 워크플로우 Python 편집기에 전체 PASTE_ALL TXT를 저장하는 단계다.
코드서빙 재배포·SSE 재시작·데이터 재구축은 필요하지 않다. 현장 편집기 저장/화면은 미확인이며
MAIN56 포인터·봉인 R4·모델 전송은 유지했다. 메일은 보내지 않았다.

2026-10-13 사용자 요청으로 승호 `integration`을 fetch하여 `4b524bdf5`, `cicd`는
`388cd3920`에서 모델/화면 스트리밍을 대조했다. 확인한 승호 경로는 모델을 일반 JSON으로
받고 진행 token과 최종 result를 화면에 보낸다. 모델 본문 추출은 finish_reason 누락만으로
실패하지 않는다. 우리 최종 작성만 `stream=true`를 켜고 `DONE AND finish_reason`을
강제하여, 사진처럼 종료 사유가 없는 이벤트는 최종 JSON/근거 검증 전에 전송 오류가 된다.
승호 화면 SSE를 모델 토큰 SSE 성공 근거로 혼동하지 않는다. 생성 중 토큰 송신 요구는
유지하며 이번 작업은 [코드 비교](09_ARTIFACTS/AUDITS/20261013-seungho-stream-comparison/COMPARISON.json)까지다.
서빙 코드·모델 설정·MAIN·현장 배포는 변경하지 않았다.
비교 요약 TXT와 commit/해시/코드 발췌 JSON을 사용자 요청으로 삼성메일
SENT `1a133aa2b150481b`에 발송하고 수신자·제목·첨부2개 이름/크기를 확인했다.
승호 경로의 token은 진행 안내이며 최종 답변은 완성 후 result/text로 전달되고,
완성 답변을 다시 토큰으로 쪼개는 구현도 확인한 경로에는 없다고 명시했다.
[발송 기록](09_ARTIFACTS/AUDITS/20261013-seungho-stream-comparison/EMAIL_SENT.json).

2026-10-13 진단 R2의 현장 실행 사진에서 `memory-compose`의 저장 SSE22개,
`content_chars=360 / content_json=parsed`, `finish_reason_counts=none_recorded`,
마지막 usage 이벤트와 model mismatch0을 확인했다. 현재 전송의 완료 조건은 DONE과
finish_reason 모두이므로 **인식된 종료 사유 부재가 직접 실패 조건**이다. 실제 서버의 종료
정보 누락과 미파싱 마지막 프레임은 아직 구분할 수 없다. DONE 수신 여부·답변 검증 성공도
미확인이다. 파일명만 넣어 발생한 FileNotFoundError 뒤 절대경로로 진단이 정상 실행됐다.
[사진 판독 기록](09_ARTIFACTS/AUDITS/20261013-model-stream-photo/FINDINGS.json).
진단 실행 확인이며 전송 수정·현장 오류 해결은 아직 수행하지 않았다.

2026-10-13 후속 사진의 `COMPOSE / MODEL_TRANSPORT_ERROR / model stream ended before completion`은
설명형 최종 작성의 내부 모델 스트림 종료 확인에서 발생했다. 사진의 `response_bytes=6069`와
`body/model/http_status=null`을 확인했으며, null은 부분 실패 전송의 저장 방식이므로 무응답의
증거가 아니다. 기존 RAW 로그 화면은 원장에 저장되는 `stream_events`를 표시하지 않는다.
[스트림 진단 R2](08_DEPLOYMENT/GENOS/handoffs/model_call_diagnose_20261013_r2/GUIDE_UTF8.txt)는
기존 요청 JSON에서 이벤트 수·종료 사유·수신 길이·JSON 파싱 여부만 요약하는 독립 RUN TXT다.
관련 단위 계약12개·단독 실행/원본 보존/덮어쓰기 거부 등12검사를 확인했다. 모델 호출·설치·
재배포는 없다. 기존 전송은 DONE/미완성 마지막 프레임을 별도 저장하지 않아 이 부분은 unknown을
유지한다. 실제 중단과 종료 형식 차이의 현장 원인은 아직 미확인이고 서빙 코드/MAIN/봉인 R2는 변경하지 않았다.
사용자 요청으로 진단 R2 ZIP·독립 RUN·안내·검증요약·해시 첨부5개를 삼성메일
SENT `1a1339b10f361e1b`로 발송하고 수신자·제목·첨부 이름/크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/model_call_diagnose_20261013_r2/EMAIL_SENT.json).
현장 진단 실행과 오류 해결은 아직 미확인이다.

2026-10-13 사용자 정정에 따라 [최종 답변 토큰 스트리밍 R2](08_DEPLOYMENT/GENOS/handoffs/rag_narrative_stream_20261013_r2/GUIDE_UTF8.txt)를 삼성메일로 발송했다. 내부 모델의 decoded text delta가 도착할 때마다 기존 SSE/워크플로우 R4로 전달하며 문장·문단 완료를 기다리지 않는다. 기존 focused RAG R3의 `~/DEV`에 이어 적용하며 미발송 narrative R1은 선행 적용하지 않는다. 원문 재구축·기존 R4 편집기 교체는 없고 commit/gate/push·새 코드서빙 리비전·별도 SSE 서버 재시작은 필요하다.

로컬 MAIN56 `token-stream-20261013-r1`의 작업/후보/선택297파일과 실제 service.service 연결을 확인했다. 전송 경계40조합·직접142계약·선택 스트리밍64계약, GENOS 설치 계약248개와 대표3상태·서비스 초기화6회·동일 committed checkout 모의 generation gate3회 통과. Shortcut AD 목록/상세/편집/중복 처리/불변 필드 보호는 로컬 실제 서비스 경로+모의 해석으로 확인했다. 실제 GENOS 내부 모델/화면 성공은 미확인이다. 외부 공개 모델 transport는 기존 buffered다. [전체 상태와 한계](04_EXPERIMENTS/ADR/ADR-0770-token-answer-stream/MAIN_RESULT.md).

SENT `1a1336fb17fd991e`에서 삼성 수신자와 ZIP/독립 RUN/안내/검증요약/해시 첨부5개의 이름·크기를 확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_narrative_stream_20261013_r2/EMAIL_SENT.json). 봉인 HANDOFF의 미발송 표시는 봉인 시점 이력이다. 실제 GENOS 반입·commit/push·선택 generation·코드서빙 리비전·워크플로우 화면은 별도 확인 대상이다.

아래 narrative R1과 MAIN54 유지 설명은 최초 준비 당시의 기록이다. 문단 스트리밍은 중간 MAIN55를 거쳐 위 토큰 스트리밍 MAIN56/R2로 갱신했다.

2026-10-13 답변이 짧고 불명확하다는 사진 피드백에 따라
[설명형 최종 답변·문단 스트리밍 R1](08_DEPLOYMENT/GENOS/handoffs/rag_narrative_stream_20261013_r1/GUIDE_UTF8.txt)을 준비했다.
기존 v8의 고정 표제 나열을 핵심 결론·짧은 소제목·구체 설명으로 작성하고, 승인된 판단과
정확한 원문을 별도 최종 작성 호출에 전달한다. 내부 모델의 SSE에서 완성된 문단의 근거 ID와
구조를 확인한 뒤 다음 문단 생성 중 송신한다. 최종 claim/인용/부족 근거와 원문은 유지한다.
최종 작성 중 부분 송신 후 실패하면 다른 응답을 재시도해 이어 붙이지 않는다.
ADR0766의 추가 단정 실패와 환경 중단된0767을 보존하고, [ADR0769](04_EXPERIMENTS/ADR/ADR-0769-narrative-main54-recovery/README.md)에서
현재 MAIN54의 위키 변경을 보존한 통합 코드의 계약63개 및 신규 공개1문항 비교·기존1문항 회귀
총3요청의 사전 기준을 확인했다. 최종 작성은 약7초가 추가됐다. 일부 반복과 범위/예외의
부정확한 표현은 별도 기록했으며 전체 의미 정확도 인증이 아니다. 외부 모델은 Qwen3.8이고
GENOS 내부 모델은 미확인이다. 작업 코드41파일(구현/설정9개·해시 연결·테스트)을 선별 통합했고
서빙297파일은 검증 후보와 동일하다. 실제 로컬 service 선택은 MAIN54 그대로이며 본 수정은 아직 활성화하지 않았다.
GENOS 인계는 기존 R3의 알려진 inventory330종에 구현/설정9개와 연결 해시를 결합한다.
대표 설치3종의52명령·서비스 부팅6회·동일 committed checkout의 모의 generation gate3회,
두 캐시 계열의 설치 계약146개를 확인했다. 스트리밍 소비자는 기존 별도 SSE 서버와 편집기R4를
대조했다. 코드 적용 후 새 코드서빙 리비전 배포와 SSE 서버 재시작이 각각 필요하다.
원문 재구축·편집기 교체는 필요하지 않다. [검증 기록](08_DEPLOYMENT/GENOS/handoffs/rag_narrative_stream_20261013_r1/VALIDATION.json).
GENOS 반입·commit/push·리비전·실제 generation hash·워크플로우 화면 성공은 미확인이고 메일은 보내지 않았다.

2026-10-13 모델 HTTP 500 원인 확인 중 전체 요청 JSON의 article/원문이 많아 읽기 어렵다는
사용자 요청으로 [모델 호출 요약 R1](08_DEPLOYMENT/GENOS/handoffs/model_call_diagnose_20261013_r1/GUIDE_UTF8.txt)을 준비했다.
기존 `genos_request_timing.py --models-only`가 저장된 요청 JSON에서 호출 단계/HTTP/입력 문자 수/
설정/스키마 지문과 직전 성공 대비 변화만 추출한다. 원문·프롬프트·답변은 출력하지 않는다.
독립 RUN TXT/ZIP의 모의 3호출 실행, 원본 보존·출력 덮어쓰기 거부, 계약7개를 확인했다.
코드서빙 재배포·모델 호출은 없으며, 실제 현장 실행과 500의 내부 원인은 미확인이다.

2026-10-13 후속 사진6장의 `SELECT / TypeError / HTTP 500`은
`UnitFulltextIndex.article_groups_page()`가 `unit_keys`를 받지 못해 중단된 기록이다.
R1이 범위 제한 검색 호출을 옮기면서 대응 `unit_fulltext.py`를 누락했고 R2에도 남은
인계 결함을 확인했다. [수정 R3](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r3/GUIDE_UTF8.txt)는
R1·R2가 적용된 기존 `~/DEV`의 알려진 inventory330종을 확인한 뒤, 캐시2계열을 보존하며
MAIN53의 범위 필터·권한 교집합·페이지 커서 결속과 엔진/PIPELINE 해시를 연결한다.
대표 설치3종에서 실제 `article_menu`의 동일 오류 재현/R3 통과, 적용 전후 서비스 초기화200,
55명령·재실행·변조 거부·원복·동일 committed checkout의 모의 generation gate3개를 확인했다.
설치 코드의 구조 탐색/SEARCH_BODY/캐시 회귀70개도 통과했다. 실제 통신/모델 추론0회다.
R2 검증은 초기화까지 확인해 이 SELECT 연결 누락을 발견하지 못했다. 원문 재구축·워크플로우
편집기 교체는 필요하지 않고 로컬 MAIN53 포인터는 유지했다. 이전 봉인 R1·R2는 보존한다.
[검증 기록](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r3/VALIDATION.json).
사용자 요청으로 R3 ZIP·독립 RUN TXT·안내·검증 요약·해시 첨부5개를 삼성메일
SENT `1a132d6eb196f40a`로 발송하고 수신자·제목·첨부 이름/크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r3/EMAIL_SENT.json).
봉인 HANDOFF의 미발송 표시는 봉인 시점 이력이다. GENOS 실제 commit/리비전/generation 해시는
사진에서 확인되지 않으며 현장 적용·push·새 리비전·워크플로우 성공도 미확인이다.

2026-10-13 R1 적용 후 사용자 사진의 `RUNTIME_BOOTSTRAP_ERROR / ContractError / 503`을 조사해
R1 인계에서 `request_entry_policy=fused-title-v1`을 추가하고 이를 받는
`workflow_tiers_policy.py`를 누락한 결함을 확인했다. 사진에는 내부 예외 메시지가 없지만,
실제 인계 코드의 `service.service` 초기화에서 `unknown v4 profile field`를 재현했다.
[수정 패치 R2](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r2/GUIDE_UTF8.txt)는
R1이 적용된 기존 `~/DEV`에 MAIN53의 동일 검증 파일과 연결 해시만 보완한다.
캐시·CM·모델/전송·서비스 예산·원문 generation·워크플로우 편집기는 유지한다.
대표 설치3종에서 R1 초기화 실패/R2 초기화200, 동일 committed checkout의 모의 generation
gate3개, 재실행·변조 거부·원복·데이터 불변을 확인했다. 실제 모델 통신/추론은0회이며
모델 목록 GET만 모의 HTTP로 응답했다. R1의 앞선 검사는 실제 설정 검증 경로를 놓쳤다.
R2 ZIP/독립 RUN/안내/검증요약/해시 첨부5개를 삼성메일 SENT `1a132b15ca149f1e`로 발송하고
수신자·제목·첨부 이름/크기를 확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r2/EMAIL_SENT.json).
R1 단독 사용은 이번 R2 적용으로 보완해야 한다. R2 undo만 하면 결함이 있던 R1로 복귀한다.
GENOS 실제 적용·push·새 리비전·워크플로우 성공은 아직 미확인이며 MAIN53 포인터는 유지했다.
아래 R1의 봉인 ZIP과 당시 검증/발송 기록은 이력으로 보존한다.

2026-10-13 사용자 요청으로 [RAG 최적화 패치 R1](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r1/GUIDE_UTF8.txt)을 삼성파트너 메일에 발송했다.
로컬 MAIN53 `focused-rules-20261013-r1`의 입력 압축·질문 범위/복구·제목 탐색·원문 의무/허용·단일 규칙 구성(v8)을 기존 GENOS 코드에 결합한다.
기존 캐시 함수/모듈, 서비스 예산, 내부 모델 전송, CM, 데이터 세대, 워크플로우 편집기는 보존한다.
알려진 330개 inventory에 대한 hash 결속과 대표 8상태/72명령, 설치 조합 RAG 계약204개,
같은 committed checkout의 모의 generation gate2개를 확인했다. 신규 모델 호출은 없다.
SENT `1a132972d56cc753`에서 수신자와 ZIP/독립 실행TXT/안내/검증요약/해시 첨부5개의 이름·크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_focused_rules_20261013_r1/EMAIL_SENT.json).
GENOS 실제 반입·commit/push·새 리비전·워크플로우 성공은 미확인이다. 로컬 MAIN53 포인터는 유지했다.
조건 AND/OR 의미 판단·의미상 중복·형식 복구 지연은 후속 개선 사항으로 남긴다.

2026-10-08 HTTPS 후속 작업은 모델 전송을 Python 표준 `urllib`로 교체했다.
공통 [GENOS 전송](02_BACKEND/semantic_runtime/genos.py)의 모델 목록·JSON·임베딩과
[에이전트 전송](02_BACKEND/semantic_runtime/legal_agent/transport.py)의 단일 JSON·답변
스트리밍이 [공통 helper](02_BACKEND/semantic_runtime/stdlib_http.py)를 사용한다.
`ssl.create_default_context()`로 OS/Python 기본 CA와 `SSL_CERT_FILE`/`SSL_CERT_DIR`를
읽으며 인증서·호스트명 검증은 유지한다. 사내 CA가 기본 저장소에 없으면 컨테이너에서
읽을 수 있는 올바른 CA 번들을 설치하거나 `SSL_CERT_FILE`로 지정해야 한다.
`REQUESTS_CA_BUNDLE`은 이 전송의 설정이 아니다. 로그의 `transport_backend=urllib`,
`transport_revision=genos-urllib-tls-20261008-r1`로 실제 호출 경로를 확인한다.
URL·키·모델 선택과 워크플로우 SSE 계약은 기존 설정을 따른다. 이번 상태는 작업 코드
반영이며 로컬 선택 릴리스·봉인 ZIP·GENOS 리비전 배포와 현장 HTTPS 성공은 별도다.
로컬 전송·스트리밍·오류 계약91개가 통과했고 실제 TLS 검증14개를 포함한다.
변경한 전송 파일과 새 helper의 엔진 pin·PIPELINE 등록 해시30개를 확인했다.
넓은 회귀 검사에서는 기존 WORKSPACE/다른 코드 pin 불일치 관련6개와 워크플로우
AD_PROBE 입력을 제공하지 않는 fixture 관련5개가 실패했다. 이 별도 항목을 제외한
해당 검사80개와 오류 상세 회귀11개가 통과한 상태이며 전체 파이프라인 통과로 보지 않는다.

2026-10-08 사용자 후속 요청에 따라 [편집기 정정 R4](08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/GUIDE_UTF8.txt)는
GENOS 기본 접이식 추론·행위 패널을 유지하고 답변 본문에 나온
“준비 중 · 자료와 요청 설정을 확인하고 있습니다”를 제거한다. R3의 첫 카드 전
준비 token 송신을 없애고 준비·원문 확인·근거 선택·현재 판단은 카드에만 보낸다.
답변 token에는 검증한 최종 답변만 보내며 end와 동일한 최종 카드 배열은 유지한다.
기존 socketio-inline도 socketio로 연결하므로 같은 설정에서 본문 진행 문구가 없다.
아래 R3 기록의 “첫 token이 카드보다 먼저 필요하다”는 당시 해석이었다. 보존된
GENOS 514 진행 브릿지는 카드→실제 답변 token→end 순서이며 준비 문구를 요구하지 않는다.
관련 계약102개·정확한 전체 편집기 TXT12개·준비/재실행/보존4개가 통과했다.
현장 화면은 미확인이다.
이번 적용은 R3 대신 R4 전체 PASTE_ALL TXT를 기존 워크플로우 Python 편집기에
저장하는 단계다. 별도 SSE 서버·R5 backend·주소/ID/token/port·NFS/DB·MAIN45는 유지한다.
R3/R5 봉인 ZIP·TXT와 실패/발송 이력은 보존한다.
삼성메일 SENT `1a1192fc24ced6e4`에 R4 편집기 ZIP·독립 PREPARE TXT·전체 PASTE TXT·
안내·검증 요약·해시 총6개를 발송하고 수신자·이름·정확한 크기를 확인했다.
[R4 발송 기록](08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/EMAIL_SENT.json).

2026-10-08 사용자 후속 보고로 **채팅 최종 답변 전에 나오던 접이식 에이전트 행위
카드가 SVG 인계 후 사라진 회귀**를 확인했다. 구
`workflow_live_progress_20261007_r1/WORKFLOW_PASTE_ALL.txt`는 워크플로우의
`main_socketio.sio_server.emit`으로 카드를 보내지만, 발송 R5의 Python은
`sid=''`/`enabled=False`와 미연결 emit 상태여서 SSE를 읽어도 처리 중 화면 송신을
하지 않는다. 구 카드 복구 코드를 SVG 버전에 연결하지 못한 코드 회귀다.
[GENOS 기본 카드 복구 R3](08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r3/GUIDE_UTF8.txt)는
기존 별도 SSE 서버와 R5 코드 ZIP을 유지하고 편집기 전체 Python만 갱신한다.
`GENOS_RAG_PROGRESS_UI=socketio`로 접이식 카드를 보내고 AD_PROBE 전부터
“준비 중 · 자료와 요청 설정을 확인하고 있습니다”를 송신한다. `on`도 이 모드다.
사용자가 말하는 SSE는 승호님 코드에서 쓰던 GENOS 기본 화면 기능이다.
승호 `fde/seungho/integration` commit `3809dfa0`의 분리 `report_chat.Progress.say`는
워크플로우 런타임 `main_socketio`로 token을 송신한다. GENOS 514/기존 진행 브릿지의
Visible Reasoner 카드·누적 배열·token·end·최종 dict 계약을 대조했다. R3는 첫 준비
token으로 패널 렌더를 시작하고 실제 송신 카드 배열을 최종 dict에도 유지한다.
미발송 R2 후보의 token 시작 전 카드 송신 문제도 별도 회귀로 보존했다.
관련 계약106개, 정확한 편집기 TXT12개, 준비/재실행/파일 보존4개를 확인했다.
삼성메일 SENT `1a119237ca5f9c18`에 편집기 R3 ZIP·독립 준비 TXT·전체 PASTE TXT·
안내·검증 요약·해시 총6개 첨부를 보내고 수신자·이름·크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r3/EMAIL_SENT.json).
SVG R10·현재 판단 상세 R2·원문/권한/hash·최종 dict·단일 backend 실행을 유지한다.
현장 질문/warmup은 워크플로우 테스트 화면에서만 한다. 실제 편집기 저장·화면
렌더링 성공은 미확인이고 로컬 MAIN45/NFS/DB/CM/예산/기존 백업은 유지한다.
[원인·실행 경로·검증](07_DOCS/REFERENCE/OPERATIONS/GENOS_WORKFLOW_LIVE_CARDS_RESTORE_20261008.md).
아래 R5 발송 기록은 그 당시 상태이며 R5 워크플로우 TXT는 이번 편집기 복구본으로
대체한다. 봉인 R5 ZIP·TXT 바이트는 이력으로 보존한다.

2026-10-08 후속 사진의 검색 후보 노드 밀집과 SSE 판단 누락을 보완한 인계는
[별도 SSE·판단·SVG R5](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r5/GUIDE_UTF8.txt)다.
사용자 선택은 `stream_app:app` 별도 SSE 서버와 기존 분리 Python 표시 단계다.
SVG R10은 법령→원문→현재 판단 관계를 먼저 배치하고 연결 없는 후보를 접힌 목록에
보존한다. SELECT에서 추가 확보한 원문도 같은 현재 판단에 연결한다. 전체 경로는
title/상세에 남긴다. 현재 판단 진행 R2는 승인된 판단 문장·선택 이유·근거·미확인을
생략 없이 전달하고, 서버 stdout/stderr에도 `agent.current_judgment`를 출력한다.
최신 모델 `claims`를 모델 제안으로 읽으며 저장 근거 재결속 수는 실제 journal 행 수로
표시한다. SSE 판단/오류 이벤트는 일반 진행 큐 정리에서 보존한다.
현재 표시·로그·전송 계약77개와 실제 WSL 로컬 START_SSE의 health/SSE_CHECK를 확인했다.
검증한 기존 코드 지문165종과 설치/원복/모의 generation gate 결과는 인계
`HANDOFF.json`·`VALIDATION.json`에 결속한다. 기존 CM/예산/오류 로그 변환·원문 generation·
DB/이전 백업은 보존한다. 신규 모델 호출은 없고 로컬 MAIN45 선택 포인터는 유지한다.
GENOS 반입/push/리비전/실제 워크플로우 화면은 미확인이다.
사용자 요청으로 삼성메일 SENT `1a1190d54cc467bf`에 R5 ZIP·독립 RUN TXT·워크플로우
전체 TXT·START_SSE·안내·검증 요약·해시 총7개 첨부를 발송하고 수신자·이름·크기를
확인했다. 이전 표시 R3/R4 대신 R5를 사용한다. 봉인 인계 파일의 미발송 표시는
봉인 시점 상태이며 [발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r5/EMAIL_SENT.json)에
후속 발송을 별도로 남겼다. 메일 발송은 현장 수신·실행·배포 성공을 뜻하지 않는다.
[변경·실행 경로](07_DOCS/REFERENCE/OPERATIONS/GENOS_STANDALONE_JUDGMENT_SVG_20261008.md).
아래 R4/main_workflow 연결과 R3 발송 기록은 이전 표시 코드의 이력이다.

2026-10-08 메일 적용본 요청으로 [main_workflow 반영 R4](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r4/GUIDE_UTF8.txt)를
삼성메일로 발송했다. 이전 표시 R3 대신 R4를 사용하며 이미 R3를 적용한 상태에서도
이어 적용한다. `main_workflow.py`의 `/json`·`/stream` 표시 생산과 분리 Python 단계의
요청/응답 SHA 결속·표시 재사용을 포함한다. 패키지 R4와 서버 내부 revision
`genos-external-workflow-svg-20261008-r3`는 다른 버전 이름이다. 전체123개 허용 지문의
정적 설치 hash/pin, 실제 최종 RUN의 대표18개 상태/180명령, 설치9개 계열의 계약
각69개, 같은 committed checkout 모의 gate 및 CM/예산/전체 오류 보존6개가 통과했다.
SENT `1a118fae16e64868`에서 수신자와 첨부7개 이름·정확한 크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r4/EMAIL_SENT.json).
실행 ZIP·독립 RUN·편집기 전체 TXT·선행 롤백 TXT·안내·검증·해시를 첨부했다.
실제 DEV에 적용/commit/gate/push/새 리비전 배포 후 편집기에 전체 TXT를 별도로
반영하고 워크플로우 테스트 화면에서 확인한다. MAIN45·이전 R3 ZIP은 유지했다.
GENOS 실제 반입·push·리비전 배포·화면 성공은 미확인이다.

2026-10-08 후속 요청으로 [main_workflow.py](main_workflow.py)에 SVG R9·짧은 진행
표시를 직접 연결했다. LEGAL_AGENT/ELS_QUERY의 `/json`·`/stream` 최종 원시 응답에
요청 ID·응답/표시 SHA로 결속한 `body.workflow_display`를 추가하며 기존 service는
한 번 실행한다. 분리 Python 단계는 같은 요청·응답·revision의 표시를 재사용한다.
이전 서버·변경된 응답은 기존 표시 경로로 처리하고 전체 오류 상세를 유지한다.
`/chat-mode`/health에서 실제 렌더러 경로와 SVG/진행 revision을 확인할 수 있다.
현재 작업 code_ship의 기본 파일 목록에도 main/router/workflow와 SSE 의존성을 넣었다.
관련 검사69개가 통과했다. [작업·검증·상태](07_DOCS/REFERENCE/OPERATIONS/RAG_KEY_PROGRESS_SVG_20261007.md).
MAIN45·기존 발송 R3 ZIP/TXT는 유지했다. 이번 후속 코드는 위 R4로 인계/메일 발송했고,
Git push/GENOS 리비전 배포/워크플로우 편집기 적용은 아직 확인하지 않았다.

2026-10-08 SVG 개선과 짧은 진행 로그를 함께 다시 보내 달라는 사용자 요청으로
[표시 재반영 R3](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r3/GUIDE_UTF8.txt)를
삼성메일로 발송했다. 이전 표시 R2 대신 SVG R9·핵심 진행 R1을 적용한다.
후속 CM 계열의 이전 표시를 최신 코드에 연결하며 CM R14/R15·조사 예산·선택 generation
binding·캐시·service.py와 R15가 보존한 오류 로그 R10의 상세 원문을 유지한다.
기존 69종 설치 상태에서 690명령, 최종 확장 TXT의 R15 12종에서 120명령을 확인했다.
설치기·기존69종의 모든 변환/결과/소스 불변을 대조했고 9개 코드 계열의 표시/진행/
JSON/SSE/분리 소비자 계약 각63개와 같은 committed checkout의 모의 gate 및
CM/예산/오류 보존 검사5개가 통과했다.
[검증 기록](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r3/VALIDATION.json).
SENT `1a118e1acfd55379`의 수신자와 첨부8개 이름·정확한 크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261008_r3/EMAIL_SENT.json).
ZIP은 TRANSFER용 실행 묶음이며 RUN으로 기존 DEV에 적용한다. 실제 적용된 DEV에서
생성한 APPLIED_CODE.zip으로 같은 checkout/generation gate를 수행한 뒤 commit/push/
새 코드서빙 리비전을 확인한다. 분리 워크플로우는 전체 TXT를 편집기에 별도로 반영한다.
실제 로딩 경로·진행 R1·SVG R9를 출력하며 현장 질문 검증은 워크플로우 화면에서 한다.
MAIN45는 유지했고 GENOS 실제 적용·push·배포·워크플로우 화면 성공은 미확인이다.

2026-10-08 후속 사진의 R14 사전 검사 실패를 보완한 현행 CM 인계는
[R15](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/GUIDE_UTF8.txt)다.
사진에서 오류 전체 표시 R10의 apply/verify는 EXIT=0이었지만, CM R14는
`budget service inventory differs; preserved`로 공통 코드 적용 전에 중단했다.
R14의 예산 검증은 이후 R10이 변경한 service와 engine inventory를 조합하지 못했다.
[현장 관찰](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/FIELD_OBSERVATION.json).
R15는 R10 VERIFIED receipt·원본 파일 백업·적용 CODE ZIP·부모 inventory 전체를 고정 변환과
대조해 원래 코드를 식별하고 CM 패치를 구성한 뒤 오류 로그 변환을 보존한다. 해시/권한/
선택 generation 검사 우회는 없다. R14의 이름·역할 연결과 등록 재사용 보호는 그대로다.
기존 조사 한도·오류 출력의 source 바이트·DB·원문·실패 로그·백업을 보존하며 현재
`~/DEV/TRANSFER`에서 R15를 실행한다. 상태·단계 로그·등록 영수증은 `cm-oneclick-r15/`다.
R10을 다시 apply/undo하거나 RAW/선택 원문 세대를 바꾸지 않는다.
이름/등록 계약79개와 최종 R15 첨부 TXT 검사9개가 통과했다. 7개 모의 설치 상태별2회 실행과
R15 부분 쓰기 실패 복구 후 실제 TXT 재개를 확인했다. 51건/98근거 등록·중복 방지·기존 코드/
DB/세대/로그/백업 보존·같은 checkout/generation gate/모의 push·코드 원복이 통과했다.
[검증 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/VALIDATION.json).
삼성메일 SENT `1a118d77f4cbb635`의 수신자와 ZIP/독립 RUN TXT/안내 TXT 세 첨부 이름·
정확한 크기를 확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r15/EMAIL_SENT.json).
메일 발송과 현장 수신·실행·배포 성공은 별도다.
기존 발송 R14와 아래 R14/R12 기록은 당시 이력이다.
로컬 MAIN45는 그대로다. 이번 사진은 R14 실패를 확인한 것이며 R15 현장 반입·등록·push·
새 코드서빙 리비전·워크플로우 질문 성공은 미확인이다. R10 자체의 부분 apply 후 undo
진입 차단은 별도 결함이며 R15가 그 구 R10 명령을 고쳤다고 설명하지 않는다.

2026-10-08 이름 연결 보완의 당시 CM 인계는
[R14](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r14/GUIDE_UTF8.txt)다.
이전 R11/R12 대신 기존 `~/DEV/TRANSFER`에서 실행한다. 정상 규정명에 포함된 서식/별첨은
보존하고 개별 정식명·파일명·원래 이름/별칭으로 연결한다. 부모 폴더명만으로 다른 법령을
선택하지 않으며 개정·제정안·신·구조문대비·요약·참고·별표/서식 폴더와 NFD 한글을 구분한다.
사본 번호·날짜·판본은 임의로 지우지 않는다. 기존 등록 재사용 전에 새로 해결한 문서·조문·
근거가 이전 기록과 같은지 확인하며 다르면 보존 후 중단한다. 같은 등록은 중복 없이 재사용한다.
R11 실패 상태와 이미 R12를 적용한 상태를 지원하고 기존 조사 한도 코드/설정·백업 계보를
대조한다. 원문 generation·RAW 이름·기존 DB·실패 이력은 보존한다.
이름/등록 계약79개와 최종 인계5개가 통과했다. 등록 외규 본문114경로·CM33경로의 이름
대조와 교차 오연결 배제, 선택 로컬159문서의 CM21개 유일 연결을 확인했다.
216개 recipe 및 R8/R10/R11/R12/미발송 R13의 업그레이드 pin과 정확한 첨부 TXT의 모의
4설치 상태·각2회 실행에서51건/98근거 등록·재사용·예산/원문/DB/백업 보존·변조 거부·
같은 checkout/generation gate/모의 push·코드 원복이 통과했다.
[검증 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r14/VALIDATION.json).
삼성메일 SENT `1a1170217b6b0164`의 수신자와 ZIP/독립 RUN TXT/안내 TXT 세 첨부 이름·
정확한 크기를 확인했다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261008_r14/EMAIL_SENT.json).
로컬 MAIN45는 그대로이고 실제 GENOS 적용·등록·push·리비전·워크플로우 성공은 미확인이다.
R13은 미발송 검증 후보로 보존했고 기존 등록 재사용 보호는 최종 R14에 추가했다.
아래 R12 이름 진단·인계는 당시 이력이며 확인한 추가 결함은 R14에서 보완했다.

2026-10-08 사용자 요청으로 이름 끝 `본문`을 처리하는
[당시 CM 인계 R12](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r12/GUIDE_UTF8.txt)를
삼성메일로 발송했다. 이전 R11 대신 R12를 기존 `~/DEV/TRANSFER`에서 실행한다.
`중소기업기본법 본문.xml` 같은 독립 이름을 정식명에 연결하고 기존 전문/조문 처리와
시행령·시행규칙·개정문 구분을 유지한다. 조사 한도 R1이 있는 R11 실패 상태에서는
R11 백업의 원래 부모 inventory까지 검증해 기존 예산 코드·백업·실패 기록을 보존한다.
원문 세대와 RAW 이름은 변경하지 않는다. 관련 계약70개,216개 recipe/엔진 pin,
실제 첨부 TXT의 모의3설치 상태·각2회 실행과 코드 원복이 통과했다.
R11의 `본문` 이름 실패 재현→R12 공통51건/98근거 등록, 중복 방지, 같은 checkout의
commit/generation gate/모의 push와 기존 DB·원문·예산·백업 보존을 확인했다.
[검증 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r12/VALIDATION.json).
SENT `1a116e71fe37d263`의 수신자와 ZIP/독립 RUN TXT/안내 TXT 세 첨부 이름·정확한 크기를
확인했다. 발송 응답 오류는 보낸메일함 조회로 성공을 확인했고 재발송하지 않았다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r12/EMAIL_SENT.json).
로컬 MAIN45는 그대로이며 실제 GENOS 적용·등록·push·새 리비전·워크플로우 성공은
미확인이다. 실제 원문 누락이면 이름 접미어 수정만으로 해결되지 않는다.
아래 R10/R11은 이전 현장 관찰과 인계 이력이다.

2026-10-08 후속 [R12 이름 변환 전수 대조](09_ARTIFACTS/AUDITS/20261008-cm-name-patterns-r12/README.md)에서
수집/RAW 등록/표시 이름/구축 메타데이터·별칭·사본 번호 처리와 현재 CM 연결식을 대조했다.
등록 외규 body114경로 중 기업공시서식 작성기준과 별지서식2경로는 파일명의 `서식` 등
부분 문자열 때문에 정식명·명시적 body 역할이 있어도 제외된다. 두 제목은 CM21 대상이 아니다.
정식명과 다른 시행령/시행세칙도 정확한 부모 폴더명으로 통과하며, 신·구조문대비표·제정안·
요약·참고·개정(202609)·NFD 개정문 등도 역할이 없거나 body인 조건에서 통과하는15개
모의 조건을 재현했다. 현재 로컬 CM body33경로의 자기 이름 연결/교차 오연결 검사와
선택 source159문서의 CM21 각1개 후보는 통과했다. 실제 GENOS 배치·문서 선택은 미확인이다.
당시 읽기 전용 진단에서는 발송된 R12·제품 코드·MAIN을 변경하지 않았다. 추가 문제는 이후 R14에서 보완했다.

2026-10-07 사용자 현장 구축 확인에 따라 CM 등록의 문서명·근거 결속을 수정하고
[현장 이름 연결 R10](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r10/GUIDE_UTF8.txt)을
삼성메일로 발송했다. SENT `1a1167e769559d89`의 수신자와 ZIP/독립 RUN TXT/안내 TXT
세 첨부 이름·정확한 크기를 확인했다. 후속 사진에서는 조사 한도 R1의 check/apply/verify와
EXIT=0이 확인됐으나 이어 실행한 CM R10은 `R8 code differs from the verified upgrade inventory`
사전 검사에서 EXIT=1로 중단했다. `unzip`도 없어 해제 명령은 실패했지만 별도 RUN TXT는
실행됐다. 사진의 변경 후 service 해시와 검증된 R1 변환 해시가 일치한다.
당시 복구는 [조사 한도 보존 R11](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/GUIDE_UTF8.txt)이었다.
R8/R10의 정확한 코드에 조사 한도 R1의 세 변경과 부모 inventory가 함께 일치할 때만
이어 적용한다. 원복·재구축 없이 조사 한도 코드와 원래 백업/실패 기록을 보존하며,
압축 해제는 `python3 -m zipfile`을 사용한다. 사용자 요청으로 R11 ZIP/독립 RUN TXT/안내 TXT를 삼성메일에 발송했다.
SENT `1a11697955af743f`에서 수신자와 세 첨부 이름·정확한 크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/EMAIL_SENT.json).
사진과 확인 범위는 [현장 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/FIELD_OBSERVATION.json)에 보존했다.
후속 [R11 실행 사진](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/FIELD_PACKAGE_CHECK_FAILED.json)에서
RUN/안내 TXT 해시 OK, CORE_SHORTCUT_ALL_PROFILES PASS, BUDGET_SETTINGS PASS
(총40회/조사37회, 모델 호출0회), 공통 코드 적용 완료를 확인했다.
이어서 `package-check`가 실패해 EXIT=1로 중단했다. 상세 오류는 사진에 없으며
기존 `~/DEV/TRANSFER/cm-oneclick-r11/package-check.log`에서 확인한다.
이번 실행은 원문51건/98근거 연결 완료·commit·generation gate·등록/검증·push에
도달하지 않았다. 후속 [단계 로그 사진](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/FIELD_TARGET_BODY_MISSING.json)에서
`target_documents`의 `target body document missing: 중소기업기본법`을 확인했다.
현장 선택 원문의 문서명·역할이 사진에 없어 실제 문서 누락과 이름/역할 제외는
아직 구분하지 않는다. 새 리비전·워크플로우 성공도 미확인이다.
사용자의 [다른 대화 RAW 이름 사진 검토](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/FIELD_RAW_NAMES_REVIEW.json)에서는
`본문.xml`·`조문.html`·`_전문.hwpx`와 기존 제목/경로/별칭 처리를 대조했다.
R11은 독립 이름의 `본문` 접미어를 처리하지 않는 누락이 있다. 정식 제목/폴더 별칭이
남은 사진 모양은 통과하므로 이 누락을 현장 `중소기업기본법` 실패 원인으로 확정하지 않는다.
RAW 존재와 선택 source DB 존재도 구분한다. 이 검토는 이름/본문/세대/코드를 변경하지 않았다.

`genos_build`가 정식명을 전체 경로 display_name으로 게시하는 실제 연결을 확인했다.
새 패키지는 정식 규정명·본문 파일 별칭·조문을 현장 source에서 해결하며 로컬 입력/본문
해시 일치를 요구하지 않는다. 현장 문서 ID·현재 조문·source/nav/fulltext 해시에 새로
결속하고 기준답변은 미승인 observation으로 보존한다. 기존 엄격한 패키지 계약은 유지한다.
본문 표현본은 기존 XML→HTML→HWPX→DOCX→PDF→HWP 순서로 선택하고 개정문/비교표,
같은 우선순위의 중복 판본·중복/누락 조문·권한 부족은 자동 승인하지 않는다.
관련 계약34개와216개 recipe의 엔진 pin을 검사했다. 실제 첨부 TXT로 현장 모양의
모의21문서에서 R8 실패→R10 이어 적용→공통51건/98근거 등록→중복 없는 재실행2회,
같은 checkout commit/generation gate/모의 local remote push와 기존 원문·DB·실패 기록
보존을 확인했다. 작업 코드의 관련30개 엔진 선언은 변경한2개 모듈만 재결속했다.
미발송 R9의 offline 모듈 의존 누락 실패는 보존했으며 R10은 그 의존이 없다.
로컬 MAIN45/원문 세대/기존 공통 DB는 변경하지 않았다. 실제 GENOS 등록·Git push·
코드서빙 리비전 배포·워크플로우 성공 및 수신자의 실제 수신은 미확인이다.
R11은216개 recipe/엔진 pin과 실제 첨부 TXT의 모의3설치 상태·각2회 실행을 확인했다.
사진 순서의 R8 실패→조사 한도 적용→R10 사전 중단→R11의51건/98근거 등록·commit·
같은 checkout/generation gate·모의 local remote push를 재현했다. R10 적용 후 조사 한도
상태와 기존 무패치 입력도 검사했다. 예산 코드의 동일 바이트·중복 없는 재실행·원문/DB/
과거 로그/백업 보존·자체 inventory에 반영한 미승인 코드 변경 거부를 확인했다.
로컬 MAIN45·운영 데이터·현장 배포는 변경하지 않았다. [검증 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11/VALIDATION.json).

2026-10-07 현장 사진에서 NFS 목록 R3 ZIP 내부 RUN은 EMBEDDED_CODE_VERIFIED까지
실행했으나 inspect 병합 중 part000030 크기49,000,001바이트/해시 불일치로 중단했다.
조각000000~000033 중30만 FAILED이고 나머지는 OK였다. NFS 복원·push 단계에는 도달하지 않았다.
Windows의47,852KB 반올림 사진으로 변형 위치나 DRM 원인을 확정하지 않는다.
사용자 요청에 따라 [전체 SHA 병합·끝 추가1바이트 복구 보조도구](08_DEPLOYMENT/GENOS/handoffs/zip_parts_recovery_20261007_r1/JOIN_VERIFY_RECOVER_20261007_R1_GUIDE.txt)를 준비해
ZIP/별도 RUN TXT/안내 TXT로 삼성메일 발송했다. SENT `1a1166b855bc587b`의 수신자·세 첨부 크기를 확인했다.
크기 상한 없이 전체 원본 SHA를 확인하고, 끝1바이트 제외는 해당 조각 및 전체 원본 SHA가
둘 다 일치할 때만 새 _verified.zip으로 출력한다. 기존 조각과 메타데이터는 보존하며
이 ZIP을 기존 R3에 직접 지정한다. 모의 계약12개와 해제/해시/구문을 확인했다.
수신자 수신과 현장 복구/복원/배포 성공은 당시 미확인이며 로컬 MAIN45와 운영 NFS는 변경하지 않았다.
후속 [현장 사진 확인 기록](08_DEPLOYMENT/GENOS/handoffs/zip_parts_recovery_20261007_r1/FIELD_RECOVERY_VERIFIED.json)에서
APPENDED_ONE_BYTE_RECOVERY_VERIFIED와 EXIT=0을 확인했다. part000030 끝1바이트 제외가
해당 원본 조각 및 전체 원본 ZIP SHA와 일치했으며 `/workspace/TRANSFER/genos-rag-data-20261007T002029Z-7c0b050f_verified.zip`을 생성했다.
업로드 조각은 보존됐다. 변형 원인은 미확인이며 NFS 복원·push·리비전 배포·워크플로우 성공은 아직 미확인이다.
후속 [R3 현장 inspect 사진](08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r3_zip/FIELD_INSPECT_VERIFIED.json)에서는
직접 지정한 _verified.zip의 해제와 선택 경로 검사를 통과하고 ARCHIVE_RESTORE_ELIGIBLE=True,
CODE_SPACE_STAGES_PASS, EXIT=0을 확인했다. SOURCE_CHANGES에는 cases-v4.sqlite의 metadata_changed/
changed_during_copy 기록이 있었다. inspect는 NFS 복사·Git commit/push를 수행하지 않으며
현장 Git checkout·NFS 복원·리비전·워크플로우 성공은 이 사진으로 확인되지 않는다.
그 뒤 [all 현장 사진](08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r3_zip/FIELD_NFS_RESTORE_VERIFIED.json)에서는
실제 NFS 입력 해시/목적지 충돌 검사를 통과하고 RESTORED/copied_files2748을 확인했다.
이후 install_existing_probe_hook의 Git rev-parse가 exit128로 실패해 전체 상태는 FAILED였다.
이 Git 확인은 코드 쓰기 전이므로 코드 적용/commit/push·서빙·워크플로우는 미완료다.
NFS 복원은 완료된 별도 상태로 보존하며, 실제 배포 Git checkout에서 R3 deploy로 코드 단계만 이어간다.
현재 대상 Git 실패의 구체적 원인은 사진에 없으며 archive의 code_evidence를 대상 checkout의 증명으로 쓰지 않는다.

2026-10-07 사용자 요청으로 [조사 한도 설정 R1](08_DEPLOYMENT/GENOS/handoffs/investigation_budget_20261007_r1/GENOS_INVESTIGATION_BUDGET_20261007_R1_GUIDE.txt)을 삼성파트너 메일에 발송했다. SENT `1a116666973d9a02`에서 수신자와 ZIP/별도 전체 실행 TXT/안내 TXT 세 첨부 이름·정확한 크기를 확인했다. 변경 직전 로컬 MAIN45의 모델 총40회(최종 판단3회 예약, 조사 최대37회)를 유지하고 모델·도구·시간·추가 검색·판단 후 재조사 한도를 환경 설정으로 선택하도록 연결한다. 기존 DEV의 service.py 세 변경 부분과 CODE_MANIFEST만 반영하며 엔진/원문/generation/CURRENT·세션·기존 캐시/로그/데이터 경로를 보존한다. ZIP 내부와 별도 실행 TXT의 동일 바이트, JavaScript 제외, Python3.11/Bash 구문, 선행 latency R4·CM R8+NFS 목록·MAIN45 세 inventory의 최종 TXT30명령 및 같은 committed checkout의 기존 generation gate·모의 local remote push를 확인했다. 신규 설정 계약27개와 실제 로컬 MAIN 서비스 HEALTH도 확인했다. 최초 로그·실패 상태·백업·재실행·원복 방법은 안내에 포함한다. 후속 [현장 사진](08_DEPLOYMENT/GENOS/handoffs/investigation_budget_20261007_r1/FIELD_APPLY_VERIFIED.json)에서 GENOS check/apply/verify와 EXIT=0을 확인했다. commit/gate/push/새 리비전/환경 저장/워크플로우와 수신자 수신 확인은 미확인이다. [발송 기록](08_DEPLOYMENT/GENOS/handoffs/investigation_budget_20261007_r1/EMAIL_SENT.json).

2026-10-07 사용자가 기존 ZIP 인계 방식을 요청하여 데이터 이관/목록 R1을
[ZIP 인계 R3](08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r3_zip/GENOS_TRANSFER_NFS_LIST_20261007_R3_GUIDE.txt)로 재포장해 삼성메일에 발송했다.
SENT `1a1165280958c314`에서 ZIP/독립 RUN TXT/안내 TXT 세 첨부의 수신자·이름·크기를 확인했다.
ZIP 내부에도 같은 실행 TXT와 분할/병합 TXT를 넣었으며 코드는 검증한 R1과 바이트가 같다.
코드스페이스에서 ZIP을 해제하고 내부 RUN TXT를 실행한다. 해제·SHA·Bash 구문과
해제한 실행본의 모의 병합/복원/commit/로컬 remote push/HTTP 워크플로우 연결을 확인했다.
삼성메일 스킬에는 코드 ZIP+별도 실행 TXT를 기본으로 반영했다. 운영 데이터/MAIN45는
변경하지 않았으며, 현장 DRM·복원·배포·워크플로우 성공과 수신자 실제 수신은 미확인이다.

2026-10-07 사용자 요청으로 전체 원문을 문서명과 이름을 무시한 원본 SHA로 각각 대조하는
[전수 진단 R2](08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r2/GENOS_CM_SOURCE_DIAG_20261007_R2_GUIDE.txt)를
[삼성파트너 메일로 발송](08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r2/EMAIL_SENT.json)했다.
SENT `1a1163917bae06bf`의 수신자와 RUN/안내 TXT 두 첨부 이름·정확한 크기를 확인했다.
현장 목록 출력 과다에 대한 사용자 정정으로 [R3 요약 TXT](08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r3/GUIDE_UTF8.txt)를
같은 삼성메일 스레드로 보냈다. SENT `1a11644df4309e93`의 요약 TXT 한 첨부2196바이트를 확인했다.
이미 저장된 R2 JSON을 재검사 없이7줄로 읽으며, 향후 R3 RUN도 상세 목록은 JSON에만 보존한다.
기존 계약11개, 실제 R3 RUN과7줄 요약 TXT를 검사했고 원문/기존 기록을 보존했다.
로컬 RAW/external/financial_team/krx/코스닥시장 상장규정의 전문.hwpx·전문.pdf·조문.html 존재/해시를 확인했다.
RAW 존재와 선택 서빙 세대의 문서명/입력 표현본 SHA는 별도이며, 현장 사진은 상세 추가 목록만 있어 집계/정확한 결속은 미확인이다.
현재 로컬 MAIN45가 선택한 전체159문서의 ID/문서명/원본 SHA와 부모 포인터·release·source 해시를
TXT 안에 고정했다. 현장에서는 기존 R8의 설정과 같은 manifest를 선택해 원문 DB 해시를 먼저
검사하고 선택 문서 전체를 양방향 대조한다. 문서명+SHA, 이름 무시 SHA, 이름만 다른 동일 원본,
누락/해시 차이/현장 추가/중복과 CM21문서 대조를 함께 기록한다. 진단에는 R1 대신 R2를 쓴다.
계약11개와 최종 TXT 전체3회, 변경된 generation 결속 거부1회를 확인했고 원문/기존 기록을 보존했다.
진단은 모델 호출·등록·코드/MAIN 수정·push·배포를 하지 않으며 현장 데이터 일치 결과는 미확인이다.
문서명에 상관없이 동일 원본 SHA를 찾는 진단 결과가 원문 조문 본문·구조·판단 품질 인증을 뜻하지 않는다.
기존 workspace 활성 receipt의 manifest hash 차이는 보존했다. 반입 inventory 작성은
논리 root의 read-only `inspection_path`와 실제 선택 포인터/릴리스 해시를 사용했고 runtime 활성 검증을 우회하지 않았다.

2026-10-07 사용자 현장 사진에서 공통 CM R8은 코드 검사 후 `package-check`의
`source document version missing or ambiguous: 코스닥시장 상장규정`으로 중단했다.
등록기는 문서명과 `source_artifact_sha256`가 동시에 일치하는 문서 한 건을 요구한다.
사진으로는 문서명 누락·원본 해시 차이·동일 원본 중복 중 어느 경우인지 확정하지 않는다.
이번 실행은 공통51건 등록·commit·push에 도달하지 않았다. 이를 R8 현장 성공으로 보고하지 않는다.
[읽기 전용 진단 TXT 안내](08_DEPLOYMENT/GENOS/handoffs/cm_source_diagnose_20261007_r1/GENOS_CM_SOURCE_DIAG_20261007_R1_GUIDE.txt)는
R8이 생성한 설정/실행 기록의 같은 generation manifest 해시와 원본 패키지를 확인하고
대상21문서의 문서명·원본 SHA 대조 결과를 실행마다 새 폴더에 저장한다.
코드·원문·등록 DB를 변경하거나 원본 해시를 덮어쓰지 않으며 모델 호출은 없다.
로컬 계약7개와 최종 TXT 실행2회에서 원문/기존 기록 불변과 재실행 기록 분리를 확인했다.
진단 결과의 현장 확인, 복구 대상 결정과 등록·리비전 배포·워크플로우 성공은 아직 미확인이다.

2026-10-07 사용자 요청으로 **TRANSFER TXT 한 번 실행하는 공통 CM 자동 인계 R8**를 준비했다. [실행 안내](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r8/GUIDE_UTF8.txt)의 한 줄은 사용자/팀 JSON·CM_PRINCIPAL_FILE·generation/runtime/receipt 환경변수 입력 없이 기존 DEV의 코드 적용·원문 검사·commit·같은 checkout/generation gate·공통51건 등록/검증·push를 처리한다. 영수증·코드/SQLite 백업·로그는 자동 생성한다. 현재 모델·인증 설정은 유지한다. 마지막 새 코드서빙 리비전 배포와 워크플로우 화면 확인은 현장 UI 단계다.

이전 삼성메일 발송 요청에 따라 [최종 R8 RUN과 짧은 안내 TXT 두 개를 발송](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r8/EMAIL_SENT.json)했다. SENT `1a1161a33176a64a`에서 수신자·제목과 두 첨부의 이름·정확한 크기를 확인했다. 이전 R4/R6 변수 입력 안내를 대체하며, 메일 제출과 현장 수신·실행·배포 성공은 구분한다.

경로는 다른 [NFS 이관 메일](08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r1/EMAIL_SUBMITTED.json)의 실제 본문을 다시 읽어 generation financial-risk-success-20261005-schema-r2, `/nfs-root/diamo/8-agent/runtime`, 별도 state 미설정을 확인했다. `service.py`는 인계 도구가 생성하는 `00_SYSTEM/GENOS_SERVING_PATHS.json`으로 같은 경로를 선택하고 generation manifest SHA를 검사한다. 설정 파일이 없는 로컬 실행의 선택은 유지한다. 로컬 MAIN45와 실제 로컬 공통 DB는 이번 작업에서 바꾸지 않았다.

R4/R6 입력 inventory108종과 알려진 NFS 목록 패치 병행의216개 해시 고정 recipe/엔진 pin을 확인했고, 대표6상태의 준비·변조 보존 검사를 통과했다. 환경변수를 비운 정확한 최종 TXT의 전체 실행3회에서 실제 CM51/98의 원문 결속·SQLite 보존·공통 등록/재실행·같은 checkout의 commit/전체 generation gate·로컬 모의 remote push와 환경변수 없는 실제 service 경로 선택을 확인했다. 경로 설정 계약9개도 통과했다. 데이터 원문은 읽기 전용 hardlink로 공유했고 모델 호출0회, 실제 GENOS·실제 remote push·리비전·워크플로우는 미확인이다. [검증 기록](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r8/VALIDATION.json)을 보존한다. R7은 R6 후속 설치 상태 누락과 큰 중복 명세의 미발송 빌드 실패 이력이다.

아래 R6와 이전 변수 입력 안내는 당시 이력이며 현재 사용자 실행은 자동 R8를 사용한다.

2026-10-07 사용자 정정에 따라 CM51은 사용자·팀별 등록을 폐기하고 **공통 카탈로그 한 번 등록**으로 고쳤다. 현행 [공통 인계 R6](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/GUIDE_UTF8.txt)는 R4 적용 상태와 그 선행 core/display 상태에 이어서 적용한다. 앞선 환경변수 안내 R1의 CM_PRINCIPAL_FILE과 개인 user/team JSON 등록 설명은 현행 CM 등록에 사용하지 않는다. 요청 ID는 기존 문서 권한·대화 이력·감사에 사용하며 공통 등록자의 ID를 소비자로 제한하지 않는다.

이전 삼성메일 인계 요청에 따라 [정정 R6를 같은 메일 스레드로 발송](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/EMAIL_SENT.json)했다. SENT `1a115fd2f87b2ff3`에서 수신자·제목·ZIP/독립 RUN TXT/안내/검증/해시 첨부5개 이름·정확한 크기를 확인했다. 최종 첨부 TXT의 알려진54설치 상태/331명령, 대표9계열의 계약227개, 같은 committed checkout·compact 모의 generation의 gate6개를 통과했다. 발송은 현장 수신·배포 성공과 별도다. R5는 미발송 verifier assertion 오류의 실패 이력으로 보존했다.

작업 코드에 공통 등록·조회와 CLI `--common`을 연결했다. [기존 로컬 SQLite](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/LOCAL_REGISTRATION_VERIFIED.json)에 공통51건/근거98개를 등록하고 다른 사용자·팀 세 곳의 동일 unit 조회를 확인했다. 이전 개인 R1/R2 102건은 RETIRED 이력으로 보존했다. 개인 대화/native shortcut을 공통으로 공개하지 않는다. source/ACL·공통 쓰기 제한·등록·기존 개인 메뉴 검사20개가 통과했다. 원문 generation과 로컬 MAIN45 포인터는 변경하지 않았다. 실제 GENOS apply/commit/gate/push/새 리비전/워크플로우 성공은 아직 미확인이다.

아래 개인 CM scope 설명과 R4/환경 안내 발송은 당시 이력이며, 공통 등록에는 R6를 사용한다.

2026-10-07 현장 사진에서 CM R4의 코드 check/apply/verify 성공
(CODE_APPLIED, ENGINE_BINDINGS PASS, CORE_SHORTCUT_ALL_PROFILES PASS,
EXIT=0)을 확인했다. ~/DEV는 /workspace로 해결됐고 실행 Python은
/venv/bin/python3, 3.11.15였다. CM51 등록·검증, commit/gate/push,
새 코드서빙 리비전 배포와 workflow 질문 성공은 이 사진에서 미확인이다.
ZIP/RUN 해시는 OK였고 GUIDE_UTF8/VALIDATION_SUMMARY는 FAILED였다.
문서 불일치 원인은 사진만으로 확정하지 않는다.
사용자 요청으로 [환경변수·배포·등록 순서 보충 안내 R1](08_DEPLOYMENT/GENOS/handoffs/cm51_env_deploy_20261007_r1/GENOS_CM51_ENV_DEPLOY_20261007_R1_GUIDE.txt)을
[삼성메일로 발송](08_DEPLOYMENT/GENOS/handoffs/cm51_env_deploy_20261007_r1/EMAIL_SENT.json)했다.
SENT 1a115e01d4b41cde에서 수신자·제목·첨부5개의 이름/정확한 크기를 확인했다.
터미널/코드스페이스와 코드서빙 리비전의 환경변수 위치, 실제 요청 principal,
data-check, receipt의36파일 stage/commit/gate/push, 새 리비전/트래픽,
data-import/data-verify, workflow 확인·원복을 안내한다.
기존 최종 R4 독립 RUN TXT와 원본 안내·검증 문서, 새 첨부용 SHA를 보냈다.
안내 shell10블록/Python heredoc2개의 문법과 원본 R4 발송 해시 일치를 검사했다.
새 코드 패치·MAIN 활성화·GENOS 배포 실행·모델 호출은 없다.

2026-10-07 사용자 요청으로 DEV의 분할 데이터 ZIP을 합쳐 기존 NFS 경로에 복원하고,
코드서빙을 통해 워크플로우에서 실제 데이터 목록을 읽는
[분할 ZIP → NFS → 목록 확인 R1](08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r1/GENOS_TRANSFER_NFS_LIST_20261007_R1_GUIDE.txt)을 준비했다.
사용자 지시에 따라 삼성파트너 메일에 RUN/안내 TXT 두 개를 발송했고 SENT
`1a115df82c32b2f5`에서 수신자와 두 첨부 이름/정확한 크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r1/EMAIL_SUBMITTED.json)은
제출 상태이며 수신자의 수신 확인과 구분한다.
독립 RUN TXT에 기존 R4 병합·데이터 복원·NFS 진단 설치/commit/push 도구를 포함했다.
확인된 `/nfs-root/diamo/8-agent`와 financial-risk-success-20261005-schema-r2 generation,
runtime/state 미설정을 명시하며 이전 코드스페이스 `.env/CURRENT`를 재선택하지 않는다.
기존 `NFS_DATA_PROBE` 배선에 실제 generation/runtime 항목 목록과 준비한 팀의
문서 ID/이름 페이징을 연결했다. 팀 생략 시 문서명은 반환하지 않으며 팀은 새 접근권한이 아니다.
실제 최종 TXT의 모의 ZIP/NFS 복원·재실행·동일 checkout commit/로컬 remote push·
설치된 service 훅을 통한 실제 로컬 HTTP/워크플로우 연결 등 관련 검사60개가 통과했다.
검증은 모의 데이터만 사용했고 모델 호출0회, 로컬 MAIN45·운영 NFS/CURRENT·실제 Git push는
변경하지 않았다. GENOS 현장 복원·리비전 배포·워크플로우 화면 성공은 미확인이다.

2026-10-07 CM 오답·미답변 등록 요청으로 **CM51 shortcut·legal_wiki 데이터 인계 R4**를
[삼성파트너 메일로 발송](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_data_20261007_r4/EMAIL_SENT.json)했다.
SENT `1a1159b1e5f0e7b8`에서 수신자와 ZIP/독립 RUN TXT/안내/검증/해시 첨부5개의
이름·정확한 크기를 확인했다. [실행 안내](08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_data_20261007_r4/GUIDE_UTF8.txt)의
최종 R4를 사용한다. 선행 core shortcut R1의9종과 최신 화면표시 R2의18종, 총27종을
해시 고정36파일 패치로 지원하고 기존 화면·검색·로그·원문·사례 이력을 보존한다.
로컬 owner `jin`/team `CM`에 활성51건과 근거98개를 등록해 legal_wiki를 만들었다.
기준답변은 검토 observation, 법률 claims/procedures는 비어 있고 현재 원문에서 다시 판단한다.
사진의 행사 시점 입력을 CM-016에 연결했다. 등록 데이터 revision은 R2이며 R4는 반입기와
최신 표시 설치 상태 호환 인계본이다. 모델 호출0회, 첨부 TXT169명령/27설치 상태와
native 계약207개, 동일 committed checkout의 compact 모의 generation 게이트6개가 통과했다.
**로컬 MAIN45 포인터·불변 코드268파일은 변경하지 않았다.** 새 curated 소비 코드는
작업 코드/인계본에 있으며 MAIN45에는 없다. GENOS 적용·push·리비전·workflow 답변 성공은
현장 확인 전까지 미확인이다. 자료는 망분리 현장에서 실제 사용자·팀/원문/runtime/state로
반입·등록해야 하며, CM은 이후 해당 등록 arm에서 training/in-sample로 표시한다.

2026-10-08 작업 SVG를 [R9 표시](07_DOCS/REFERENCE/OPERATIONS/RAG_KEY_PROGRESS_SVG_20261007.md)로
다듬었다. 그래파이트 배경·유형별 청록/블루/앰버 원형 아이콘·색을 잇는 곡선과
조문별 분기 배치를 사용한다. 직접 JSON/SSE·분리 워크플로우의 같은 SVG/답변,
표시·진행·판단 검사44개와 작업 v6 pin을 확인했다. 경험 재사용 검사1건의 기존
모의 모델 오류는 수정 전 표시 코드에서도 재현했다. 아래 발송된 R8 반입본은 보존한다.
R9 새 ZIP/메일/push/GENOS 배포·워크플로우 편집기 반영은 이번 작업에서 실행하지 않았다.
로컬 MAIN45와 NFS generation/CURRENT는 유지하며 현장 실제 화면은 미확인이다.

2026-10-07 사용자 요청으로 화면용 핵심 진행 로그와 SVG R8 그래프를
[표시 전체 반입 R2](08_DEPLOYMENT/GENOS/handoffs/rag_progress_graph_20261007_r2/GUIDE_UTF8.txt)로
삼성파트너 메일에 발송했다. SENT `1a11580903a8c6a3`에서 수신자와 코드 ZIP,
독립 RUN TXT, 워크플로우 전체 TXT, 선행 로그 롤백 R3 TXT, 안내·검증·모의 이미지·해시
첨부8개의 이름/정확한 크기를 확인했다. 발송 해시는 해당 `EMAIL_SENT.json`에 보존한다.
306파일 대표 전체 ZIP과 별도로 RUN은 최근 알려진 설치 inventory18종에 맞춰
검색 캐시·순위·권한·세션·기존 로그와 shortcut을 보존하며 표시/의존성과 엔진 pin을 갱신한다.
대기/경과 초/모델 START·종료를 화면에서 빼고, 7단계 핵심 판단·한 줄 한 법령·실제
fulltext 값·법령 열람/조사 복귀 이유와 답변 바로 아래 접힌 근거 관계 SVG를 연결했다.
R1은 미발송 검증 실패 이력이며 누락 로그 모듈 의존성을 R2에서 해결했다.
실제 TXT180명령, 코드 계열별 표시/JSON/SSE 계약63개씩, 동일 commit된 checkout의
모의 generation 배포 gate3개와 전체 워크플로우 TXT의 동일 SVG가 통과했다.
새 모델 호출·로컬 MAIN45·NFS generation/CURRENT 변경은 없으며 GENOS 현장
apply/push/리비전 배포/워크플로우 화면/NFS 동작은 미확인이다.

2026-10-07 최종 채택 핵심 근거에서 재사용 원문 경로를 역으로 만들고 멀티턴의
현재 head를 갱신하는 [shortcut R1 인계](08_DEPLOYMENT/GENOS/handoffs/core_evidence_shortcut_20261007_r1/GUIDE_UTF8.txt)를
삼성파트너 메일로 발송했다. SENT `1a115740809cc5bb`에서 수신자와 코드 패치 ZIP,
독립 shortcut RUN TXT, 독립 선행 로그 롤백 R3 TXT, 안내, 검증 요약, 해시 등
첨부6개의 이름/크기를 확인했다. 발송 당시 해시는 해당 `EMAIL_SENT.json`에 보존한다.
계측 R3/R4 또는 시스템 로그 R1에 DB 로그 롤백 R3를 적용한 9개 알려진 inventory만
허용하며 ADR0683의 검증한 변경분을 선행 코드에 병합해 기존 캐시/전송/로그 상태를
보존했다. 8개 runtime·30개 엔진 pin·PIPELINE·CODE_MANIFEST 총40파일 패치다.
실제 첨부 TXT 적용/재실행/원복/변조 보존90명령, 선행 코드3종의 핵심 계약23개씩,
모의 generation의 동일 commit된 checkout 배포 gate3개가 통과했다.
로컬 MAIN45와 NFS 데이터/CURRENT는 변경하지 않았다. 실제 GENOS apply/push/
리비전 배포/내부 질의 및 모델 정확도·속도는 미확인이다.

2026-10-07 사용자 코드서빙 사진의 `StageRunner.verify_profile` / HTTP422 /
`engine manifest hash mismatch`와 같은 오류를 로그 롤백 R1/R2에서 재현했다.
R1/R2가 엔진 JSON의 코드 pin은 바꿨지만 `PIPELINE.json`의 엔진 manifest 등록
해시를 갱신하지 않은 반입본 작성 누락이다. 현재 로그 롤백에는
[등록 해시 수정 R3](08_DEPLOYMENT/GENOS/handoffs/db_log_rollback_20261007_r3/GUIDE_UTF8.txt)를 사용한다.
이미 R1/R2를 적용했으면 먼저 원복하지 않고 R3 check/apply/verify로 이어간다.
이 상태의 Python 코드/검색 캐시/순위/권한/원문/세션은 같은 바이트로 유지한다.
system_logging R1 계열의 알려진 WORKSPACE 의존 pin 불일치24개도 파일 변경 없이
등록을 결속한다. 원본5종과 각각의 R1/R2 적용 결과 총15개 inventory만 허용하며
30개 엔진의 PIPELINE→manifest→코드와 slot/port·schema를 쓰기 전에 확인한다.
실제 TXT150명령, 모든 profile의 실제 StageRunner 검사15회, 사진 오류 재현10회,
모의 compact generation의 동일 checkout gate5개가 통과했다. 과거 데이터 gate는
엔진 등록 검사를 포함하지 않아 R1/R2의 오류를 놓쳤으며 해당 실패 이력은 보존한다.
MAIN45·NFS 데이터/CURRENT는 변경하지 않았다. 사용자 요청으로 R3를 삼성파트너
메일에 발송했고 SENT `1a1155a0b057f9b2`에서 수신자와 ZIP·독립 RUN TXT·안내·
해시4개 첨부의 이름/크기를 확인했다. 발송 근거는 R3 `EMAIL_SENT.json`에 별도로
기록해 발송한 checksum과 준비 시점 HANDOFF를 보존한다. 사진의 실제 배포
commit/리비전/코드 hash와 R3 현장 apply/push/배포/질의는 미확인이다.

아래 R1/R2 발송과 검증은 당시 이력이다.

2026-10-07 사용자 현장 사진의 로그 롤백 R1 `Existing DEV checkout required`
오류에 대해 [DEV 경로 수정 R2](08_DEPLOYMENT/GENOS/handoffs/db_log_rollback_20261007_r2/GUIDE_UTF8.txt)를
삼성파트너 메일로 보냈다. SENT `1a1152e9627ac5ff`에서 R2 도구 ZIP·독립 RUN TXT·
안내·해시 4개 첨부를 확인했다. R1의 DEV 루트 심볼릭 링크 거부를 모의 환경에서
사진과 같은 오류로 재현했다. 실제 현장 링크 대상은 사진에 없어 미확인이다.
R2는 지정 DEV의 실제 checkout을 먼저 해결하고 내부 코드 링크/알 수 없는 해시는
계속 차단한다. `GENOS_DEV_ROOT → GENOS_DEV → ~/DEV` 선택과 실제 경로를 기록한다.
사진의 R1 check/apply/verify는 코드 변경 전 중단했으므로 R1 원복 없이 R2 check부터
진행한다. 상세 로그 롤백 코드와 검색 기능은 R1과 동일한 바이트이며 이전 자료는 보존한다.
실제 TXT 반입/원복50건·경로 선택/링크24건과 실제 checkout의 모의 generation gate4건을
통과했다. 로컬 활성 포인터는 그대로이며 GENOS R2 apply·push·리비전 배포·질의 결과는 미확인이다.

2026-10-07 사용자 요청으로 DB 지연 확인용 세부 계측만 제거한
[로그 롤백 R1 실행 안내](08_DEPLOYMENT/GENOS/handoffs/db_log_rollback_20261007_r1/GUIDE_UTF8.txt)를
삼성파트너 메일로 보냈다. SENT `1a1152164c6f02ca`에서 수신자와 코드 도구 ZIP·
독립 실행 RUN TXT·안내·해시 4개 첨부를 확인했다. `query_latency`의 INFO span,
CPU 압력/SQL 타이머와 `unit_fts.connection`/PRAGMA 진단을 제거하며 기존 검색 캐시·
순위·권한·원문·세션과 일반 진행/오류/감사 로그를 유지한다. 과거 전체 코드로 원복하지 않는다.
RUN TXT는 알려진 계측 R1~R4/시스템 로그 R1의 설치 inventory를 확인하고 기존
`~/DEV`에 두 코드와 기존 엔진 pin 30개만 백업/적용한다. 같은 checkout의
`APPLIED_CODE.zip`과 원복 receipt를 생성하며 기존 NFS 데이터/CURRENT는 보존한다.
작업 코드의 관련 계약38개, 실제 TXT 적용/재실행/원복/변조 보존 등50건 및
모의 generation의 동일 checkout 배포 gate2건을 통과했다. 로컬 활성 포인터
generation45는 변경하지 않았다. GENOS 실제 apply·push·리비전 배포·워크플로우
질의 결과는 미확인이다. 아래 계측 인계·완료 기록은 역사적 근거로 보존한다.

2026-10-07 현장 사진의 RECALL 약 141초 / SELECT 준비 약 190초 공백을 대상으로
[검색 준비 계측·중복 조회 감소 R3](08_DEPLOYMENT/GENOS/handoffs/query_latency_20261007_r3/README.md)를
삼성파트너 메일로 발송했다. SENT `1a115033dc621c25`에서 코드 ZIP·적용/워크플로우/
원격 push/로그 요약 TXT·안내·검증 기록·해시 8개 첨부와 수신자를 확인했다.
권한 범위는 원문 JSON 전수 읽기 대신 source ID 단일 SQL로 구하고, 요청의 SQLite
연결 안에서 FTS 적중 메타데이터를 재사용한다. 50,000개 초과 시 기존 전체 SQL로
돌아가며 순위·전체 건수·페이지·ACL·근거 계약을 유지한다. INFO 계측은 토큰화,
SQL execute/fetch, 원문 검증/읽기, 후보 구성, checkpoint, 모델 구성/예약/transport를 나눈다.
마지막 무소켓 R3와 선택된 `session-runtime-v6-20261007-r1`(MAIN45)의 세션 런타임을
함께 결속한 300파일 ZIP이다. 통합 검사93개와 실제 TXT 반입/원복/gate 검사9개가
통과했고, 이전 발송본에서도 재현되는 구 계약 테스트7개 실패는 별도 보존했다.
현장에는 계측 R3를 사용하고 분리 workflow 편집기도 첨부 전체 TXT로 갱신한다.
이번 작업은 로컬 활성 포인터를 변경하지 않았다. GENOS 반입·push·새 리비전 배포·
workflow 질의와 내부 속도 개선 정도는 미확인이다. 앞선 인계/실패 기록은 보존한다.

2026-10-07 사용자가 R2를 현장 `~/DEV`에 **apply까지만** 했다고 보고하고
Socket.IO 없이 `통합 직접 JSON / 분리 Python 워크플로우 SSE` 두 방식으로 복귀를 요청했다.
[무소켓 R3 인계](08_DEPLOYMENT/GENOS/handoffs/no_socket_chat_20261007_r3/README.md)는
R2 적용 바이트를 허용 선행 상태로 포함한 297파일 누적 ZIP이다.
통합은 기존 `main.py /chat` JSON, 분리는 `main_workflow.py /stream` HTTP SSE와
별도 Python 단계의 최종 JSON을 사용한다. 워크플로우 단계의 플랫폼 `main_socketio`
송신도 비활성화하고 두 코드서빙 연결의 Socket.IO 옵션을 끄도록 안내했다.
R2 백업을 먼저 원복하지 않고 R3 `check`가 통과할 때만 R3를 적용한다.
로컬 경로·회귀 39개와 반입/원복/gate 7개를 통과했고, 삼성메일 SENT
`1a11485b79056248`에서 R3 ZIP·실행/워크플로우/원격 TXT·안내·해시 6개 첨부를 확인했다.
R2 apply 상태는 사용자 보고이며 현장 R3 check/apply, Git push, 새 리비전 배포,
채팅앱 전환, 화면 결과는 아직 확인되지 않았다. 아래 R1/R2 이력은 보존한다.

2026-10-07 사용자 정정에 따라 HTTP/Socket.IO 전송 선택 R1을
[통합 Socket.IO / 별도 Python 워크플로우 SSE 선택 R2](07_DOCS/REFERENCE/OPERATIONS/GENOS_ROUTED_CHAT_MODES_20261007_R2.md)로 수정했다.
`python3 main_router.py`에서 `GENOS_MAIN_MODE=workflow`는 기존 Python 단계의 `/stream` SSE 백엔드,
`integrated`는 같은 프로세스 RAG와 Socket.IO token/end를 선택한다. 기본값은 workflow이며
existing은 workflow의 호환 별칭이다. 직접 `python3 main.py`는 이 선택을 적용하지 않는다.
워크플로우 모드의 일반 `/chat`은 409로 잘못된 연결을 알리며 별도 워크플로우 실행으로 가장하지 않는다.
GENOS의 채팅앱 대상·워크플로우 정의·소켓 옵션은 플랫폼에 저장되어 서버 변수로 자동 전환되지 않는다.
R2는 MAIN 44 코드를 보존한 296파일 ZIP·실행/워크플로우 TXT로 준비했고,
R1 대신 R2를 사용하라는 정정 메일 SENT `1a11475e83c04de8`에서 첨부 5개를 확인했다.
기존 코드 ZIP들을 순서대로 모두 적용하지 않는다. R2의 `check`가 현재 `~/DEV` 파일 해시와
선택 NFS generation 결속을 통과할 때만 R2 단독 적용하며 실패하면 현장 파일을 보존한다.
코드 적용·같은 checkout generation gate·push·리비전 배포·플랫폼 연결·현장 테스트는 별도 상태다.
실제 GENOS 배포·전환·화면 렌더링과 로컬 활성 포인터 변경은 수행하지 않았다. 아래 R1 기록은 보존한다.

2026-10-07 사용자 요청으로 기존 코드서빙을 유지하면서 새 코드서빙의 `/chat`을
환경변수로 기존 HTTP 방식 또는 직접 실행+Socket.IO 방식으로 선택하는
[작업 코드와 로컬 검증 안내](07_DOCS/REFERENCE/OPERATIONS/GENOS_ROUTED_SOCKET_CHAT_20261007.md)를 추가했다.
사진의 `socket.io 실시간 스트리밍 사용`은 사용자 코드에서 소켓 서버를 띄우는
모드다. 새 `main_integrated.py`가 그 서버를 제공하고 `main_router.py`가 앱을 선택한다.
실제 GENOS 연결 경로·인증 헤더·화면 렌더링과 새 코드서빙 배포는 미확인이다.

2026-10-07 로컬 MAIN generation **44**의 서빙 268파일을 동일 바이트로 담은
[조사 완료 계약 반입 R1](08_DEPLOYMENT/GENOS/handoffs/investigation_completion_20261007_r1/README.md)을
삼성파트너 메일로 발송했다. 코드 ZIP·실행 TXT·워크플로우 TXT·28질문 실제 결과·안내서
5개를 SENT `1a1145c6ab72f3cd`에서 확인했다. 설치/gate/NFS 지원 포함 코드 290파일이며
모의 적용·재실행·원복·변조 보존·동일 checkout gate/로컬 push 검사 14개가 통과했다.
**직접 `/chat` 통합과 별도 Python 워크플로우 방식 모두 지원한다.** 직접 방식은
`python3 main.py`의 `/chat`, 별도 방식은 첨부 Python TXT를 워크플로우 편집기에 반영한다.
첫 안내에서 편집기 교체를 공통 필수처럼 적은 부분은 같은 메일 스레드의
`GUIDE_CURRENT_ENTRY_R2.txt`(SENT `1a1145d470f3f508`)로 정정했다.
앞단 Socket.IO는 별도 진행 작업이며 이번 발송본에 그 후속 변경이 들어갔다고 보지 않는다.
후속 전체 에이전트 루프 검토는 설계이며 이번 코드에 추가 구현하지 않았다.
GENOS 현장 적용·push·리비전 배포·내부 질의 검증은 미확인이다.

2026-10-07 사용자가 워크플로우 없는 직접 통합 `/chat`으로 복귀를 지시했다.
승호 cicd를 fetch해 `388cd392`와 10월 6일 `36b9cc38`의 현장 SSE 오류 후
`REPORT_PROGRESS=off` 복귀 기록을 확인했다. 우리 직접 JSON 경로에 요청 단위
답변/progress 수집기와 `token → result.data.text` SSE를 연결한 작업 코드와
[직접 채팅 반입 R1](08_DEPLOYMENT/GENOS/handoffs/native_chat_sse_20261007_r1/README.md)을 준비했다.
관련 계약 26개와 ZIP 적용·재실행·원복·같은 checkout gate/로컬 push 검사 4개가 통과했다.
JSON은 기본이며 `?stream=1`/본문 stream=true는 명시적 SSE다. 플랫폼 등록 확인은 JSON이다.
소켓·HTTP 자기 호출·별도 Python 워크플로우 실행을 요구하지 않는다.
[원인·cicd 근거·실행 계약·검증 범위](07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_CHAT_SSE_20261007.md).
선택된 로컬 MAIN generation43과 GENOS 현장 배포/채팅 렌더링은 이번 작업 코드와 별도다.

2026-10-07 사용자 요청으로 데이터 ZIP 해제 명령·위치·기대 구조만 담은
`08_DEPLOYMENT/GENOS/handoffs/rag_data_unzip_20261007_r1/`의 RUN TXT와 짧은 GUIDE를 삼성메일로 보냈다.
`~/DEV/TRANSFER`의 실제 ZIP 파일명을 지정하여 SHA 파일이 있으면 검사하고
`~/DEV/TRANSFER/RAG_DATA_UNPACK/<ZIP stem>/payload/nfs-root/diamo/8-agent/`에 해제한다.
기존 해제 폴더는 보존하며 NFS 복사·Git·배포를 실행하지 않는다. 모의 해제·손상 SHA 차단 검증 PASS다.
SENT `1a113dac5a777c93`에서 삼성파트너 수신자와 TXT 첨부 두 개를 확인했다. GENOS 실제 해제는 미확인이다.

2026-10-07 현장 사진에서 데이터 ZIP 전용 R1이 압축 후 입력 변경 검사로 중단된 것을 확인했다.
사진에는 변경 경로가 없어 위치는 미확인이다. 사용자 요청으로
[데이터 ZIP 전용 R2 TXT](08_DEPLOYMENT/GENOS/handoffs/rag_data_zip_only_20261007_r2/README.md)를 준비했다.
선택 generation/runtime의 추가·삭제·수정 경로를 `SOURCE_CHANGES.txt/JSON`에 남기고 변경 중에도 ZIP을 완성한다.
실행 중 SQLite는 DB별 online backup을 사용하며 전체 파일의 동일 시점 일관성은 보장하지 않는다.
읽기 누락·generation 해시 불일치도 기록하고, 복원 허용 상태와 ZIP 완성을 구분한다.
계약 26개와 실제 첨부 TXT의 동시 파일 변경·SQLite WAL 백업 등 모의 검사 4개가 통과했다.
출력은 기존 `~/DEV/TRANSFER`이며 코드 설치·Git 변경·배포를 실행하지 않는다.
삼성메일 SENT `1a113b90b311643c`에서 수신자와 R2 TXT 첨부 한 개/18,561바이트를 확인했다.
데이터 ZIP 생성에는 R1 대신 R2 TXT를 사용한다. R2 현장 실행은 미확인이다.

2026-10-07 사용자가 요청 범위를 데이터 ZIP 생성만으로 정정하고 삼성메일 인계를 지시했다.
[데이터 ZIP 전용 TXT](08_DEPLOYMENT/GENOS/handoffs/rag_data_zip_only_20261007_r1/README.md)는
검증된 R7 데이터 도구를 같은 해시로 내장해 첨부 한 개와 한 명령으로 실행한다.
현장 generation/runtime을 원래 경로·DB 바이트 그대로 압축하고 `~/DEV/TRANSFER`에 출력한다.
RAG/AD 쓰기가 정상 종료된 상태에서 실행하며 SQLite sidecar/변조 검사는 유지한다.
모의 ZIP 생성·복원·Git 수정 보존·실패 처리 4개를 통과했다. SENT `1a113a78310df395`에서
삼성파트너 수신자와 TXT 첨부 한 개/14,500바이트를 확인했다. 실제 GENOS ZIP 생성은 미확인이다.

2026-10-07 두 현장 사진의 조사 제어 R2 해시 오류와 NFS R7 Git 사전 검사 중단을
함께 다루는 [조사 제어 반입 R4](08_DEPLOYMENT/GENOS/handoffs/investigation_control_20261007_r4/README.md)를 준비했다.
검증된 이전 릴리스에 R7 훅을 적용해 사진의 `7ea18ce5...`/`051b508b...`를 재현했다.
MAIN 서빙 265파일은 그대로이며 기존 R7 도구 4파일을 추가한 286파일 ZIP이다.
알려진 NFS 도구 변경을 조사 제어와 같은 반입/검증/커밋 범위에 묶고, 적용 전
코드·Git 추적/스테이징 충돌의 파일명·해시를 CHECKOUT_PREFLIGHT 보고서로 남긴다.
사진 2의 다른 수정 파일명은 화면에 없어 미확인이며 임의 변경은 계속 보존/차단한다.
모의 검사 14개와 실제 R7 TXT의 같은 Git 오류 재현, 동일 checkout gate·로컬 push를 확인했다.
기존 데이터·CURRENT·runtime을 보존했고 모델 호출은 없었다. 진단 로그는 해시와 무손실 압축으로 보관했다.
R4는 이 작업에서 메일을 발송하지 않았으며 아래 R3 발송본을 보존한다.
현장 R4 적용·전체 generation gate·push·리비전 배포·워크플로우 질의는 아직 미확인이다.

2026-10-07 사용자 현장 사진의 조사 제어 R2 `CHECKOUT_DRIFT`를 재현하고
[조사 제어 반입 R3](08_DEPLOYMENT/GENOS/handoffs/investigation_control_20261007_r3/README.md)를 삼성파트너 메일로 발송했다.
이전 NFS 설치기가 동적으로 바꾼 `stream_app.py`와 `service.py`의 결과 해시를 R2 허용 목록에서
누락한 반입본 작성 오류였다. 과거 원본 ZIP과 당시 설치기로 두 해시를 재현해 사진과 일치했다.
출고 코드 282개 및 선택 MAIN 서빙 265개는 R2와 같은 바이트다. 두 선행 해시와 진단 로그만 보완했다.
알 수 없는 현장 수정은 계속 거절하며 기존 generation·CURRENT·runtime DB는 보존한다.
R3의 실제 TXT 적용/재실행/원복/데이터 보존/변조 차단/동일 checkout gate·로컬 Git push
12개 검사를 24.76초에 통과했다. 임시 모의 checkout/DB는 로그 보존 후 정리했다.
SENT `1a1139ec2056e2f1`에서 수신자와 첨부 5개 이름·크기를 확인했다. 조사 제어에는 R2 대신 R3 ZIP/TXT를 사용한다.
사진은 R2 ZIP 및 cache 사전 검사 PASS와 코드 적용 전 중단을 확인한다.
R3 현장 적용·전체 generation gate·push·리비전 배포·워크플로우 실제 내부 질의는 아직 미확인이다.

2026-10-07 로컬 MAIN generation 43의 조사 제어 통합을 그대로 담은
[GENOS 반입 R2와 40문항 결과·시간](08_DEPLOYMENT/GENOS/handoffs/investigation_control_20261007_r2/README.md)을 삼성파트너 메일로 발송했다.
서빙 265파일은 선택된 `investigation-control-v6-20261007-r1`과 같은 바이트이며,
설치기·gate 의존성을 포함한 ZIP은 282파일, 약 1.35MB다. 원문·DB·키·JS를 포함하지 않는다.
기존 `~/DEV`에 백업/적용하고 기존 generation을 그대로 검증하며, 실제 push checkout의
commit·release gate·push를 기록하는 별도 Bash TXT와 워크플로우 전체 TXT를 첨부했다.
모의 적용/재실행/원복/변조 거절/데이터 보존/로컬 Git gate·push 7개 및
서빙 Python 3.11·워크플로우 Python 3.10 문법 검사를 통과했다. R1은 gate 의존성 누락을
발견한 미발송 중간본이고 R2에 기존 검증 지원 코드와 같은 의존성을 포함했다.
Gmail SENT `1a1136fc78d836dc`에서 수신자와 첨부 5개 이름·크기를 재확인했다.
R2 준비·발송 당시 현장 코드 적용·세대 gate·push commit·리비전 배포·워크플로우 실제 내부 질의는 미수행이었다.
아래 NFS_READ_R7의 데이터 이관 도구는 별도 목적이며 기존 실행 기록을 보존한다.

2026-10-06 사용자 최신 지시로 데이터 ZIP 기본 출력을 `~/DEV/TRANSFER/`로 변경한
[NFS 읽기·데이터 이관 R7](08_DEPLOYMENT/GENOS/handoffs/nfs_read_probe_20261006_r7/GUIDE_UTF8.txt)를 준비했다.
DEV가 NFS여도 생성하며 mount 종류는 정보로 기록한다. R6의 `/tmp` 기본값과 비NFS 제한을 대체한다.
확인된 generation/runtime 선택과 절대경로·DB·manifest·pointer 바이트 보존은 유지한다.
R1/R2/R6 helper의 정확한 해시를 허용하여 기존 반입 상태에서 이어서 적용한다.
계약 41개 및 실제 R7 TXT의 적용·읽기·로컬 remote push·DEV/TRANSFER ZIP 생성·복원 검증 PASS다.
최신 사용본은 R7 ZIP+RUN TXT다. 실제 GENOS 실행·배포·워크플로우 결과는 미확인이다.
R7는 삼성파트너 메일로 첨부 5개를 발송했고 SENT 메시지 `1a111357c8b8fbfb`에서
수신자와 첨부 이름·크기를 재확인했다.

2026-10-06 과거 대화·현장 마운트 기록을 다시 대조한
[NFS 읽기·데이터 이관 최종 R6](08_DEPLOYMENT/GENOS/handoffs/nfs_read_probe_20261006_r6/GUIDE_UTF8.txt)를 준비했다.
코드 `~/DEV → /workspace`이며 `/workspace`도 NFS다. 과거 `findmnt` 기록의 세 경로
`/workspace`, `/nfs-root/diamo`, `/ext_vol/aiweb_upload`는 모두 `nfs`다.
현장 generation은 `/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation`,
runtime은 `/nfs-root/diamo/8-agent/runtime`, 별도 state는 미설정으로 확인된 기록을 사용한다.
R6 RUN은 이 값을 명령행으로 지정하며 코드스페이스의 과거 `.env/CURRENT`를 재선택하지 않는다.
코드서빙은 준비 경로와 실제 리비전 환경변수의 일치를 별도로 검사한다.
데이터 ZIP 기본 출력은 `/tmp/genos-rag-data-export`이고 실제 mount가 비NFS임을 확인해야 생성한다.
NFS 데이터 논리 경로·manifest·SQL·pointer 바이트는 보존한다.
사진의 R2는 INSTALLED 후 prepare에서 경로 검사 실패이며 거부된 링크 위치는 사진만으로 미확인이다.
R6는 전체 경로와 실패 단계·선택 경로·mount 정보를 기록한다.
모의 계약 41개 및 실제 R6 TXT의 R2 후속 적용/검사/정확한 커밋 push/ZIP·복원/변조 차단을 확인했다.
앞서 발송한 R1/R2 대신 R6 ZIP/TXT를 사용한다. R3/R4/R5는 미발송 중간본이다.
현장 GENOS 읽기·Git push·리비전 배포·워크플로우 성공은 아직 미확인이다.
최종 R6는 삼성파트너 메일로 ZIP/별도 RUN TXT/안내/검증 기록 5개를 발송했고,
SENT 메시지 `1a11123dd3cf4987`에서 수신자와 첨부 이름·크기를 재확인했다.

2026-10-06 사용자 사진의 `symlink refused: /home/genos/DEV`는 NFS 접근 전 코드 root
검사에서 발생했다. [NFS 읽기 검사 R2](08_DEPLOYMENT/GENOS/handoffs/nfs_read_probe_20261006_r2/GUIDE_UTF8.txt)는
GENOS DEV alias를 실제 checkout root로 확인한 뒤 코드 파일·NFS 데이터의 링크 검사는
유지한다. 이전 NFS 읽기 검사 R1 대신 R2 ZIP/TXT를 사용한다. 데이터 ZIP 출력은
NFS 밖의 임의 로컬 폴더를 `--output-dir`로 지정할 수 있었다. R2의 당시 기본 DEV 출력은
DEV도 NFS라는 과거 마운트 근거를 놓쳤으므로 위 R6에서 수정했다.
모의 계약 33개와 사진 오류/R1 우회/정확한 R1 helper 교체/R2 TXT all·pack-data·변조 차단을
확인했다. GENOS 실제 적용·NFS 읽기·push·서빙 배포·워크플로우 성공은 미확인이다.

2026-10-06 [NFS 코드·데이터 읽기 검사 R1](08_DEPLOYMENT/GENOS/handoffs/nfs_read_probe_20261006_r1/GUIDE_UTF8.txt)을 준비했다.
DEV에 작은 `NFS_DATA_PROBE` 진단 훅을 적용하고, NFS 코드 복사·SQL 읽기·커밋/push 후
동일 커밋의 코드서빙을 워크플로우 테스트 화면에서 확인한다. 일반 RAG 진입점은 보존하며
검사는 모델/DB 쓰기 없이 실행한다. 모의 검사 28개와 실행 TXT의 전체 단계/변조 차단을
확인했다. 기존 service 회귀 22개는 PASS, 입력 바이트 상한의 과거 기대 검사 1개는
진단 훅 전에도 동일 실패였다. 실제 GENOS 접속·현장 배포·워크플로우 성공은 미확인이다.

2026-10-06 운영 데이터 공유볼륨 이관용 [RAG 데이터 ZIP 도구 R1](08_DEPLOYMENT/GENOS/handoffs/rag_data_bundle_20261006_r1/GUIDE_UTF8.txt)를 준비했다.
현장 DEV에서 선택 generation의 run 폴더와 runtime/별도 state를 묶고,
압축 해제 후 `/nfs-root/diamo`의 동일 절대경로로 해시 검증하며 복사한다.
기존 SQL·manifest·pointer 바이트를 보존하며 쓰기 중지 선언·sidecar/충돌 검사를 요구한다.
모의 파일/SQL의 압축·복원·재실행·오류 차단 12개 검사 PASS이며 실제 GENOS ZIP 생성·
볼륨 연결·데이터 복사·코드서빙 배포·워크플로우 검증은 미수행이다.

2026-10-06 사용자 요청으로 **로컬 RAG 서빙만**
`local-genos-unit-v6-20261006-r1`(포인터 generation 42)로 전환했다.
아래 `investigation_logging_20261006_r2` 누적 인계본의 런타임 171개 파일이
로컬 릴리스에서 동일한 해시로 확인됐다. 최신 설정 초안의 사전 원본은 보존하고,
compact 용어집 캐시·navigation v7·230,299개 소유 본문 단위 색인을 새 세대로 연결했다.
실제 로컬 서비스에서 최소 단위 검색과 첫 12그룹 READ를 확인했다.
GENOS 내부 자료·모델·배포 리비전은 접근 불가로 미확인이며 로컬 공개 자료·Qwen3.8과 구분한다.
[코드·데이터·전환·원복 검증](09_ARTIFACTS/AUDITS/20261006-local-genos-parity-r1/검증결과.txt).

2026-10-06 사용자 사진의 `REQUIRED_CONNECTION_PENDING → MemoryError → HTTP 422`에 대해
[원인별 로그 R2](08_DEPLOYMENT/GENOS/handoffs/investigation_logging_20261006_r2/README.md)를 준비했다.
저장된 참조 resolution/locator/해석 사유, 실제 모델 보류 결정, 미처리 메뉴·커서,
실제 실행 한도를 분리한다. 연결→선별→요청 실패의 journal·컨테이너 JSON·요청 로그에
참조 ID와 단계·발생 위치·메시지를 보존하며 화면 생략의 전체 기록 위치를 명시한다.
미평가 근거 현황과 중단 원인을 구분하고 과거 pending만으로 데이터 결함을 추정하지 않는다.
기존 조사 완료 기준·HTTP 종료 동작과 R3·compact reader·AD·읽기 위치 로그를 유지한다.
R1은 의존성 누락으로 실패한 미발송 중간본이며 현장에서는 R2를 사용한다.
ZIP 복원 코드 검사 199개와 인계 검사 17개 PASS다. 확대 검사에서 남은 과거 계약
실패 13개는 변경 전 R3에서도 같은 항목·사유로 확인했다. 전체 검사 통과로 보고하지 않는다.
이 인계본 준비 당시 로컬 frozen MAIN·NFS generation/CURRENT와 실제 GENOS 리비전은 전환하지 않았다.
이후 로컬 전환은 위 기록을 따른다.

2026-10-06 적중 단위 조사 루프 감사 F01~F12를 수정한 [RAG control flow R3](08_DEPLOYMENT/GENOS/handoffs/rag_control_flow_20261006_r3/README.md)를 준비했다.
미제시 연결의 다음 메뉴, 신규 span 재검토, 해소된 보류 제거, 차집합 READ,
수락한 선택·연결/읽기 커서 재개와 호출 timeout을 연결했다. 작은 적중 단위에서 시작한다.
최종 ZIP 코드 계약 169개와 인계/원복 검사 16개 PASS이며 compact reader·AD R2를 보존한다.
워크플로우 AD 메타데이터/API/서명 계약도 맞췄으므로 편집기 전체 코드 교체가 필요하다.
실제 GENOS 배포·내부 모델 정확도/지연과 로컬 frozen MAIN 승격은 미수행이다.

2026-10-06 원문 394곳 누적/약 9분 후 조건부 연결 판단 오류 사진에 대응해
[묶음 열람·충분 시 중단 R1](08_DEPLOYMENT/GENOS/handoffs/progressive_reading_20261006_r1/GUIDE_UTF8.txt)을 준비했다.
같은 조의 검색된 항·호·목과 상위 조건 본문을 묶고 처음 12묶음만 확보한 뒤,
실제 근거와 필수 연결 검토가 충분하면 남은 후보 열람을 멈춘다. 부족하면 다음 묶음을 읽는다.
미열람 후보/중단 이유와 상세 감사 원장을 보존한다. Fulltext 검색어/조항 위치를 표시하며
Reasoner 열람 채널은 진행 중 각 한 번과 최종 현황을 전달해 현장 카드 누적을 줄인다.
조건부 연결 판단에 적용 여부·이유를 필수로 요구하며 잘못된 재판단은 모델 제안 오류로 구분한다.
판단 표시 R2·AD R2·compact 용어집 복구를 보존한 누적 후속본이다.
로컬 반입 계약 검증과 실제 GENOS 모델 판단/배포/워크플로우 적용/지연 측정은 구분한다.

2026-10-06 사용자 요청으로 최종 답변 아래 판단 전체·일곱 단계·사용 데이터/행위를
중첩 토글로 표시하고 마지막 Mermaid를 코드에서 생성하는 작업 코드/누적 반입 R2를 준비했다.
현재 route/native refs와 payload hash에 결속하고 실제 조·항·호·목·원문·선택 이유·판단을
표시한다. 표시를 위한 LLM 호출은 추가하지 않으며 ‘이유 없음’ 기본 문구를 표시 로그에서 제거했다.
용어집 binding 복구 R1의 compact reader, AD R2와 연결 읽기 R2를 보존한다.
[실행·표시 계약·미리보기·검증 범위](07_DOCS/REFERENCE/OPERATIONS/GENOS_JUDGMENT_VIEW_20261006.md).
코드서빙 리비전 배포와 워크플로우 편집기 전체 코드 교체가 각각 필요하다.
로컬 frozen MAIN·NFS generation/CURRENT와 GENOS 현장 배포·렌더링은 별도이며 미수행이다.

2026-10-06 검사기 현장 사진에서 선택된 `financial-risk-success-20261005-schema-r2/generation`의
cache가 compact reader `e03dab54...`를 요구하지만 `/workspace` checkout은 legacy
`ba2c6ced...`임을 확인했다. receipt/용어집 manifest/사전 메타데이터는 PASS이고
compact reader/compiler는 FAIL이다. [용어집 결속 복구 R1](08_DEPLOYMENT/GENOS/handoffs/glossary_binding_repair_20261006_r1/GUIDE_UTF8.txt)은
reference R1의 정확한 reader와 관련 engine pin을 복구하는 연결 읽기 R2 누적 반입본이다.
AD 기능과 연결별 읽기를 보존하며 기존 캐시/NFS 데이터/receipt/CURRENT는 변경하지 않는다.
필요한 모의 계약 84개, 9개 알려진 반입 상태의 적용/재실행/원복/캐시 보존과
사진 오류 재현 후 전체 로컬 gate를 통과했다. 검증 범위 밖의 과거 검사 차이는 별도 기록했다.
현장 SQLite 전체 검증·새 코드서빙 배포·내부 모델 질의·MAIN 승격은 별도이며 미수행이다.

2026-10-06 추가 현장 사진의 `glossary compiler/cache binding mismatch` / HTTP 422를
확인하고 최근 보존 ZIP을 대조했다. reference R1·request_input R2의 compact 용어집
reader(`e03dab54...`)를 AD 언어 R1/R2가 legacy reader(`ba2c6ced...`)로 교체하며,
연결 읽기 R2도 legacy 바이트를 포함한다. compact 스키마 지원까지 빠지는 코드 회귀다.
현장 cache receipt가 요구하는 hash·실제 선택 generation·배포 리비전은 아직 미확인이다.
[읽기 전용 검사기와 실행 안내](08_DEPLOYMENT/GENOS/diagnostics/glossary_binding_20261006_r1/GUIDE_UTF8.txt)로
두 hash를 대조한다. 기존 반입본·데이터·receipt를 보존하며 해시 수동 변경으로 우회하지 않는다.
이번 작업은 진단/최근 반입 검토만 수행했고 서빙 코드 복구·현장 배포는 수행하지 않았다.

2026-10-06 현장 사진에서 AD 언어 R2 적용은 성공했으나 연결 읽기 R1이 이전
`ad_gateway.py`를 required pin으로 요구해 적용 전에 중단됐다. 반입 기준 누락을 수정한
[연결 읽기 R2](08_DEPLOYMENT/GENOS/handoffs/relation_reading_20261006_r2/GUIDE_UTF8.txt)는
AD R2의 gateway/context/model/store/표와 연결 읽기 R1 및 화면 요약을 함께 유지한다.
기존 연결 읽기 R1은 적용하지 않는다. 현장 순서의 오류/파일 보존을 재현했고,
8개 알려진 predecessor의 적용·재실행·원복·코드 변조 거부·엔진 pin·ZIP/Git 비교와
반입 backend 기반 모의 계약 121개를 통과했다. 실제 generation 전체 gate·코드서빙 배포·
워크플로우 편집·내부 모델 판단과 로컬 frozen MAIN 승격은 별도이며 미수행이다.

2026-10-06 사용자 지시로 연결 종류·방향별 읽기 정책과 화면 로그 요약을 누적 R1로 준비했다.
v6 조 단위 FTS도 최소 단위 READ와 선택 뒤 연결 탐색을 사용한다. 준용·정의 범위 누락과
조건부 연결의 근거 없는 생략을 거부하며 상위 조건 원문과 이미 읽은 범위 재사용을 연결했다.
필수 연결과 선택 탐색의 메뉴 초과를 구분하고 검토 후 넓힌 범위의 연결을 재확인한다.
[반입·실행·워크플로우 편집·검증·원복 안내](08_DEPLOYMENT/GENOS/handoffs/relation_reading_20261006_r1/GUIDE_UTF8.txt).
작업 코드 계약 90개, 발송 backend 코드 핵심 계약 55개, 네 predecessor 적용/원복과
ZIP/Git 결속 검사를 통과했다. 로컬 공개 세대는 원문 E2E PASS이나 GENOS용 reader와
glossary cache binding이 달라 전체 게이트는 미통과다. actual GENOS generation/revision,
내부 모델 판단·워크플로우 편집·현장 배포와 로컬 frozen MAIN 승격은 별도이며 미수행이다.

2026-10-06 AD 후속 R2 작업 코드는 긴 표의 가로·세로 스크롤 HTML 표시와
구간별 내부 LLM 읽기를 연결했다. 기존 20행 목록/상세 이어보기와 전체 SQL 원본을
보존하고, 모델에는 참조·미리보기 및 필요한 구간 하나씩 전달한다. 복수 모델 호출은
개별 SQL 감사 기록으로 남기며 미완료 읽기를 완료로 처리하지 않는다.
코드 ZIP 적용·새 코드서빙 배포와 워크플로우 편집기 전체 교체가 모두 필요하다.
GENOS HTML/CSS 렌더링과 내부 모델 품질은 현장 검증 전까지 미확인이다.
[AD R2 계약·제한·반입](07_DOCS/REFERENCE/OPERATIONS/AD_NATURAL_LANGUAGE_20261006.md).

2026-10-06 원문 열람 화면 로그 과다를 줄이도록 워크플로우 표시를 수정했다.
항·호·목마다 새 Reasoner 노드를 추가하는 대신 열람 중/확보 현황 두 요약을 갱신한다.
문서별 원문 위치 건수와 일부 열람 상태를 표시하며 본문에는 각 요약을 한 번만 추가한다.
`progress_display_revision=reasoner-display-read-summary-20261006-r1`이다.
128개 마디의 반복·부분/완료 전환·누적 노드·최종 답변 보존을 포함한 표시 관련29개 검사와
Python3.11 구문 검사를 통과했다. 검색·실제 READ·원장·세대·로컬 활성 frozen MAIN은 유지한다.
GENOS 워크플로우 편집기에 전체 Python 반영이 필요하며 현장 적용은 아직 수행하지 않았다.
[표시 계약·검증 범위](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md).

2026-10-06 사용자 지시로 작업 코드의 모델 입력 바이트 상한과 그 상한을 이용한
입력 구성 제한을 제거했다. 일반 GENOS의 출력 토큰은 기존
`GENOS_RAG_MAX_OUTPUT_TOKENS` 설정을 유지한다. v6 요청 해석·검증·수정 입력에서는
전체 문서 목록과 이력에 반복 저장된 문서 ID 목록을 제외하며 서버 권한 검사·복원,
멀티턴 이력·legal_wiki 힌트·목록 요청 경로는 유지한다.
[누적 반입 R2·적용/게이트/현장 확인/롤백](08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2/GUIDE_UTF8.txt)은
SQL/AD R5와 compact 로더를 함께 유지하고 기존 reference R1의 compact 용어집 reader를
보존한다. 로컬 작업 코드·반입본 수정이며 활성 frozen MAIN과 실제 GENOS 리비전은 별도다.

2026-10-02 누적 v6 R4 반입 후보는 R2 이후 최소 원문 단위/펼치기·묶음 참조·압축 메뉴/범위 재선택을
연결하고 판단·답변 의미 검증 LLM 두 호출을 제거한다. 현재 색인 구현과 NFS 저널·service/service.py를
보존한다. 단위 탐색은 명시 선택한 단위 fulltext에서만 동작하며 CURRENT/서빙 배포는 별도다.
연결 수집의 조 단위 범위와 CM003/CM051 실패는 남아 있다.
[실행·미확인 사항](07_DOCS/REFERENCE/OPERATIONS/UNIFIED_LEGAL_AGENT_20261002.md).

2026-10-02 후속 사용자 사진에서 GENOS latest 로더의 실제 입구는
`project_root/service/service.py`이며 컨테이너 로그도 `/app/service/service.py`를 가리킨다.
사진의 직접 오류는 `unsupported GENOS_RAG_IMPLEMENTATION`이고, 값 원문·실제 코드 hash는
미확인이므로 경로 오류 하나로 원인을 확정하지 않는다. 작업 저장소에는 루트 `service.py`만
있었고 R2의 v6 변경이 플랫폼 입구에 연결되지 않을 가능성을 확인했다.
`service/service.py` 배포 adapter가 정확한 루트 v6 구현을 읽고 `service`/`service.service`
import는 같은 모듈·cache·warmup을 공유한다. 루트 구현·데이터 경로는 보존하며 별도 실행기를
늘리지 않는다. `service/`는 사용자 요청에 따른 플랫폼 호환 입구이며 MAIN의 논리 데이터 root가 아니다.
기존 Python 워크플로우와 service JSON 입구를 유지하고 `/chat` 이관은 선택사항이다.
앞선 연결 전용 R1과 main.py 제거 R2 롤백 안내는 적용 금지다. 사진 이후의 어댑터 반입·새
코드서빙 리비전·실제 v6 질문 성공은 현장 확인 전까지 미확인이다.


2026-10-02 현장 continuation R1 사진은 `/workspace/01_DATA/TERM_RELEASES/<run>/reindex/.lock`
부재로 입력 확인 전에 종료됐음을 보여 준다. 색인/검증/NFS 복사는 시작되지 않았다.
[후속 R2](08_DEPLOYMENT/GENOS/handoffs/fulltext_continue_20261002_r2/GENOS_FULLTEXT_CONTINUE_20261002_R2.txt)는
같은 명시 run의 설정 데이터 루트·checkout 데이터·`/workspace/01_DATA` 완료본을 먼저 대조한다.
복수 완료본은 정확한 `GENOS_FT_BASELINE` 지정을 요구하며, 없으면 완료본 경로 목록을 표시한다.
다른 run/최신 날짜를 자동 선택하거나 빈 입력 폴더를 생성하지 않는다. 원본/목록/경로 선택/lock 및
frozen R8 fulltext·NFS 모의 실행 관련 12개 검사 통과. 실제 완료본 위치와 현장 실행은 미확인이다.

2026-10-02 사용자 요청으로 [완료 navigation 이후 최소 단위 fulltext·검증·NFS 발행 실행기](08_DEPLOYMENT/GENOS/handoffs/fulltext_continue_20261002_r1/GENOS_FULLTEXT_CONTINUE_20261002_R1.txt)를 추가했다.
R8 `reindex/baseline/result.json`이 있는 완료본에서 저장된 마디의 직접 본문만 별도 색인한다.
구조화·용어집·연결·navigation을 재구축하지 않고 원본 세대와 기존 조 단위 FTS를 보존한다.
동일 reindex lock으로 동시 실행을 거부하며 건수/바이트 진행률과 현재 단계 ETA를 기록한다.
검증 뒤 `/nfs-root/diamo/8-agent/term-releases/<run>/fulltext-unit-r1/generation` 및 형제 links/audit 자료를
새 임시 폴더에 복사·전체 hash 검증·원자적 발행한다. 기존 세대/CURRENT/서빙 코드는 전환하지 않는다.
ADR-0620의 색인 builder만 명시 선택한 standalone payload이며 전체 연구 후보의 READ 실패/미승인 상태와 구분한다.
NFS index 산출물을 serving bundle/E2E 완료로 인증하지 않는다. 동작과 원본 보존·변조·R8 실제 바이트 호환을
포함한 로컬 8개 검사 통과. 실제 GENOS/NFS 접근·발행·서빙은 미확인이다.

2026-10-02 사용자 요청으로 [navigation 병목 관찰 검사기](08_DEPLOYMENT/GENOS/handoffs/navigation_diagnostic_20261002_r1/GENOS_NAVIGATION_DIAGNOSTIC_20261002_R1.txt)를 추가했다.
별도 터미널에서 명시 run의 같은 사용자/checkout 구축 PID를 약 30초 관찰한다.
CPU·프로세스 I/O·커널 대기·DB/journal 크기와 최근 완료 SQL을 수집하며 프로세스 신호·코드/DB 변경은 하지 않는다.
현장 설치 코드의 SQL 실행 계획은 빈 메모리 스키마에서 확인하고, 실제 DB는 잠깐 조회 전용으로
색인 메타데이터와 EXPLAIN만 확인한다. 100ms busy timeout·0.3초 조회 예산·2초 하위 프로세스 제한,
활성 WAL 생략·큰 테이블 COUNT/원문 수집/분석·재색인 없음. 결과는 GENOS 내부 LOGS에 남기며 반출을 요구하지 않는다.
현재 SQL 번호는 마지막 완료 로그에 따른 추정으로 확정하지 않는다. 로컬 읽기 보존/잠금 생략/실행 유지/인계 실행 6개 검사 통과.
GENOS 실제 실행과 병목 확정은 미확인이다.

2026-10-02 사용자가 실제 건수와 예상 시간을 요청해
[진행 계측 R9](08_DEPLOYMENT/GENOS/handoffs/reindex_progress_20261002_r9/GENOS_REINDEX_PROGRESS_20261002_R9.txt)를 추가했다.
R8 준비본/범위는 유지하고 연결 블록·일치 표면, navigation 문서, 전문 색인 source를 실제 루프에서 계수한다.
5초 로그에 완료/전체/단위/진행률·최근/평균 속도·현재 처리 예상 잔여/종료 UTC 시각을 표시한다.
준비·SQL·해시·검증 등 계수 없는 구간은 task 이름과 ETA 미측정 상태를 표시하고,
후속 단계가 미측정인 전체 완료 시각을 만들어 내지 않는다. 30초 이상 진전이 없으면 ETA를 중지한다.
새 출력 기본값은 `financial-risk-success-20261002-index-r9`이며 동일 입력의 R8 실행은 신원 확인 후 종료한다.
원자료/R8 반입본/산출물은 보존하며 코드 적용 시 R8 해시를 명시적으로 허용한다.
로컬 연결/검색/재개/건수/ETA/적용·원복 관련 41개 검사가 통과했다. GENOS 실제 속도/완료/서빙은 미확인이다.

2026-10-02 사용자는 완료된 구조화/용어집을 재사용해 연결과 색인만 다시 만들도록 범위를 지정했다.
[연결·색인 전용 R8](08_DEPLOYMENT/GENOS/handoffs/reindex_only_20261002_r8/GENOS_REINDEX_ONLY_20261002_R8.txt)는
기존 `term_generation.build_generation(serving=False)`와 `fulltext.build`를 직접 연결한다.
새 용어 의미 검토·정의/번역 생성·내부 모델 명시 참조 검토·전체 근거 묶음 검사/복사·서빙 캐시·공유 발행은 수행하지 않는다.
native 규칙 참조의 모호함은 미해결 상태로 보존한다. 실제 조회하는 lookup.sqlite·legal.sqlite와
선택 manifest/준비 입력만 결속·검증한다. 원본 근거·완료 세대는 보존하며 서빙 인증은 별도다.
새 출력은 `financial-risk-success-20261002-index-r8/reindex` 아래 baseline/links,
baseline/generation/navigation, baseline/audit/navigation, fulltext, release.json이다.
완료 navigation 뒤 전문 색인이 실패하면 navigation은 검증해 재사용한다.
동일 사용자/checkout/prepared 입력의 알려진 이전 구축만 기록·종료 확인 후 적용한다.
전체 로그 이벤트를 유지하고 current.json의 fsync는 초당 최대 한 번으로 제한한다.
로컬 실제 연결·규칙 참조·전문 검색·입력 보존·재개·제한 검증·기존 실행 중단 범위를 확인했다.
GENOS 실행·전체 시간·서빙은 아직 미확인이다.

2026-10-02 사용자는 외부 파일 반출이 어렵고 반복 반입을 근본적으로 줄이도록 지시했다.
[대체 실행 R7](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r7/GENOS_PIPELINE_OPTIMIZATION_20261002_R7.txt)는
현장 전체 rehash 검증 대신 패키지 범위의 엔진 코드 pin 계획을 적용 전에 작성한다.
패키지 밖 기존 코드/미등록 파일/스키마 pin 불일치는 해시와 목록을 현장에 기록하고 그대로 보존한다.
기존 불일치를 정상이라고 인증하거나 실제 코드와 맞도록 일괄 덮어쓰지 않는다.
profiles·과거 데이터 pin은 유지하며 새 입력/산출물 검증·전체 서빙 인증과 분리한다.
현장에 이미 있던 차이와 실행 중 새로 발생한 외부 코드·메타데이터 변경을 구분하고 후자는 중단한다.
패키지 파일 버전 검사는 유지한다. 새 출력은 `financial-risk-success-20261002-opt-r7`다.
이전 코드·스키마 pin 불일치·미등록 파일·없는 과거 데이터가 함께 있는 모의 현장을 재현해
적용·검증·정확한 원복·알 수 없는 패키지 파일 거부·동시 외부 변경 보존을 확인했다.
현장 적용·전체 구축·서빙은 아직 미확인이며 외부 진단 파일 반출을 요구하지 않는다.

2026-10-02 R5 사진의 직접 호출 진단은 과거 `relation-subtree-main-serving-20260920-v1`
navigation manifest 부재와 코드 원복을 보여 준다. 이번 준비본 구축은 시작되지 않았다.
[대체 실행 R6](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r6/GENOS_PIPELINE_OPTIMIZATION_20261002_R6.txt)는
엔진/PIPELINE 메타데이터의 임시 복사본에서 네이티브 코드·스키마 검사를 수행하고,
검증한 엔진 파일 hash와 PIPELINE의 engines sha만 원본에 반영한다.
원본 profiles·데이터 경로·데이터 pin은 보존하고 과거 데이터 검증은 완료로 처리하지 않는다.
새 prepared/output 검증·활성화는 별도다. 이전 파일 부재 재현·적용·원복·관련 없는 코드/스키마
거부를 포함한 로컬 검사 31개와 Python 3.11/bash 문법 검사를 통과했다.
기본 출력은 `financial-risk-success-20261002-opt-r6`이며 현장 적용·전체 구축·서빙은 미확인이다.

2026-10-02 R4 현장 사진은 코드 사전 검사 통과·파일 적용 후 엔진 결과의
JSON 파싱 실패와 `ROLLBACK COMPLETE`를 보인다. 구축 단계는 시작되지 않았다.
[대체 실행 R5](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r5/GENOS_PIPELINE_OPTIMIZATION_20261002_R5.txt)는
선택 checkout의 `control.rehash_engines`를 직접 호출하고 stdout/stderr/종료코드를
`engine-command-*.json`에 보존한다. 빈 출력/잘못된 JSON/관련 없는 변경은 성공 처리하지 않는다.
최적화 코드·실행기·허용 predecessor는 R4와 같다. 기본 출력은 `financial-risk-success-20261002-opt-r5`다.
이전 반입 control의 실제 subprocess 검사·pin 적용·검증·원복을 포함한 관련 검사 27개와
Python 3.11 문법 검사를 통과했다. 현장 stdout 원문·전체 적용·구축·서빙은 미확인이다.

2026-10-02 R3 현장 사진에서 `term_index.py`와 `fulltext.py`가 사전 검사에서
불일치해 코드 적용 없이 종료된 것을 확인했다. 실제 해시는 보존된
response_overhead R3와 fulltext_diagnostics R1 패치 코드에 각각 일치한다.
[대체 실행 R4](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r4/GENOS_PIPELINE_OPTIMIZATION_20261002_R4.txt)는
검증된 두 predecessor만 추가하며 최적화 코드·실행기 바이트는 R3와 같다.
새 출력 기본값은 `financial-risk-success-20261002-opt-r4`다.
사진의 두 불일치 재현·적용·롤백·알 수 없는 변경 거부를 포함한 관련 검사 22개와
Python 3.11/bash 문법 검사를 통과했다. 현장 적용·구축·서빙 완료는 미확인이다.

2026-10-02 현장 R2는 이전 worker 종료 후 `term_generation.py FILE_DRIFT`로
코드 적용 전에 중단됐다. [대체 실행 R3](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r3/GENOS_PIPELINE_OPTIMIZATION_20261002_R3.txt)는
보존된 이전 반입 ZIP에서 검증한 세 코드 해시만 이행 대상으로 추가하고,
코드 검사 후 worker를 중단한다. 불일치한 실제 해시와 코드 차이는 진단 ZIP에 기록한다.
입력 준비본은 그대로이며 새 출력 기본값은 `financial-risk-success-20261002-opt-r3`다.
최적화 코드 바이트는 R2와 같고 로컬 계약·회귀 검사 91개가 통과했다.
현장 해시 일치·적용·전체 구축·서빙은 아직 미확인이다. R1/R2 반입본과 원자료는 보존한다.

2026-10-02 사용자 확인에 따라 완료된 준비본을 재사용하는
[최적화 OFF 재구축 R2](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r2/GENOS_PIPELINE_OPTIMIZATION_20261002_R2.txt)와
[실행값·로그·보존 안내](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r2/GENOS_PIPELINE_OPTIMIZATION_R2_GUIDE_UTF8.txt)를 추가했다.
입력은 `financial-risk-success-20261001-r3`, 새 출력은 기본
`financial-risk-success-20261002-opt-r2`다. 원문/구조화/용어 초안/검토 원장을 보존하고
새 용어 의미 검토를 실행하지 않으며, 문서–용어 연결·navigation/감사·전문 색인과
기존 내부 모델의 명시 참조 처리·검증·별도 공유 발행을 연결한다.
기록된 기존 worker의 PID/boot ID/시작시각과 실행 잠금을 확인한 뒤 종료 확인·백업·적용한다.
최적화 R1의 11개 코드 바이트를 그대로 사용하며 현장에 없는 navigation_storage는
검증한 파일로 추가할 수 있다. 예상 밖 코드/engine/schema 변화는 적용을 중단하거나 원복한다.
입력/선택 범위와 실제 적용 코드의 해시를 새 계보에 결속하며 기존 plan pin을 수정하지 않는다.
최초 실행부터 전체 stdout/stderr를 `run.log`에 남기고, 파일 복사·해시·용어집 캐시·색인·참조·검증에
5초 생존 로그와 `events.jsonl`, `current.json`, `phases.csv`, `summary.txt`를 기록한다.
전문 색인 실패 시 navigation checkpoint를 검증해 재개한다. 과거 결과 삭제는 필요하지 않다.
GENOS 실제 적용/구축/서빙, CURRENT·Git push·workflow 반영은 별도이며 미확인이다.

2026-10-02 구축·검토·색인 공통 반복 처리를 최적화했다.
[ADR-0616](04_EXPERIMENTS/ADR/ADR-0616-pipeline-bottleneck-optimization/README.md),
[ADR-0617](04_EXPERIMENTS/ADR/ADR-0617-lexical-trie-scan-optimization/README.md)의
원문·연결·미해결·감사·전문색인 순위 계약을 유지한 작업 코드다.
[현장 실행 TXT](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r1/GENOS_PIPELINE_OPTIMIZATION_R1.txt)와
[기존 검토 자료 재사용·적용/롤백 안내](08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r1/GENOS_PIPELINE_OPTIMIZATION_R1_GUIDE_UTF8.txt)를 준비했다.
기존 복구 R3를 먼저 보존하고, 기존 checkout hash가 일치할 때만 백업 후 적용한다.
검토 implementation pin을 조작하지 않고 완료된 source/glossary로 새 미활성 generation을 만든다.
151개 로컬 통합 검사가 통과했으며 GENOS 적용·현장 전체 속도·MAIN/서빙 활성화는 미확인이다.

2026-10-02 legal_agent를 유지하는 통합 v6 작업 코드를 추가했다.
같은 질문·정정·확정 경험을 두 위키와 다음 대화가 공유하며,
[실행·신원·카탈로그·이관·복구 계약](07_DOCS/REFERENCE/OPERATIONS/UNIFIED_LEGAL_AGENT_20261002.md)을 따른다.
진행 표시는 v6의 실제 수락 단계·정정·재검색·경험 재결속에 연결했으며,
기존 누적 Reasoner 배열/JSON 문자열 형식을 유지한다.
[출력 계약·코드서빙/편집기 반영·확인](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md).
명시 선택 후보이며 기존 MAIN·NFS 세대·현장 코드·서빙 리비전·workflow는 변경하지 않았다.
WSL 모의 계약 검증과 GENOS 내부 모델·저장·답변 품질 검증을 구분한다.

2026-10-02 최신 MAIN 작업 코드와 누적 멀티턴 구현의 통합 반입본을 준비했다.
[통합 상태](07_DOCS/REFERENCE/OPERATIONS/SYSTEM_MEMORY_INTEGRATION_20261002.md),
[전체 체크리스트](08_DEPLOYMENT/GENOS/handoffs/system_integration_20261002_r1/CHECKLIST.md),
[적용·검증·복구 안내](08_DEPLOYMENT/GENOS/handoffs/system_integration_20261002_r1/README.md).
기존 `~/DEV`의 파일별 백업·적용을 사용하며 과거 실험 증거는 별도 보관한다.
멀티턴은 기본 비활성이고 현재 MAIN 릴리스·NFS 데이터·서빙 리비전·워크플로우 편집기는
이 반입 준비로 변경되지 않는다. 실제 현장 검증과 법률 품질 인증은 남아 있다.

현장 Python 실행 명령은 사용자 확인(2026-10-01)에 따라 `python3`다.
현장 인계 TXT는 checkout 안의 `.venv/bin/python` 존재를 가정하지 않는다.
실제 인터프리터 경로·버전은 `python3`의 `sys.executable`·`sys.version`으로 로그에 남긴다.
WSL 로컬 개발·테스트는 기존 규칙대로 저장소 `.venv/bin/python`을 사용한다.

2026-10-01 후속 사용자 요청으로 의미 검토를 실제 벌크 전송하는
[R2 실행 TXT](08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt)와
[짧은 안내](08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R2_BULK_GUIDE_UTF8.txt)를
추가했다. 기존 R1의 100건 반복은 단건 API이므로 2일 목표에는 R2를 사용한다.
R2는 최대 32개 비교/물리 호출·최대 4개 동시 호출·출력 8192토큰·read timeout 120초,
105000자 요청 한도를 사용한다. 큰 요청은 실제 묶음 수를 줄이며 원문/근거/범위는
자르지 않고 공유 테이블로 무손실 전달한다. 배치·근거 alias는 원래 job/입력 해시로
복원 후 v3 의미/스키마 검증을 수행한다. 중복 JSON 키·비JSON·잘린 응답·누락/중복/외부
작업 ID는 성공 처리하지 않고, 잘못된 전체 JSON만 최대 2단계 소묶음 재시도한다.
교차 작업 근거 오류는 해당 결과를 반영하지 않는다. 완전히 실패한 3개 wave면 남은 큐를
보존하고 중단한다. 원래 r3 원장/프롬프트 pin은 수정하지 않고
`r3/<run>-bulk-r2`의 snapshot·execution_variant·origin·물리 호출 원장에 새 프로토콜과
설정/코드/프롬프트/입력 계보를 결속한다. 기본 36시간 검토+12시간 후속 여유는 목표이지
측정된 성능이 아니다. 249242건에는 약 1.92개/초가 필요하며 실제 32건/4병렬 기준
평균 약 66초/호출 이하가 검토 목표 조건이다. 48시간 완료와 GENOS 서빙 성공은
미확인이며 실제 pairs/s·ETA·목표 위험을 현장 로그로 확인한다. OFF/ON은 독립 최종
연결·색인·명시 참조 LLM을 유지하고 NFS에 `<run>-bulk-r2-meaning-off/on`으로 저장한다.
현재 서빙/CURRENT·코어 checkout·워크플로우는 변경하지 않는다. 기존 v3 attempts는
논리 작업 시도 수이고 실제 벌크 물리 호출 수는 `review/bulk-status.json`에 별도 기록한다.
로컬 모의 계약·회귀 62개, 내장 두 Python 소스와 Bash 구문, 실제 launcher의 중복 방지·
중단·재개를 검증했다. 실제 내부 데이터/모델의 의미 품질과 현장 48시간 성능은 미확인이다.

2026-10-02 현장 사진에서 R2의 색인 생성은 34002.4초 뒤 전문 색인 시작 시
`/workspace/<stdin>`을 spawn 자식이 열려다 실패했고, 임시 폴더 정리도
`Directory not empty: navigation`으로 실패했다. 사진 재확인 결과 navigation은
**33384.2초(9시간16분24초)**이며 초기 안내의 3384.2초(56분24초)는 숫자 오독이다.
generation 전체 34002.4초와의 차이는 약10분18초다.
[시간 판독 정정 TXT](08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r1/GENOS_NAVIGATION_TIMING_CORRECTION_20261002_UTF8.txt)와
[사진·정정 영수증](09_ARTIFACTS/AUDITS/20261002-navigation-timing-correction/receipt.json)을 따른다.
원본 R2 TXT 바이트·검토 원장·계획은
보존하고 [복구 실행 TXT R3](08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r3/GENOS_MEANING_RECOVERY_20261002_R3.txt)와
[실행·로그·재개 안내](08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r3/GENOS_MEANING_RECOVERY_20261002_R3_GUIDE_UTF8.txt)를 사용한다.
복구 실행기는 기존 `~/DEV`에 추가한 실제 Python 파일로 실행하고, 동일 R2 검토·참조·발행
경로를 호출한다. 완전한 이전 scratch는 native 입력·범위·컴파일러·색인·감사 결속 검증 후
원본을 보존한 사본으로 재사용한다. 없으면 저장된 준비본에서 연결·색인을 재구축한다.
새 전문 색인 시작 전 checkpoint를 남기고 실패 scratch를 보존하며 다음 실행은 검증 후
전문 색인부터 재개한다. 후속 사진의 R1 worker는 기존 `off/plan.json`과의
`Immutable receipt differs`로 종료 코드 1로 중단했다. R1 사전 검사는 기존 variant
plan 비교를 빠뜨렸다. R2는 실제 현재 코드/입력에서 원래 실행기가 만드는 plan을
구축 전 대조하고 같은 파일(dev/inode)·동일 SHA-256의 checkout 경로 별칭만 기존
pin 키로 재사용한다. 기존 plan 바이트를 바꾸지 않으며 별칭 증거는 별도 append-only
원장에 남긴다. 별도 사본·파일 변경·설정 변경·추가/누락 pin은 중단한다. 2026-10-02
후속 현장 코드스페이스 사진에서 Python 3.11.15, `PLAN ALIASES verified same inode + SHA-256`,
`CHECK existing off frozen plan PASS`를 확인했다. 기존 OFF plan 충돌은 같은 파일의 pin 경로
별칭 차이였으며 plan 보존 검사가 통과했다. 개별 별칭은 현장 별칭 원장에서 확인한다.
09:46 worker의 `VARIANT off: document-term linking and baseline index` 진입은 확인했지만
baseline 완성·전문 색인 재개·NFS 발행은 아직 확인되지 않았다. 함께 찍힌
`GENOS_REFERENCE_CHECK_R1_UTF8.txt`의 `sqlite3.OperationalError: database is locked`는
이전 `.baseline-*`의 navigation DB를 점검한 별도 명령의 종료 기록이다. 잠금 소유자는
사진만으로 확정하지 않으며 이 오류를 R2 worker의 종료로 간주하지 않는다.
09:48 후속 사진에서는 R2 worker가 기존 scratch 검사 중 현장에 없는
`semantic_runtime.navigation_storage`를 무조건 import하여 종료 코드 1로 중단했다.
R3는 R1 검증식의 이 import만 기존 storage 분기로 옮기며 통합 색인은 현장의 원래
Store/TermIndex·원문/범위/연결/용어집/컴파일러 해시 검사로 검증한다. 감사 분리 색인은
이 모듈이 필수이며 없으면 시작 전 중단한다. 필수 검증 함수의 실제 import/callable과
기존 색인 형식별 의존성을 사전 검사하고 실행 환경·소스 해시를 별도 원장에 남긴다.
코어 파일은 추가/교체하지 않는다. 실제 모듈이 없는 모의 구버전에서 오류 재현·원본
scratch 사본의 전문 색인 재개·참조 처리·로컬 공유 발행 계약을 검증했다.
R1/R2 runner·R1 checkpoint는 정확한 기존
해시로 유지하고 R3 runner를 추가한다. R1/R2/R3의 PID·잠금은 공유한다. `log-off/on/review`는
기록된 worker 로그를 그 터미널에서 열고 `status`는 일회 상태 출력이다.
로컬 원인 재현·복구·인계 계약 67개를 검증했으며 실제 현장 잔여 파일,
구축·NFS 발행·서빙 성공은 미확인이다. CURRENT·Git push·워크플로우는 변경하지 않는다.

2026-10-01 사용자 요청으로 준비된 `financial-risk-success-20261001-r3`의 용어 의미
검토를 별도 장기 작업으로 분리했다. [OFF/ON 실행 TXT](08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R1_UTF8.txt)는
기존 foreground BUILD를 Ctrl+C로 종료한 뒤 `review-background`로 남은 검토를
자동 반복하고 완료 시 ON을 구축한다. `baseline`은 현재 의미 검토를 생략한 OFF를
먼저 구축한다. 기존 구조화·원문 범위는 공유하지만 최종 문서–용어 연결·참조 overlay·
색인은 각자 생성하고, 명시 문서·조문 참조 LLM은 두 경로 모두 유지한다. OFF는
기존 용어집의 과거 LLM 산출물까지 제거한 순수 비LLM 세대가 아니다. ON의 의미
관계는 근거 결속 제안이며 PARTIAL/미확인 상태를 정본 승인으로 바꾸지 않는다.
실패 작업은 무한 재시도하지 않고 원장·원래 traceback을 보존한다(자격증명만 마스킹).
연속 10회 API/검증 실패 시 남은 큐를 보존하고 중단하며 완료/ON 구축을 주장하지 않는다.
코어 파일을 hot patch하지 않으며 원래 의미 검토 구현/입력 해시를 유지한다.
로그는 기능 시작/종료, 활성 기능 경과, 의미 검토 잔여 수와 근사 ETA를 표시한다.
100건은 자동 반복의 한도이지 호출 묶음/병렬화가 아니다. 캡처 속도 10초/건이면
24만 건은 약 29일이며 nohup은 터미널 종료만 견디고 서버/컨테이너 재시작 후에는
수동 재개가 필요하다. `status`로 PID·로그·실패 요약을, `stop-review`로 기록된 PID만
중단한다. NFS의 별도 `*-meaning-off/on/generation`과 `rag-selection.json`은 서빙
시작 시 `GENOS_GENERATION` 선택용이다. 각각 별도 서빙 설정/리비전이 필요하며
이 TXT는 CURRENT·활성 서빙·Git·워크플로우를 바꾸지 않는다. 현장 구축·서빙 검증은
미확인이다. 로컬 모의 계약·회귀 46개 및 Bash/내장 Python 구문을 확인했다.

2026-10-01 사용자 요청으로 후속 구축의 반복 전체 상태 로그를 변경 항목만 표시하도록
수정했다. [로그 수정 TXT R3](08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SELECTED_ONLY_BUILD_R3_UTF8.txt)는
선택 2,121개·문서 근거 replace·실행 ID `financial-risk-success-20261001-r3`·모델 프로필을
R2와 같게 유지한다. 첫 상태는 전체 1회, 이후 변경 항목과 현재 기능/경과 한 줄을
표시한다. 정의 단서 추출·새 사본의 과거 근거 분리·용어 출현 재탐색을 하위 기능 로그로
추가하며 오류·traceback은 변경 감지 필터의 대상이 아니다. 준비는 로컬 규칙/DB
처리로 LLM 검토 전 단계다. 실행 중 R2는 hot patch하지 않으며 완료/정상 종료 후
다음 재개에서 R3를 사용한다. `--watch`는 별도 터미널 읽기 전용 관측으로 기존 R2
터미널의 출력 형식을 바꾸지 못하고 저장되기 전 준비 내부 위치도 알 수 없다.

2026-10-01 현장 후속 r2의 원문 통합 2,121개는 완료했지만 용어 후보 준비는
`Document version ID reused with changed content`로 중단했다. 원문 base를 제외해도
기존 용어집의 corpus_document 근거가 append 정책으로 남아 충돌한 것이다.
현행 [실행 TXT R2](08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SELECTED_ONLY_BUILD_R2_UTF8.txt)는
기존 문서 근거를 새 용어집 사본에서만 `--glossary-corpus-policy replace`로 재구성하고
새 run `financial-risk-success-20261001-r3`를 사용한다. 기존 r1/r2 계획·원본 용어집·
RAW·구조화 결과는 보존하며 lexical 근거와 정확히 일치하는 독립 검토 재사용 계약은
기존 replace 구현을 따른다. 본문 정의·출현·문서 근거 연결은 이번 선택본으로 다시
검토한다. R3 코드 배선과 현장 replace 계약을 검사하고, 로컬 감사/검색 색인 분리
배선의 현장 존재 여부를 출력한다. 색인 최적화 코드를 이 TXT가 현장에 배포하는 것은
아니다. 로컬 관련 검사 28개 통과; 현장 후속 구축·활성화·최적화 적용은 미확인이다.

2026-10-01 사용자 사진에서 후속 원문 통합은 기존 NFS 세대와 선택 구조화 입력의
중복 2,104개 중 673개 행 차이로 중단했다(동일 1,431개). 표시된 6건은 기록된 원본
해시가 같으며 전체 충돌의 원본 동일성은 사진만으로 확정하지 않는다. 사용자 승인에
따라 기존 NFS 원문 입력을 제외하고 DOCX 재처리 성공분 포함 기존 선택 2,121개만
새 run `financial-risk-success-20261001-r2`로 구축한다.
[실행 TXT](08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SELECTED_ONLY_BUILD_R1_UTF8.txt)는
R3 코드 배선 적용 후 사용하며 이전 성공 스냅샷과 부모의 문서별 구조화 키·영수증
동일성을 검증한다. 기존 RAW·실패한 r1 계획·NFS 세대는 보존한다. 내부 참조 모델
프로필·용어 검토·문서 연결·참조 보정·색인·진행 로그를 유지하며 활성화는 하지 않는다.
종료 코드 3은 남은 검토 작업으로 같은 명령을 재실행한다. 로컬 관련 검사 23개 통과;
GENOS 실제 구축·배포 성공은 아직 미확인이다.

2026-10-01 사용자 사진의 진행 표시 전송 형식을 워크플로우 작업 코드에 적용했다.
`GENOS_RAG_PROGRESS_UI=socketio`는 `agentFlowExecutedData` 누적 배열과
`data.output.content`의 JSON `visible_rationale`을 사용하며 진행 문구를 답변 본문에
붙이지 않는다. 기존 본문 표시는 `socketio-inline`로 선택할 수 있다. 답변 SSE·출처·
검색·모델·팀 범위·오류 경로는 유지한다. 워크플로우 편집기 전체 교체만 필요하며
코드서빙·데이터·로컬 MAIN은 변경하지 않는다. 관련 로컬 검사 118개 통과이고 현장
반영·렌더링은 미확인이다. [교체 Python](08_DEPLOYMENT/GENOS/patches/GENOS_REASONER_DISPLAY_20261001_R1_WORKFLOW.py)과
[적용·확인·복구 안내](08_DEPLOYMENT/GENOS/patches/GENOS_REASONER_DISPLAY_20261001_R1_GUIDE.txt)를 따른다.

2026-09-29 사용자 지시로 채팅 워크플로우의 문장 뒤 숫자 참조 `[1]` 등을 표시 단계에서
제거했다. 생성 중·완료 후 표시를 함께 처리하고 인용문·코드·문자 괄호와 문서명·조문 출처,
모델의 원래 답변·근거 원장은 유지한다. 워크플로우 Python 전체 교체로 적용하며
코드서빙·데이터·로컬 frozen MAIN 변경은 없다. 현장 편집기 반영·배포·질문 확인은 미확인이다.
[범위·현장 교체·검증·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_ANSWER_REFERENCE_DISPLAY_20260929.md).

2026-09-29 사용자 지시로 형식·판단 오류 수정 기능을 새 immutable 릴리스
`legal-agent-structure-catalogue-pecab-repair-20260929-r1`에 결속하고 로컬 MAIN generation31로
활성화했다. 기존 PeCab 데이터·모델 결속을 유지하며 기본 수정1회를 사용한다.
frozen 계약42개와 서비스 결속을 확인한다. 실제 GENOS 리비전 배포는 별도다.
[MAIN 반영·검증·복구](07_DOCS/REFERENCE/OPERATIONS/MODEL_DECISION_REPAIR_MAIN_20260929.md).
현장 사진의 코드 조합에서는 최초 메일 R1이 기준 해시 검사로 쓰기 전에 중단했다.
사진의 세 파일 바이트에 맞춘 단독 적용 R2와 다른 코드 메일의 선택 적용·재실행 안내는
[사진 기준 인계·메일 호환성](07_DOCS/REFERENCE/OPERATIONS/GENOS_SELECTIVE_MAIL_COMPATIBILITY_20260929.md)을 따른다.

2026-09-29 사용자 지시로 MAIN 작업 코드의 구조 기반 판단에서 JSON·스키마·참조 및
교차 필드 오류를 이전 출력·검증 오류와 함께 모델에 돌려줘 수정하도록 연결했다.
선택 프로필의 형식 수정 횟수와 원래 호출·시간 예산을 사용하며 서버·저장소 장애와 구분한다.
진행 표시에는 수정 중/수정 횟수 소진을 전달한다. 작업 코드·로컬 frozen MAIN·현장 배포는 별도다.
[실행·검증·복구](07_DOCS/REFERENCE/OPERATIONS/MODEL_DECISION_REPAIR_20260929.md).

2026-09-29 최신 사용자 지시로 구조 원문 우선·네 가지 요청 분류·PeCab 세대·답변 SSE를
통합하고 로컬 MAIN을 `legal-agent-structure-catalogue-pecab-20260929-r1`로 전환한다.
진행 중 품질 실험의 통과로 간주하지 않으며 `quality_certified=false`를 유지한다.
GENOS 환경도 bounded 경로를 사용하도록 연결했다. 공개 색인과 내부 전체 구축을 구분하며
Git main 병합·GENOS 배포·워크플로우 확인은 별도다.
[통합 범위·현재 상태·현장 인계](07_DOCS/REFERENCE/OPERATIONS/RAG_USER_DIRECTED_MAIN_20260929.md).

2026-09-29 사용자 요청으로 v5 MAIN 작업 코드의 문서 구조를 검색 시작점에 연결했다.
법령명·등록 약칭과 본문 조문/표제가 유일하면 기존 READ로 원문을 먼저 확보한다.
구조 미일치·모호함 또는 읽은 근거 부족 시 기존 fulltext로 확장한다. bounded와
모델 도구 탐색 프로필에 적용하며 데이터 재구축·워크플로우 교체는 필요하지 않다.
로컬 계약 검사와 GENOS 적용·내부 모델의 판단·실제 속도는 구분한다.
[경로·기록·검증·복구](07_DOCS/REFERENCE/OPERATIONS/STRUCTURE_FIRST_SEARCH.md).

2026-09-29 사용자 지시로 v5 MAIN 작업 코드의 최종 답변 본문을 생성 중 전달하도록
연결했다. 최종 검토가 꺼진 작성 단계에서 내부 모델 SSE의 문단 본문만 request별
`answer_delta`로 보내고, 확정 dict·검증·원장과 완료 후 출처를 유지한다. 적용 TXT와
코드 ZIP, 편집기 교체용 전체 Python을 준비했다. 모의·연결·인계 검사 136개 통과이며
내부 모델/게이트웨이의 점진 전달·현장 리비전 적용·화면 표시는 미확인이다.
[호출·반영·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_ANSWER_STREAMING_20260929.md).

2026-09-29 사용자 지시로 현행 형태소 처리·fulltext 구축/질의를 PeCab 1.0.8로 통일하고
서비스 진입점에서 Kiwi 색인과 frozen runtime 실행을 거부한다. 공개 145문서는 새 색인으로
재구축하며 실제 내규는 GENOS에서 같은 `--rebuild` 생성기로 처리한다. 요청 판단과 짧은
사유를 SSE에 연결했다. 네 가지 요청 모드 후보의 Qwen3.8 비교는 ADR0555에 격리한다.
로컬 활성 포인터·MAIN 후보 승격·GENOS 배포는 별도다.
[PeCab·요청 분류의 실제 연결과 검증](07_DOCS/REFERENCE/OPERATIONS/GENOS_PECAB_REQUEST_ROUTING_20260929.md).

2026-09-29 사용자 지시로 v5 MAIN 작업 코드의 첫 검색 계획에서 인사·사용법 안내는
검색 없이 직접 응답하도록 연결했다. 문서 목록 표현을 보완하고 현재/볼수있는 표현의
제목 필터 오인을 수정했다. 기존 요청 범위·원문 질문 경로·출처 발행 계약을 유지하며
코드서빙 리비전 적용과 내부 모델 분류 정확도는 현장 미확인이다.
[분기·실행 계약·검증·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_REQUEST_ROUTING_20260929.md).

2026-09-29 fulltext 배포 전 비교 TXT의 현행 실행본은 R2다. R1은 코드스페이스에
코드서빙의 세대 설정/CURRENT가 없는 경우 검색 전 `GenerationUnavailable`로 중단했다.
R2는 실제 현재 checkout의 논리 data root와 기존 공유 NFS 발행 세대에서 검색 입력을 확인하며
배포 설정이 없어도 직접 실행한다. 후보 하나면 실행하고 여러 개면 사용자가 번호로 고른다.
검색 함수·비교 기준·데이터·CURRENT는 변경하지 않는다. 설정/CURRENT/E2E 스크립트가 없는
모의 checkout에서 ZIP 내장 TXT 전체 실행을 검증했고 실제 GENOS 속도는 미확인이다.
[실행·데이터 선택·R1 교체](07_DOCS/REFERENCE/OPERATIONS/GENOS_FULLTEXT_LOCATION_20260929.md).

2026-09-29 사용자 지시로 MAIN 작업 코드의 fulltext 위치 구성에서 결과 전체의
본문 JSON 조회를 제거했다. 문서/폴더 범위는 세대가 검증된 matcher 위치 메타데이터를
사용하고 조문 내부 본문 검사·페이지 프리뷰·READ·정확 total/cursor·요청 deadline을
유지한다. 엔진 코드 pin도 함께 갱신했다. 디스크/파일 I/O는 병목 후보이며 NFS 단독
원인으로 확정하지 않는다. 데이터·로컬 활성 frozen 릴리스·GENOS 리비전은 별도다.
[변경·계약·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_FULLTEXT_LOCATION_20260929.md).

2026-09-28 기존 로그에서 초반 로딩과 FULLTEXT 계측만 TXT로 분리하는
독립 검사 도구를 추가했다. 질문·본문·모델 응답을 제외하고 구간별 작업/CPU,
캐시와 SQL 읽기·위치 구성을 정리한다. 중첩 계측은 합산하지 않으며 누락은
미확인으로 표시한다. TXT 한 개로 실행하고 코드서빙·데이터 배포는 변경하지 않는다.
[실행·입력·확인 범위](07_DOCS/REFERENCE/OPERATIONS/GENOS_BOTTLENECK_LOGS_20260928.md).

2026-09-28 사용자 지시로 MAIN 작업 코드의 v5 최종 답변 검토를 기본 비활성화했다.
`final_review_enabled=false`인 경우 작성한 답변을 반환하며 review 호출·형식 보정·검토
재작성 루프를 실행하지 않는다. 작성 한계는 보존하고 원장에는 검토 생략·UNREVIEWED를
기록한다. GENOS 환경 기본과 파일 프로필, 도구 탐색과 bounded 회수 경로에 적용한다.
로컬 활성 frozen 릴리스·데이터·CURRENT·GENOS 리비전은 별도다.
[배선·검증·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_FINAL_REVIEW_DISABLED_20260928.md).

2026-09-28 fulltext 병목 계측을 MAIN 작업 코드에 추가했다. SQL 배치별 벽시계·CPU,
현재 색인 크기와 cache/query plan, 같은 프로세스의 동시 검색 수, 위치 구성의
본문 SQL·JSON 변환을 나눠 기록한다. 검색 순위·범위·정확 total/cursor·요청 deadline은
유지한다. 사진의 fetch 약 83초와 위치 구성 약 21초는 관측이며 NFS 단독 원인으로
확정하지 않는다. GENOS 반입·리비전 배포·새 로그 확인은 별도다.
[계측·해석·검증·후속 후보](07_DOCS/REFERENCE/OPERATIONS/GENOS_FULLTEXT_DIAGNOSTICS_20260928.md).

2026-09-28 MAIN 작업 코드의 v5 LLM 입력에서 중복 본문·스키마와 작성 단계의 탐색 안내를
제거하고 지침을 단계별로 정리했다. 원문·좌표·번호 매핑·출력 검증과 실제 전송 영수증은
보존한다. 정상 응답에는 형식 보정 호출이 붙지 않는다. 데이터·워크플로우·로컬 활성
frozen 릴리스는 변경하지 않으며 GENOS 새 코드서빙 리비전 적용과 실제 속도는 미확인이다.
[배선·전송 계약·검증·원복](07_DOCS/REFERENCE/OPERATIONS/LEGAL_AGENT_PROMPT_COMPACTION_20260928.md).

2026-09-28 작업 코드의 공유 요청 기록을 한국 시간 `날짜/team_id/` 아래로 나누고,
팀별 `질문답변.xlsx`·CSV 요약을 기존 비동기 finalizer에 연결했다. 위험관리·재무관리
워크플로우는 기존 `TEAM_ID=risk_team`·`financial_team`을 사용한다. 두 코드서빙의
동시 갱신은 팀·날짜별 파일 잠금과 요청별 요약 행으로 처리한다. 로컬 계약 검증이며
현장 리비전 적용·NFS 잠금은 미확인이다.
[설정·요약표·기존 기록 복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_TEAM_REQUEST_LOGS_20260928.md).
현행 인계 R3는 R2의 Python 버전별 `ast.dump` 해시 차이로 생긴 함수 검사 실패를
수정했다. 실제 Python 3.11에서 사진의 생성자 오류 해시를 재현하고 3.14와 같은
서명·변환 결과를 확인했다. 필요한 함수만 변경하고 기존 현장 진단 바이트와 등록
hash 검증은 보존한다. 팀 로그 R1/R2 대신 R3를 사용하며 실제 GENOS 적용은 별도다.

2026-09-28 관계 탐색의 별도 5초 제한을 사용자 지시로 제거했다.
`follow_relations`·`follow_reference`의 SQLite 조회와 Python 목록 순회에는
요청 전체 deadline만 적용한다. 기존 프로필의 `relation_scan_seconds`는
호환용으로 보존하며 실행에서는 사용하지 않는다. 페이지·문자 수·횟수·
자동 읽기 깊이·범위/해시 검증은 유지한다. 데이터 재구축과 워크플로우 교체 없이
새 코드서빙 리비전이 필요하다. 로컬 모의 계약 검증과 현장 배포·질문 성공은 별도다.
[변경·반입·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_RELATION_WAIT_20260928.md).

2026-09-28 답변 속도 요청으로 `response-overhead-20260928-r1`에서 정상 단계·캐시 적중의
상세 INFO 로그를 DEBUG로 옮기고, 이벤트/보고서의 중복 인증정보 정제와 환경 순회를 줄였다.
공유 로그 생성·질문 저장도 답변 경로에서 분리하고, 반복 manifest/receipt/코드 해시와
스키마 검사기 생성을 재사용한다. 오류·진행·원장·팀/원문/세대 검증은 유지한다.
부분 패치와 코드/pin 원복을 준비했으며 GENOS 적용·리비전과 실제 단축 시간은 별도다.
[변경·검증·반입·한계](07_DOCS/REFERENCE/OPERATIONS/GENOS_RESPONSE_OVERHEAD_20260928.md).
현행 인계 설치기는 R3다. R2 사진의 report SHA `febd2ee763…d18b40`, 44082 bytes와
`_LiveLog.emit` 함수 서명 `4a00a4ad…d817bd4`를 모두 재현했다. R2는 fulltext 진단
표시가 적용된 함수를 목록에서 누락해 쓰기 전에 중단했다. R3는 해당 표시와 같은
fulltext 파생 조합을 보존해 수정하며, 실제 적용 전 파일 9개와 최종 TXT를 검증한다.
R1 전체 hash 거부·R2 함수 거부는 적용 성공이 아니며 원복할 소스 변경이 없었다.
기존 진단·팀 로그·현장 추가 바이트와 Python 3.11/3.14 고정 서명을 유지한다.
동시기 다른 인계본의 정상 적용은 사용자 보고다. 실행 코드 표식은 R1 그대로다.

2026-09-28 1차 성능 수정 `latency-20260928-r2`: 세대 결속 팀·문서 catalogue,
최종 구조 검증·문서별 source 목록 재사용, 계획 전 admission, WARMUP 연결,
진단 로그 비동기 출력 및 FTS/원장/모델 준비 세부 계측을 구현했다.
로컬 계약·설치기 검증이며 현장 속도·generation gate·코드서빙 배포는 미확인이다.
R1 적용 checkout에는 새 R2 ZIP/TXT를 사용한다. [수정·반입·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_LATENCY_R2_20260928.md).

2026-09-28 두 번째 질문의 준비 지연을 확인하기 위해 `latency-20260928-r1`
진단 로그를 추가했다. `ask.started` 전후 팀 조회·범위 계획·스키마 검증과
`session.sources` 내부의 핸들 저장·구조 검사를 분리하고, 실제 블록 시간·스레드 CPU·
로그 출력 시간을 함께 기록한다. [패치·적용·로그 해석·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_LATENCY_DIAGNOSTICS_20260928.md).
로컬 계약 검증이며 현장 원인 확정·성능 개선·코드서빙 배포는 미확인이다.

2026-09-27 사용자 지시로 v5 fulltext SQL의 별도 20초 중단 제한을 제거했다.
기존 FTS5 순위·범위·결과 수 계약을 유지하며 요청 전체 deadline만 적용한다.
GENOS generation의 v5 요청 시간은 기본 1800초(30분), 워크플로우 대기는
2100초(35분), 내부 모델 연결 대기는 60초로 늘렸다. 기존 환경변수 값이 있으면
새 값으로 별도 변경해야 한다. 플랫폼 게이트웨이·워크플로우 실행 제한은 코드로
변경되지 않는다. [시간 제한·설정·반입·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_FULLTEXT_WAIT_20260927.md).
데이터 재구축은 없으며 실제 현장 오류 해소와 GENOS 리비전 배포는 미확인이다.

2026-09-28 현재 인계본 `timeout-sync-20260928-r3`는 기존 설정/CURRENT/검증 영수증으로
데이터 세대를 자동 확인해 적용 TXT에 경로를 다시 입력하지 않는다. R2와 같은 캐시 호환 복구로 R1의 용어집 캐시 결속 오류를
수정해 `full_glossary.py`를 이전 바이트/해시로 복구한다. 캐시 receipt·데이터·CURRENT는
변경하지 않는다. 실제 v5 요청 예산1800/워크플로우2100은 유지한다. 현장의 정확한
generation 경로는 코드서빙 환경의 GENOS_GENERATION 또는 GENOS_DATA_ROOT 아래
generations/CURRENT.json의 path에서 확인한다. R1 시간 변경은 현재 프로필 5개·PIPELINE의 7개
요청 시간 설정과 v1~v5·navigation·term/task 기본 실행 시간을 1800초로 맞췄다.
현재 GENOS 구축/authoring의 300초 모델 대기는 1800초, 호출 스크립트는 2100초,
DOC 변환 진단은 기존 변환 설정과 같은 900초다. 워크플로우의 두 HTTP 경로도
같은 2100초 기본값과 명시 환경변수를 사용한다. 완료된 릴리스·실험·고정 코드
세대는 바꾸지 않는다. 전체 ZIP을 기존 `~/DEV`에 백업 후 적용하고, 워크플로우
Python을 별도로 교체한다. 현장 300초 HTTP 500의 발생 주체는 아직 미확인이다.
[전수 목록·배포·설정 확인·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_TIMEOUT_SYNC_20260928.md).

2026-09-28 승호 통합 브랜치의 긴 요청 경로를 대조한 뒤
`sse-transport-20260928-r1` 전송 패치를 추가했다. 법률 질문은 소켓 ID나 진행 표시
설정과 관계없이 `/stream`을 읽고, 최종 답변은 같은 HTTP 응답으로 받는다.
서버는 즉시 응답을 시작하고 조용한 동안 10초마다 heartbeat를 보낸다.
코드서빙 시작 앱을 `stream_app:app`으로 연결하고 워크플로우 Python도 별도 교체해야 한다.
`{"question":"SSE_CHECK"}`를 워크플로우 테스트에 입력해 실제 연결을 확인한다.
이 진단은 모델·검색·데이터 세대 없이 SSE 경로만 검사한다.
기존 요청 예산 1800초와 데이터·용어집 캐시 결속은 유지한다. 로컬 계약·HTTP 연결을
검증했으며 현장 300초 이후 결과 수신과 새 리비전 배포는 미확인이다.
[적용·시작 명령·워크플로우 교체·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_SSE_TRANSPORT_20260928.md).
현행 SSE 인계 설치기는 R2다. 현장 `~/DEV` 심볼릭 링크를 R1이 거부해 적용 전
중단한 문제를 수정했다. 사용자가 지정한 checkout 입구를 실제 Git root로 해석하고
논리 경로·실제 경로를 영수증에 기록한다. 변경 파일 내부의 링크 거부와 바이트 검증은
유지한다. 서버·워크플로우 코드는 R1과 동일해 SSE_CHECK 서버 리비전은 R1이다.

SSE Run 변경 뒤 약 12분의 기동 지연 보고에 따라 `sse-startup-20260928-r1` 시작
수정을 별도로 준비했다. HTTP 시작·상태 확인·SSE_CHECK에서 service 자동 준비를
시작하지 않도록 지연 적재하고, HTTP 생존 경로와 worker 1개를 명시한다. 질문이나
WARMUP에서 기존 자료 검증은 그대로 실행한다. 기존 앱의 import 시 준비 시작,
GET `/health` 404, WEB_CONCURRENCY 상속을 로컬에서 재현했지만 현장 지연의 단일
원인·플랫폼 probe 계약·worker 수는 아직 미확인이다. 최초 자료 준비 비용은 남으며
데이터·워크플로우·엔진 pin 변경은 없다. [시작 수정·검증·반입](07_DOCS/REFERENCE/OPERATIONS/GENOS_SSE_TRANSPORT_20260928.md).

현행 진행 표시 작업 코드 `chat-flow-20260928-r2`는 진행 문단을 번호·빈 줄로
나누고 실제 열람 문서·조문, 완료/일부 상태, 커밋된 근거 선택 이유와 검토 결과를
표시한다. 동일 문서의 페이지 알림과 모델 수신/형식 검증 반복은 합치거나 생략한다.
해시 검증된 요청 binding의 문서 범위에 한정하며 원문 본문·숨은 추론은 보내지 않는다.
네 소스 파일과 관련 코드 pin을 함께 적용하고 코드서빙 리비전을 배포한 뒤
워크플로우 Python 전체를 별도로 교체해야 한다. Run·Build·generation·CURRENT는
유지한다. [R2 반입·편집기 교체·확인](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md).
작업 코드와 로컬 검증이며 R2 현장 반영은 아직 미확인이다.

이전 진행 표시 `chat-status-20260928-r1`은 고정 시작 안내를 실제 단계별 채팅
토큰으로 바꾸고, heartbeat에 마지막 단계·경과 시간을 표시한다. 첫 지연 service
적재의 로깅 초기화가 진행 수집기를 제거하던 문제도 수정했다. 코드서빙 파일 적용과
워크플로우 Python 전체 교체·저장·배포가 모두 필요하다. `GENOS_RAG_PROGRESS_UI=socketio`
모드에서 사용한다. 시작 R1·데이터·원장·최종 답변 계약은 보존하며 로컬 회귀 61개
통과와 현장 화면 표시는 별도다. [표시 수정·반입·확인](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md).

2026-09-27 사용자 지시로 v5 최종 검토는 답변 차단 대신 **법률 검토 필요사항**을
출력한다. 최종 작성해 저장한 답변 문장은 관계 검토 누락·인용 불일치·요건/예외
불일치·검토 미완료에도 보존한다. 문서명·조·항과 확인할 내용을 표시하며
검토 미완료를 통과로 저장하지 않는다. `GENOS_RAG_RELAX_REVIEW_QUOTE_MATCH`는
기존 검토 기록의 엄격성만 제어하며 이제 답변 표시를 차단하는 스위치가 아니다.
선택·전달된 원문, 접근 범위·해시·세대 결속 검사는 유지한다. 데이터 재구축 없이
새 코드서빙 리비전과 워크플로우 Python 전체 교체를 적용해야 한다.
[출력 계약·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_FINAL_REVIEW_ADVISORY_20260927.md).
작업 코드 변경이며 현장 배포와 실제 질문 성공은 아직 미확인이다.

2026-09-25 채팅 출력 작업 코드: 소켓 ID가 있으면 답변 완료 후 최종 텍스트를
조각으로 전송하며, 채팅 본문은 최종 답변과 채택 출처의 문서명·조문 위치·핵심/보완 구분을 표시한다.
GENOS 채팅에서는 출처 항목을 문서명·위치 텍스트로 표시한다. 상대 열람 경로가
출처명 대신 노출된 현장 사진을 반영해 링크를 채팅 본문에서 제외했다.
열람 경로는 API source bundle에 보존한다.
`확인 한계`와 원문 발췌는 채팅 출처 목록에서 제외한다. 생성 자체의 토큰별
스트리밍과 GENOS 현장 적용은 아직 확인되지 않았다.

**현장 테스트는 워크플로우 테스트 화면에서만 가능하다. 코드서빙 직접 테스트 UI/API 실행을 사용자에게 요구하지 않는다.**

2026-09-25 후속 작업 코드: v5 법률 에이전트가 `FINAL` 답변을 만들면 응답에
`publication_status=PENDING`을 표시하고 즉시 반환한다. 전체 원문 DB 검증과 출처
발행은 별도 worker가 수행하며, 완료 전 출처 URL은 아직 열리지 않을 수 있다.
worker 종료 시 최종 답변 journal에서 복구한다. 요청마다 glossary SQLite 연결을
다시 여는 비용은 프로세스별 전용 lease pool로 줄였다. `rag.loop.started.elapsed_ms`와
`session.context/journal/sources/gateway`로 질문 후 실제 루프 진입을 측정한다.
현장 코드서빙·워크플로우 적용, 첫 질문 1초 달성은 아직 미확인이다.
[반환·준비 경로](07_DOCS/REFERENCE/OPERATIONS/GENOS_RESPONSE_COMPLETION_20260925.md).

2026-09-25 후속 수정: 요청별 `resources.tools` 목록 로딩도 검증된 navigation 세대의
프로세스 캐시에 포함했다. 일반 질문으로도 준비되며 다음 질문에서 `tools.cache.hit`가
남는다. 워크플로우 Python 단계는 `WARMUP`/`WARMUP_STATUS`를 그대로 전달하고,
질문이 없을 때 플랫폼 UUID를 질문으로 선택하지 않는다. 코드서빙 배포와
워크플로우 Python 전체 교체를 각각 적용해야 한다. 현장 단축 시간은 미확인이다.

2026-09-25 답변 생성 뒤 NFS 보고서 저장을 기다리던 반환 경로를 분리했다.
fulltext 검증 캐시와 배포된 코드서빙의 `WARMUP`/`WARMUP_STATUS`로 첫 질문 전
리소스를 준비한다. 기존 PeCab generation을 재사용하며 현장 배포·단축 시간은
미확인이다. [반환 지연 수정·사전 준비·로그·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_RESPONSE_COMPLETION_20260925.md).

2026-09-24 연결관계 `reference-scope-v2` 로직을 MAIN **작업 코드**의 선택형 새 빌드 경로로 반영했다. 기존 구조화 세대의 질문→답변 E2E를 먼저 확인하도록 기본 빌드는 v4로 유지한다. 새 관계 색인은 별도 run에서 `GENOS_REFERENCE_SCOPE_V2=1`로 구축한다. 로컬 고정 계약만 확인했으며 Git `main` 병합·push, GENOS 새 세대 구축·코드서빙 배포·현장 E2E는 **아직 하지 않았다**. [변경·검증·남은 작업](07_DOCS/REFERENCE/OPERATIONS/GENOS_REFERENCE_SCOPE_V2_CODE_20260924.md).

2026-09-24 작업 코드의 fulltext 형태소 분석을 `pecab==1.0.8`로 전환했다.
기존 Kiwi 세대를 덮어쓰지 않고 PeCab v2 fulltext를 별도 NFS generation에
결속한다. 로컬 계약 테스트 상태이며 GENOS 새 세대 생성·배포·질문 성공은
미확인이다. 설치, 로컬 scratch 색인, NFS 인계와 300초 예산 설명은
[PeCab fulltext 전환](07_DOCS/REFERENCE/OPERATIONS/GENOS_PECAB_FULLTEXT_20260924.md)을 따른다.

2026-09-23 법률 에이전트의 요청별 진행 상태를 GENOS **기존 채팅 앱**으로 보내는
작업 코드를 추가했다. 커스텀 코드서빙 `/stream` SSE, 워크플로우의
`Visible Reasoner` 소켓 중계, 기본 `/json` 복귀를 제공한다.
당시 `GENOS_RAG_PROGRESS_UI=off`가 기본이었으며 `socketio` 활성화 전에 같은 현장
V1.8.6 채팅에서 조기 표시·답변 중복과 게이트웨이 SSE 전달을 확인해야 한다.
사용법은 [채팅 연결](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md)을 따른다.
로컬 계약 검증 상태이고 GENOS 리비전 배포·실제 채팅 E2E는 미확인이다.

2026-09-23 로컬 RAG의 외부 Gemma 결속은 [로컬 Gemma 실행 안내](07_DOCS/REFERENCE/OPERATIONS/LOCAL_GEMMA_SERVING.md)를 따른다.
GENOS에서는 `GENOS_GENERATION` 또는 데이터 CURRENT로 세대를 선택하고 `GENOS_BASE_URL`,
`GENOS_LLM_SERVING_ID`, `GENOS_LLM_KEY` 등 현장 파라미터로 내부 모델을 결속한다.
로컬 Gemma의 `.env` 키·공개 문서 승인 목록을 GENOS 모델 설정으로 사용하지 않는다.

2026-09-23 코드 ZIP·Git checkout·NFS generation이 서로 다른 판이 되는 일을 막기
위해 배포 전 `genos_release_gate.py`를 사용한다. 이 도구는 ZIP의 전체 파일 해시와
배포할 clean Git commit을 대조하고, 바로 그 checkout으로 generation E2E와
`verify_assets`를 실행한다. 사용법과 배포 후 별도 확인은
[세대 교체 서빙 계약](07_DOCS/REFERENCE/OPERATIONS/GENOS_RAG_GENERATION_HANDOFF.md)을 따른다.
로컬 구현·모의 테스트 상태이며 GENOS 현장 적용은 별도다.

2026-09-22 GENOS 공유 볼륨 `/nfs-root/diamo/8-agent`의 새 전체 MAIN 구축·관계 코드
해시 확인·NFS 발행·코드서빙/워크플로우 E2E와 파생 run 정리는
[새 MAIN E2E 안내](07_DOCS/REFERENCE/OPERATIONS/GENOS_FRESH_MAIN_E2E_20260922.md)를 따른다.

GENOS RAG의 데이터 세대 교체, 공유 NFS 발행, 코드서빙 모델·출력 토큰 설정,
워크플로우 E2E 검증과 원복은 [세대 교체 서빙 계약](07_DOCS/REFERENCE/OPERATIONS/GENOS_RAG_GENERATION_HANDOFF.md)을 따른다.
현재 v5의 `GENOS_RAG_MAX_OUTPUT_TOKENS`는 코드서빙 환경에서 모델 호출 1회당
`max_tokens`를 선택하며, 비우면 6400이다. 구조화의 80000토큰 설정과 별개다.

2026-09-22 워크플로우 작업 코드는 `LEGAL_AGENT`로 호출하고 `team_id`로 팀별 내규·외규를
선택한다. 이전 `ELS_QUERY`는 호환 별칭이다. 입력 메타데이터의 `user_id` 계약 충돌도 수정했다.
워크플로우 환경변수 `TEAM_ID`가 있으면 입력 `team_id`보다 우선 전달한다.
[호출·팀 범위·배포·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_LEGAL_AGENT_TEAMS.md)를 따른다.
작업 코드 변경이며 로컬 frozen 릴리스·GENOS 배포는 별도다.

2026-09-22 모델 ID 자동 조회: GENOS 코드서빙의 v5는 환경변수로 모델을 메모리에서
결속할 수 있다. 모델 종류와 무관하게 `GENOS_LLM_SERVING_ID`·`GENOS_LLM_KEY`를
지정하며 `GENOS_LLM_MODEL`은 생략할 수 있다. 입력 바이트 보호 상한은 v5 프로필에서
코드가 계산하므로 별도 환경변수는 필요하지 않다. 실제 모델 문맥 수용량은 현장 검증 대상이다.
모델별 변수와 `GENOS_LLM_PROFILE`은 현행 작업 코드에서 읽지 않는다. 생략한 ID는
`/models`에서 단일 모델만 조회하며 시작 시 검증한다. 로컬 활성 릴리스는 이 변경과 무관하다.
여러 모델·조회 실패에는 임의 fallback이 없다. 현장 실행은 미확인이다.

2026-09-22 단계별 구축: `pipeline.py document-release select/merge/prepare/review/index/status/verify`로
성공한 구조화만 새 범위에 고정하고 원문 통합·용어 검토·색인을 각각 실행할 수 있다.
원래 실패/입력 제외 기록과 RAW는 보존하고, 부분 범위와 제외 사유를 최종 release까지 결속한다.
기존 `build-all`의 전체 완료 검사는 유지한다. [명령·재개·반입·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_RELEASE_STAGES.md).
로컬 모의 계약 검증이며 GENOS 설치·실제 2,105건 후속 실행은 미확인이다.
새 용어집에 남은 과거 문서 연결과 현재 문서가 충돌하면 새 run의
`--glossary-corpus-policy replace`로 현재 구조화를 재사용해 연결을 재생성한다.
원본 용어집·완료 구조화를 보존하며 [재연결 패치·실행](07_DOCS/REFERENCE/OPERATIONS/GENOS_GLOSSARY_CORPUS_REPLACE.md)을 따른다.
의미 비교를 보류하면 준비된 run에서 `document-release index --skip-meaning-review
--skip-review-reason 사유`로 모델 호출 없이 색인을 만든다. 별도 `serving-unreviewed` 결과에
SKIPPED와 부분 범위를 명시하고, 기존 검토·완료 기록과 일반 경로의 검증은 유지한다.

2026-09-22 현행 MAIN 작업 기본과 로컬 활성 릴리스는 `legal-agent-tools-v5` /
`legal-agent-v5-20260922-r3`(generation 20)다. 내부 모델은 기본 미결속이며
GENOS 배포는 별도다. 코드 ZIP 반입, 기존 용어집·전체 관계 묶음 배치, 통합 구축,
내부 Gemma 결속과 서빙 실행은 [v5 용어집 실행 안내](07_DOCS/REFERENCE/OPERATIONS/GENOS_V5_GLOSSARY_START_20260922.md)를 따른다.
아래 날짜별 v2/v3·80,000토큰 설명은 당시 기록이며 현재 v5 RAG 출력 상한은 6,400토큰이다.

2026-09-21 작업 코드의 GENOS 생성 요청 출력 예산은 80,000토큰으로 맞췄다.
구조 recipe는 `STRUCTURE_RECIPE_MAX_TOKENS`와
`STRUCTURE_RECIPE_REVIEW_MAX_TOKENS`를 모두 80000으로 설정해야 한다.
예시값은 `.env.genos.example`에 있다. 법률 에이전트 프로필과 레거시
GENOS 호출 기본값도 80000이다. 이는 요청의 `max_tokens` 값이며 모델의
실제 출력 가능 길이나 입력 문맥 길이를 보장하지 않는다. 망분리 GENOS의
모델 수용 여부·실제 출력량·선택된 서빙 리비전은 현장 확인 전까지 미확인이다.

2026-09-21 전체 코드 재반입: 루트 `genosIgnore`를 읽는
`python 06_TOOLS/COMMANDS/code_ship.py pack --ignore-file genosIgnore`로 ZIP을 만든다.
Git 제외 규칙은 로컬·GENOS 공통 `.gitignore`, 설치 의존성 정본은 사용자 지정
153개 버전을 고정한 `requirements.txt`다. 기존 `requirements-serving.txt`,
`requirements-pipeline.txt`, `requirements-genos.txt`는 정본을 참조한다.
[전체 ZIP 범위·사용법](07_DOCS/REFERENCE/OPERATIONS/GENOS_FULL_CODE_ZIP.md).

2026-09-21 추가 작업: `legal-agent-tools-v3` / `legal-agent-rag-v3`를 명시 선택 경로로 구현했다. 인용·준용·위임·정의·용어·구조·원천 지식의 관계 안내, 질문별 판단 이력과 실제 제시 확인, 제한된 준용 선읽기와 관계 의존 주장 검토를 기존 요청 세션에 연결한다. 작업 기본 v2·로컬 활성 포인터는 유지하며 실제 모델 품질·GENOS 배포는 미확인이다. [v3 설정·검증·복구](07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V3.md).

2026-09-21 작업 MAIN 기본 RAG는 `legal-agent-tools-v2`다. 기존 서비스/API/파이프라인에 도구 선택·원문 전달·평가·검토/반론·outbox를 연결했다. 현장에서는 `GENOS_RAG_IMPLEMENTATION=legal-agent-tools-v2`와 해시 고정 LEGAL_AGENT_PROFILE을 명시할 수 있다. 기본 프로필의 모델은 미결속이고 내부 모델 설정 전 의미 답변을 실행하지 않는다. [v2 설정·검증·복구 안내](07_DOCS/REFERENCE/OPERATIONS/TOOL_EXPLORATION_V2.md). 실제 GENOS 호출·배포는 미실행이며 로컬 ACTIVE_RELEASE도 이번 변경으로 전환하지 않았다. 아래 2026-09-17 기본값 설명은 당시 코드 기록이다.

2026-09-17 문서 탐색 도구는 `GENOS_RAG_IMPLEMENTATION=document-navigation-v1`로 명시 선택한다.
전체 목록·폴더/제목·목차·전체 원문 페이지 조회와 복수 원문 읽기/종합을 기존 RAG에 연결했다.
연구 실행기를 제품에서 호출하지 않으며, 호환되는 기존 원문/색인/용어 묶음을 재사용한다.
로컬 모의 HTTP/계약 검증이며 GENOS 현장 반입·내부 모델 호출·배포는 미확인이다.
같은 날 로컬 MAIN 기본 모드도 이것으로 전환했다. 새 코드에서는 `PIPELINE.json` 기본값이므로 환경변수를 빼도 이 모드다.
[설치·설정·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_TOOLS.md).

2026-09-17 팀별 RAW 파일 수정/이동 후 `prepare-data --refresh-team-layout --apply`로
등록 해시와 동일 내용 이동 경로를 자동 갱신한다. 이전/이후 등록과 변경 영수증은 별도
이력으로 보존한다. 파생본 계보 검증·완료 구조화·CURRENT는 우회/변경하지 않는다.
로컬 모의 검증이며 현장 적용은 미확인. [실행·제약](07_DOCS/REFERENCE/OPERATIONS/GENOS_TEAM_RAW.md).

2026-09-17 팀별 RAW 작업 코드: `prepare-data --team-layout --apply` 이후
`RAW/internal|external/<team>/...`을 선택한다. `build-data-stages`에 ZIP 해제 → XML Markdown →
없는 PDF 생성 → 형식별 구조화를 연결했다. PDF 생성은 `--pdf-conversion on|off`로 제어하고
파싱용 전처리기와 별도 설정을 쓴다. [설정·실행·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_TEAM_RAW.md).
현장 PDF 생성 실행은 미확인이다. 아래의 과거 ZIP 별도 도구는 호환용으로 유지한다.

2026-09-17 원본 우선 작업 코드: 동일 폴더의 HWPX/DOCX를 구조 입력, PDF를 참고 파일로
연결한다. DOC+PDF는 PDF가 주 입력이다. ZIP 병합·해시 중복 점검은 별도 스크립트이며,
파일명/폴더/중복 별칭을 구조화와 RAG 문서 탐색에 보존한다. `--only-internal`로 외규 scope와
독립적으로 내규를 선택한다. [원본 우선 반입·실행 가이드](07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_PRIMARY.md).
로컬 모의 연결 검증과 GENOS 현장 적용은 구분하며, 현장 설치·전수 중복/품질은 미확인이다.

구조화 현행 작업 코드는 v36: basic으로 전체 원문을 먼저 구조화하고, 기본 한 페이지씩
원본/bbox 이미지와 번호 체계로 VLM 검토한다. 지적된 본문을 LLM이 확인하고 코드가 재구조화한다.
기본 `STRUCTURE_RECIPE_ACCEPT_WARNINGS=on`에서는 VLM 보류·출력 잘림·형식 오류·검수 예산
소진을 `accepted_with_warnings`로 기록해 저장·후속 처리를 계속한다. 미승인을 승인으로 표시하지 않는다.
소속 없는 제목/머리말은 조문을 만들어내지 않고 `unstructured_text` 구역으로 보존한다.
원문 누락·깨진 좌표·부모 순환·해시 불일치는 계속 차단한다. 모델 요청 출력은 현행 작업 코드에서 기본 80,000토큰,
문서 규칙 수정은 기본 2회이며, 이미지 창은 겹치지 않는다. `off`는 이전 엄격 검수 모드다.
작업 코드/로컬 연결 검증과 GENOS 현장 실행은 구분한다. v34 현장 실패는 사용자 사진으로 확인했다.
2026-09-17 사용자 사진 `9354F755-258B-4665-A9F7-AECFE34CB15C`에서 v36a의 PATCH OK,
VERIFY OK와 내규 PDF 1건 구조화 완료·실패 0을 확인했다. 실제 구조 정확도·전수 품질은 미확인이다.
현장 확인 설치기는 v36a다. v35는 미발송이며, v34에서 바로 설치하도록 이전 배포 v3/v4의
`genos_stages.py` 해시 누락을 보완했다. v36 실행 파일 20개는 그대로다. 보관된 v4 코드와
v34 ZIP으로 기존 설치 오류를 재현하고 v36a 설치·검증·재적용·원복을 확인했다.
v37 작업 코드는 로그의 `doc-status.html`에서 최종 저장 구조의 원본/bbox 이미지 HTML을 연다.
종료 시 또는 `06_TOOLS/COMMANDS/genos_data_status.py --run-id <ID> --export`로 생성하며,
기존 성공 건도 모델 재호출 없이 보고서를 만들 수 있다. 이미지 생성 오류는 구조화 상태와 분리한다.
v37 현장 적용은 미확인이다. 샘플 5개로 틀 확정 후 LLM/VLM 없이 전체 실행하는 경로는 아직 미구현이다.
v36 구조화 모델 요청은 `chat_template_kwargs.enable_thinking=false`를 명시하며 형식 재시도에서도 유지한다.
`raw_response`는 JSON 추출 전 답변 내용이고 `call-*-provider-response.json`은 서버 수신 이벤트 원문이다.
부칙 공백·대괄호·날짜 표기를 인식하고 본문 속 인용은 제외한다. 다른 문장/표제와 한 블록으로 합쳐진
부칙은 후보를 탐지하되 블록 분할 미확인 경고로 보존한다. GENOS 서버의 옵션 수용은 현장 확인이 필요하다.
[현행 구조화 실행 계약](07_DOCS/REFERENCE/OPERATIONS/GENOS_RECIPE_VLM.md)을 먼저 대조한다.

확인일: 2026-09-11. 연결 저장소 `infocz`의 main 커밋 `7b42bc4cbf9b7ccef6dfea522d20370cedb237ce`와 현재 8-AGENT 작업 코드를 대조했다.
이 문서는 GENOS 관련 답변의 공통 기준과 자료 안내다. 현장 배포 상태나 최신 설정값을 대신하지 않는다.
출처 전체와 갱신 방법은 [GENOS_SOURCES.md](07_DOCS/REFERENCE/GENOS_SOURCES.md)를 본다.

## 1. 답변 전에 확인할 것

- GENOS 질문이면 이 파일을 먼저 읽고, 아래 표에서 해당 주제의 자료만 추가로 읽는다.
- **사용자에게 확인된 제약**: 최종 서빙은 망분리 GENOS다. **현재 Codex 세션에서는 GENOS 세션·코드스페이스·서빙 API·내부 LLM/임베딩에 접근할 수 없다.** 공개 법령은 외부 처리 가능하고 실제 내부 데이터의 처리·실험은 GENOS에서 내부 모델로 한다.
- 이 접근 불가 상태는 알려진 환경 제약이다. 문서에 주소·설정이 있더라도 현재 Codex에서 GENOS 연결 테스트·로그 조회·배포를 시도하지 않는다. 여기서는 코드·반입 자료를 대조하고 현장 실행 절차를 준비한다. 현장 확인은 사용자가 제공한 환경·버전·리비전·실행 기록에 근거한다.
- `127.0.0.1`/WSL의 **로컬 개발 서버**와 **GENOS 현장 서버**를 구분한다. 로컬 health 성공·시간 초과로 GENOS 상태를 추정하지 않는다. 환경을 밝히지 않은 “상주 서버” 표현을 사용하지 않는다.
- 모의 내부 데이터로 확인한 것은 입력 계약·연결 검증이다. 실제 내부 데이터의 품질·성능은 현장 검증 전까지 미확인이다.
- 플랫폼 사용법은 **같은 버전·같은 실행 환경의 확인 기록**, 우리 구현은 **선택된 코드/배포 리비전과 설정**을 근거로 답한다. 두 근거가 다르면 충돌을 설명한다.
- `상위 저장소의 현장 관찰`, `데모 실측`, `문서상 추정`, `우리 작업 코드`, `우리 현장 검증`을 구분한다. 다른 과제의 성공을 8-AGENT 배포 성공으로 바꾸지 않는다.
- 기존 문서의 “최신”, 파일명 날짜, 로컬 테스트 성공만으로 현장 적용을 단정하지 않는다. 과거 ZIP/패치 명령은 설치된 버전과 맞는 경우에만 안내한다.
- 이미 알려진 정보는 재질문하지 않는다. 버전/리비전/실제 호출 경로처럼 답을 바꾸는 정보가 없으면 저장소와 로그를 먼저 확인하고 필요한 항목만 묻는다. 키 값·비공개 원문은 요구하거나 답변에 복사하지 않는다.
- 답변은 결론 → 해당 환경에서의 절차 → 근거 문서/코드 → 남은 미확인 사항 순서로 짧게 쓴다.

## 2. 질문별로 읽을 자료

| 질문 | 먼저 볼 자료 | 확인할 코드/보조 자료 |
|---|---|---|
| GENOS 개념·용어·화면 | [상위 저장소 안내](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/README.md), [용어 사전](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/glossary.md) | [화면 가이드](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/genos-guide.md)는 데모 기준 |
| 버전 차이·현장 제약 | [현장 지식](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md), [버전 차이](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/version-gap.md) | [검증 범위](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/coverage-map.md); 기록된 환경/과제 확인 |
| 코드서빙·워크플로우 역할 | [역할 설명](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/codeserving-vs-workflow-design.md) | [service.py](service.py), [채팅 브릿지](08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py) |
| 코드 배포·Git·키·리비전 | [프로젝트 배포 자료](07_DOCS/REFERENCE/OPERATIONS/GENOS_CODE_SERVING_CURRENT.md) | [현장 지식](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md), [기본 의존성](requirements-serving.txt) |
| 구버전·누적 패치 → 전체 실행 코드 교체 | [전체 코드 교체](07_DOCS/REFERENCE/OPERATIONS/GENOS_CODE_REPLACEMENT.md) | 코드 트리 백업·교체·복구. 원문/환경/가상환경/Git 보존; 현장 설치·파싱 미확인 |
| 채팅 실패·return/yield·대화 이력 | [채팅 연결](07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md) | 브릿지의 `run`, `_run_once`, `call_code_serving`; 현장 지식의 버전별 응답 규약 |
| 골든 등록·정답 조문 매핑·최초 회수/최종 답변 평가 | [골든 평가](07_DOCS/REFERENCE/OPERATIONS/GENOS_GOLDEN_EVALUATION.md) | `pipeline.py golden`; GENOS 코드스페이스 배치·오프라인 채점, 현장 실행 미확인 |
| 원문 추가·RAW·단계별 구축 | [데이터 위치](01_DATA/README.md), [4단계 구축](07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md) | [pipeline.py](06_TOOLS/pipeline.py), `lawrag.pipeline.raw_prepare`, `genos_stages` |
| ZIP → PDF·전처리기 직접 호출·NFS 경로 | [변환/NFS 현장 기록](07_DOCS/REFERENCE/OPERATIONS/GENOS_ZIP_TO_PDF_NFS.md) | 전처리기 187·NFS 경로, DRM 해제 후 DOC 1건 PDF 확보/후속 NLTK punkt_tab 누락; 전체 변환·품질은 미확인 |
| PDF 변환 장애·유지보수팀 이관 | [유지보수 요청서](07_DOCS/REFERENCE/OPERATIONS/GENOS_PDF_MAINTENANCE_REQUEST.md) | 사용자 전처리기 수정·LibreOffice 설치 불가. DOC NLTK 오류와 DOCX API 성공/PDF 미확보 분리, 기존 로그 수집 |
| 추가 문서·용어·통합 서빙·활성화 | [추가 문서 연결](07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md) | `pipeline.py build-all` → `document-release` |
| 용어집과 내규·외규 통합 구축 | [통합 실행](07_DOCS/REFERENCE/OPERATIONS/GENOS_GLOSSARY_SINGLE_COMMAND.md) | [genos_all_pipeline.py](02_BACKEND/lawrag/pipeline/genos_all_pipeline.py) |
| Wikidata·FIBO·전체 용어 관계 반입 | [기본 관계 묶음](07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_KNOWLEDGE_BUNDLE.md) | `pipeline.py glossary knowledge`, `glossary_linking.project`, `GLOSSARY_PIPELINE.json.knowledge_bundle` |
| 모델 연결·JSON·임베딩 | [현장 지식](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md) | [공통 전송](02_BACKEND/semantic_runtime/genos.py), [RAG provider](02_BACKEND/semantic_runtime/provider.py), [구축 provider](02_BACKEND/semantic_runtime/genos_backend.py) |
| 문서 형식·구조화·진행률·재개 | [세부 자료 목록](07_DOCS/REFERENCE/GENOS_SOURCES.md) | 형식·선택 실행기별 자료를 읽고 옵션/출력 경로를 대조 |
| PDF Docling 파싱·전처리기 ID/URL·모델 반입 대체 | [전처리기 파싱·적재](07_DOCS/REFERENCE/OPERATIONS/GENOS_PREPROCESSOR_PARSING.md) | `GENOS_PREPROCESSOR_ID`/`URL` 환경 설정 → 파싱용 전처리기 `data.document` → 기존 원문·용어 적재. 현장 미검증 |
| 플랫폼 지식 준비·벡터DB·Flowise | [플랫폼 RAG 런북](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/rag-runbook/RUNBOOK.md) | 현장 지식의 전처리/벡터DB 보정; 우리 SQLite 파이프라인과 별도 경로 |
| MCP·도구 호출 | [MCP 런북](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/mcp-runbook.md) | 데모 v1.9.2의 검증이며, 현재 프로젝트가 MCP를 사용한다는 뜻은 아님 |

## 3. 환경과 버전 — 서로 섞지 않는다

상위 저장소의 기록 기준이다. 현재 대상의 버전·컨테이너·리비전이 다르면 재확인한다.

| 항목 | 기록된 사실 | 우리 작업에서의 해석 |
|---|---|---|
| 플랫폼 | 데모 v1.9.1~1.9.2 / 현장 V1.8.6 | 데모 사용법을 현장에 무조건 적용하지 않는다 |
| Python | 현장 코드스페이스 3.11.15 / 워크플로우 컨테이너 3.10 기록 | 실행 위치별 호환성을 확인. 우리 코드서빙 기본 의존성 기준은 3.11.15이며 현장 이미지 확인도 필요 |
| Python 워크플로우 | 데모 v1.9.1은 JSON token/end `yield`; 현장 V1.8.6은 `{"text": ...}` dict `return` | 현재 우리 `run(data)`는 dict 반환. 오류 `000200003`이면 반환 규약부터 확인 |
| 진행 상황 | V1.8.6에서 최종 dict 반환과 워크플로우 소켓 emit 병행 사례 존재 | 우리 브릿지에 구현되었다고 가정하지 않는다. `main_socketio`는 해당 워크플로우 런타임의 기능 |
| 코드서빙 주소 | 현장에는 게이트웨이가 앱의 `/chat`, `/json` 등 실제 라우트를 전달한 사례 | `/chat`을 모든 앱의 정답으로 바꾸지 않는다. 배포 방식·앱 라우트·전체 URL을 대조 |
| 모델 인증 | 플랫폼 노드의 인증 주입과 Python 코드의 직접 API 호출은 다름 | 코드 호출의 URL·서빙 ID·키·모델 설정은 해당 provider가 실제 읽는 변수로 지정 |
| 권한/승인 | 승인 절차 관찰; 자기 승인 가능 여부는 일부 환경 미확인 | 다른 환경의 자체승인 사례를 우리 권한으로 간주하지 않는다 |

근거: [knowledge.md](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md), [version-gap.md](07_DOCS/REFERENCE/GENOS_UPSTREAM/7b42bc4cbf9b/version-gap.md), [현재 브릿지](08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py).

## 4. 우리 시스템의 GENOS 연결

MAIN은 데이터 입력·구조화·용어집 구축/연결·지식그래프·온톨로지·RAG·피드백 루프 전체다. [전체 MAIN 정의](00_SYSTEM/ARCHITECTURE.md)를 따른다. 아래 코드서빙·채팅 배선과 데이터 CURRENT는 이 중 실행/서빙 부분이며 전체 MAIN 완료를 의미하지 않는다.

```text
외부: 공개 원문 처리·실험 → 코드/공개 데이터/실행 명세 인계
GENOS 코드스페이스: 실제 내부 데이터 + 내부 모델로 구축·실험
GENOS 코드서빙: 선택한 코드 리비전 + 데이터 세대 → RAG
채팅 앱 → 워크플로우 브릿지 → 코드서빙 LEGAL_AGENT (+ team_id) → /v1/rag/ask
```

- `service.py`는 `async def service(config, data)`와 로컬 ASGI factory `application()`을 제공한다. 현장 플랫폼이 어느 방식을 적재하는지 별도로 확인한다.
- 워크플로우는 입력·응답을 중계한다. 이미 RAG에서 생성한 답변을 별도 LLM으로 재생성하지 않는다. 현재 `session_id`는 추적에 쓰며 대화 이력은 저장하지 않는다.
- 코드스페이스의 직접 실행으로 로직과 내부 모델 연결을 확인할 수 있다. 게이트웨이 인증, 채팅 연결, 배포 자원 한도, 영속 볼륨은 배포 환경에서 별도 확인한다.
- 한 코드서빙 내부의 Python 모듈화는 가능하다. 서로 다른 배포가 코드·파일·패키지를 자동 공유한다는 보장은 없다. 상위 문서의 “런타임 공유 없음”은 당시 현장 관찰 범위다.
- ZIP 반입/압축 해제, 내부 Git 커밋·push, 플랫폼 리비전 배포, 실제 요청의 리비전 선택은 각각 별도 상태다. 배포 시 선택 커밋·환경변수·트래픽·워크플로우/채팅 앱 바인딩을 확인한다.
- 기존 저장소를 clone하고 이력을 보존하는 절차를 기본으로 한다. 상위 문서의 첫 push `--force`는 특정 초기화 사례이며 일반 배포 명령으로 복사하지 않는다.

### 데이터 세대 선택

현재 `service.py._resolve_binding()`의 순서:

1. `GENOS_GENERATION`의 명시된 세대 디렉터리.
2. `GENOS_DATA_ROOT/generations/CURRENT.json`이 선택한 세대.
3. 로컬 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`의 릴리스.

GENOS에서는 1 또는 2를 현장 경로로 명시하고, 준비되지 않았을 때 로컬 릴리스를 현장 정본으로 취급하지 않는다.
세대와 런타임 캐시 때문에 CURRENT 변경 후 새 프로세스가 필요할 수 있다. 실제 선택 결과로 확인한다.
데이터 파일은 코드스페이스와 코드서빙 양쪽에서 읽을 수 있는지 확인한다. 경로 문자열이 같다는 것만으로 공유·쓰기·재배포 후 보존을 보장하지 않는다.

### 서로 다른 구축 명령

| 진입점 | 목적/산출물 | 활성화 의미 |
|---|---|---|
| `pipeline.py prepare-data` | RAW 준비·입력 검증, `--apply`로 반입 | SourceSet/서빙 자동 변경 아님 |
| `pipeline.py build-data-stages` | 내규 `PDF/internal` + 외규 `RAW/<source>` → 구조화 → LLM/검토 → 임베딩, 문서별 DRAFT | `--stage structure`는 구조화·용어 연결까지; 통합 CURRENT를 선택하지 않음 |
| `pipeline.py build-all` | 전체 구조화 → 명시 원문 통합 → 기존/신규 용어 후보 검토 → 전체 연결·서빙 DRAFT | 검토 미완료 시 exit 3, 구조화 결과 보존. 통합 CURRENT 선택 없음 |
| `pipeline.py build-all-legacy` / `genos_pipeline.sh` | 과거 용어 ZIP + 내규·외규 + 벡터 + 통합 세대; v3 검토 미소비 | `--publish`는 GENOS CURRENT 변경. 품질 승인/로컬 MAIN 채택과 다름 |
| `service.py`의 `PIPELINE_*` | `genos_unified`의 raw/common batch 구축 | `PIPELINE_PUBLISH`는 source-only DRAFT 선택; 의미 구축 전체 완료와 다름 |

모든 명령을 하나의 동일 구현이라고 답하지 않는다. 전체 실행은 선택한 명령의 기본값과 실제 코드 경로를 확인한다.
`--check-only`도 파일/목록/계획을 만들 수 있다. “모델 호출 없음”과 “변경 없음”은 다르다.
구조화도 PDF recipe/VLM 설정에 따라 모델을 호출할 수 있다. [GENOS_RECIPE_VLM.md](07_DOCS/REFERENCE/OPERATIONS/GENOS_RECIPE_VLM.md)를 먼저 대조한다.

### 선택 데이터 전수 점검·문서별 검수

구조화 건수·문서별 마디/본문·용어/정의·명시 참조·색인·구축 감사 확인은
[읽기 전용 전수 점검 R2](08_DEPLOYMENT/GENOS/diagnostics/data_audit_20261006_r2/GUIDE_UTF8.txt)을 사용한다.
R1 현장 사진은 `Report output symlinks are forbidden`로 보고서 초기화 전에 중단했다.
R2는 output 상위 폴더의 링크를 실제 경로로 해결하고 요청/실제 경로를 로그에 남긴다.
입력과 겹치는 output·output 자체 및 내부 링크는 계속 거부하며 R1과 현장 로그를 보존한다.
독립 RUN.txt 한 파일을 `python3` 표준 라이브러리로 실행하고 실제 코드서빙의 선택 generation을 명시한다.
source v1/v2·navigation v2~v7·glossary serving v2·unit fulltext v1을 구분하며 compact 물리 orphan도 검사한다.
문서별 HTML에서 트리·본문·출현/참조 근거와 대상 마디를 열고 검수 상태/메모를 세대에 결속해 내보낸다.
실패·제외 입력은 정확한 선택 파일/완료 상태 원장, 감사 대조는 해당 세대에 결속된 audit root를 추가한다.
원문/코드/캐시/CURRENT를 변경하지 않으며 모델·네트워크를 호출하지 않는다.
자동 검사 완료는 원본 의미·법률 판단·배포 성공 인증이 아니며 GENOS 현장 전체 실행은 미확인이다.

## 5. 모델·키·데이터 경계

Gemma thinking·모델 호출 지연 확인은
[thinking 공유 로그 R3](07_DOCS/REFERENCE/OPERATIONS/GENOS_THINKING_LOG_R3_20260928.md)을 따른다.
작업 코드는 기존 `enable_thinking=false` 요청을 유지하고 호출별 요청 옵션·응답의
추론 보고 여부·숫자 토큰 수를 기록한다. 서버가 추론 정보를 주지 않으면 `unknown`이며
OFF로 확정하지 않는다. R1에서 누락된 공유 `.log`·요약 `.txt` 출력 허용 목록을
R2에서 연결했다. R2 현장 설치의 report 전체 hash 미지원은 R3에서 설치 파일·
엔진 pin 일치와 표시 구문 계약을 확인한 부분 수정으로 처리한다.
TXT는 코드서빙 진단/표시 소스와 엔진 pin에 적용한다.
로컬 계약 검증과 GENOS 리비전 배포·실제 thinking 확인은 별도다.

- GENOS RAG는 `SEMANTIC_LLM_BACKEND=genos`를 명시한다. 현재 코드 기본값이 `anthropic`이므로 자동 선택으로 두지 않는다.
- RAG와 구축 provider의 설정 해석이 다르다. `GENOS_GATEWAY_API_PREFIX`, `GENOS_LLM_API_PREFIX`, `SEMANTIC_LLM_API_PREFIX`를 서로 바꾸어 안내하지 않는다. `/v1` 추가/제거는 실제 호출하는 함수와 게이트웨이 규약을 확인한다.
- RAG provider는 `GENOS_BASE_URL`, `GENOS_LLM_SERVING_ID`, `GENOS_LLM_KEY`를 사용한다. 직접 URL은 `GENOS_LLM_URL`로 지정하며 MODEL은 자동 조회 시 생략한다. 모델별 변수·프로필 선택은 사용하지 않는다.
- 운영 RAG 설정은 [.env.genos.example](.env.genos.example), 분리 Python 워크플로우는 [workflow.env.example](08_DEPLOYMENT/GENOS/workflow/workflow.env.example)을 따른다. 구현은 GENOS_RAG_IMPLEMENTATION을 생략하면 배포 코드 PIPELINE.json의 기본 legal-agent-unified-v6을 사용한다. 멀티턴은 GENOS_MEMORY_ENABLED=1과 실제 사용자·대화 식별자로 이어지며 user_wiki 생성·조회·개인 질문 이력의 자동 모델 입력 및 별도 HMAC signing을 제거했다. GENOS_MEMORY_SIGNING_KEY를 등록할 필요가 없다. TEAM_ID는 문서 선택 범위이며 분리 방식은 워크플로우 요청으로 전달하고, 통합은 서빙 환경 또는 입력 team_id를 사용한다. AD 관리 모드의 workspace는 서빙 TEAM_ID 또는 AD_WORKSPACE로 별도 고정하며 기존 진입 검사를 유지한다. 플랫폼·코드서빙·LLM API 인증키는 기존대로 사용한다. shortcut DB와 legal_wiki 컴파일·조회·재구축 및 기존 저장 기록은 보존한다. 구축 설정은 [pipeline.env.example](08_DEPLOYMENT/GENOS/pipeline.env.example)에 있다.
- Git 인증, 코드서빙 API 인증, LLM 인증, 임베딩 인증, 벡터DB 인증을 구분한다. 과거 문서의 모델명/서빙 ID는 현장 당시 기록이며 현재 배정값을 대신하지 않는다.
- 적재와 질의의 임베딩 모델·버전·전처리는 일치해야 한다. 차원이 같아도 모델이 다르면 검색 품질이 무너질 수 있다. 설정 누락 시 다른 모델로 자동 대체하지 않는다.
- 내부 원문·질문·계약서·모델 출력·실제 키를 외부 실험 입력이나 지식 문서에 넣지 않는다. 공개 산출물은 출처/버전/해시를 보존하고, 모의 내부 데이터는 실제 데이터와 구분한다.
- 플랫폼 채팅 첨부, 플랫폼 벡터DB 업로드, 우리 RAW 파서의 지원 형식은 서로 다르다. V1.8.6의 다른 과제에는 `uploadFiles[].path`로 NFS 경로를 받은 기록이 있지만, 우리 `_upload_paths`와 허용 루트에 자동 호환된다고 가정하지 않는다.

용어집 의미 검토 v3는 `pipeline.py glossary review complete`가 준비·GENOS LLM 실행·새 초안 생성까지 이어서 호출한다. 개별 `review run`도 같은 내부 LLM 전용 경로다.
임베딩이나 외부 모델 fallback은 사용하지 않는다. `prepare`는 외부에서도 모델 없이 가능하고,
실제 실행·재개·초안 반영은 [용어집 운영 가이드](07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md)의
LLM 검토 배선을 따른다. 현재 배선은 모의 응답으로 검증했으며 현장 모델 검증은 미실행이다.

## 6. 장애 질문에 답하는 순서

2026-10-07 사진의 SELECT 실패와 사용자 요청에 따라
[오류 전체 표시 인계](08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10/GUIDE_UTF8.txt)를 준비했다.
`LAW_DECISION_REJECTED`를 일반 결정으로 출력해 검증 오류를 버리는 분기,
API/워크플로우의 오류 길이 제한, 큰 ERROR의 큐 탈락을 수정했다.
거절된 결정·재시도·조사 사유 전체·traceback을 서버 로그와 채팅까지 전달한다.
원문 시스템 로그는 `GENOS_SYSTEM_LOG_DIR` 또는 `/nfs-root/diamo/8-agent/logs/system/`,
요청 공유 로그는 설정된 `GENOS_SHARED_LOG_DIR`다. 공유 경로 미설정 시 해당 요청 파일은 생성하지 않는다.
[읽기 전용 로그 TXT](08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10/READ_ERROR_LOGS.txt)는
파일 목록 또는 request/run ID가 포함된 파일 전체를 길이 제한 없이 출력한다.
인계본은 기존 DEV의 inventory/엔진 결속 확인 후 오류 부분만 적용하고 백업·실패 상태·원복 경로를 남긴다.
워크플로우 전체 TXT에는 동일 해시의 시스템 로그 수집기를 내장했다.
로컬 MAIN45 포인터·선택 데이터는 변경하지 않았고, 실제 GENOS 반입·push·리비전·워크플로우 확인은 미실행이다.
현재 다른 작업의 코드 변경과 검증 인계본은 구분하며, 검증 대상은
[고정 SHA 기록](08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10/DELIVERY.json)으로 확인한다.
2026-10-08 사용자 위험 검토에서 발송된 오류 출력 R10의 추가 실패 조건을 확인했다.
[후속 진단](09_ARTIFACTS/AUDITS/20261008-full-error-r10-review/FINDINGS.json)의 모의 부분 쓰기 실패에서는
원본 백업이 남아 있지만 `undo` 진입 전 전체 inventory 검사가 `CHECKOUT_DRIFT`로 막혔다.
또한 모의 CM R12 상태에 오류 출력 R10을 정상 적용한 뒤 CM R12의 재검증이
`installed code differs from sealed recipe`로 중단했다. 두 검사는 GENOS/모델 호출 없이 수행했다.
기존 87개 PASS는 정상 적용/원복과 오류 전파 검증 기록이며 이 두 조건을 포함하지 않는다.
발송 ZIP/TXT는 변경하지 않았다. 부분 실패 복구와 CM 패치 공존을 고치기 전에는 오류 출력 R10의 apply를 보류한다.
이 검토는 실제 현장 손상이나 이미 적용된 상태를 뜻하지 않는다.
후속 사진에서는 기존 오류 출력 R10의 apply/verify EXIT=0과 CM R14 사전 검사 실패를 확인했다.
공존 문제는 위 R15 인계에서 검증한 VERIFIED 백업 계보로 처리한다. R10 자체의 부분 적용 후
undo 진입 차단 결함을 수정한 것은 아니다. R10 추가 apply 보류와 이미 VERIFIED된 코드 보존은 구분한다.
사용자 요청으로 오류 출력 R10 ZIP·독립 실행 TXT·안내 TXT를 삼성파트너 메일로 발송했다.
SENT `1a116de146a7f4d6`에서 수신자와 첨부 3개의 이름·정확한 크기를 확인했다.
[발송 기록](08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10/EMAIL_SENT.json)을 보존한다.
메일 발송과 현장 수신·실행·새 리비전 배포 성공은 별도다.

배포 준비·코드 적용·빌드·환경 오류·서버 일반 로그는
[전체 로그 저장 계약](07_DOCS/REFERENCE/OPERATIONS/GENOS_SYSTEM_LOGGING_20261007.md)과
[NFS 로그 반입 R1](08_DEPLOYMENT/GENOS/handoffs/system_logging_20261007_r1/README.md)을 따른다.
기존 query-latency R3/MAIN45 코드를 보존한 304파일 인계본이며, 첫 배포 명령의
stdout/stderr·종료 코드와 전체 traceback을 `/nfs-root/diamo/8-agent/logs/system/<run_id>/`에 기록한다.
NFS 실패분은 로컬 pending으로 보존·재전송하고, 원문은 길이 제한하지 않는다.
플랫폼 프로세스 실행 이전 로그는 별도 내보내기가 필요하다. 작업 코드·로컬 합성 검증 상태이며
GENOS 실제 NFS·리비전·워크플로우 화면 확인과 로컬 MAIN 전환은 별도다.

2026-10-07 로그 반입 R1의 ZIP·실행 TXT·워크플로우 전체 TXT·안내 TXT·SHA256SUMS를
삼성파트너 메일 `hyungjininfocz.son@partner.samsung.com`로 발송했다.
보낸메일함에서 수신 주소와 첨부 5개의 파일명·크기를 확인했으며 메시지 ID는
`1a1151adea1a521d`다. 동결 파일의 발송 전 상태는 보존하고,
후속 [발송 영수증](08_DEPLOYMENT/GENOS/handoffs/system_logging_20261007_r1/EMAIL_SENT.json)에
실제 발송 결과를 기록했다. 메일 발송은 현장 적용·push·리비전 배포 완료를 뜻하지 않는다.

2026-09-29 수신 LLM 출력 원문 확인을 위해 기존 R2/R3 수정을 포함한 단독 R4를 준비한다.
요청 `.log`의 `MODEL RAW RESPONSE`와 같은 위치 `.llm_raw.jsonl`에 최초·수정 호출의
원문 문자열, 호출 계보, 거절/필터 신호와 수신 본문을 기록한다. 인증정보 마스킹을 유지한다.
이는 LLM 서빙에서 받은 값이며 GENOS 가드레일 적용 전 출력을 복원하지 않는다.
[원문 계약·R4 반입·현장 확인·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_LLM_RAW_LOG_20260929.md).
메일의 R4 하나로 적용하며 새 코드서빙 리비전 배포 후 워크플로우 테스트 화면에서 확인한다.

2026-09-29 현장 사진의 `DRAFT/CLARIFY`와 도구 행동 동시 제출 오류를
작업 v5의 응답 검증 단계로 옮겨 같은 view·이전 출력·오류를 모델에 반환한다.
기존 R2 기능을 포함한 단독 R3는 R2 적용 코드·사진 기준 코드·통합판을 지원한다.
출력 가드레일 차단 여부는 이 오류 문구만으로 확정하지 않으며 재수정 한도를 유지한다.
[원인·가드레일 구분·R3 반입·검증·복구](07_DOCS/REFERENCE/OPERATIONS/GENOS_TURN_INTENT_REPAIR_20260929.md).
작업 코드·인계 검증이며 로컬 frozen MAIN·GENOS 현장 배포는 별도다.

2026-09-28 현장 채팅·터미널 사진에서 E 근거 재읽기의 잘못된 extent/cursor가
`ProposalError → SOURCE_TOOL_ERROR → HTTP 500`으로 중단되는 경로를 확인했다.
작업 코드에 실행 전 E 재읽기 검증을 추가하고, 사용자 지시로 handler에서 뒤늦게
판명한 모델 호출 오류도 기존 수정 제안·재진입으로 돌려준다. 오류 이유와 수정 방법을
주며 원래 질문에 다시 응답하도록 요청하고 채택 출처·원문·범위·해시 검증은 보존한다.
실제 저장소/SQL/계약 장애와 수정 예산은 유지한다. 인계는 PROPOSAL_RETRY를 사용한다.
데이터 재구축·워크플로우 교체 없이 새 코드서빙 리비전이 필요하며 현장 적용·실제
질문 성공은 미확인이다. [모델 재요청·검증·인계·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_MODEL_PROPOSAL_RETRY_20260928.md),
[최초 사진 원인](07_DOCS/REFERENCE/OPERATIONS/GENOS_EVIDENCE_READ_REPAIR_20260928.md).

2026-09-28 동시 요청 제한 해제 작업 코드: GENOS v5는
동시 요청 수로 거절하지 않도록 코드에서 제한을 해제한다. 환경변수 추가·변경은 필요 없다.
기존 `GENOS_RAG_MAX_CONCURRENT_REQUESTS`는 더 이상 읽지 않으므로 값이 남아 있어도 무시한다.
환경 모델 결속·명시 프로필·source-only 모두 부팅 시 동일 정책을 적용하며,
고정 프로필 파일을 덮어쓰지 않고 실행 프로필에 기록한다.
`runtime.request_admission`의 `unlimited=true`로 설정 반영을 확인한다.
코드서빙 새 리비전 배포가 필요하며 데이터 재구축·워크플로우 변경은 필요 없다.
원복은 패치 적용 전 코드·엔진 해시와 이전 코드서빙 리비전으로 복귀한다.
로컬 모의 계약·회귀 104개 및 설치기 24개 통과. 6개 요청의 동시 세션·HTTP 200,
팀 범위·run ID 격리, 오류 이후 재요청과 구 환경변수 무시를 확인했다.
R1/R2 실제 코드 바이트의 격리 Git checkout에서 최종 ZIP/TXT 적용·재실행·원복·코드 gate를 확인했다.
[인계 ZIP](08_DEPLOYMENT/GENOS/patches/GENOS_REQUEST_UNLIMITED_20260928_R1.zip)과
[실행 TXT](08_DEPLOYMENT/GENOS/patches/GENOS_REQUEST_UNLIMITED_20260928_R1_APPLY.txt)를 사용한다.
변경 코드의 엔진 manifest와 PIPELINE 해시도 갱신·일치 확인했다.
세션·팀 범위 격리와 요청 시간 제한은 유지한다. 출처 발행 큐의
`publication capacity reached`는 별도이며, 요청 정체·화면 전달 문제의 원인 해결을 의미하지 않는다.
GENOS 현장 배포·실제 적용은 미확인이다.

| 증상 | 먼저 확인할 것 |
|---|---|
| 채팅 실패, 이용 로그 Success | 버전별 return/yield 규약, 반환 `text`, 브라우저 응답 코드, 브릿지가 반환한 실패 상태 |
| 401/403 | 어떤 요청의 인증인지, 해당 리소스 키와 호출자 허용 범위; 키를 출력하지 않음 |
| 404/405 | 코드서빙 ID, 전체 API 경로, HTTP 메서드, 리비전 환경변수. `/chat`이나 `/json`을 추측해 고정하지 않음 |
| 새 코드가 적용되지 않음 | Git 커밋 → 배포 리비전 → 트래픽 → 워크플로우/채팅 앱 바인딩 |
| health/검색 초기화 실패 | 실제 선택 세대, manifest/코드 해시, 영속 볼륨 접근, 필수 설정 |
| 검색 0건/엉뚱한 결과 | 활성 데이터·필터·적재/질의 임베딩 일치·선택 인덱스. 플랫폼 VDB라면 암호화/속성 규약도 확인 |
| 구조화/LLM/임베딩 정체 | 선택 실행기의 단계별 로그·run ID·재시도·한도·문서별 상태. 과거 실행기와 재개 옵션 혼용 금지 |
| 코드스페이스 성공, 서빙 실패 | 컨테이너 Python/의존성/메모리/파일시스템/환경변수 차이 |
| 첨부 실패 | 테마/권한 → 허용 확장자 → 수신 payload → 파일 접근 → 우리 파서 순서 |

단일 Success 표시나 `/health`만으로 실제 모델 호출·정답률·전수 구축 성공을 보고하지 않는다. 요청 ID로 워크플로우/코드서빙/모델 로그를 연결한다.
진단용으로 내부 원문·키를 통째로 echo하지 말고 필요한 키 이름·자료형·크기·오류 분류만 확인한다.

## 7. 지식 갱신

현장 확인이 생기면 `환경/플랫폼 버전/실행 위치/배포 커밋·리비전/관찰일/확인 내용/근거/미확인 범위`를 함께 기록한다.
새 정보가 기존 규칙을 대체하면 관련 항목과 질문별 안내를 함께 수정한다. “최신 패치” 절을 계속 맨 위에 쌓지 않는다.
상위 main 갱신은 출처 인덱스의 절차를 따른다. 보관본은 과거 증거로 유지하고 현재 읽을 버전은 이 파일에서 하나를 선택한다.

## 2026-09-16 구축 단위 재구성

현행 작업 코드는 `RAW/internal`과 지원 외규 RAW를 형식별로 구조화한다. `structure`는 용어집에 의존하지 않는다. `build-all`은 전체 문서 구조화 후 기존·신규 용어 후보를 함께 검토하고 연결·색인을 수행한다. 전처리기 REVISION은 선택사항이며 미설정 캐시는 run ID 범위다. 전처리기 연결은 사용자 확인 기준이다. 새 코드의 GENOS 배포·전체 처리와 파일 이행은 별도 미확인이다. 위 표의 이전 PDF/internal·직렬 실행 설명 대신 [현행 실행 안내](07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md)를 따른다.

## 2026-09-16 전처리기 실제 응답과 구조화 틀 보완

사용자 사진의 한 PDF 호출은 HTTP/API 성공 후 `data`에 청크 11개를 반환했다. 기존
Docling 전용 클라이언트가 이를 거부한 것이 확인된 장애다. 공유 폴더 오류는 그 이전 단계다.
현행 작업 코드는 전체 청크 결합과 Docling 구조 응답을 모두 수용하며, 전체 파싱 텍스트로
틀 생성 → PDF VLM 보정 → 최종 틀로 재구조화한다. 청크 입력은 전 페이지 검수 필수이고
없는 좌표/표 구조는 미확인으로 남긴다. `--only-internal-pdf --limit 1`로 내규 한 건만 실행한다.
[수신 계약](07_DOCS/REFERENCE/OPERATIONS/GENOS_PREPROCESSOR_PARSING.md)과
[새 서버 코드](08_DEPLOYMENT/GENOS/preprocessor/README.md)를 따른다. 새 서버는 공개
고정 리비전 기반이며 현장 187 설치 원본과의 동일성·새 코드 배포·실제 품질은 미확인이다.

## 현행 추가 문서의 전체 연결

`build-all`은 전체 구조화 후 `document-release build`로 명시 기존 세대와 통합하고, 기존 미검토 후보와 새 문서 정의를 함께 검토하여 전체 연결·서빙 묶음을 만든다. `--base-generation`을 생략하면 기존 세대를 자동 유지하지 않는다. 전체 표기 연결 v3·명시 문서 간 참조·검토/재개·별도 CURRENT 활성화/롤백은 [현행 계약](07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md)을 따른다. 앞의 과거 의미/임베딩/legacy 표는 현행 실행 명세가 아니다. GENOS 현장 실행은 미확인이다.

### 최소 구조 단위 fulltext 작업 경로 (2026-10-02)

완료된 구조화/navigation에서 `06_TOOLS/pipeline.py fulltext --generation PATH --output NEW_PATH`로 항·호·목 소유 본문만 새 색인에 결속한다. 원본과 연결/navigation을 재구축하지 않는다. 로컬 작업 코드에 연결했으며 GENOS/활성 릴리스는 별도 반입·선택이 필요하다. 입력·스키마·소비자·로그·재개 계약은 [최소 단위 fulltext 안내](07_DOCS/REFERENCE/OPERATIONS/MINIMUM_UNIT_FULLTEXT_20261002.md)를 따른다.

### 2026-10-03 완료 자료 재사용 경로의 compact 구현

[구현·측정 보고](07_DOCS/REFERENCE/REPORTS/GENOS_COMPACT_LIFECYCLE_IMPLEMENTATION_20261003.md)와
[GENOS 인계 안내](08_DEPLOYMENT/GENOS/handoffs/compact_lifecycle_20261003_r2/GENOS_COMPACT_LIFECYCLE_GUIDE_UTF8.txt)를 추가했다.
`--serving --storage-profile compact-v1`은 원문 v2, navigation v6, glossary-serving-v2와
단계 재개를 연결한다. 코드와 새 generation/cache를 함께 검증·선택해야 한다.
작업 코드/로컬 계약 검증 상태이며 현장 배포·워크플로우 E2E·GENOS 속도 인증은 아직 아니다.

이 경로의 후속 반입 대상은 [참조 구축 R1](08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_GUIDE_UTF8.txt)이다.
명시적 `--storage-profile compact-v2`는 인용별 전체 제목 검사를 문자 색인으로 교체하고,
본문 지연 읽기·참조 본문 공유·처음부터 감사 DB 분리·문서/참조 단위 중단 복구를 추가한다.
새 navigation v7/storage-v3에서 기존 논리 참조와 감사 근거를 보존한다. v1/v2 감사 snapshot은 그대로 유지한다.
완료 자료 재사용부터 단위 색인·서빙 검증·공유 발행까지 기존 실행기에 연결했으며,
[구현/검사 결과와 미확인 범위](07_DOCS/REFERENCE/REPORTS/GENOS_REFERENCE_BUILD_IMPLEMENTATION_20261003.md)를 따른다.
사용자 요청에 따라 성능 측정 없이 구현했다. 현장 9시간16분의 단축 폭, 내부 모델 E2E,
NFS 복구 및 실제 배포는 미확인이다. ACTIVE/CURRENT를 전환하지 않았다.

2026-10-06 제공된 코드서빙 사진은 `_explicit_generation`의
`GENOS_GENERATION has an unsupported manifest`와 HTTP 503을 보여 준다.
작업 코드의 명시 세대 선택은 v1만 허용했으나 compact 구축·Store·오프라인 E2E는
`term-source-generation-v2`를 지원하는 불일치가 있었다. 명시 선택도 v1/v2를
허용하도록 수정했다. 모의 compact 원문으로 동일 오류를 재현했으며, 실제 선택
경로/manifest 버전/배포 코드 해시는 사진에서 확인되지 않아 현장 원인 확정은 아니다.
manifest 버전 수동 변경이나 재구축 없이 선택 경로·버전과 서빙 코드 결속을 먼저
확인한다. 작업 코드 수정과 현장 리비전 배포·워크플로우 성공은 별도 상태다.
이번 변경의 세대 선택/모의 원문 읽기/변조 거부와 기존 서비스 회귀 검사 31개가
통과했다. 전체 compact 구축 경로는 별도의 `Glossary(allow_cache_build=...)`
인자 불일치로 완료 검증하지 못했으며 이번 선택기 수정으로 해결됐다고 보지 않는다.


### compact generation 서비스 로더 오류 (2026-10-06)

현장 사진의 `GENOS_GENERATION has an unsupported manifest`와 HTTP 503은 서비스 입구가
새 source v2를 거부한 상태다. reference R1의 하위 원문·단위 색인 reader와 오프라인 E2E는
이미 지원하지만 서비스의 source/PeCab 허용 목록 연결이 누락됐다.
[수정·반입·검증·원복](07_DOCS/REFERENCE/OPERATIONS/GENOS_COMPACT_SERVICE_LOADER_20261006.md)의
작은 패치로 두 진입 검사를 연결한다. 기존 데이터 재구축·NFS 재발행·CURRENT 변경 없이
새 검증 commit의 코드서빙 리비전 배포가 필요하다. 현장 반입본 재현에서 38개 모의 계약·회귀와
실제 TXT·세대 gate가 통과했으며 GENOS 실제 적용·내부 모델·워크플로우 성공은 미확인이다.

## 2026-10-06 SQL AD 운영 모드

[구현 설계와 운영 계약](07_DOCS/REFERENCE/REPORTS/SQL_AD_MODE_SHORTCUT_WIKI_20261006/README.md). 정확한 `[AD모드 시작]`/`[AD모드 종료]` 경계와 SQL 관리 상태를 기존 서비스에 연결했다. 이 AD 인계본 준비 당시 로컬 서빙 MAIN은 `sql-ad-mode-v6-20261006-r1`(generation 41)이었다. 이후 generation 42 전환은 문서 상단 기록을 따른다. GENOS 현장 배포는 별도다. 일반 법률 실행과 AD 제어는 분리한다. GENOS_STATE_DIR의 영속 로컬 SQL 볼륨·상주 작업자·워크플로우 Python 교체 조건을 인계에서 확인한다. Redis는 사용하지 않는다.

### NFS만 제공되는 환경의 SQL 후보 진단 (2026-10-06)

사용자 사진의 HTTP 422와 `shortcut v4 requires local durable storage and one writer service`는
shortcut repository의 NFS/CIFS 사전 거부 지점에서 발생했다. 사용자는
`GENOS_RUNTIME_DIR=/nfs-root/diamo/8-agent/runtime`, `GENOS_STATE_DIR` 미설정,
NFS 외 사용 가능한 저장소가 없다고 확인했다. 기존 `GENOS_MEMORY_JOURNAL_MODE=DELETE`는
이전 메모리 구현에서만 읽으며 shortcut/AD의 WAL 고정 및 NFS 거부를 바꾸지 않는다.
[독립 실행 진단 TXT와 안내](08_DEPLOYMENT/GENOS/handoffs/sql_candidates_20261006_r1/GUIDE_UTF8.txt)는
기존 DB를 열지 않고 별도 합성 DB로 같은 호스트의 DELETE 잠금·rollback·중단 복구를 확인한다.
현재 설정된 SQL 주소와 loopback의 PostgreSQL/MySQL/SQL Server 연결 가능성,
실제 mount·클라이언트·driver 후보를 기록한다. 비밀 값·전체 망 스캔·SQL 인증/DDL은 제외한다.
시험 PASS는 NFS 운영 안전·다른 호스트 잠금·재배포 영속성 인증이 아니다.
코드스페이스 발견 결과를 코드서빙 결과로 간주하지 않는다. WSL 단독 TXT/보존/비밀 비출력 등
5개 검사와 Bash/Python 3.11 문법을 확인했다. 현장 실행·SQL 사용 가능성은 미확인이다.
기존 서비스/MAIN/환경 설정을 이 진단으로 변경하지 않았다.

### 기존 SQLite의 NFS 상태 저장 수정 (2026-10-06)

사용자 요청에 따라 작업 코드의 shortcut/AD/case adapter가 공통
`semantic_runtime.state_sqlite` 정책을 사용하도록 수정했다. NFS/CIFS는 DELETE,
로컬은 WAL이 기본이며 FULL 동기화·외래키·30초 잠금 대기와 기존 BEGIN IMMEDIATE를
사용한다. 저널 적용 결과를 확인하며 WAL의 NFS 사용을 거부한다.
`GENOS_MEMORY_JOURNAL_MODE=DELETE`를 명시할 수도 있지만 현재 NFS 설정에는 추가가 필요 없다.
`GENOS_STATE_DIR`이 없으면 기존 `GENOS_RUNTIME_DIR`과 SHORTCUT_CURRENT 선택을 유지한다.
이번 작업 코드와 [NFS 상태 저장 수정 R1](08_DEPLOYMENT/GENOS/handoffs/nfs_state_sqlite_20261006_r1/GUIDE_UTF8.txt)은
이전 R5/R2의 'NFS 상태 저장 거부/영속 로컬 볼륨 필수' 조건을 대체한다. 과거 반입본은 보존한다.
6개 상태 저장 코드와 30개 엔진 pin을 연결하며 현장 ZIP은 기존 request-input R2의
compact 용어집 reader와 나머지 코드 pin을 보존한다. 데이터/스키마/MAIN 포인터를 변경하지 않는다.
모의 NFS 분기·실제 HTTP ingress·동시 쓰기·중단 복구와 현행 AD/shortcut 회귀 148개 통과,
독립 TXT의 백업/적용/재실행/저장소 확인/원복/알 수 없는 코드 보존과 Git ZIP 대조를 확인했다.
확장 v3 테스트의 11개 실패는 수정 전 R2 코드에서도 같은 항목으로 재현했으며 이번 수정으로
해결하거나 전체 과거 검사 통과로 보고하지 않는다. 현장 NFS의 서버 간 잠금·fsync·장애 내구성,
코드서빙 리비전 적용과 실제 요청 성공은 미확인이다. SQLite 변경만으로 현장 내구성을 인증하지 않는다.

### 원문 수집 단계의 별도 시간 제한 제거 (2026-10-06)

사용자 사진의 `source recall policy time limit`과 HTTP 504는 원문 수집 코드의
180초 타이머에서 발생했다. 사용자 요청으로 작업 코드의 해당 타이머와 하위
global 회수의 120초 타이머를 제거했다. 기존 조 단위와 최소 단위 fulltext 읽기는
같은 변경을 사용한다. 전체 요청 deadline·모델 통신·건수/문자/행동 예산은 유지하며
v6의 법률 무관 입력 분기 누락을 이 변경으로 해결했다고 보지 않는다.
[누적 R1 적용·검증·원복 안내](08_DEPLOYMENT/GENOS/handoffs/source_recall_timeout_20261006_r1/GUIDE_UTF8.txt)는
request-input R2와 NFS SQLite R1의 정확한 코드/compact reader를 보존한다.
관련 합성 계약 48개와 두 기준 반입본의 적용/재실행/원복/변조 거부를 확인했다.
작업 코드·Git push·현장 리비전 배포·워크플로우 질의 성공은 별도 상태다.

### v6 대화 입력의 직접 안내 분기 (2026-10-06)

사용자 요청으로 v6 사건 진입부에 `source-request-route`를 연결했다.
입력창 안내 문구·무의미한 글자/기호·무관한 일상 대화는 현재 질문/조건을 참고해
직접 안내 응답으로 끝내며 원문 검색·읽기·법률 판단과 command replay를 실행하지 않는다.
현재 사건의 조건·리비전·판단 근거는 안내 입력으로 변경하지 않는다. 인사와 법률/문서
질문이 섞인 입력과 현재 질문에 관한 짧은 정정·복원·표현·확인 요청은 기존 처리로 연결한다.
LLM 수신 원응답, 분류 이유와 `request_routing`을 남긴다.
[누적 R2 적용·검증·원복](08_DEPLOYMENT/GENOS/handoffs/source_recall_timeout_20261006_r2/GUIDE_UTF8.txt)은
앞 시간 제한 제거 R1과 NFS SQLite R1·compact reader를 보존한다.
전체 요청 deadline·통신·기타 예산은 유지하며 실제 내부 모델 분류 품질과 현장 배포는 미확인이다.


### AD 자연어·멀티턴 해석 연결 (2026-10-06)

사용자 요청으로 활성 AD의 매 턴을 GENOS 내부 LLM으로 해석하는 작업 코드를 연결했다.
현재/최근 표·선택·이전 확인 질문을 SQL 맥락으로 전달하고 닫힌 action/args를 검증해
기존 SQL 실행기로 처리한다. 상세·상태·변경 결과는 표로 출력한다. 이전 고정 표현만
지원/관리 명령 모델 호출 없음 규칙을 대체하며 정확한 모드 경계는 유지한다.
[계약·실제 배선·검증·적용 상태](07_DOCS/REFERENCE/OPERATIONS/AD_NATURAL_LANGUAGE_20261006.md).
52개 관련 계약과 35개 SQL AD 호환 회귀 통과. 모의 모델 배선 검사이며 내부 모델 품질·
GENOS 배포·Git push는 미확인이다. 활성 frozen MAIN·데이터 CURRENT는 전환하지 않았다.

## 2026-10-06 법령별 후보 탐색 작업 코드

[구현과 완료 정책](07_DOCS/REFERENCE/REPORTS/LAW_GROUPED_NAVIGATION_DESIGN_20261006/IMPLEMENTATION.md). 선택 generation의 소유 본문 fulltext를 법령·조별 페이지로 조회하고 모델의 법령 선택 이유, 부모·형제 READ, 다른 법령 이동·재검색·SQL 재개를 v6에 연결했다. 미해결 REQUIRED 연결도 완료를 허용하되 상태·경고를 보존한다. 코드와 profile/PIPELINE/engine 해시를 함께 반영해야 하며 기존 최소 단위 색인을 다시 만들 필요는 없다. 워크플로우 Python의 법령별 표시 수정도 편집기에 별도 적용해야 한다. 현장 명령은 `python3`를 사용한다. 작업 코드와 합성 계약 검증 상태이며 GENOS 리비전 배포·현장 내부 모델 검증은 수행하지 않았다.

2026-10-07 후속 조사에도 [구조 조회·조문 목차·전체 범위 읽기](07_DOCS/REFERENCE/OPERATIONS/FOLLOWUP_STRUCTURE_LOOKUP_20261007.md)를 연결했다.
`SEARCH_STRUCTURE`/`OPEN_STRUCTURE`/`NEXT_STRUCTURE`는 fulltext 적중 여부와 관계없이 저장된
본문 좌표·제목을 조회하고 기존 원문 READ/인용/SQL 재개로 넘긴다. 본문 법령과 별표 문서의 역할을
구분하며 현재 로컬 세대의 기존 약칭 projection도 작업 설정에 결속했다.
작업 reader에서 원문/navigation SHA와 `자본시장법 제6조`의 유일한 본문 위치(2,387자)를
모델/fulltext 호출 없이 확인했다. 새 도구 계약15개와 모의 API 게시, 관련 기존 계약61개를 확인했으며 전체 과거
계약·환경 검사 통과는 아니다. 작업 코드 변경이고 MAIN45·frozen release·데이터·GENOS 배포는 유지했다.

2026-10-08 사용자 정정에 따라 같은 [후속 구조 탐색 경로](07_DOCS/REFERENCE/OPERATIONS/FOLLOWUP_STRUCTURE_LOOKUP_20261007.md)에
현재 문서의 실제 계층/번호 예시/상위 경로/직계 하위 항목, `BROWSE_STRUCTURE`와
`SEARCH_STRUCTURE.structure_filter`(좌표·제목·저장 분기)를 추가했다. 조회 실패 후에도
현재 문서 구조와 재조회 도구를 유지하며 fulltext로 자동 전환하지 않는다. 작업 구조
reader에서 `제1편 총칙 → 제6조 금융투자업`을 모델/fulltext 호출 없이 확인했고 후속 계약27개·
관련 기존61개가 통과했다. 작업 코드·엔진/PIPELINE 결속 상태이며 MAIN45 frozen release와
GENOS 배포/내부 모델의 선택 품질은 이번 작업에서 변경·검증하지 않았다.

2026-10-07 사용자 캐시 정정과 16GB 서버 확인에 따라
[전체 데이터 상주 캐시 R4](08_DEPLOYMENT/GENOS/handoffs/query_latency_20261007_r4/README.md)를
삼성파트너 메일로 발송했다. SENT 1a1151de7ae334ad의 수신자와 ZIP·적용/원격 push/요약 TXT·안내·검증·해시 7개 첨부를 확인했다.
원문/navigation/FTS/실제 서빙 Glossary SQLite 전체를 최초 사용 때 적재해 어떤 질문과 세션에서도 재사용한다.
RAM 예산8GiB auto이며 부족한 데이터도 전체 로컬 snapshot을 유지한다. snapshot에 TTL/LRU는 없고
서버 프로세스 재시작 때 다시 준비한다. 검색 결과 LRU128MiB는 별도 보조 기능이다.
이전 query-latency R3 최적화와 누적 system logging을 보존한 307파일 인계본이다.
통합 계약118개 및 실제 TXT 반입/원복/gate/mock push9개가 통과했다. 기존 stale adoption fixture2개와
WORKSPACE activation receipt의 이전 hash 결속 문제는 별도 기록하고 생산 receipt를 수정하지 않았다.
현재 진행 UI 작업은 working tree에서 보존하며 인계 snapshot에는 검증된 system logging 기준을 사용했다.
캐시 변경에는 workflow 편집기 변경이 필수하지 않으므로 별도 진행 UI 수정은 유지한다.
이 작업은 MAIN45 포인터와 NFS generation을 바꾸지 않았다. GENOS 실제 반입/push/리비전/내부 속도는 미확인이다.

2026-10-08 [ADR-0688](04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery/README.md)에서
후속 구조 조회 조건·현재 위치·실패 원인의 행동/진행/workflow 표시, 같은 문서·검색식의
새 원문 없는3회 Fulltext 페이지 반복 후 구조 전환, 실패 종류 구분을 기존 작업 코드에
통합했다. 동결 후보106개와 통합 소비자/native API45개 검사 통과. 합성 Qwen 보조
실험은8호출 중6개 원문 전달, 조문 부재2개 upstream 빈 오류 응답으로 확인 불가다.
선택된 로컬 MAIN45 포인터와 GENOS 코드/워크플로우/리비전은 변경하지 않았고 현장 검증은 미수행이다.
