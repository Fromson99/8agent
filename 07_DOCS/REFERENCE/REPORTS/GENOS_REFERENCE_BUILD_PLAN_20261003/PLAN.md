# GENOS 참조 연결과 navigation 구축 최적화 계획

2026-10-03. 대상은 완료된 구조화·용어집을 재사용한 연결·색인 구축이다. 기존 실행기에 문서명 검색 개선, 구축 중 저장량 감소, 중단 후 재개를 연결하고 최종 RAG 소비 경로까지 검증한다. 이 문서는 구현 전 계획이며 신규 실험·모델 호출·GENOS 실행·배포를 시작하지 않았다.

우선순위는 **문서명 전체 반복 검색 제거 → 구축 중 본문·근거 저장과 메모리 사용 개선 → 참조 처리 재개 → 동일 입력의 GENOS 구축 및 워크플로우 검증**이다. 현장 완료 시간은 아직 예측하지 않는다.

## 근거와 현재 상태

| ID | 확인한 사실 | 근거와 해석 범위 |
|---|---|---|
| E1 | 현장 navigation 33,384.2초, 전문 색인 시작까지 누적 34,002.4초 | [시간 정정 기록](../../../../09_ARTIFACTS/AUDITS/20261002-navigation-timing-correction/receipt.json). 뒤에서 실패했으므로 성공한 전체 구축 시간이 아니다. |
| E2 | 막바지 화면에 2,121/2,121문서와 navigation_bytes=25666207744 | [보존 사진](../../../../09_ARTIFACTS/AUDITS/20261002-navigation-timing-correction/photo2-timing-crop.png). 약 25.7GB인 구축 중 파일이며 최종 서빙 크기·모든 파일을 합친 피크 용량은 아니다. |
| E3 | 과거 두 실행 위치 캡처의 판독 기록이 legacy 별표 참조의 반복 정규식 컴파일을 가리킴 | 과거 진단 대화와 [재현 조사](../../../../04_EXPERIMENTS/ADR/ADR-0614-annex-reference-index-latency-reproduction/README.md). 이번에 해당 두 원본 이미지를 다시 열지는 못했다. 9시간 전체의 원인별 비중은 미확인이다. 과거 잘못 판독된 시간은 E1을 따른다. |
| E4 | 작업 코드에는 정규식 재사용이 있으나 별표 인용마다 모든 제목을 검사함 | [legacy 참조](../../../../02_BACKEND/semantic_runtime/term_references_legacy.py) `compile_references`의 `annex_title_patterns`. GENOS에 적용됐다는 증거는 별도다. |
| E5 | legacy와 scope-v2 모두 모든 source JSON을 목록으로 적재함. 참조마다 source_text를 저장함 | [legacy](../../../../02_BACKEND/semantic_runtime/term_references_legacy.py), [scope-v2](../../../../02_BACKEND/semantic_runtime/term_references.py)의 `sources`, `record`. 같은 블록에서 여러 인용이 나오면 본문 저장·해시 작업이 반복된다. 실제 크기 기여율은 미측정이다. |
| E6 | compact도 전체 구축 DB를 만든 후 감사 DB로 보존하고 서빙 DB를 투영함 | [compile_index](../../../../02_BACKEND/semantic_runtime/term_index.py), [separate_navigation](../../../../02_BACKEND/semantic_runtime/navigation_storage.py). 최종 서빙 DB 축소만으로 구축 중 용량·작업 감소를 증명할 수 없다. |
| E7 | 용어 출현과 같은 key의 후보를 결합해 ACCEPTED와 HELD 근거를 모두 생성함 | [LinkProjector.finish](../../../../02_BACKEND/semantic_runtime/term_links.py). 동일 표기 후보가 많은 자료에서 결합 행 증가가 가능한 구조다. 현장 주원인으로 확정하지 않는다. |
| E8 | 현재 재개 단위는 links/source/glossary/navigation/fulltext 단계 | [Stages.run](../../../../02_BACKEND/lawrag/pipeline/generation_build_steps.py). 미완성 navigation 내부의 완료 문서·참조 묶음은 재개하지 못한다. |

기존 작은 합성 입력의 7.39→6.16초는 이미 compact를 적용한 로컬 기준과의 비교다. 이 계획의 현장 예상 시간이나 기존 GENOS 대비 개선율로 사용하지 않는다.

## 입력과 실행 경로

기존 `genos_reindex_runner.py build --serving` → `genos_reindex_only.rebuild_serving` → `term_generation.build_generation` → `generation_build_steps.build` 경로를 확장한다. 연결 → 원문 투영 → 용어집·캐시 → navigation → unit FTS → 검증 → NFS 발행 → 워크플로우의 순서를 하나의 실행 명세로 추적한다.

재사용 입력은 명시한 prepared run의 원문 DB·선택 문서 목록·완료 용어집·원천 knowledge bundle이다. 기존 `select_completed_glossary`로 완료 상태와 부모 결속을 확인한다. 완료본을 찾지 못한 경우 미검토 draft로 자동 대체하지 않고 필요한 입력을 명시한다. 파생 index run은 origin의 원래 prepared 입력을 확인한다. 최신 날짜 폴더를 자동 선택하지 않는다.

원문 구조화, 정의 생성, 완료된 의미 검토는 다시 실행하지 않는다. `GENOS_REFERENCE_SCOPE_V2`, 문서 범위, 사전, aliases/delegations, FTS 단위, PeCab 버전과 모델 사용 정책은 비교 중 고정한다. 현재 재사용 실행기는 참조 LLM을 호출하지 않고 이전 LLM 판정을 자동 이식하지 않는다. 실제 목표 세대에 기존 승인 참조 판정이 필요하면 해당 판정의 원문·후보·해시를 검증하는 기존 `reference_resolution` 경로와 새 적용 영수증까지 명세에 포함한다. 속도 비교를 위해 이 단계를 몰래 생략하거나 추가하지 않는다.

## 구현 순서와 완료 조건

### 1 기준 고정과 단계 계측

현재 compact 작업 코드의 정확한 파일 해시를 비교 기준으로 고정한다. 사진의 9시간 기록은 역사적 참고값이다. 당시 코드·입력·설정이 완전히 복원되지 않으면 후보와의 직접 개선율을 계산하지 않는다.

기존 로그에 문서 준비, 제목·약칭 인덱스 준비, 참조 탐색, 참조 기록, 용어 근거 결합, 통계·무결성, 감사 처리, FTS, 해시·게시 시간을 분리한다. 각 단계에 벽시계·CPU 시간, 완료 source/블록 수, 검사한 제목 수, 생성/미해결 참조 수, 근거 행 수, 커밋 횟수, 프로세스 최대 메모리를 남긴다. DB·journal·임시 파일·감사·서빙 파일을 함께 계수한다. 완료된 별도 DB에서 테이블별 페이지 사용량을 조사하고, 실행 중 거대한 COUNT나 본문 덤프는 하지 않는다.

현재 `_BUILD_PROGRESS`, `BuildLog`, `phase`, SQL 타이밍을 확장한다. 새 실행기를 만들지 않는다. 로그의 `.start` 행이 직전 단계 소요 시간을 나타내는 현재 표현은 start/end 쌍 또는 명시적 completed_phase로 분명히 한다. 전체 잔여 시간은 미측정 후속 단계를 포함해 꾸며 내지 않는다.

완료 조건: 동일 실행의 시간·용량·작업량을 단계별로 설명할 수 있고, 계측 자체의 오버헤드를 별도로 확인한다.

### 2 문서명 전체 반복 검색 제거

문서명 끝부분을 찾는 역방향 문자 인덱스를 구축별로 한 번 만든다. 인용 앞 문자열의 끝에서 일치하는 문자 경로만 탐색해 제목 수만큼 정규식을 실행하는 루프를 제거한다. 제안 helper는 `semantic_runtime/reference_name_index.py`이며 아직 존재하지 않는다.

우선 legacy 별표 fallback에 적용한다. 선언 약칭·등록 약칭의 같은 형태 반복은 별도 이름 공간으로 인덱스화하고 legacy와 scope-v2에서 공유한다. 두 compiler의 선택 조건과 해석 규칙은 유지한다. scope-v2로 강제 전환하는 방식으로 속도를 비교하지 않는다.

보존 조건은 따옴표 명시 이름 우선, 문서별 약칭 우선순위, 가장 긴 일치 이름, 기존 왼쪽 경계 `[가-힣A-Za-z0-9]`, Unicode 공백, 제목 내부 공백·특수문자, 전체 경로/끝 제목, 동일 제목의 복수 판본, 미해결 사유, 참조 ID와 span이다. 기존 일반 조문 이름의 80문자 창 정책도 별개로 보존한다. prefix 전체 복사와 같은 블록의 본문 해시·역참조 범위 계산은 원문 위치를 바꾸지 않는 범위에서 재사용한다.

인덱스 준비 비용은 제목의 총 문자량에 비례한다. 조회는 일치 경로와 후행 공백 길이에 비례하도록 설계한다. 임의 제목 잘라내기·후보 상위 몇 개 제한·유사도 검색은 넣지 않는다.

완료 조건: 이름 수만큼 검사하는 호출당 루프 제거, 동일 입력의 참조 다섯 표 전체 논리 행 일치, 대규모 제목·인용 조합에서 현행 캐시 구현 대비 실측 개선. 기존의 재컴파일 제거 전 코드를 유리한 비교 기준으로 사용하지 않는다.

### 3 구축 중 본문과 근거 저장 개선

먼저 E5/E6/E7의 실제 기여량을 나눠 확인한다. `source`의 블록/조 전체 본문 중복, `reference.source_text` 반복, `occurrence_evidence` 결합 수, 인덱스·임시 공간을 각각 측정한다. 용량의 대부분을 차지한 항목부터 처리하되, 같은 대상을 여러 방식으로 중복 측정해 개선율을 합산하지 않는다.

구현 후보는 다음과 같다.

- 참조 compiler의 전체 본문 목록을 문서·제목·좌표 metadata와 제한된 본문 캐시로 분리한다. 대상 좌표·문서 약칭·위임 관계에는 전체 범위가 필요하므로 작고 불변인 전역 카탈로그를 유지하고 본문만 순회해서 읽는다. 원래 결정 순서와 ID 생성은 유지한다.
- 블록별 본문·해시를 한 번 저장하고 참조에는 원문 키와 span을 저장한다. 기존 논리 reference JSON은 필요할 때 동일하게 복원한다. `SELECT * FROM source_block`처럼 호환 view의 큰 JSON을 복원하는 조회는 소비자가 쓰는 열만 선택한다.
- 같은 표기의 출현×후보 결합은 분포를 계측한 뒤 상태·범위 인덱스와 묶음 처리로 최적화한다. ACCEPTED뿐 아니라 HELD와 미해결 근거도 보존한다. 감사 근거를 제거해 빨라진 것으로 평가하지 않는다. 중복 물리 저장을 공통 근거로 묶는 경우 원래의 모든 논리 조합을 복원할 수 있어야 한다.
- 최종 서빙 자료와 감사 근거를 구축 시점부터 분리해 기록하는 새 물리 계약을 도입한다. 현재의 전체 DB 생성 후 서빙 재복사를 줄이는 것이 목적이다. 생성량이 필수 근거 수에 비례하는 부분은 남는다.

중요한 계약 변경: 현재 `audit_policy=exact-completed-index-snapshot`은 분리 전 DB 바이트의 보존을 약속한다. 새 저장 방식은 **새 세대에만 적용하는 버전 계약**으로 정의하고 감사의 완전한 논리 내용·원문·부모 해시를 보존한다. 기존 v1/v2 감사 파일의 바이트 보존 약속을 소급 변경하지 않는다. `term-navigation-storage-v3`와 navigation 후속 버전은 제안 이름이며 현재 허용 enum이 아니다.

`reference_resolution`은 reference를 읽기만 하지 않고 적용 결과를 새 DB에 쓰므로, 읽기 호환 view만 만든 것으로 연결 완료 처리하지 않는다. 쓰기 어댑터, 감사 검증, 게시, 재개, FTS 결속, 엔진·PIPELINE 코드 pin을 함께 갱신한다. 새 감사 형식 지원이 끝나기 전에는 구형 검증기를 우회하지 않는다.

완료 조건: 서빙·감사 모두 논리 내용 동일, 중복 본문 물리 저장 감소, 전체 생성 경로에서 총 쓰기량·피크 디스크·메모리·시간 개선 확인. 서빙 DB만 작아지고 감사/임시 파일이 커지는 결과는 따로 보고한다.

### 4 참조 묶음 단위 재개

기존 `Stages` 아래에 navigation 세부 checkpoint를 추가한다. 전역 제목·구조 카탈로그를 고정한 뒤 완료된 문서 또는 결정론적으로 나눈 source 묶음을 재사용한다. 본문 안의 앞선 인용을 이어받는 상태가 끊기지 않도록 checkpoint 경계를 정한다. 여러 문서에 걸친 위임 처리, 근거 결합, 통계·무결성·최종 발행은 별도 완료 단위로 둔다.

작은 인용마다 commit하지 않고 기록량에 상한을 둔 묶음으로 쓴다. 묶음 크기와 메모리 상한은 비교 전에 고정한다. 산출 행과 완료 표지를 같은 트랜잭션에 기록하거나, 별도 DB라면 각 파일의 내구 저장·검증이 모두 끝난 후 결합 영수증을 발행한다. 서로 다른 DB에 쓴 사실만으로 원자 완료를 가정하지 않는다.

실패 시 미완료 묶음만 제거·재생성하고 완료 묶음의 해시를 확인한다. 완료 영수증 없는 파일, 코드/입력/이름 목록/사전/설정 변경, 다른 실행의 결과는 재사용하지 않는다. 기존 불완전 scratch를 새 compiler의 checkpoint로 인정하지 않는다. 이번 재개는 같은 입력의 중단 복구이며, 문서 변경 후 다른 세대로의 증분 재사용은 전역 참조 의존성 무효화 계약이 별도로 필요하다.

완료 조건: 여러 위치에서 중단한 뒤 재개해도 신규 일괄 구축과 논리 행·상태·참조 결과가 같고, 완료 묶음은 다시 계산하지 않는다.

### 5 기존 파이프라인 통합과 GENOS 확인

새 후보를 기존 `storage_profile` 선택과 build identity에 명시적으로 연결한다. 제안 선택값은 `compact-v2`이며 현재 CLI에는 없다. 검증된 helper까지 코드 해시에 포함하고, 변경된 엔진 manifest와 PIPELINE 상위 해시를 함께 대조한다. 현재 compact-v1 및 이전 세대의 읽기·원복 경로를 유지한다.

완료 입력을 재사용해 새 navigation/감사, unit FTS, 서빙 캐시와 전체 결속을 만든다. 모델 호출이 없는 구축 비교와 GENOS 내부 모델을 쓰는 최종 RAG 검증을 구분한다. 최종 질의에서 입력 제한 오류 등 별도 문제가 나타나면 이번 색인 변경의 성공으로 가리지 않는다.

현장 인계는 기존 `~/DEV` 백업 적용, `python3`, 최초 단계부터 지속 로그, 명시 입력·출력, 새 NFS 세대, 검증한 Git commit과 코드서빙 리비전의 순서다. 현재 세션은 GENOS에 접근할 수 없으므로 내부 실행·속도·배포를 대신 확인하지 않는다. 최종 warmup과 질의는 워크플로우 테스트 화면에서 수행한다. 코드 ZIP, Git push, 코드서빙 배포, 워크플로우 편집기 반영, CURRENT 선택은 각각 기록한다.

## 변경 지도

| 기존 위치 | 변경 책임 | 소비자와 이행 |
|---|---|---|
| `semantic_runtime/term_references_legacy.py`, `term_references.py` | 제목/약칭 검색, 본문 순회, 참조 기록·진행률 | 기존 dispatcher와 해석 모드 유지. 참조 ID/span/상태 전수 비교 |
| 제안 `semantic_runtime/reference_name_index.py` | 구축 범위에 묶인 정확한 접미 이름 검색 | 두 compiler, 신규 dependency hash와 테스트 추가 |
| `semantic_runtime/term_index.py`, `term_links.py` | metadata 조회, 묶음 기록, 근거 결합, 단계 계측 | 제목·좌표·후보·감사 소비자 유지 |
| `semantic_runtime/navigation_storage.py`, `compact_storage.py` | 새 물리 저장·감사 manifest·구형 호환 | `verify_audit`, `verify_build`, `TermIndex`, 참조 읽기·쓰기 소비자 모두 변경 |
| `lawrag/pipeline/generation_build_steps.py`, `term_generation.py` | 세부 checkpoint, 새 선택값, 코드/입력 identity | 기존 단일 build entrypoint와 result 소비자 |
| `lawrag/pipeline/reference_resolution.py`, `term_serving_bundle.py` | 참조 적용 쓰기와 새 감사 결속 검증 | 승인 기록·FTS·cache 재결속, 이전 판정 자동 복사 금지 |
| `genos_reindex_runner.py`, `genos_reindex_only.py`, `genos_generation_e2e.py` | CLI·완료 입력 선택·검증·게시 배선 | 외부 모의 검사와 현장 실행을 구분 |
| `DATA_MODEL.md`, 관련 manifest/schema, engine manifests, `PIPELINE.json` | 신규 계약·버전·이행·의존 파일 pin | 작업 코드 등록과 실제 MAIN/현장 선택은 별도 |

위 경로는 backend=`02_BACKEND`, tools=`06_TOOLS/OFFLINE` 또는 `06_TOOLS/COMMANDS`, system=`00_SYSTEM`이다. 구현에서 데이터 경로는 `lawrag.platform.workspace`의 논리 root와 명시한 run으로 해결한다.

## 비교와 통과 기준

계획 문서 작성은 신규 실험이 아니다. 실제 후보 수정·효과 측정 전에 진행 중 동일 scope를 확인하고 stable runner의 `adr_structure.py new --adr-root 04_EXPERIMENTS/ADR`로 선점한다. 후보 snapshot/register/freeze/validate 후 실행한다. 직접 부모는 구현 시점의 정확한 완료 arm을 확인하며 ADR0632/io를 현재 기준 후보로 검토한다. 여러 완료 분기의 변경을 합치면 정확한 부모와 채택 범위를 새 통합 ADR에 기록한다.

| 검증 | 자료와 방법 | 통과 기준 |
|---|---|---|
| 이름 검색 동등성 | 따옴표, 공백, 동명 판본, 긴 겹침 제목, 특수문자, 약칭 우선순위, 불일치, 새 문서 집합 | 선택 이름·대상·미해결 사유 동일. 전체 제목 순회 0 |
| 참조·근거 동등성 | legacy와 scope-v2를 각각 같은 모드 안에서 비교 | reference/end/target/candidate/candidate_end 및 ACCEPTED/HELD 감사 내용의 누락·추가·변경 0 |
| 구조 보존 | 항·호·목, 별표, 정·역참조, 복수 대상, 원문 hash·span | 기존 유효 연결과 거부 동작 동일. 입력 원본 해시 불변 |
| 저장·재개 | 중간 중단, 미완료 묶음, 완료 파일 변조, 입력/코드 변경, 동일 출력 동시 실행 | 완전 신규 구축과 동일 결과. 변조·다른 실행 혼용 거부. 원본 보존 |
| 규모·성능 | 현장 문서 수를 포함한 여러 규모의 모의 자료, 긴 본문·참조 밀집·후보 편중·불일치가 많은 별도 holdout | 준비 비용을 포함한 참조 단계 시간과 전체 구축·피크 메모리·총 디스크 보고. 작은 반복문만으로 일반화 금지 |
| 현장 비교 | GENOS에서 같은 완료 입력·코드 기준·설정·실행 자원·저장 위치로 기준/후보 | 구축 단계별 시간, unit FTS 완료, 검증·게시까지의 총시간을 분리. 단일 실행을 p95로 표기하지 않음 |
| RAG 연결 | 기존 전체 E2E 사례를 같은 문서 범위·내부 모델로 워크플로우에서 실행 | 검색/원문/정·역참조/인용/권한/미해결 처리 확인. 첫 준비와 반복 질문 분리. HTTP 200만으로 성공 판정 금지 |

기존 계약 테스트는 `test_annex_pattern_reuse.py`, `test_annex_linking.py`, `test_cross_law_references.py`, `test_provision_references.py`, `test_reference_resolution.py`, `test_navigation_storage.py`, `test_genos_compact_lifecycle.py`, `test_genos_prepared_serving_reuse.py`와 generation E2E를 기준으로 확장한다. 재컴파일 횟수 자체를 구현 목표로 강제하는 기존 테스트는 정확한 검색 결과와 작업량 상한을 검사하도록 바꾼다.

성능 채택 목표 초안은 **대규모 이름 조회 단계 중앙값 50% 이상 단축**, **대표 전체 구축 중앙값 20% 이상 단축**, **최대 메모리와 전체 피크 디스크 증가 없음**이다. 이는 기대값이 아니라 사용자 체감 개선을 확인하기 위한 목표다. 구체적인 데이터·반복 횟수·arm 순서·측정 범위를 후보 결과 전에 동결하고, 실패하면 기능 보존 성공과 속도 목표 실패를 별도로 보고한다. 결과를 본 뒤 목표를 낮춰 같은 실험을 통과시키지 않는다.

로컬과 GENOS는 별도 결과로 기록한다. 완료 ADR의 final validator와 graph를 확인하고, 기존 graph 문제와 신규 문제를 구분한다. 활성 MAIN 승격 및 GENOS 리비전 배포는 구현 채택과 별도 상태다.

## 시간과 자원 예상의 한계

| ID | 종류 | 값 또는 식 | 의미 |
|---|---|---|---|
| N1 | 현장 관측 | navigation 33,384.2초 | E1의 한 과거 실행. 개선 후 예상치가 아님 |
| N2 | 현장 관측·단위 환산 | 25,666,207,744 bytes ÷ 10^9 ≈ 25.7GB | E2의 한 파일 크기. 피크 총량으로 사용하지 않음 |
| N3 | 설계식 | 새 시간 = 이름 인덱스 준비 + 후보 이름 조회 + 본문 처리 + 참조/근거 쓰기 + 검증/해시 + 재개 기록 | 각 항목은 앞으로 같은 조건에서 측정. 기존 시간과의 차이가 순절감 |
| N4 | 손익분기 | 줄인 조회·중복 쓰기 시간 > 새 인덱스·검증·checkpoint 비용 | 제목/인용이 적거나 필수 근거 결합이 대부분이면 이득이 작거나 음수가 될 수 있음 |
| N5 | 채택 목표 | 이름 조회 50%, 전체 구축 20% 이상 단축; 메모리·총 피크 디스크 증가 없음 | 결과 전 확정할 목표이며 성능 예측이나 GENOS 보장이 아님 |
| N6 | 미산정 | GENOS 완료 시간, 총 개발 인일, 추가 디스크 여유 | 테이블별 규모·실행 자원·새 계약 변경 범위를 확인한 뒤 산정. 9시간에 로컬 가속률을 곱하지 않음 |

신규 라이브러리 없이 기존 Python·SQLite 경로를 우선한다. SQLite의 내구성을 끄거나 NFS에 WAL을 강제해 시간을 줄이지 않는다. 작업 위치가 NFS인지 로컬 디스크인지 실제 mount로 확인한다. 로컬 디스크가 허용되고 공간이 충분한 경우에만 준비·검증·NFS 게시의 총비용을 별도 후보로 비교한다. 저장 위치를 바꾸고 같은 조건의 알고리즘 개선으로 보고하지 않는다.

## 자체 검토와 완료 보고

검토 방식은 작성자의 자체 검토이며 독립 에이전트 검토나 현장 성능 인증이 아니다.

| ID | 검토 사항 | 문서 반영 | 구현·검증 상태 |
|---|---|---|---|
| R1 | 작은 합성 입력과 현장 시간을 직접 비교하면 안 됨 | 비교 기준과 수치 원장에 반영 | 현장 동일 조건 비교 대기 |
| R2 | 조기 감사 분리는 기존 exact snapshot 계약과 다름 | 신규 버전·구형 보존·읽기/쓰기 소비자 변경 명시 | 새 계약 미구현 |
| R3 | prefix 검색 최적화가 경계·약칭·최장 선택을 바꿀 위험 | 동등성 조건과 두 compiler별 검증 명시 | 후보 미구현 |
| R4 | 묶음 재개가 중복/누락이나 이전 문맥 손실을 만들 위험 | 완료 경계·트랜잭션·영수증·중단 검사 명시 | 후보 미구현 |
| R5 | 최종 서빙 용량만 줄이고 구축 피크를 해결했다고 할 위험 | 감사·임시·journal을 포함한 총량 측정 명시 | 현장 기여량 미측정 |

완료 보고는 코드 구현, 논리 동등성, 로컬 성능, GENOS 구축 성능, 실제 RAG 성공, 배포·활성화를 각각 표시한다. 사용자에게 제시할 최종 비교는 같은 입력의 기준/후보 단계 시간과 전체 시간이며, 확인하지 못한 항목을 완료로 표시하지 않는다.
