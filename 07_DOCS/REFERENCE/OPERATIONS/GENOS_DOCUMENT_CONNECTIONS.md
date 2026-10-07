# GENOS 추가 문서와 전체 용어 연결

현재 작업 코드의 계약이다. GENOS 현장 설치·내부 모델 실행·품질 검증은 아직 미확인이다.
로컬 활성 릴리스 `navigation-rag-20260916-v1`과 그 불변 코드·데이터는 이번 변경으로 교체하지 않는다.

## 책임과 실행 흐름

```text
A 내부·외부 RAW 전체 → 파싱·PDF 구조 복원 → STRUCTURE/source.sqlite
  → B 전체 완료 확인 → 명시한 기존 세대 + 이번 구조화 원문 통합
  → C 기존 사전의 미검토 후보 유지 + 문서의 새로운 명시 정의 후보 추가
  → D 동일 근거의 완료 검토 재사용 → 나머지 후보를 하나의 GENOS 계획으로 검토
  → E 검토된 사전으로 통합 원문 전체의 표기·별칭·번역·정의·결정론 참조 연결
  → 선택: 같은 baseline에 결속된 명시 참조 observation을 검토·승인
  → F 승인 overlay를 적용한 navigation-v4·사전·지식 묶음·캐시를 하나의 서빙 후보로 검증
  → 별도 명시 활성화 → GENOS 프로세스 재시작·현장 확인
```

시스템은 표기 매칭·좌표·원문 해시·공식 관계·명시 참조·충돌·버전·재개·인용 검증을 처리한다.
LLM/VLM은 PDF 구조 검수, 정의 쌍의 의미·관계 판단, 질의 시 탐색 방향·근거 채택·답변을 담당한다.
문서별 연결·색인에는 모델 호출이 없다. LLM이 정의의 법적 적용 범위를 자동 승인하지 않는다.
명시 참조 모델 observation도 자동 연결하지 않으며, 완료된 운영자 검토 state를 명시한 구축에서만 반영한다.

## 반입과 입력

- 코드 교체 ZIP과 공개 용어 데이터 묶음은 별도다. 코드만 설치해도 사전이 생기는 것은 아니다.
- 코드의 `00_SYSTEM/GLOSSARY_PIPELINE.json`이 지정한 기본 사전과 전체 knowledge bundle을 같은 해시로 반입한다.
- 실제 내부 문서는 GENOS의 논리 data root 아래 `RAW/internal`에 둔다. 내부 원문·정의·모델 결과는 외부로 반출하지 않는다.
- 기존 서빙 문서를 유지하려면 `--base-generation`을 반드시 명시한다. 여러 번 지정할 수 있다. CURRENT나 날짜순 최신 폴더를 자동 발견하지 않는다.
- 입력 파일·사전·코드가 바뀌면 새 run ID를 사용한다. 문서 버전 ID가 같고 원문이 다르면 실패한다. 기존 버전은 `--exclude-document <정확한 기존 ID>`로 명시 제외하고 새 버전 ID를 추가한다.
- 전처리기·VLM·내부 LLM 설정과 Python 의존성은 [구축 가이드](GENOS_FOUR_STAGE.md), [전처리기 계약](GENOS_PREPROCESSOR_PARSING.md), `.env.genos.example`을 따른다. 임베딩은 이 경로의 필수 단계가 아니다.

## 구축과 재개

각 단계를 따로 실행하거나 일부 구조화 실패를 보류한 채 성공분부터 처리하려면
[단계별 실행](GENOS_RELEASE_STAGES.md)을 따른다. `document-release select`로 새 실행 범위와
제외 감사 기록을 고정한 뒤 `merge` → `prepare` → `review` → `index` → `verify`로 이어간다.
원래 전체 구조화 실행을 성공으로 바꾸지 않으며, `build-all`의 전체 완료 검사는 유지한다.

GENOS 코드스페이스에서 실행한다. 다음 경로는 현장에 반입한 실제 절대 경로로 바꾼다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-all \
  --run-id additions-001 \
  --base-generation /현장/data/기존세대 \
  --max-review-jobs 100 --execute
```

명시 참조 검토를 반영할 때만 같은 결정론 baseline에 결속된 완료 state를 추가한다. 미완료 state는
`REFERENCE_REVIEW_PENDING`으로 중단되고, 옵션을 생략하면 모델 호출 없이 결정론 참조만 포함한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py build-all \
  --run-id additions-001-reviewed \
  --base-generation /현장/data/기존세대 \
  --reference-review-state /현장/data/REFERENCE_REVIEWS/review-001 \
  --max-review-jobs 100 --execute
```

state 준비·모델 관측·운영자 검토 절차는 [명시 참조 해소 운영 계약](REFERENCE_RESOLUTION.md)을 따른다.
state의 parent generation과 이 release가 재현한 baseline의 manifest/navigation 해시가 다르면 적용은 실패한다.

다음 추가 구축에서 이전 검토를 재사용하려면 `--glossary-dir /현장/논리data/TERM_RELEASES/<이전run>/glossary-reviewed`를 함께 지정한다. 완료 영수증·검토 DB 해시를 확인한 뒤 완료 관측을 보존하며, 근거·후보·검토 계약이 같은 작업만 재사용한다. 미검토·근거 변경·새 정의 후보는 통합 검토한다. 이전 release의 검토 디렉터리도 보존한다.

같은 명령으로 재개한다. 통합 용어 검토가 미완료이면 exit 3이다.
실패 작업을 다시 호출하려면 `--retry-review-failed`를 추가한다. 완료 검토는 재호출하지 않는다.
기존 검토의 구현/모델 결속이 달라졌으면 옛 계획을 덮어쓰지 말고 새 상태 경로를 설정한다.

이미 전체 문서 구조화가 끝났다면 아래 후속 단위를 직접 실행할 수 있다.

```bash
# 모델 호출 없이 기존/신규 후보의 통합 검토 계획 준비
.venv/bin/python -B 06_TOOLS/pipeline.py document-release prepare \
  --run-id additions-001 --base-generation /현장/data/기존세대

# GENOS 내부 모델로 제한 검토 후 통합 서빙 후보 생성
.venv/bin/python -B 06_TOOLS/pipeline.py document-release build \
  --run-id additions-001 --base-generation /현장/data/기존세대 --max-review-jobs 100

.venv/bin/python -B 06_TOOLS/pipeline.py document-release verify \
  --release /현장/논리data/TERM_RELEASES/additions-001
```

직접 실행 시에도 같은 `--glossary-dir`을 명시하면 사전 선택을 고정할 수 있다.
구조화 선택 기록에 완료·전체 문서 목록이 없는 과거 실행은 먼저 structure를 재개해 새 영수증을 만든다.
`prepare`도 계획 파일을 작성한다. 읽기 전용 명령은 `verify`다.

## 산출물과 소비자

| 위치: 논리 data root 아래 | 내용·소비자 |
|---|---|
| `LOGS/<run>/structure-selection.json` | 전체 구조화 완료·문서 목록·영수증 해시; 통합 입력 선택 |
| `TERM/<run>/<document>` | 단독 `build-data-stages --stage index/all`의 개별 DRAFT; build-all 선행 단계 아님 |
| `TERM_RELEASES/<run>/plan.json` | 기존 세대·구조화 영수증·사전 결속 |
| `sources/selection.json`, `sources/store.sqlite` | 명시 입력·제외·중복 처리와 통합 원문 |
| `glossary-draft` | 기존 미검토 후보·완료 관측 + 새 정의 후보를 보존한 통합 초안 |
| `review` | 기존 GENOS 검토 계약의 작업·입력·호출·실패·완료 영수증 |
| `glossary-reviewed` | 검토 결과를 관측으로 보존한 새 사전 |
| `serving/generation` | 원문, navigation-v4, `glossary/bundle`, 사전, 캐시; 승인 reference state가 있으면 overlay 포함; RAG 소비 |
| `release.json` | 검토 상태·산출물 해시·DRAFT 완료. 품질 인증/활성화와 구분 |

기존 미검토 후보를 유지하고 새로운 정의 위치를 후보로 추가한다. 완료 검토는 사전 전체 해시를 제외한 입력 근거가 같을 때만 재사용하며 `reused_job` 원장에 부모 작업 ID를 기록한다. 같은 표기끼리 비교하며, 정의 없는 후보는 deferred,
새 표제어에 비교 대상이 없으면 UNLINKED_REVIEW로 남는다. 기존 정의의 의미를 덮어쓰거나 임의의
동의어를 생성하지 않는다. `SAME`/관계 관측은 근거·sense ID·범위 키를 가진 탐색 간선이며 정본 병합은 없다.
충돌·UNKNOWN은 확정 관계로 내보내지 않는다. 문서별 정의와 그 관계는 요청 문서 범위를 지킨다.
전체 미등록 일반어 추출이나 모든 문서 쌍의 의미 비교는 수행하지 않는다.

검토가 terminal 상태에 도달해도 실패·근거 부족·미확인이 남으면 `review_status=PARTIAL`이다.
이는 검토 절차 종료이며 의미 정확도 인증이 아니다. `quality_certified=false`를 유지한다.

## 명시 문서 참조

선택 원문들의 문서명과 조문 좌표를 대조한다. `「문서명」 제N조`와 명확한 등록 문서명 뒤의
조문은 유일한 문서 버전·대상이 있을 때만 연결한다. 같은 문서·부모·역할 축에 양 끝과 중간 좌표가
실제로 존재하는 단순 조·항·호 범위는 규칙으로 확장한다. 같은 이름의 복수 버전, 없는 문서/조문,
약칭·직전 문맥·복수 후보는 폐쇄 후보 observation으로만 남기고 운영자 승인 전에는 연결하지 않는다.
날짜로 최신 버전을 추정하지 않는다. 문서 간 이동도 질의에서 허용한 문서 범위 안에서만 가능하다.

## 활성화·롤백

구축은 CURRENT를 변경하지 않는다. 코드·후보 데이터를 GENOS 코드서빙이 읽을 수 있는 영속
경로에 준비하고 `verify`를 통과한 뒤, 해당 GENOS data root에서 명시 활성화한다.
현재 포인터가 있으면 `sha256sum /현장/data/generations/CURRENT.json`으로 해시를 확인하고,
없으면 `absent`를 사용한다. activation은 포인터 해시가 달라지면 실패한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py document-release activate \
  --release /현장/data/TERM_RELEASES/additions-001 \
  --active-data-root /현장/data \
  --expected-current <확인한_CURRENT_SHA256_또는_absent> --confirm-main

.venv/bin/python -B 06_TOOLS/pipeline.py document-release rollback \
  --receipt /현장/data/generations/receipts/<활성화_영수증>.json \
  --active-data-root /현장/data \
  --expected-current <현재_CURRENT_SHA256> --confirm-main
```

release 후보는 active data root 아래 있어야 한다. 영수증은 이전 포인터와 새 포인터를 보존한다.
첫 활성화를 롤백하면 포인터가 없던 상태로 복구한다. 기존 세대 파일은 삭제하지 않는다.
`GENOS_GENERATION`이 설정되어 있으면 CURRENT보다 우선하므로, CURRENT 방식으로 운영할 때는
그 명시 설정을 해제한다. `GENOS_DATA_ROOT`는 위 활성화 root, `SEMANTIC_LLM_BACKEND=genos`는
내부 모델로 설정하고 해당 서빙 프로세스를 재시작한다. 코드 리비전 배포는 플랫폼에서 별도 실행한다.

현장에서 실제 선택 generation ID, 추가 내규·기존 외규의 동시 조회, 명시 참조, 내부 모델 호출,
근거 인용, 재시작 후 파일 보존, 롤백을 확인한다. 로컬 모의 테스트 성공을 현장 성공으로 보고하지 않는다.

## 로컬 검증

`05_TESTS/CONTRACTS/test_document_release.py`는 합성 원문과 고정 내부-provider 응답으로
전체 연결 v4·번역 표기·새 정의 검토/재개·UNKNOWN 보존·문서 범위·모호 참조·버전 충돌·해시 변조·
기존 미검토 후보 보존·완료 근거 재사용/변경 재검토·실제 XML 구조화부터 통합 서빙까지·HTTP 답변/피드백·활성화 CAS/롤백을 검증한다.
법률 답변 품질 비교 실험이나 실제 GENOS 모델 호출은 아니다.

기존 `PIPELINE_PUBLISH` API는 별도 common 구조화 저장 경로의 source-only 게시다. 같은 생성기·서빙 자원 포장을 사용하지만 `build-all`의 완료 결과를 선택하는 명령이나 새 정의·명시 참조 검토의 대체 경로는 아니다. 신규 추가 구축은 위 통합 명령을 사용한다.

## 이전 실행에서 이행

기존 병렬 구축 결과·완료 세대·검토 원장·배포 ZIP은 보존한다. 새 순서에는 새 run ID를 사용한다.
이미 구조화한 문서는 같은 파서 지문의 캐시를 재사용할 수 있다. 완료 사전을 재사용하려면
`--glossary-dir`과 유지할 원문의 `--base-generation`을 각각 명시한다. 최종 사전이 바뀌므로
전체 연결·색인·서빙 캐시는 새 세대로 생성한다. 현행 활성 포인터는 별도 활성화 전까지 유지된다.

통합 실행은 `TERM_RELEASES/<run>/review`에 계획을 생성한다. 과거 별도 검토 계획 ZIP을
이 경로에 복사하지 않는다. `glossary review` 단독 명령의 새 기본 상태는
`LEXICON/glossary-v1/reviews/boundary-20260914-v3-structure-first-20260916`이며,
이전 상태와 출력은 덮어쓰지 않는다. `build-all --check-only`는 입력 목록·지식 묶음을
검사하며 아직 없는 구조화 결과에 대한 통합 검토 계획을 만들지 않는다.
