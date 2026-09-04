# 영구 v2 전환 상태와 잔여 경계

## 2026-09-04 코드 상태

- workspace는 `v2-only`이며 legacy top-level root와 unknown root가 없다.
- editable backend/tool source를 각각 `02_BACKEND/lawrag`,
  `06_TOOLS/LEGACY_SCRIPTS`에 두고, 실행 선택은 활성화 영수증에 봉인된
  `20260904-code-v5` 불변 generation을 사용한다.
- 과거 기록의 `data/docs/scripts/lawrag/var` 경로는 기록을 재작성하지 않고
  활성·이력 activation receipt의 source→target binding으로 해석한다.
- `ExperimentStore`는 ADR/experiment ID 중복을 fail-closed 처리하고 artifact SHA-256을
  읽기 전에 검증한다.
- 기본 pytest 수집 범위는 smoke+legacy regression이며 `1960 passed`다.
- `pyproject.toml` 기반 wheel을 만들 수 있고 research 및 agent6 raw corpus는 wheel에
  포함되지 않는다. GenOS 코드 ZIP도 canonical code/config만 포함하고 data/runtime/
  experiment/research root를 제외한다.
- `release-manifest-v1`, source-set 고정, index build provenance, embedding fingerprint,
  `ACTIVE_RELEASE` generation+hash CAS, append-only apply/rollback receipt 계약은 구현·검증돼 있다.
- root의 domain graph 정적 파일은 코드 ZIP에서 제거됐으며 권위 데이터 패키지로만 운반한다.

## 코드와 분리된 잔여 작업

1. Legal Graph compiler의 regex Requirement/Frame observation을 canonical `ACCEPTED`로
   자동 승격하는 경로는 별도 효과성 ADR에서 제거해야 한다. 조건·결과·효과·연결은
   observation→validator→명시 승인 경계를 거쳐야 하며, 이 변경은 검색 의미를 바꾸므로
   ADR-0166의 결정론적 경로 이행에 섞지 않는다.
2. GenOS host의 실제 activation/rollback smoke, 내부+외부 source-set 검색, ACL 누수와
   관찰 기간은 배포 작업이다. 사용자가 배포를 제외했으므로 이번 코드 작업에는 포함하지 않았다.

위 두 항목 전에는 제품 의미 배선이나 GenOS 활성 포인터를 변경하지 않는다.
