# 용어 검색 DB와 구축 감사 원장

2026-10-08 사용자 정정에 따라 로컬 MAIN 신규 구축은 **생성 중 감사량**도 줄이는
`factorized-v1`/storage-v4를 명시 선택한다. 아래 storage-v3와 완료 후 gzip은 이전
구현 기록으로 보존하며, 새 구축의 추가 선택은 다음 계약을 따른다.

## 신규 생성의 factorized-v1 감사 계약

`build-all` → `document-release reindex`의 settings가 `audit_profile=factorized-v1`을
고정하고, 기존 `rebuild_serving` → `term_generation` → `generation_build_steps` →
`term_index` → `LinkProjector` 경로로 전달한다. 원문 source-v2, navigation-v7,
단위 fulltext와 모델 호출 0회는 유지한다. `term_generation.build_generation`을
직접 호출할 때는 `storage_profile='compact-v2', audit_profile='factorized-v1'`을 명시한다.
기본 materialized 선택 및 기존 완료 데이터는 유지하며 오래된 실행을 새 포맷으로 재개하지 않는다.

| 기록 | 실제 저장 | 조회·검증 시 재현 |
|---|---|---|
| 후보 및 원문 출현 | `link_catalogue`, `link_occurrence` 전수 | 기존 컬럼·ID·span·해시·상태·사유 |
| 출현×후보 근거 | 조합 행·PK·복제 ID를 쓰지 않음 | `occurrence_evidence` view의 같은 6컬럼 및 모든 accepted/held 조합 |
| 기존 label-match 출처 | `audit_term`, `audit_source` 독립 ID 사전과 `audit_legacy_origin` 정수 쌍 | `occurrence_origin`의 LEGACY_LABEL_MATCH |
| 용어집에서 추가한 연결 출처 | 별도 문자열 쌍 복사를 쓰지 않음 | accepted 근거의 distinct 쌍 및 VERIFIED_GLOSSARY_LINK |

최종 NO_ACCEPTED_CATALOGUE_CANDIDATE 변경 전의 검증 상태를 view에서 복원하고
문서 scope, catalogue 사유, span 실패 사유를 같은 우선순위로 판정한다. RAG의 원문·
용어 연결 결과와 감사 논리 행은 동일하다. SQLite view 정의 자체와 retained DB는
감사 SHA로 고정하며 manifest에 profile/재현 코드 SHA/전수 논리 건수/물리 표를 남긴다.
검증기는 v4 물리 표/논리 view 및 독립 legacy 좌표를 확인하고 기존 v1~v3도 계속 읽는다.
문서/참조/근거/checkpoint의 공동 트랜잭션과 중단/강제 종료 복구를 유지한다.
완료 후 gzip과 검증 시 임시 복원은 **작게 생성한 원장**에 적용한다.

이 변경은 조합별 감사 행을 상시 저장하지 않는 대신 전수 조회 때 join/dedup 계산이
필요하다. 감사 조회는 서빙 요청과 분리된다. 원문 native audit, 작업 source/glossary,
검색/navigation/fulltext 및 SQLite 임시/저널 용량은 별도로 필요하며, 감사 감소량만으로
신규 전체 corpus의 최대 용량을 확정하지 않는다. GENOS 봉인 인계와 실제 현장 코드는 유지한다.

2026-10-03 작업 코드에는 명시적 `compact-v2`의 navigation v7/storage-v3 경로를 추가했다.
아래 2026-09-29의 v1/v2 snapshot 기록은 보존한다. 현재 활성 릴리스 판정에는
`01_DATA/ACTIVE/local/ACTIVE_RELEASE.json`을 사용하며 이 문서의 과거 MAIN 기록으로 선택하지 않는다.
새 경로는 [구현 결과](../REPORTS/GENOS_REFERENCE_BUILD_IMPLEMENTATION_20261003.md)와
[GENOS 인계](../../../08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_GUIDE_UTF8.txt)를 따른다.

## compact-v2의 새 구축 계약

| 항목 | v1/v2 기존 계약 | storage-v3 명시 선택 |
|---|---|---|
| 감사 | 분리 전 완성 DB의 정확한 snapshot | 처음부터 별도 DB에 작성한 구축 근거 4개 표 전수 |
| 검색 DB | 완성 원장에서 runtime 표를 복사 | 처음부터 runtime만 작성; occurrence 정수 키 |
| 참조 본문 | reference JSON마다 source_text 반복 | reference_body에 hash별 저장, 호환 reference view와 쓰기 trigger |
| 재개 | navigation 전체 완료 단계 | 문서/참조 source의 64개 묶음 및 전역 처리 완료 경계 |
| 원문 | native audit 및 source generation | 동일 원문 보존 계약; 작은 본문 cache로 필요한 source만 읽음 |

`genos_reindex_runner.py build --serving --storage-profile compact-v2 --fulltext-granularity unit`
→ `genos_reindex_only.rebuild_serving` → `term_generation.build_generation`
→ `generation_build_steps.build` → `term_index.compile_index`로 연결한다.
기존 `legacy`/`compact-v1` 선택과 이미 완성된 데이터는 보존한다. 새 포맷은 새 세대에서만 쓴다.
reference_resolution의 검토/적용도 호환 view를 통해 읽고 쓰며 파생 세대의 감사 lineage를 결속한다.

native 감사, 새 runtime, 새 구축 감사가 전체 보존 묶음이다. storage-v3 감사 DB 하나를
분리 전 전체 navigation snapshot으로 설명하지 않는다. HELD/ACCEPTED/미해결 근거는 삭제하지 않는다.
문서와 참조 checkpoint는 해당 결과와 같은 트랜잭션에 저장하고 입력/코드/범위가 바뀌면 재개를 거부한다.
동일 파일시스템의 attached SQLite, DELETE journal, FULL sync를 사용하며 실제 GENOS NFS의
잠금·저널 보장은 현장 검증이 필요하다. 로컬 강제 프로세스 종료 복구는 확인했다.

## 2026-10-08 로컬 완료 감사 원장 압축

로컬 MAIN의 모델 없는 구축은 오프라인 검증 후 완료 navigation 감사 SQLite를 gzip으로
무손실 압축한다. 원래 감사 manifest·generation·result의 바이트와 SHA는 바꾸지 않는다.
`archive.json`에는 복원할 파일의 권한·소유자·시각을 남긴다. 압축본 전체를 풀어 원래 SHA와
크기가 일치하는지 확인한 뒤 평문 DB를 제거하며, 원문·근거 행을 요약하거나 버리지 않는다.
검증·재개·승인 참조 복사에서는 임시 SQLite로 복원하고 사용 후 지운다.
따라서 완료 후 상주 용량은 줄지만 구축 중 또는 검증 중에는 평문 감사 DB 공간이 필요하다.
미완료 checkpoint 원장은 압축하지 않는다. GENOS 기존 ZIP·현장 코드는 변경하지 않았다.

```bash
# BUILD는 generation/, audit/, result.json이 있는 완료 구축 디렉터리다.
.venv/bin/python -B 06_TOOLS/pipeline.py document-release archive-audit --release BUILD
# 압축을 모르는 과거 continuation 도구를 쓰기 전 원래 DB를 복원한다.
.venv/bin/python -B 06_TOOLS/pipeline.py document-release restore-audit --release BUILD
```

## 2026-09-29 기존 분리/승격 기록

2026-09-29 사용자 지시로 공통 `term_generation.build_generation`과
`pipeline.py document-release`에 검색 DB/구축 원장 분리를 연결했다.
[전수 저장 검증](../../../04_EXPERIMENTS/ADR/ADR-0550-navigation-serving-audit-separation/README.md),
[릴리스 연결 검증](../../../04_EXPERIMENTS/ADR/ADR-0552-navigation-audit-release-contracts/README.md),
[MAIN 적용 기록](../../../09_ARTIFACTS/AUDITS/20260929-navigation-storage-main/README.md)을 따른다.

## 입력·순서·소비자

기존 `원문 → 용어 연결 → compile_index → fulltext → release` 순서를 유지한다.
compile 완료 뒤 구축 표 4개를 감사 원장에 보존하고 검색 DB에서만 분리한다.

| 위치 | 내용 | 소비자 |
|---|---|---|
| `serving/generation/navigation/navigation.sqlite` | term, edge, source, occurrence, definition, reference 등 검색 표와 기존 색인 | RAG·용어/원문 탐색 |
| `serving/audit/navigation/navigation.sqlite` | 분리 전 완성 DB 원본 snapshot; link_catalogue, link_occurrence, occurrence_evidence, occurrence_origin 및 맥락 | 근거 감사·오프라인 검증·재개 |
| `serving/audit/navigation/manifest.json` | 감사/서빙 파일 SHA·bytes, 구축 건수, compiler hash | generation/nav/result 결속 |
| `serving/result.json` | `navigation_audit.path=audit/navigation` 및 감사 manifest SHA | 구축 재개·릴리스 검사 |

감사 snapshot에는 검색 표도 포함한다. 후보·held·ambiguous 근거를 삭제/요약하지 않는다.
RAG 요청은 generation만 사용한다. 작성 측 reviewed/unreviewed release·resume·publish는
감사 파일도 확인한다. generation만 서빙 볼륨에 게시한다. 기존 단일 DB 세대도 읽을 수 있다.
nav manifest의 선택적 `storage.schema_version=term-navigation-storage-v1`이 분리 구조를 식별한다.

## 기존 선택 세대 이행

원문·용어집·fulltext를 재추출하지 않고 명시 선택한 단일 DB 세대를 파생한다.
완료 세대나 공유/hardlink navigation DB를 직접 수정하지 않는다. 새 output에서만 DROP/VACUUM한다.
원문 generation ID와 store SHA·문서 범위·반출 상태는 유지해 origin/alias/source grant 결속을 보존한다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py document-release compact-navigation \
  --base-generation 01_DATA/TERM/relation-subtree-main-serving-20260920-v1/generation \
  --fulltext-binding 09_ARTIFACTS/AUDITS/20260929-navigation-storage-main/legacy-fulltext-binding.json \
  --output 01_DATA/TERM/<new-run>
```

새 run은 `generation/`, `audit/navigation/`, `result.json`을 만든다.
재개는 입력·compiler·generation·audit 해시가 같아야 한다. 입력/코드 변경이나 변조가 있으면
기존 결과를 보존하고 새 run을 사용한다. 오프라인 검증은
`semantic_runtime.navigation_storage.verify_build(output)`이다.
현 로컬 MAIN 데이터는 `01_DATA/TERM/navigation-storage-main-20260929-v2/generation`이다.
전수 비교 실행기의 frozen research candidate는 제품 경로에서 사용하지 않는다.

기존 r3 세대의 fulltext는 generation manifest에 없고 릴리스 profile에 결속돼 있다.
이 경우 위처럼 선택된 profile의 정확한 binding JSON을 명시해야 한다. 누락하면 CLI가
거부한다. compaction은 `<new-run>-navigation`을 보존하고 본문 색인 메타데이터를
`<new-run>`에 새로 결속한다. payload와 검색표는 immutable hardlink로 그대로 공유한다.
이미 분리된 build를 사용할 때는 다음 기존 document-release action으로 이어간다.

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py document-release rebind-fulltext \
  --release 01_DATA/TERM/navigation-storage-main-20260929-v1 \
  --fulltext-binding 09_ARTIFACTS/AUDITS/20260929-navigation-storage-main/legacy-fulltext-binding.json \
  --output 01_DATA/TERM/<new-run>
```

이전 profile 소유 계약을 유지하므로 새 `result.fulltext_binding`을 선택된 릴리스 설정에
명시 결속해야 한다. v1 payload에는 해당 frozen v1 reader를 사용하며 현재 작업 코드의
v2 reader로 자동 변환하지 않는다. 본문 재추출·재토큰화·랭킹 변경은 없다.

## 승인 참조·릴리스 결속

reference_resolution.apply는 원문/fulltext postings를 보존하고 새 navigation SHA를 private
fulltext manifest에 연결한다. 부모 JSON은 수정하지 않는다. document_release는 감사 snapshot을
보존하고 새 감사 manifest에 부모 audit manifest SHA·reference apply receipt SHA·부모 nav SHA를
연결한다. result → generation → navigation → audit가 어긋나면 릴리스/게시를 거부한다.
result에서 감사 항목을 지워도 nav.storage가 있으면 검증이 거부한다.

## 검증·MAIN·복구

선택 전체 DB의 검색 12표/6,821,126행과 색인 SQL 차이 0, 감사 원본 SHA 동일.
navigation은 14,933,344,256 → 1,945,915,392 bytes, 13.91 → 1.81 GiB(86.97% 감소).
저장·참조·릴리스·재개·변조 검사 25개 및 진입점/로컬 모델 결속 검사 20개 통과. 보조 기존 계약 실패 3개와 과거 ADR graph 오류
6개는 적용 기록에 보존했다. 법률 답변 품질·요청 지연·GENOS 현장 효과는 미측정이다.

로컬 MAIN은 `legal-agent-navigation-storage-20260929-r3`, 활성 포인터 generation 29이다.
직전 r3 frozen release의 183개 구현·스키마·모델 프로필·공개 source grant 파일 SHA는 같다.
PIPELINE.json 한 파일에서 navigation/fulltext 경로·해시만 갱신했다.
현재 진입점은 로컬 릴리스의 profile normalizer도 같은 선택 package에서 읽는다.
최신 작업 policy의 필드가 과거 frozen 코드에 섞이는 기존 오류를 막는다.
quality_certified=false를 유지하며 Git 병합·GENOS 배포는 별도다.

동일 바이트의 원본 navigation과 감사 snapshot은 검증 후 immutable hardlink로 공유해
중복 할당만 제거했다. 이전 MAIN 릴리스·데이터·원문·감사 근거는 보존한다.
전체 저장소 과거 자료 삭제나 용어집 원장 축소를 수행한 결과가 아니다.

stable prepare/apply가 코드·데이터·승인·검증 hash와 이전 활성 포인터를 고정한다.
해시·범위·검색 차이나 감사 손실 발견 시 직전 포인터와 작업 배선을 다음 명령으로 복원한다.

```bash
.venv/bin/python -B 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
```

기존 로컬 RAG 프로세스는 발견하지 않았다. 프로세스가 실행 중이라면 적용/롤백 뒤 재시작한다.
