# 데이터 티어 계약

`python scripts/data_tiers.py`는 현재 원천 계보를 읽어 다음 묶음을 생성한다.

| 티어 | 내용 | 배포 |
|---|---|---|
| `production_lawxml_raw` | law.go.kr 현행·시계열 본문 XML, 관계 XML과 manifest | 포함 |
| `production_lawxml_structure` | `source_kind=lawxml`의 meta/result/source.xml | 포함 |
| `production_connected_non_vector` | 법령 색인·위임 간선·별칭과 doc_id로 귀속 가능한 frame/taxonomy | 포함 |
| `evaluation_mock_or_fixture` | bench, review/golden, 테스트 fixture, examples | 운영 데이터와 분리 |
| `excluded_vectors` | embeddings, NPZ 등 모델 종속 벡터 | 제외·현지 재생성 |
| `separate_authoritative_or_mixed` | Wiki, 판례·해석례, KRX·KOFIA, 내규, rules, 혼합 graph | 별도 보존·정책 필요 |
| `separate_operational_generated_or_unresolved` | archive, pipeline 상태, 다른 원천 구조화본, 귀속 미확정 파생물 | 자동 배포 금지·경로별 검토 |

처음 제안한 두 묶음만으로는 전체 데이터가 닫히지 않는다. 판례·해석례와 사람이 편집한 Wiki·
rules는 실험용 mock이 아니고, 순수 법 XML 파생도 아니다. `domain_graph`와 `legal_graph`도 현재
여러 원천이 한 세대에 섞여 있어 법 XML 행만 내보내려면 row-level projection이 추가로 필요하다.
마지막 `separate_*_unresolved` 계층은 누락 방지용 catch-all이다. 감사기는 `data/`의 모든 파일이
정확히 한 티어에 속하는지도 검사한다.

운영용 최소 패키지는 앞의 세 `production_*` 티어 합집합이며 vector, 합성 PDF, 페이지 PNG,
평가 fixture를 포함하지 않는다. 감사 JSON은 다음처럼 만든다.

2026-08-31 전수 감사 기준으로 현행 본문 50개와 시계열 고유 본문 12개는 모두 구조화본이
있다. `data/structure`의 64개 doc ID 중 2개는 현재 원천 폴더에 대응 XML이 없는 잔존
구조화본이다. 삭제 대상으로 간주하지 않고 원천 보존·복구 여부를 따로 확인해야 한다.

```bash
.venv/bin/python scripts/data_tiers.py \
  --output var/reports/data-tier-inventory.json
```
