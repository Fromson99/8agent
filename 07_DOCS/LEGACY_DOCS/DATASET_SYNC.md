# 내부·외부 동형 데이터셋 ZIP

내부와 외부는 같은 실험 코드·질문셋·공개 데이터 hash를 사용한다. 반출 불가 문서만 같은
`logical_id`와 기능 계약을 가진 overlay로 교체한다.

```text
내부 환경                         외부 환경
common-runtime ───────── hash 동일 ───────── common-runtime
common-evaluation ─────── hash 동일 ───────── common-evaluation
overlay-real ───────── 논리 계약 동일 ─────── overlay-mock
  실제 내규·파생물                              가상 내규·파생물
```

내용이 다른 real/mock overlay의 payload hash나 content 기반 `doc_id`를 서로 같다고 가장하지
않는다. 실험 동등성은 다음 두 조건으로 판정한다.

1. `common-runtime`, `common-evaluation`의 `content_sha256`가 정확히 같다.
2. overlay의 논리 ID, 문서 종류, 형식 계열, 버전 역할, 필수 파생물 역할을 접은
   `overlay_contract_sha256`가 같다.

## ZIP 세트 구성

`scripts/dataset_sync.py pack`은 한 환경을 세 bundle로 나눈다.

| bundle | 내부 | 외부 | 용도 |
|---|---|---|---|
| `common-runtime` | 동일 | 동일 | 법·외규 원천, 구조, frame/taxonomy, 비벡터 연결 데이터, Wiki |
| `common-evaluation` | 동일 | 동일 | 질문·golden·평가 기준 |
| `overlay-real` / `overlay-mock` | 실제 사내 자료 | 가상 대체자료 | 내부 문서와 파생 구조 |

각 bundle은 기본 35MB 이하 ZIP shard들, `bundle.manifest.json`, 파일별 SHA-256으로 구성된다.
세트 루트의 `SYNC_SET.json`과 `SYNC_SET.json.sha256`이 환경·bundle identity·overlay 계약을
고정한다. vector, 페이지 PNG, 합성 PDF, parse cache, 운영 로그, archive는 포함하지 않는다.

## 외부 작업용 세트

저장소에 있는 4개 가상 내규/검토요청서와 파생 구조를 locked mock overlay로 사용한다.

```bash
.venv/bin/python scripts/dataset_sync.py list --environment external
.venv/bin/python scripts/dataset_sync.py pack \
  --environment external \
  --out var/out/ship/dataset-sync-external \
  --size 35
.venv/bin/python scripts/dataset_sync.py verify \
  var/out/ship/dataset-sync-external
```

외부 pack은 임의 overlay를 받을 수 없고
`config/dataset_sync/external-mock-overlay.json`만 사용한다.

## 내부 작업용 세트

`config/dataset_sync/internal-real-overlay.example.json`을 Git 비추적 영역인
`var/private-data/`의 실제 문서·구조·frame·taxonomy에 맞게 복사·작성한다. 네 논리 ID와
각 `contract`는 바꾸지 않는다. 실제 `doc_id`와 물리 경로는 달라도 된다.

```bash
.venv/bin/python scripts/dataset_sync.py pack \
  --environment internal \
  --overlay-manifest var/private-data/internal-overlay.json \
  --out var/out/ship/dataset-sync-internal \
  --size 35
```

내부 overlay는 `representation=real`, `export_allowed=false`가 아니면 pack이 거부한다.
`dataset-sync-internal` 폴더는 외부 반출 금지다. 외부에는 공통 bundle과 external mock
overlay만 전달한다.

## 양쪽 싱크 검증

두 세트의 manifest를 내부 승인 경로에서 대조한다.

```bash
.venv/bin/python scripts/dataset_sync.py compare \
  var/out/ship/dataset-sync-internal \
  var/out/ship/dataset-sync-external
```

`compatible`은 공통 payload hash와 overlay 논리 계약이 같다는 뜻이며, 실제 문서와 목업의
답변 정확도가 같다는 뜻은 아니다. 결과 비교에서는 환경을 분리해 보고하고 mock 성능을 실제
내규 성능으로 승격해서는 안 된다.

## 반입과 실험 잠금

```bash
.venv/bin/python scripts/dataset_sync.py unpack <세트폴더> \
  --root <저장소뿌리> --dry-run
.venv/bin/python scripts/dataset_sync.py unpack <세트폴더> \
  --root <저장소뿌리> --replace
```

반입 후 `data/sync/ACTIVE_DATASET.json`은 논리 ID를 현재 환경의 `doc_id`와 물리 파일에
연결하고, `data/sync/SYNC_SET.json`은 공통 bundle hash를 보존한다. 실험 코드는
`lawrag.datasets.sync.resolve(logical_id)`로 overlay를 찾고, ADR에는
`environment_receipt()` 결과와 `overlay_contract_sha256`를 동결한다.
