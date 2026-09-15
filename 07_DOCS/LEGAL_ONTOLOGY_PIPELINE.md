# Legal Ontology Lifecycle Pipeline

정식 이름은 **Evidence-Grounded Legal Ontology Lifecycle**이고 계약 ID는
`legal-ontology-lifecycle-v1`, 실행 파이프라인 ID는 `legal-ontology-pipeline-v1`이다.

## 사용자 흐름

```text
입력                추출                         변환
원문·출처·버전  →  구조 + Observation       →  Canonical KG + Projection
                                                        │
재구조화          사용                                 │
피드백→후보→승인 ← 검색·판단·trace·release  ←───────────┘
```

사용자는 `/pipeline/`에서 다섯 단계를 한 번에 본다. 각 세부 stage에는 현재 수량,
누락 수량, 실행 방식, gate와 다음 동작이 같이 표시된다.

## 실행 정책

- `automatic`: 기존 증분 batch와 같은 기본 범위다. 기본 실행 버튼은 이 단계만 돈다.
- `explicit`: Legal Graph 전체 컴파일처럼 비용이 크거나 immutable generation을 새로 만드는
  단계다. 단계별 실행과 확인을 거쳐야 한다.
- `manual_only`: release 활성화와 피드백 승격이다. 화면과 CLI는 상태만 보여 주며 자동
  승격하지 않는다.

## 2026-09-04 현재 상태

- 원문 159/159, 구조 207문서. 저신뢰 4문서는 격리 상태다.
- delegation은 최신이며 scope 3/3이 해석된다.
- 용어는 4,438개·출현 문서 133/207이다. 나머지 78문서도 재검사는 완료됐으며
  결정론 추출 결과가 0인 품질 대상으로 남는다.
- 의미 프레임은 172문서·21,913조가 미추출이다. 호출 입력은 한 조의 본문을 가장 깊은
  조·항·호·목 owner 좌표로 나누며 6,000자 초과 tail은 추가 청크로 보존한다.
  현재 corpus 예상 호출은 21,996회다.
- ADR-0180 실제 Haiku probe는 목/단서/최장 조 3/3, node 100%, 표면 grounding 95.6%로
  기술 gate를 통과했다. 표본 기반 전체 입력 추정은 약 4,784만 token이므로 명시적 비용
  승인 전에는 프레임 대량 실행과 Canonical generation 재컴파일을 하지 않는다.

```bash
# 전체 상태만 확인 — 파일을 쓰거나 모델을 부르지 않는다.
.venv/bin/python 06_TOOLS/ontology_pipeline.py status

# 스키마·stage mapping·Projection 파일을 검증한다.
.venv/bin/python 06_TOOLS/ontology_pipeline.py validate

# 기본 증분 단계만 실행한다. Legal Graph/release는 포함하지 않는다.
.venv/bin/python 06_TOOLS/ontology_pipeline.py run

# 무거운 변환 단계는 명시한다.
.venv/bin/python 06_TOOLS/ontology_pipeline.py run --stages legal_graph,definition_projections --yes
```

## 코드와 폴더 책임

| 경로 | 책임 |
|---|---|
| `00_SYSTEM/ONTOLOGY_PIPELINE.json` | 실행 단계와 gate의 기계 정본 |
| `00_SYSTEM/SCHEMAS/` | lifecycle과 DefinitionProjection JSON Schema |
| `02_BACKEND/lawrag/ontology/` | 계약 로더·검증·상태 snapshot 재사용 코드 |
| `02_BACKEND/lawrag/feedback/lifecycle.py` | 운영 trace·검증 오류를 불활성 변경 후보로 컴파일 |
| `02_BACKEND/lawrag/core/batch.py` | 단계 실행과 증분 상태·receipt |
| `02_BACKEND/lawrag/pipeline/ontology.py` | 얇은 사용자 CLI |
| `02_BACKEND/lawrag/api/routers/pipeline.py` | 동일 snapshot의 HTTP API |
| `01_DATA/PROJECTIONS/DEFINITIONS/` | 검증 대상 DefinitionProjection authoring 레코드 |
| `01_DATA/FEEDBACK/` | append-only 피드백·교정 계보와 검토 후보 계약 |
| `08_DEPLOYMENT/CI/` | 로컬과 CI가 함께 쓰는 결정론 검증 진입점 |

## CI/CD 경계

Pull request와 수동 실행은 lifecycle/Projection schema, stage mapping, ClauseSpan,
API/CLI와 기존 batch·Legal Graph 회귀를 검사하고 설치 가능한 wheel을 만든다. 여기까지가
자동 CD 산출물이다. 실제 GENOS/Sites/사내 release 활성화는 `release-manifest-v1`, smoke,
provenance, ACL, rollback receipt와 사람 승인이 모두 있어야 하므로 이 workflow가 자동으로
배포하지 않는다.
