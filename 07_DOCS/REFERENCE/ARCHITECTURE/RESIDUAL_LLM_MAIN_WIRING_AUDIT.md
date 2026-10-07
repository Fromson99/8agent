# 잔여 LLM 작성과 MAIN 배선 감사

2026-09-11 · ADR-0365 · 현재 MAIN generation 11 유지

잔여 작성 모드를 연구 후보로 구현했다. 코드가 확정할 수 있는 원문 좌표·근거 객체·명시 법령명/조문 위치는 코드가 처리하고, 모델은 의미 유형·조건·효과·단서 귀속·미해결 판단을 작성한다. **15개 계약 테스트와 통합 ZIP→용어 조회→작성→검토→SQLite 저장·재개 검증을 통과했다.**

159문서의 작성 가능 51,293개 구간을 같은 조건으로 재구성했을 때, 추출 요청 JSON은 1,794,006,670 → 1,027,629,146 bytes로 **42.72% 감소**했다. 이는 직렬화 바이트 측정이며 토큰·실모델 속도 측정이 아니다. 추출 1회+독립 검토 1회의 호출 수는 유지한다. GENOS 모델 목록 연결이 사내 주소에서 시간 초과되어 실제 추론은 실행되지 않았다. 법률 의미 품질 비열등성도 아직 검증되지 않았다.

## 1. 코드와 모델의 경계

| 작업 | 처리 주체 | 경계 |
|---|---|---|
| XML 조/항/호, 비XML 등록 파서 구조 | 기존 코드 | 형식별 입구 이후 같은 작성 큐 |
| 용어집에서 표제어 출현 찾기 | 기존 DictionaryHints | 의미 유형·정의 효력 확정 아님 |
| 근거 span, 좌표, 원문 인용, Evidence 객체 복원 | 코드 | 모델은 제공된 근거 ID를 선택 |
| 명시 인용 법령명+조문 번호 | 잔여 후보의 ReferenceIndex | 수집 법령명 정규화 후 유일한 본문 조문 위치만 해소 |
| 명시적으로 선언된 약칭 | 코드 | 선언 이후, 블록 숫자 순서, 부칙 범위 구분 |
| 항/호 세부 좌표, 모호한 법령/조문, 누락 대상 | 미해결로 모델에 전달 | 없는 위치나 외부 의미 entity를 만들지 않음 |
| Concept/Mention 의미, Clause 역할 | LLM | schema 유지 |
| Rule 조건·효과, Proviso 귀속 | LLM | 원문과 독립 검토 유지 |
| 위임·준용·예외 등 의미 관계 | LLM | 위치 매칭만으로 규범 효과를 확정하지 않음 |
| admission/품질 승인 | 별도 절차 | 모델 리뷰 통과는 DRAFT |

압축 응답 스키마는 SSOT에서 파생한다. `evidence`와 `crosswalk`의 기계적 출력을 제외하고 Concept·Mention·Clause·Rule·Proviso·Relation의 의미 스키마와 필수 배열은 유지한다. 중첩 role binding의 근거까지 복원하고 알 수 없는 근거 ID는 검토·임베딩 전에 거부한다.

추출 입력에서는 catalogue의 중복 원문 quote와 불필요한 geometry/해시 메타데이터를 덜어낸다. 해당 작성 구간의 원문 문자·오프셋·구조 제목·단서 표지는 유지하며, 독립 리뷰는 기존 원문과 복원한 전체 graph를 받는다. 기존 1,500자 분할 자체는 그대로이므로 **분할 경계를 넘는 문맥 문제가 해결됐다는 뜻은 아니다.**

## 2. 계측 결과와 분모

| 항목 | 결과 |
|---|---:|
| 현재 원문 문서 | 159 |
| 원문 블록 | 308,795 |
| 원문 문자 | 18,508,408 |
| 구조 미배정 블록/문자 | 56 / 2,218 |
| 작성 구간 수 | 51,293 |
| 계측한 구간 수 | 51,293 |
| 각 arm에 보존된 작성 원문 문자 | 18,506,190 |
| single 추출 요청 bytes | 1,794,006,670 |
| residual 추출 요청 bytes | 1,027,629,146 |
| 추출 요청 감소율 | 42.7188% |
| 실제 모델 추론 | 0회 |

구조 미배정 56블록은 원문 DB에 남아 있다. 분모에서 숨기거나 임의 조문 ID를 생성하지 않았다. 해당 15문서를 현 작성기로 그대로 다시 작성하면 구조 배정 오류를 먼저 해결해야 한다. 나머지 작성 가능한 모든 구간의 bytes를 비교했다. 양쪽 모두 용어집을 주입하지 않은 동일 source accounting이며 실제 제공자 payload의 토큰 수를 추정하지 않았다.

명시 참조 스캔은 30,538건이다. 위치 해소 3,545건, 법령 없음 8,010건, 본문 조문 없음 5,401건, 항/호 세부 좌표 미검증 13,582건이다. 이 수치는 **정확도 평가가 아닌 코드 처리 상태**다. 인용이 분할 경계를 가로지르면 그 구간에 불완전 앵커를 붙이지 않는다.

이 위치 앵커는 작성 입력과 큐에 보존한다. 이번 후보가 이 3,545건을 현재 MAIN의 RAG relation으로 자동 적재한 것은 아니다. 위치 기반 탐색과 검토된 의미 관계 적재는 별도로 확인해야 한다.

동일 합성 graph를 복원하는 계약 사례는 추출 요청 28,369 → 15,434 bytes, 모델 응답 6,246 → 6,033 bytes였다. 이 가짜 응답을 실제 모델의 출력 길이 예측으로 사용하지 않는다. 리뷰와 생성 의미 작업이 남으므로 호출 수 병목은 별도로 남아 있다.

원장: [전수 계측](../../../09_ARTIFACTS/STAGING/ADR-0365/run-002-final/summary.json), [구간별 hash/bytes](../../../09_ARTIFACTS/STAGING/ADR-0365/run-002-final/slices.jsonl), [15개 테스트](../../../09_ARTIFACTS/STAGING/ADR-0365/run-001-attempt-005/test.log), [GENOS 연결 결과](../../../09_ARTIFACTS/STAGING/ADR-0365/run-003/discovery-network.json).

## 3. 실제 MAIN 선택 경로

1. `06_TOOLS/serve.sh` → 루트 `service.py:application()`.
2. `GENOS_GENERATION`이 있으면 해당 절대 경로를 사용한다.
3. 그 외 `GENOS_DATA_ROOT/generations/CURRENT.json`이 있으면 해당 세대를 사용한다.
4. 그 외 `01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`이 지정한 로컬 릴리스를 사용한다.

현재 로컬 포인터는 `semantic-moleg-rag-20260911-v1`, generation 11이다. 앱·검색·저장 코드는 `08_DEPLOYMENT/RELEASES/semantic-moleg-rag-20260911-v1/code`의 고정 사본을 별도 Python 패키지로 읽는다. **루트 service.py의 관측 코드와 주입 provider는 작업 트리 코드다.** 따라서 MAIN의 모든 실행 코드가 이 릴리스 사본으로만 고정돼 있다고 보면 안 된다.

고정 release manifest·포함 파일·generation manifest·store·용어 연결 DB·로컬 vector artifact 해시는 확인했다. 작업 트리 엔진 지문과 비교하면 `app.py`, `provider.py`, `storage.py`는 다르고, `genos_backend.py`, `genos_index.py`는 로컬 릴리스 파일 목록에 없다. 이것이 기존 workspace 검사에서 드러난 5개 runtime 경로 불일치다. 릴리스 파일 자체의 해시 손상과 구분한다.

LLM 선택은 실행 위치 라우터와 별개로 `SEMANTIC_LLM_BACKEND=anthropic|genos`다. 설정이 부족한 GENOS 답변 경로는 source-only로 동작하도록 되어 있다. 이번 조사로 외부 GENOS 배포 프로세스의 환경변수까지 확인한 것은 아니다.

## 4. 현재 RAG 연결

질문 → query plan → 원문 BM25 / 의미 FTS / 구조 좌표 / 선택적 vector / 공식 용어 회수 → 후보 ID 선택 → DB 원문 재조회 및 의미 관계 확장 → 인용을 포함한 답변이다. 사용자 질문 단계의 선택·답변 LLM은 데이터 생성 단계의 작성 LLM과 별도다.

현재 SQLite에는 159문서, 구조 unit 230,417개, 의미 entity 7,631개, relation 375개가 있다. 로컬 MAIN은 `vectors.npz`, 새 GENOS 생성기는 기존 `genos-sqlite-v1` vectors를 사용한다. 외부 vector DB로 전환하지 않았다.

공식 용어 연결은 label 12개, edge 7개, hit 112개, unresolved 기록 72개다. 법제처 일상용어 출발점은 **계약취소·환불·반품 3개**다. 수집 용어집 437,778개와 이 연결 수를 혼동하면 안 된다. 112개 hit도 112개의 법령 간 의미 관계라는 뜻이 아니다.

조문 확장은 실제 저장된 Rule·정의·Proviso·LegalRelation과 template의 허용 순회에 따른다. 명시 법령명 위치 매칭만으로 위임·예외·준용 의미를 만들어 전체 조문을 따라가는 것은 아니다. XML에 등장한 참조가 모두 현재 MAIN의 의미 relation으로 적재됐다는 근거는 없다.

## 5. 미연결·고아·보존 대상을 구분한 결과

| 대상 | 확인 결과 | 처리 판단 |
|---|---|---|
| 원문 블록 56개 / 15문서 | `source_unit` 연결 없음, 2,218자 | 원본 보존 후 등록 파서/첨부·머리말 배정 규칙에서 고칠 대상 |
| `legal-authoring` registry | extract/admit/index 엔진 null, MIGRATION_REQUIRED | 별도 GENOS CLI와 범용 엔진 배선을 구분해 등록 필요 |
| glossary alignment | SQLite와 CLI 존재, UI 시작 버튼 not_connected | 자동 RAG 반영으로 간주하지 않음 |
| ADR-0360 전처리 | 연구 격리 | 현재 single 기본 경로와 별도 |
| ADR-0365 residual | 연구 후보, 통합 계약 통과 | 내부 모델 의미 품질 확인 전 자동 MAIN 승격 제외 |
| 구 `legalclosure-v2` / `ontology-rag-v1` registry | 현 서비스 진입 경로가 아님 | 구 인터페이스·재현 기록으로 분리 |
| 정적 고아 후보 9파일 | 조사 범위의 코드 호출자 없음 | 외부 사용 가능성 때문에 자동 삭제하지 않음 |
| 보존 도구 사본 3,776개 | 과거 GENERATIONS | 9개 고아 후보에 포함하지 않음 |
| data descriptor 36개 중 미선택 35개 | 현 MAIN에서 직접 선택되지 않음 | 패키지/출처로 간접 참조할 수 있어 고아로 단정하지 않음 |

정적 조사 대상 Python은 4,388개(현재 경로 612개+도구 보존 사본 3,776개), shell 161개, data descriptor 36개, ADR manifest 202개다. 모든 `.py` 파일의 호출자 부재를 곧바로 미사용으로 판정하지 않았다. `structure.registry`의 동적 package discovery로 불러오는 proposer/guard들은 실제 연결에 포함했다. `run_tool.py`도 allowlist와 migration receipt를 따라 `06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS`를 고른다.

9개 정적 후보는 `agents/agent6/src/transcript.py`, 구 `api/structure_app.py`, `datasets/cutover.py`, `datasets/sync.py`, 현재 `COMMANDS/workspace_paths.py`, 보고서용 `arch_diagrams.py`, `rag_diagrams.py`, `law_annex_vlm_report.py`, `recipe_loop_report.py`다. 경로·해시·호출자 근거는 [고아 목록](../../../09_ARTIFACTS/STAGING/ADR-0365/network-v2/orphan-candidates.csv)과 [전체 파일/간선](../../../09_ARTIFACTS/STAGING/ADR-0365/network-v2/module-network.json)에 있다.

DB의 부모 없는 unit, entity 없는 entity_source, source block 없는 entity_source, source entity 없는 relation, 존재하지 않는 non-null target을 가진 relation은 각각 0건이었다. [무결성 결과와 56블록 원문](../../../09_ARTIFACTS/STAGING/ADR-0365/network-v2/data-integrity.json)을 보존했다.

## 6. 재현과 다음 적용 순서

연구 후보는 이 작업 트리에서 다음 단일 shell로 실행할 수 있다. 실제 GENOS 기본 배포 번들에 포함된 명령은 아니다. 기본 운영 명령 `06_TOOLS/genos_pipeline.sh`의 single 동작과 MAIN은 이번에 바꾸지 않았다.

```bash
bash 04_EXPERIMENTS/ADR/ADR-0365-residual-authoring-wiring-audit/artifacts/residual_pipeline.sh \
  --knowledge-zip /mounted/genos-glossary.zip \
  --data-root /mounted/GENOS_DATA \
  --run-id residual-check \
  --input-root /mounted/legal-xml \
  --source external --check-only
```

GENOS 내부에서 준비된 입력을 작성하려면 `--check-only`를 `--execute --model-revision <실제 배포 리비전> --max-calls 4 --max-attempts 2 --timeout 120`으로 바꾼다. 작은 검증 입력부터 시작하고 새 run-id를 사용한다. `--publish`는 생성 후 GENOS CURRENT를 선택하는 별도 옵션이다. 4회 call budget은 전체 말뭉치 완료 예산이 아니다.

다음 작업 우선순위는 ① 56블록 구조 배정 ② 내부 GENOS에서 조건/단서/참조 품질과 토큰·지연 비교 ③ 범용 작성 레지스트리 정리 ④ 관계 API 출발점 확대다. 용어집 전체 목록을 다시 수집하는 것보다 **어떤 용어에 관계 패키지가 아직 없는지**를 기준으로 수집해야 한다. 이 문서는 조사·후보 구현 결과이며 위 작업을 완료했다고 보고하지 않는다.

과거 ADR 계보 검사의 `ADR-0305` run purpose 오류와 누락된 `ADR-0158-experiment-v1/v2-candidate` parent edge는 기존 기록의 문제다. 이번 ADR의 실험 기록과 분리하고 완료된 과거 manifest를 고치지 않았다.

실험 정본: [ADR-0365](../../../04_EXPERIMENTS/ADR/ADR-0365-residual-authoring-wiring-audit/README.md).
