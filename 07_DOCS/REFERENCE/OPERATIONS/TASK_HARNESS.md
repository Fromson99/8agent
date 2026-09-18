# 개념 정의·적용 범위 작업 하네스 v1

2026-09-16 작업 코드에 `definition-scope-harness-v1`을 구현했다. 기존 RAG의 retrieve 선택지이며 기본 선택은 `navigation-loop-v1` 그대로다. 첫 구현 시점에는 로컬 활성 릴리스 변경·품질 비교 실험·GENOS 배포를 수행하지 않았다. [연결 설계 검토](../REPORTS/RAG_TASK_HARNESS_FIT_20260916.md)의 첫 구현 범위를 따른다.

후속 [ADR-0438 실제 모델 검사](../../../04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation/README.md)에서는 설명 답변 0/6, 필수 원문 읽기 0/6이었다. 설명6개와 미등록 개념1개가 모델의 문자 위치 오류로 해석 단계에서 중단됐다. 재시도에 오류가 전달되지 않아 동일 요청을 반복했다. 실제 매도 요청 거절은 동작했다. 자동 채점이 오류 출력을 보호 경계 통과로 판정한 충돌도 보존했다. 이 첫 구현은 정상 작동이 검증된 후보가 아니며 MAIN에 반영하지 않았다. 코드 수정·재실행은 새 ADR의 후속 과제다.

후속 [ADR-0440 모델 상향 비교](../../../04_EXPERIMENTS/ADR/ADR-0440-task-harness-flash-medium/README.md)는 사용자 요청에 따라 같은 하네스에 `gemini-3.8-flash`와 추론 `medium`을 실험 한정으로 주입했다. 설명6개 모두 원문 문자 위치가 일치했지만, 문서명을 목표 개념처럼 부분문자열 매칭해 후보24개 상한에 걸리면서 원문 읽기와 최종 답변은 다시0/6이었다. 미등록 용어는 명칭 확인 요청, 실제 매도는 미지원 안내로 종료했다. 코드·전역 기본 모델·MAIN은 변경하지 않았다. 다음 수정 대상은 문서 범위와 목표 개념의 분리, 후보 검토와 진척 처리다.

## 책임과 실행 경로

`service.py → semantic_runtime.app → Pipeline → ServingTaskHarnessAgent → TaskSession → 기존 select/assemble/answer → feedback`이다. 별도 질의 서버나 원문 파이프라인을 추가하지 않는다. 새 구현의 API도 `/v1/rag/ask`, 조회 모드는 `use_llm=false`다.

| 단계 | 입력·출력 / 검사 |
|---|---|
| 정의 결속 | 선택 세대 안의 DB 경로·DB SHA-256·정의 ID/버전/해시·명시 검토 영수증 해시를 검사하고 요청마다 메모리에 고정 |
| 해석 | 사용자 원문 전체와 정확한 문자 span 보존. 모델의 개념명 제안을 등록 용어로만 역매칭. 미등록·모호·첫 범위 밖 작업은 사용자 확인으로 종료 |
| 개념 검토 | 출처별 정의 또는 연결 원문이 모델에 전달되어야 개념을 선택/제외할 수 있음. 다른 후보를 미확인으로 남긴 상태에서는 완료 불가 |
| 탐색 | 기존 STARTS/OPEN_TERM/GRAPH/STRUCTURE/LIST/READ/REFERENCES 재사용. 목록은 근거 읽기로 계산하지 않음. 자료 위치와 확보된 근거에 따라 조회 순서 선택 |
| 근거 검토 | 고정 ID `definition`, `requirements`, `exceptions`별 JUDGE 제안. 전달된 구간·정확한 인용·주장·문서 범위를 검사한 후 별도 모델 호출로 의미 검토 |
| 완료 | 선택 개념 1개, 나머지 후보 검토, 모든 의무 REVIEWED, 미확인·충돌·미해결 없음. 의미 검토의 SUPPORTED 외에도 범위 검사와 한계 없음이 필요 |
| 출력 | 검토된 의무의 채택 근거만 기존 findings/selected_ids로 변환. 미완료이면 확보한 검토 근거와 미해결 의무를 함께 반환. 충돌 의무의 주장은 제외 |
| 기록 | 기존 HTTP run_id의 query.id와 같은 ID로 DB checkpoint 기록. 실패·미정의·오류 복구 결과는 전체 요청/span·원문 세대·정의 버전에 연결된 PROPOSED 후보로 저장 |

고정 의무 문장은 모델 응답 스키마에 없다. 이를 재작성하는 응답·잘못된 ID/인자·조회 실패는 제한 안에서 재시도하며 상태를 소유하지 못한다. 이미 확인된 충돌은 단순 제외 제안으로 지울 수 없고 새로운 근거 검토가 필요하다. 실행 중 개념 선택을 바꿔 이미 만든 주장의 의미를 바꿀 수 없다.

호출 한도는 해석·탐색·근거 검토·실패 재시도를 모두 포함한다. DB 예산은 코드 상한 이내이고 요청 설정은 그보다 줄일 수 있다. 반복 조회·읽기 해제 후 재조회·이력 조회는 새 진척으로 계산하지 않으며 새 페이지·새 원문 구간·새 근거 검토는 구분한다. 시간 초과 후 돌아온 모델 제안은 실행하지 않는다. 진행 중 provider 호출의 물리적 중단은 provider timeout을 따르며 하네스 자체가 네트워크 호출을 취소하지는 않는다.

## DB와 설정

관리 진입점은 `.venv/bin/python 06_TOOLS/pipeline.py task-harness`다. `--db`를 생략하면 `lawrag.platform.workspace`의 `runtime` root 아래 `semantic/task-harness/definitions.sqlite`를 사용한다.

1. `template --output <새 JSON 파일>`: 정의·도구 계약·허용 행동·예산·완료 검사 ID를 가진 미검토 초안 작성.
2. `propose --file <JSON 파일>`: ID/버전으로 단 한 번 삽입. 수정은 새 버전으로 제안.
3. `review --version 1 --reviewer <검토자> --reason <검토 근거>`: 운영자가 명시적으로 검토 기록 작성. 모델 제안이나 초안 생성으로 자동 승인하지 않음.
4. `publish --version 1 --definition-sha256 <제안 해시> --review-sha256 <검토 해시> --output <새 DB>`: 검토된 DB 복사본 생성. 기존 파일 교체·MAIN 활성화 없음.

CLI의 `--db`는 하위 명령 앞에 둔다. 공개 여부나 모델 전송 권한을 이 명령으로 변경하지 않는다. 정의 DB에는 지원된 도구와 완료 연산 ID만 허용하며 임의 Python/SQL 실행문은 거부한다. 새 검사 연산이나 시스템 연결은 코드가 필요하다.

새 후보 세대에 게시 DB를 함께 배치한 뒤 기존 retrieve 노드의 `parameters.term_agent`에 다음 필드를 명시한다. 아래는 설정 형식이며 활성 `PIPELINE.json`에는 선택하지 않았다.

```json
{
  "implementation": "definition-scope-harness-v1",
  "task_policy": {
    "path": "task-policy/definition-scope-v1.sqlite",
    "sha256": "<게시 DB SHA-256>",
    "id": "definition_scope",
    "version": 1,
    "definition_sha256": "<정의 SHA-256>",
    "review_sha256": "<검토 영수증 SHA-256>"
  }
}
```

기존 `enabled`, 원문/용어 index 및 glossary 설정은 필요하다. 정책 path는 선택 원문 세대에 상대적이며 세대 밖 경로는 거부한다. 게시된 원문 세대에 파일을 추가하지 말고 정책을 포함한 새 후보 세대를 준비한다. `learning.bundle`의 기존 고정 탐색 recipe와 동시 사용은 거부한다. `learning.capture`의 잔여 문자열 수집 대신 이 하네스의 개선 후보 DB를 사용한다.

앱은 자신의 runtime 디렉터리 `90_RUNTIME/semantic/task-harness/execution.sqlite`를 주입한다. `Pipeline`을 직접 사용하는 호출자는 로컬 쓰기 경로를 `pipeline.task_harness_journal`에 명시해야 하며, 누락 시 모델 실행 전에 거부한다. 모델 미사용 조회는 원문 채택·모델 호출·실행 DB 기록을 하지 않는다.

원문·좌표·해시·용어/참조 색인 계약은 변경하지 않는다. 외부 Query/Result는 `term-runtime-v1` 그대로이고 `retrieval.term_agent`에 내부 task_spec/task_state/reviews가 추가된다. 기존 답변·피드백 소비자는 계속 동작한다. 새 구현 코드와 기존 배선 파일은 작업 트리 엔진 manifest 해시에 포함했다. 릴리스 준비 과정에서도 정책과 용어 묶음을 검사한다.

## 검증과 한계

```bash
.venv/bin/python -m pytest -q \
  05_TESTS/CONTRACTS/test_task_harness.py \
  05_TESTS/CONTRACTS/test_task_harness_wiring.py \
  05_TESTS/CONTRACTS/test_navigation_loop.py \
  05_TESTS/CONTRACTS/test_navigation_main_wiring.py \
  05_TESTS/CONTRACTS/test_term_agent_main_wiring.py
```

고정 모의 provider로 계약·회귀를 검사한다. 새 하네스의 HTTP 검사는 가상 원문·용어 묶음 생성 → 실제 색인/조회 도구 → 근거 검토 → 답변 → 피드백 → DB 기록을 연결한다. 기존 RAG 검사는 기존 선택 세대를 읽기 전용으로 사용한다. 외부 모델 호출·질문 품질 비교가 아니므로 새 ADR 실험으로 처리하지 않는다.

- 의미 span의 정확한 원문 위치는 검사하지만, 의미 단위의 적절성·개념 해석·근거 함의의 실제 정확도는 모델 품질 평가가 필요하다. 별도 의미 검토도 같은 provider의 모델 판단이며 독립 사람 검토나 법률 정답 인증이 아니다.
- 필수 참조와 예외의 의미적 충분성은 모델 검토에 의존한다. 전체 관련 법령을 빠짐없이 검토했다는 보장은 없다.
- 검토 실패·잘못된 제안의 요청 내 복구와 중간 상태 저장까지 구현했다. 프로세스 재시작 후 자동 재개, 사용자 후속 답변의 resume API, 권한 변경 재검사는 미구현이다.
- 사용자/조직별 ACL은 기존 문서 범위 필터와 별도 과제다. 외부 작업 실행·중복 방지·실제 결과 확인은 첫 구현에 포함하지 않았다.
- 승인된 운영 정책 게시·새 하네스 활성화·GENOS 내부 모델 검증은 하지 않았다. 공개 원문/Gemini 단회 probe는 위 ADR-0438에 있으며 첫 구현의 실패를 확인했다. 운영 품질·비용 개선은 입증되지 않았다.

후속 실제 비교는 실험 표준의 reservation/ADR 동결 및 Gemini 기본 모델 정책을 따르고, 실제 내부 데이터·내부 모델 평가는 GENOS에서 수행한다. 검증한 후보의 운영 반영은 별도 릴리스/MAIN 절차를 따른다. 이전 릴리스와 그 정책 DB를 함께 보존하면 기존 명시적 롤백 경로를 유지할 수 있다.
