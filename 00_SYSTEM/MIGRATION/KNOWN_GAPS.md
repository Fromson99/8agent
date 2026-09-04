# Bridge 단계 차단 목록

`LAWRAG_LAYOUT_VERSION=v2`를 활성화하기 전에 닫아야 하는 사항이다.

## 2026-09-03 현재 확인된 진행 상태

- `data`, backend, frontend, tests, scripts, ADR, ADR 외 docs, runtime/archive와
  supporting roots를 하나의 287항목 plan으로 묶어 `copy-verify-0`,
  `dual-read-compare`, `final-verify` 영수증을 발행했다.
- 제품 API·검색 core·수집/인제스트 pipeline의 주요 `data/var` 기본값은
  `lawrag.platform.paths`를 통하며, 기본 v1 경로 비회귀 테스트를 통과했다.
- 최신 backend/tests/scripts shadow는
  `20260903-code-shadows-refresh.*.json` 세대로 다시 고정했다.
- final-verify는 완료됐지만 activation receipt는 발행·설정하지 않았다. 따라서
  기본 v1과 legacy root는 그대로 유지된다.

1. `data/`, `docs/`, `scripts/`, `lawrag/`, `var/`, `artifacts/` 물리 경로 참조를
   `lawrag.platform.workspace` 또는 도메인별 Settings API로 교체한다.
   제품 API·검색 core·수집 pipeline의 1차 교체는 끝났지만, agent6·배포 도구·
   일부 legacy CLI와 문서/ADR resolver inventory가 남아 있다.
2. `scripts.*` 재사용 import를 설치 가능한 `lawrag` 패키지로 옮긴다.
3. `pyproject.toml` 패키지 계약과 GENOS install/build 절차를 확정한다.
4. 완료 ADR의 path/hash 계보를 보존하는 `ExperimentStore` ID resolver와
   append-only migration receipt를 만든다.
5. `DatasetPackage` 각 row의 dataset/build provenance가 graph·index·hit·RuleBundle까지
   유지되는 projection adapter를 만든다.
6. 현재 Legal Graph compiler가 regex Requirement/Frame observation을 source-backed라는
   이유만으로 canonical `ACCEPTED` 의미로 승격하는 경로를 제거한다.
   규칙은 단서 존재·span·주변 문맥만 hint로 만들고 조건·결과·효과·
   연결은 LLM observation·validator·승인 경계를 거친다.
7. 검증된 `release-manifest-v1`과 `release-activation-plan-v1`을 기반으로
   `ACTIVE_RELEASE` 단일 포인터의 compare-and-swap 활성화와 롤백 receipt를
   GENOS 영속 볼륨에 구현한다. SourceSet을 별도 가변 포인터로
   두지 않고 릴리스 내에 고정해 split-brain을 막는다.
8. 현재 index builder가 source-set hash·semantic generation·embedding model fingerprint를
   artifact manifest에 실제로 기록하게 한다. 릴리스 validator의 재사용 차단
   계약은 추가되었지만 기존 index에는 아직 fingerprint가 없다.
9. `ROOT_CLASSIFICATION.json`에 고정한 root DOCX/CSV/PNG/TXT와 legacy ADR
   목적지의 copy/dual-read는 완료했다. DOCX의 기존 golden provenance 경로를
   새 resolver에 연결하고 final-verify하기 전에는 원본을 제거하지 않는다.
10. 전체 회귀, GENOS package pack/verify, 내부+외부 source-set 검색,
    ACL 누수, ADR graph/hash 검증 후에만 strict target 모드를 켠다.
11. 현재 code ZIP에 호환성 때문에 남은
    `data/domain_graph/canonical.json`을 권위 데이터 패키지로 이행한다.
    `lawrag/research/`는 이미 production ZIP에서 제외한다.
12. v2 활성화 전 `code_ship.py`의 legacy `lawrag/scripts/config` 수집 root를
    `02_BACKEND/06_TOOLS/08_DEPLOYMENT`의 중앙 레이아웃 resolver로 교체한다.
13. **완료:** whole-root-only 계약을 partition-aware root binding v3로 확장했다.
    부모의 모든 direct child는 `covered_sources`, 중첩 logical root는
    `delegated_sources`, 허용 생성물은 `excluded_sources` 중 정확한 경로로 기록된다.
    최종 세대는 12/12 root와 287개 source/target을 한 receipt로 증명한다.

## 최종 활성화 전 남은 핵심 작업

- **완료:** backend 최신 target은 `migration_target("lawrag")`으로 선택하고
  `scripts/serve.sh`는 그 target의 부모만 app-dir로 사용한다. runtime 쓰기는
  `90_RUNTIME/{OUT,LOGS,...}` canonical bucket으로 분리했다. 전체 rehash는 explicit
  activation audit로 분리해 API import를 25초 timeout에서 1.75초로 줄였다.
- SourceSet runtime의 실제 내부+외부 조합, ACL 누수, index fingerprint를 검증한다.
- GENOS host에서 activation/rollback smoke와 관찰 기간을 통과한 뒤에만 legacy
  retirement receipt를 검토한다.
