# 구현·이행·검증 계획

설계 단계의 변경 지도다. 아래 추가 모듈·API·설정은 아직 구현되지 않았다. 현재 진입점과 함수는 [조사 근거](evidence.json)에 고정한다.

## 1. 실제 연결 지점

| 현재 파일/함수 | 확인한 제약 | 제안 변경과 소비자 |
|---|---|---|
| `main.py::chat_endpoint`, `chat_adapter.request_body/chat` | 신뢰 플랫폼 경로와 일반 경로 분리; 사건 식별자·관리 응답 일부 누락 | 기존 신뢰 연결 유지, workspace/session envelope 왕복; 관리 표 응답 분기 |
| `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py::_request_body/_user_id/_for_markdown` | 스튜디오 중첩 사용자 처리 부족; 고정 genos-chat; 줄바꿈 일괄 변경 | 승호님 channel/identity 추출 방식 적용, 관리 필드 전달, 표 보존 렌더러 |
| `service.py::_normalize/_POST_ALLOWLIST` | JSON 게이트웨이는 POST ask만 허용; 일반 세션 필드 제거 | 명시적 `MEMORY_QUERY`, `MEMORY_COMMAND`, `MEMORY_CHAT` API_TYPE와 한정 경로 추가 |
| `semantic_runtime/app.py::ask/shortcut_command/memory_query` | 관리 명령 capture 필수; use_llm 의존 인증; 일부 목록 cursor 없음 | 공통 관리 서비스 호출, command/query와 대화 어댑터가 동일 계약 사용 |
| `legal_agent/memory_identity.py::resolve/verify_assertion` | 개인 user/team/session + memory/use_llm 요구 | 신뢰 workspace 주체와 legacy 개인 주체 구분; 관리에 모델 실행 요구 제거 |
| `shortcut_repository.py::scope/current/search/...` | 개인 범위, immutable 원장, 공개 상태 중심 조회 | workspace scope adapter, inspect, tombstone·review·revision 검사 추가 |
| `shortcut_commands.py::execute` | issue/assign/fact/relate/detach/publish/retire만 지원 | 허용 필드 기반 edit/review/trash/restore/features/job 계약; 기존 명령 호환 유지 |
| `shortcut_ingress.capture`, `unified_runtime.open_cases` | 캡처/저장소 선택과 통합 실행 결합 | 관리 요청은 캡처 전 분기; 기능 OFF용 단기 대화 상태와 장기 기록 분리 |
| `procedure_memory.py`, `wiki_execution.py`, `shortcut_cases.py` | 기존 조건·원문 기반 재사용 | 모든 후보·캐시·직접 재실행에 review/lifecycle/feature 검사 |
| `legal_wiki_compiler.build_with_pipeline/compile_snapshots/rebuild` | bounded batch/lease, 기본 draft, projection 있음 | durable job 결속, 입력 watermark, pause·cancel·fence, 삭제·편집·OFF 검사 |
| `lawrag/pipeline/action_memory.py::main` | shortcut-v4 build/status, manual 및 내부 모델 제한 있음 | 기존 CLI와 채팅·야간이 같은 작업 서비스 호출; runner 중복 금지 |
| `shortcut_operations.py`, `unified_memory.py`, `shortcut_store.py` | 백업·새 세대 이행·selected_store 존재 | v4→v5 새 세대, 검증 receipt, 관리 저장소는 capture OFF에도 같은 pointer 사용 |
| `00_SYSTEM/PIPELINE.json`, `WORKSPACE.json`, 아키텍처/스키마 문서 | 선언과 실제 호출 연결 필요 | 단계·설정·workspace 논리 root·소비자·검증 방법을 함께 반영 |

제안 모듈은 `semantic_runtime/legal_agent/memory_management.py`(공통 작업), `management_session.py`(표·선택·문맥), `management_render.py`(정확한 표/본문)로 역할을 나눈다. 큐 worker는 기존 action-memory 실행 계통을 확장한다. 별도 챗봇·독립 지식 파이프라인을 만들지 않는다.

제안 `/v1/rag/memory/chat`은 자연어를 구조화해 기존 query/command 서비스 함수를 호출한다. 내부 HTTP 자기 호출은 하지 않는다. 일반 `/v1/rag/ask`에서도 같은 분기 함수를 써 관리 의도가 인식되면 캡처·법률 추론 전 관리 경로로 보낸다. 워크플로우와 `/chat` 모두 `service/service.py → root service.py`의 같은 모듈·상태를 사용한다.

명령어/관리 의도 인식의 명시 규칙을 먼저 적용하고, 자유 표현의 후속 해석은 기존 요청 의도 판단에 닫힌 관리 도구 메뉴를 추가하는 방식으로 결합한다. 모든 법률 질문 앞에 추가 LLM 호출 하나를 무조건 넣지 않는다. 판단이 애매한 변경은 실행하지 않고 필요한 대상만 묻는다.

## 2. 구현 순서와 종료 조건

1. **세션·저장 계약 확정:** 플랫폼/스튜디오 payload fixture, trusted workspace와 actor 구분, 영속 저장 토폴로지 결정. 같은 대화·다른 채널·다른 공간·재시작 시험으로 연결 확인.
2. **읽기 전체 경로:** schema catalog, consistent view manifest, 상세/원문 청크, 전용 표 렌더러. 각 테이블·필드·artifact 수를 원장과 대조해 누락·중복 없는 탐색 확인.
3. **수정·승인·휴지통·복구:** CAS·중복 방지·부모/공유 의존·재사용 차단을 먼저 구현. 명령어로 확인한 뒤 자연어 표현을 같은 작업 계약에 연결.
4. **작업과 기능 스위치:** 수동/야간 같은 큐, job pause/resume/cancel, 두 기능 독립 ON/OFF. OFF 후 관리·복구·ON이 가능한지 확인.
5. **통합 검증·패키징:** 양쪽 GENOS 입구와 frozen 후보의 소비자까지 검사. 실제 모델 자연어 멀티턴, 회귀 평가, 배포 폴더 의존·부팅 검사 후에만 MAIN 후보.
6. **현장 검증:** 실제 내부 모델·Redis/정본 저장·워크플로우 테스트 화면에서 여러 턴 실행. 코드 ZIP 적용, 워크플로우 편집기 반영, Git push, 코드서빙 리비전, 데이터 세대, 확인 영수증을 각각 기록.

설계 문서 작성은 새 실험이 아니므로 이번에는 ADR·모델 호출을 만들지 않는다. 구현 후 모델 비교/멀티턴 평가를 실행할 때는 기존 표준 두 문서를 끝까지 읽고 예약·부모·기준·분리 표본·후보 동결을 선행한다. 결과를 보고 만든 후속 후보는 새 ADR이다. 로컬 제품 MAIN은 적격 arm과 hash 고정 promotion plan/receipt 절차로 연결한다. 사용자 요청 없이 이 설계를 배포 완료로 바꾸지 않는다.

## 3. 데이터 이행과 되돌리기

기존 v4 DB를 제자리 ALTER하지 않고 `selected_store`가 선택할 새 v5 세대를 만든다. 원장·artifact·지식 내용과 해시를 그대로 복사하고 관리 테이블·scope binding을 추가한다. 원문·용어 색인은 이 설계만으로 재구축하지 않는다. shortcut/wiki의 관리·재사용 색인과 Markdown projection은 새 상태 정책으로 재구축한다.

이행 receipt에 원본/대상 경로·해시·schema, 테이블별 행 수, FK·불변 hash 검증, legacy scope 대응, 이전/새 feature 상태, 캐시 정책 revision을 기록한다. 경로는 `lawrag.platform.workspace` 논리 root로 해결한다. 같은 팀이라는 이유로 기존 개인 기록을 모두 공개하지 않는다. 공유할 원본 scope·문서 범위는 명시된 이행 manifest만 사용한다.

전환 직전 쓰기를 짧게 멈추고 마지막 watermark 이후 변경을 반영한 다음 원자적으로 pointer를 바꾼다. 서비스와 worker의 세대·schema·policy가 맞아야 재개한다. 새 기록의 승인 상태를 LEGACY_UNREVIEWED/PENDING 중 출처에 맞게 표시한다. 기존 승인 receipt가 있으면 해시가 맞는 대상에만 이행한다.

되돌리기는 두 수준이다. **동작 중단**은 새 관리 쓰기·worker를 멈추고 호환 reader를 유지한다. **저장소 rollback**은 새 세대 쓰기가 없다면 이전 pointer로 복귀할 수 있다. 쓰기가 있었다면 v5를 보존하고 변경 이력·tombstone·OFF 설정을 반영하는 복구 세대를 검증한 뒤 전환한다. v4로 단순 pointer 복귀해 삭제 항목을 부활시키거나 새 편집을 잃지 않는다. 호환 reader가 없으면 관리/재사용을 차단하고 원문 RAG로 제한한다.

백업은 정본 DB의 일관된 snapshot과 artifact manifest를 묶는다. 라이브 WAL 파일의 일부만 복사하지 않는다. 휴지통 복구는 이 백업 복원과 독립적이다. projection 실패 시 새 CURRENT를 내지 않고 이전 산출물을 유지하되 서비스는 최신 tombstone을 검사한다. 오래된 정적 Markdown을 독립적으로 공개해 차단을 우회하지 않는다.

## 4. 필요한 검증

| 요구/위험 | 검사와 통과 조건 | 남은 한계 |
|---|---|---|
| 별도 로그인 없이 연결 | 신뢰된 workspace+GENOS 대화로 작동; 개인 user_wiki 의존 없음 | 실제 플랫폼 권한 전달은 현장 |
| 멀티턴 대상 정확성 | 페이지 전환/이전 표/선택/작업 영수증별 정확 ID 일치 | 다양한 자연어는 모델 평가 필요 |
| 전체 조회 | 카탈로그 모든 필드·버전·artifact를 끝까지 열거; 누락·중복 0 | UI 최대 payload·파일 지원 측정 |
| 행 충돌 | 조회 후 수정/삭제/권한 축소 시 잘못된 대상 변경 0 | 동시성 부하 실측 별도 |
| 휴지통 차단 | 모든 소비자·캐시·직접 ID·진행 중 결과·재구성에서 제외 | 이미 발송한 답변 소급 회수 불가 |
| 복구 | 원내용 hash·연결 복구, 최신 근거 달라지면 재사용 차단 | 의미적 검증은 계약 검사로 대체 불가 |
| 승인과 검증 분리 | 사용자 승인만으로 법률 PASS/판단 재사용 허용되지 않음 | 기존 품질 평가와 별도 |
| OFF/ON | 두 스위치 조합, 진행 중 작업, 재시작, 관리·복구 유지 | 플랫폼 자체 로그 보존은 별도 정책 |
| 반복/부분 실행 | 동일 message 재시도 중복 0; 청크 실패 후 개별 receipt 일치 | message ID 실제 전달 확인 필요 |
| 큐 내구성 | worker 중단·lease 만료·중복worker·수동/야간 경쟁 시 stale commit 0 | 실제 GENOS worker 배치 확인 |
| 표시 | 표 줄바꿈·파이프·긴 한글·빈 값·본문 청크 보존 | 워크플로우 화면 렌더 확인 |
| 배포 | 실제 패키지 파일/의존/hash·부팅·공통 입구 검사 후 활성화 | 로컬 통과 ≠ 현장 배포 성공 |

자연어 평가의 독립 단위는 여러 표현이 아니라 **관리 사건 전체**다. 서로 다른 사건·범위·변경 충돌·의존 관계를 분리한 holdout을 만들고, 기준은 현재 API/수동 작업으로 만든 기대 상태·ID·hash다. 어휘만 바꾼 턴을 독립 사례로 과대 계산하지 않는다. 정답 대상 변경·누락·무단 범위 변경은 허용 회귀 0의 목표로 둔다. 법률 응답 회귀도 동일 입력·데이터·모델 조건으로 비교한다. 현재 사례 수·통과율·속도 결과는 아직 없다.

담당 경계: 애플리케이션 구현은 세션·관리·상태/소비자 검사, 플랫폼 운영은 신뢰된 payload·영속 볼륨/DB·worker 실행·현장 편집기, 도메인 검토는 wiki 해석 검증이다. 실제 담당자/일정은 미지정이다.

## 5. 기대효과·비용·시간의 근거 수준

| ID | 구분 | 값/산식과 의미 | 근거·한계 |
|---|---|---|---|
| O1 | 코드 관측 | 현재 query limit 기본32, 허용1–100 | app.py; UI 적정 페이지 크기 실측 아님 |
| O2 | 코드 관측 | 현재 compiler 기본 batch4/max_seconds120, CLI 상한8/300 | action_memory.py; 처리량·완료시간 보장 아님 |
| A1 | 설계 가정 | 관리 표 기본20행, 응답 텍스트 예산 안에서 축소 | 큰 셀·GENOS 화면 확인 후 조정; 성능 예상 아님 |
| C1 | 산식 | 목록 호출 수 ≥ ceil(N / 페이지당 행 수); 본문·artifact 청크 호출은 별도 합산 | 실제 N과 크기 미측정 |
| T1 | 검증 목표 | 정형 명령·페이지 이동·표 렌더 추가 LLM 호출0 | 자유 표현 해석·wiki 구성은 별도 호출 |
| C2 | 산식 | 작업시간 = 큐 대기 + 각 청크(읽기+모델+검사+commit) 시간 합 + 재시도 | 병렬 가속·ETA 근거 없음 |
| C3 | 산식 | 추가 저장량 = view manifest + 관리 이력/영수증 + 새 버전 + 휴지통 보존 + export | 실데이터 크기·조회 보존기간 측정 필요 |
| U1 | 미확인 | 실제 GENOS 지연, 자연어 정확도, 내부 모델 사용량, 운영비, 개발 인일 | 이번 작업에서 실험/배포하지 않음 |

기대효과는 입력창에서 관리 대상과 결과를 직접 추적하고, 삭제 실수를 복구하며, 고정 작업의 불필요한 LLM 호출을 피하는 것이다. 현재 수치 근거로 몇 배 빨라진다거나 며칠에 끝난다고 예측하지 않는다. 장기 보존하는 휴지통과 전체 본문 조회는 저장·전송 비용을 늘릴 수 있다. 첫 측정에서 페이지 바이트·도구 호출수·모델 사용량·단계별 지연·이행 시간을 따로 기록한다.

## 6. 자체 검토

이번 문서는 코드 기반 자체 검토이며 독립 감독 검토나 현장 인증이 아니다. user_wiki/새 로그인 제외, 승호님 멀티턴 재사용 범위, 입력창 수동 실행, 전체 표/본문과 분할 조회, 앞 표 행 참조, 승인·수정·휴지통·복구, 독립 ON/OFF를 계약·시나리오·검증에 대응시켰다. 가장 큰 미해결 외부 조건은 GENOS의 v4 이후 정본 저장 토폴로지다. 코드·DB·운영 설정·활성 MAIN은 이번 설계에서 변경하지 않았다.
