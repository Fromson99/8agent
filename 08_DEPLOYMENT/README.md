# 08_DEPLOYMENT

코드 ZIP과 데이터 release를 분리해 local·onsite·GenOS에 배포한다. 각 대상은 검증된
SourceSet, semantic generation, immutable index, MAIN generation, 코드 package hash,
ACL 및 provenance receipt가 모두 일치해야 활성화된다.

현재 최종 코드는 `GENOS/adr0185-code-main-g5-final.zip`, 활성화 결과는
`RELEASES/adr0181-v2-cutover/final-activation-receipt.json`, 실제 GenOS 검색 검증은
`RELEASES/adr0181-v2-cutover/post-cutover-smoke.json`에 고정했다.

`CI/ontology_pipeline_check.sh`는 동일 계약을 로컬과 CI에서 검사한다. rollback은 각
대상의 직전 활성 release로만 수행한다.

과거 `dataset-overlay-v1` 파일 복사 동기화는 폐기했다. 현재 배포 입력은
`CONFIG/dataset_sync/profiles.json`의 대상별 SourceSet과 활성 release store이며,
`DatasetPackage → SourceSet → immutable index → release activation` 순서만 사용한다.

현재 활성 code generation은 `20260904-code-v18`, MAIN은 generation 5다. ADR-0186의
mutable 구조 정리본은 API TestClient 호환성과 장기 legal-graph CI가 완료될 때까지 새
generation으로 발행하지 않는다. 발행 전 게이트는 `02_BACKEND/MIGRATION_BACKLOG.md`에
기록한다.
