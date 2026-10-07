# legal_llm_wiki — 이유와 연결 해제 이력을 갖는 조사 경험

2026-10-01 사용자 요청으로 기존 action-memory의 LLM 개념화 결과를
`raw/` 불변층과 `wiki/` 개념층으로 저장한다. 서로 다른 질문도 같은 조사 목적에
연결할 수 있지만, 잘못 묶인 경험은 이유를 남겨 개념과의 연결만 끊는다.
개념 자체가 잘못되면 개념 전체를 중단할 수도 있다. 원래 질문·원문·선택 이유와
이전 연결 기록은 보존한다.

## 단계·실행·소비자

담당 단계는 MAIN의 피드백 후처리·조사 경험 구축이다.

```text
완료된 native journal
 → 기존 action-memory build의 반출 승인 확인·LLM 목적 개념화
 → memory.sqlite의 episode / concept / observation
 → legal_llm_wiki.export_wiki
 → raw/experiences + raw/snapshots + wiki/investigation + index + log
```

`pipeline.py action-memory build` 종료 시 같은 build.lock 안에서 자동 갱신한다.
모델 미준비 시에도 이미 저장된 경험을 로컬 projection으로 갱신한다. 야간 시간
밖에서 건너뛴 호출은 위키도 갱신하지 않는다. `wiki-export`로 명시 재구축할 수 있다.
별도의 수집기·모델 호출·온라인 라우터를 추가하지 않았다.

소비자는 사람이 읽는 개념 페이지와 기존 Memory.catalogue/compile이다.
후자는 연결 중단 상태만 반영한다. **온라인 활성 RAG에 위키 내용 전달이나
새 질문의 의미 매칭은 미연결이다.** 현재 로컬 활성 포인터 generation 37,
frozen 서빙 코드·원문 세대는 이번 작업에서 변경하지 않는다.

## 저장 계약

workspace의 `runtime` root 아래 `semantic/action-memory/legal_llm_wiki/`에 저장한다.
기존 법령 해석 위키인 `01_DATA/wiki/`와 조사 경험을 섞지 않는다.

| 경로/테이블 | 내용 |
|---|---|
| `raw/experiences/<ID해시>-<revision해시>.md` | 기존 episode JSON 그대로. 같은 revision의 파일 내용이 달라지면 갱신 거부 |
| `raw/snapshots/<snapshot해시>.json` | 경험·관계·개념·중단 상태·DB 이벤트의 불변 snapshot |
| `wiki/investigation/<개념ID해시>.md` | 정의·질문·조사 이유·선택 이유·개념 연결 이유·세대·원문 좌표·해시·중단 이유 |
| `wiki/index.md` / `wiki/log.md` | 개념별 상태·유효 연결 수 / 새 snapshot 생성 시 append. 단순 재실행은 Updated 보존 |
| `manifest.json` | 현재 projection 무결성·snapshot ID·온라인 미연결/정답 미인증 표시 |
| `abstraction_state` | 같은 memory.sqlite의 v1 호환 overlay. concept/observation별 DISPUTED 또는 RETRACTED, 이유·처리자·시각 |

LLM 의미 판단은 기존 CONCEPT_SYSTEM/concept_schema를 쓴다. 위키 생성은 그 결과와
근거를 결정론으로 렌더링하며 새로운 의미를 만들어 내지 않는다. 개념 페이지의
EXPERIENCE_ONLY와 관계의 ACTIVE는 법적 정답 검증이 아니다. 판단 자체의 재사용에는
원문·적용 조건·예외·정확성 검증과 온라인 소비 계약이 별도로 필요하다.

디렉터리 0700·산출물 0600으로 저장한다. WAITING_AUTH 경험도 로컬 보관만 하며
외부 모델로 전송하지 않는다. 위키 projection은 반출 승인을 확장하지 않는다.
기존 야간 모델 정책과 매 배치 반출 검사는 유지한다.

## 실행과 연결 해제

WSL 저장소에서 기존 진입점을 사용한다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py action-memory wiki-export
.venv/bin/python 06_TOOLS/pipeline.py action-memory wiki-status
.venv/bin/python 06_TOOLS/pipeline.py action-memory wiki-check

.venv/bin/python 06_TOOLS/pipeline.py action-memory wiki-unlink \
  --observation-id OBSERVATION_ID --reason '조사 목적이 다름' --reviewer REVIEWER

# 한 질문 경험의 여러 원문 연결을 원자적으로 해제
.venv/bin/python 06_TOOLS/pipeline.py action-memory wiki-unlink \
  --concept-id CONCEPT_ID --episode-id EPISODE_ID \
  --reason '서로 다른 의사결정 목적을 잘못 묶음' --reviewer REVIEWER

.venv/bin/python 06_TOOLS/pipeline.py action-memory wiki-retire \
  --concept-id CONCEPT_ID --reason '개념을 과도하게 일반화함' --reviewer REVIEWER
```

이견으로 일시 중단하려면 `--abstraction-status DISPUTED`를 쓴다. 두 상태 모두
catalogue/compile에서 제외되며, 제외 관계를 끊으면 원문 접근은 기존 scope로 돌아간다.
이유·처리자 없는 중단은 거부한다. 중단 전 snapshot, DB 사건, 중단 후 snapshot을 남긴다.

동일 경험을 재수집하거나 모델이 같은 관계를 다시 제안해도 overlay가 우선한다.
RETRACTED를 DISPUTED로 낮출 수 없다. 재연결하려면 검토한 새 개념/관계 identity가
필요하다. 자동 restore는 없다. 원문 세대가 바뀌면 이전 data_key 관계를 compile하지 않는다.

Markdown은 DB projection이다. 직접 페이지 수정은 연결 상태·정답 승인으로 반영되지
않는다. wiki-check는 현재 manifest의 파일 무결성만 검사하고 의미적 정확성이나
모든 과거 snapshot의 무결성을 인증하지 않는다. 재생성 시 가변 페이지는 DB에 맞추며
raw 변조는 덮어쓰지 않는다.

## 검증·재개·복구

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -B -m pytest -q \
  05_TESTS/CONTRACTS/test_legal_llm_wiki.py
```

모의 경험으로 해제 후 재수집·재개념화, 개념 중단과 다른 개념 보존, 제외 중단 시
원문 접근 복구, 세대 변경, raw 불변성, 구 v1 읽기 전용 호환, 그룹 해제 원자성을
확인한다. 실제 DB export/check는 연결 확인이며 모델 품질·성능 비교 실험이 아니다.

실패한 projection은 wiki-export로 재개한다. 완료 raw와 snapshot은 보존한다.
코드 복구는 해당 작업 변경을 되돌릴 수 있지만 중단 overlay를 모르는 옛 consumer를
다시 쓰면 해제한 관계가 적용될 수 있다. 온라인 연결 전에는 중단 상태를 포함한
소비자 계약을 검증해야 한다. DB backup 복원으로 감사 이력을 지우는 방식을 일반적인
관계 재연결에 쓰지 않는다. 모델 개념화 정확성 평가·MAIN 서빙 승격·GENOS 배포는 별도다.
