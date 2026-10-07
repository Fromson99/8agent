# AD 자연어·멀티턴 관리 연결

2026-10-06 후속 R2는 긴 표 스크롤 표시와 구간별 모델 읽기를 추가한다.
아래 R1 경로의 자연어 해석·SQL 계약은 유지하며, R2 표시에는 **워크플로우 편집기
전체 교체도 필요**하다. 실제 GENOS의 HTML/CSS 허용 여부는 미확인이다.

## R2 긴 표·모델 구간 읽기

원본 표는 SQL에 보존한다. 사용자 목록은 20행, 상세는 기존 약 10,000문자 페이지를
유지하며 `다음`/`계속`으로 끝까지 조회한다. 서버는 Markdown과 함께 안전하게 escape한
`table_html`을 반환한다. workflow 및 `/chat`은 HTML을 기본 표시하며, 최대 높이 480px,
가로·세로 overflow, 고정 헤더를 제공한다. 원문이 HTML·스크립트로 실행되지 않는다.
워크플로우 설정 `GENOS_AD_TABLE_FORMAT=markdown`은 원본 Markdown으로 되돌린다.
GENOS가 인라인 HTML/CSS를 제거한다면 채팅 프런트의 표 컨테이너 CSS 지원이 필요하다.
로컬 HTML 생성·전달 검사를 현장 스크롤 성공으로 보고하지 않는다.

모델 입력은 `ad_context.ContextReader`의 미리보기·전체 길이·불투명 cursor를 사용한다.
160문자 초과 문자열과 8개 초과 배열은 생략 표시와 실제 전체 데이터를 읽는 참조를
전달한다. `read_table`은 같은 대화의 표/상세를 8행씩, `read_context`는 긴 문자열을
2,000문자씩 읽는다. 다음 offset/cursor와 complete 여부로 누락 없이 이어서 읽는다.
화면의 표시 위치와 선택은 읽기 과정에서 바뀌지 않는다. 전체 테이블을 한 프롬프트에
붙이지 않으며, 매 후속 호출은 최근 구간 하나와 최대 2,000문자의 모델 작업 메모를
전달한다. 이미 읽은 원문을 대화 전체로 재누적하지 않는다.

번호·다음 같은 단순 요청에는 추가 읽기가 필요 없고, 필요한 경우에만 같은 사용자
턴에서 내부 LLM을 여러 번 호출한다. 각 호출에는 별도의 사용량/시간/입출력 receipt를
남긴다. 최대 32회 안에 최종 계획이 나오지 않으면 AD_CONTEXT_INCOMPLETE 오류로
범위를 좁히게 한다. 미완료 분석을 전체 처리로 표시하거나 중간 변경을 실행하지 않는다.
호출 실패의 자동 재시도/provider fallback은 없다. 일반 GENOS 입력 바이트 상한을
부활시키지 않으며, 구간 크기는 AD 자료 접근 계약이다.

`ad_language_call(operation,sequence,input,model_output,plan,receipt,created_at)`을 기존
상태 DB에 가산한다. 전체 원래 맥락은 ad_language_turn에 보존하고, 매 모델 요청은
구간 맥락만 전달한다. 모든 read/final 실행 전에 대화 상태·lease를 대조한다.
cursor는 한 턴에서만 유효하며 다른 대화 표/상세 ID는 거절한다. 최종 변경은 기존
행 revision 검사와 request_id 캐시를 유지한다. `model_call_count`·`model_receipts`가
복수 호출을 보여 주며 로그는 `ad.language.context_read`를 추가한다.

새 Excel 업로드/수집기를 만든 작업은 아니다. 기존 shortcut/SQL 표와 상세 내용에
구간 읽기를 연결했으며, Excel 반입은 원래 수집 경로에서 처리한 뒤 이 자료 계약으로
연결해야 한다. 실제 내부 모델의 구간 선택·메모 정확도는 현장 검증 대상이다.

R2 반입: `08_DEPLOYMENT/GENOS/handoffs/ad_language_20261006_r2/`의 코드 ZIP/APPLY TXT로
기존 ~/DEV에 적용하고, PASTE_ALL TXT를 워크플로우 Python 편집기에 전체 반영한다.
기존 R1·원본 세대·DB·CURRENT를 보존하며 Git push와 코드서빙 배포는 별도다.
현장 테스트는 워크플로우 화면에서만 수행한다. language_revision은
`ad-language-v2-20261006-r2`, table_display_revision은 `ad-scroll-table-v1-20261006-r2`다.

2026-10-06 사용자 요청에 따라 작업 코드의 AD를 GENOS 내부 LLM 해석으로 변경했다.
이 문서는 이전 SQL AD 설계의 “고정 한국어 표현·관리 명령에서 모델 호출 없음” 부분을
대체한다. 정확한 `[AD모드 시작]`/`[AD모드 종료]` 경계와 SQL 저장·권한·변경 계약은 유지한다.
로컬 frozen MAIN·데이터 CURRENT와 실제 GENOS 코드서빙 리비전은 이 작업으로 전환하지 않는다.

## 실제 경로

| 단계 | 입력 | 처리 | 출력·소비자 |
|---|---|---|---|
| 워크플로우 | question, 안정된 chatId/channel/request_id | 기존 AD_PROBE | service.service |
| 진입 | 서버 TEAM_ID, 선택 shortcut DB, 대화 ID | ad_gateway → ad_mode.handle | 모드 밖은 일반 경로, 활성 AD는 ad_language |
| 맥락 | 현재·최근 5개 표의 표시 행, 현재 선택, 편집 대기, 최근 12개 완료 요청/응답 | ad_operation·ad_view·ad_selection 조회 | 내부 모델의 해석 입력 |
| 해석 | 자연어·이전 의도·표 번호 | ad_model → 기존 GenosTransport.send_once | ad_command_v1 구조화 action/args |
| 실행 | 스키마 검증한 계획, 같은 대화의 표/행 | ad_language.execute → 기존 Controller/Backend | 실제 SQL 조회·변경 결과 |
| 표시 | 조회한 목록/상세/상태/변경 결과 | 서버 표 렌더러 | 기존 ad-mode-v1.text → workflow/chat adapter |

GENOS service의 모델 해석은 asyncio.to_thread에서 수행한다. `/v1/rag/ask`의 동기
FastAPI 진입도 같은 해석기를 사용한다. 법률 RAG 초기화나 법률 command resolver를
관리 LLM 호출의 입구로 쓰지 않는다. AD 발언은 shortcut 대화/위키 구성 입력에 넣지 않는다.
저수준 handle의 interpreter 없는 실행은 기존 SQL 명령 호환·단위 검사용이며,
실제 서비스와 API의 활성 AD 자연어 턴에는 내부 해석기를 전달한다.

## 모델과 설정

기존 GENOS_LLM_URL 또는 GENOS_BASE_URL/GENOS_LLM_SERVING_ID, GENOS_LLM_KEY,
GENOS_LLM_MODEL, GENOS_LLM_TIMEOUT과 GENOS_RAG_MAX_OUTPUT_TOKENS를 재사용한다.
내부 GENOS만 사용하며 다른 모델·외부 공급자·규칙 해석기로 자동 fallback하지 않는다.
출력 token 설정은 기존 서비스와 같고 thinking은 false다. 입력 바이트 상한을 추가하지 않는다.
내부 모델 설정/응답 오류는 AD 오류로 반환하고 일반 법률 경로로 흘려보내지 않는다.
TEAM_ID는 코드서빙 서버와 워크플로우에 같은 실제 팀 값으로 설정한다.
선택 상태 DB, NFS DELETE/로컬 WAL 및 기존 동기화 정책은 그대로 사용한다.

모드 진입·종료는 정확한 경계이므로 모델 호출 없이 처리한다. 그 외 도움말·고정 표현·
표 이동·확인 답변을 포함한 활성 AD 턴은 매번 LLM으로 해석한다.

## 자연어와 멀티턴

| 입력 흐름 | 해석·처리 |
|---|---|
| 숏컷보여줘 → 1번 보여줘 | shortcut 목록 → 현재 표 1번 상세 |
| 1번 보여줘 → 그 사건의 사실도 보여줘 | 선택 사건 → 사실 목록 |
| 그거 지워 → 몇 번인가요? → 첫 번째 거 | 확인 질문 기록 → 원래 휴지통 의도·번호 결합 |
| 첫 번째 제목 바꾸자 → 제목은 새 이름 | 대상 선택·필드 질문 → 새 제목 revision |
| 12시에 야간작업 예약 → 정오/자정? → 자정 | 원래 예약 의도와 답변 결합 |
| 상세 → 계속 / 목록 → 다음 | 이전 출력 위치에 맞는 본문·목록 이동 |

모호한 표현에는 LLM이 구체적인 확인 질문을 반환하고 SQL 변경은 하지 않는다.
확인 질문과 해석 계획도 SQL에 저장하므로 프로세스 재시작 후 후속 입력을 연결한다.
이전 표를 명시하면 실제 그 대화에 속한 view ID만 사용할 수 있다. 다른 공간·대화의
표나 존재하지 않는 행을 모델이 생성해도 실행기는 거절한다.

목록은 기존 20행 페이지를 유지한다. 상세는 JSON 코드 블록 대신 항목/값 표로 표시한다.
긴 값을 2,000문자 셀로 나누고 출력 페이지는 약 10,000문자씩 이어서 제공한다.
원래 값을 보존하고 `계속`으로 끝까지 조회한다. 실제 모델이 저장 데이터를 임의로
요약·재작성해 표 값을 만드는 경로는 없다. 사용자 승인과 법률 검증은 별도다.

## SQL·재실행·경합

기존 schema-v1 DB에 ad_language_turn과 session/created_at 색인을 가산한다.
기존 테이블/데이터를 덮어쓰거나 삭제하지 않는다. operation FK·session FK로 연결하며
input, 원모델 응답, 검증 계획, 모델/사용량/시간/해시 receipt, 대화 fingerprint와
claim lease를 남긴다. 사용량 누락은 미확인으로 보존한다. 인증 비밀은 출력/원모델 기록에서 가린다.

요청 claim과 맥락을 짧은 SQL 트랜잭션으로 저장한 뒤, 쓰기 잠금을 해제하고 모델을
호출한다. 모델 반환 후 같은 대화 상태의 fingerprint와 lease를 검사하고 SQL 실행·
응답 캐시를 한 트랜잭션에서 commit한다. 같은 request_id/입력 재전송은 캐시를 반환하며
모델을 다시 호출하거나 변경을 반복하지 않는다. 동일 ID/다른 입력은 거절한다.
동시 처리 중 요청은 pending을 반환한다. 중단된 claim은 재실행하지 않고 오류로 남긴 뒤
새 request_id를 사용하게 한다. 모델 대기 중 AD 종료나 다른 표/선택 변경이 발생하면
AD_CONFLICT로 실행을 차단한다. 대상 콘텐츠의 동시 변경은 기존 revision CAS가 거절한다.

## 검증과 적용 상태

새 AD와 NFS SQL·기존 v6 입력/직접 안내 회귀 52개 통과. 기존 SQL AD 호환 회귀 35개 통과.
스크립트 모델은 실제 자연어 품질을 인증하지 않는다. 외부 모델 호출·GENOS 접근은 0회다.
기존 workflow 회귀의 6개 실패는 앞서 메일로 보낸 변경 전 byte-preserved 편집기 코드에서도
같은 항목으로 재현했다. 이번 변경으로 해결하지 않았고 전체 workflow 회귀 통과로 보고하지 않는다.

관련 30개 엔진 manifest에 4개 변경 모듈·2개 새 모듈의 hash를 갱신·추가했다.
다른 코드·스키마·데이터 pin을 일괄 rehash하지 않는다. 활성 frozen MAIN은 이전 코드다.
GENOS 반입·Git push·새 코드서빙 리비전 배포·실제 자연어 해석 품질은 별도 상태이며 미확인이다.

이번 기능은 서버 코드 변경이다. 사용자가 적용한 AD 대응 workflow의 raw text/표 전달 경로는
재사용할 수 있으며 Python 편집기를 이번 기능만을 위해 다시 교체할 필요는 없다.
실제 확인은 같은 대화의 워크플로우 테스트 화면에서 시작 → 숏컷보여줘 → 1번 보여줘 →
후속 요청 → 종료 순서로 수행한다. 코드서빙 직접 테스트를 요구하지 않는다.

복구는 반입 TXT의 정확한 backup 경로로 코드만 되돌린다. 추가된 ad_language_turn/감사 자료는
보존하며 이전 호환 AD 코드가 이를 사용하지 않는 상태로 돌아간다. 진행 중인 AD 요청이
끝난 뒤 반입·원복하고, 원본 DB·generation·CURRENT는 변경하지 않는다.
