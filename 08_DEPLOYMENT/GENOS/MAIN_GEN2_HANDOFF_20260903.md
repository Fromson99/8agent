# MAIN generation 2 · GENOS handoff

- MAIN: `legalclosure-v2`, generation `2`
- active promotion: `main-20260902-931aac8d0691`
- switches: `internal_compliance_compiler_v1=true`, `sourceset_content_snapshot=true`
- canonical transition chain: `9d3074d25be31fece3c3e3abf695b0a8cf81f4bb21205cb3275e41fd54bc4de2`
- code artifacts: 72/72 hash·size 일치
- ADR-0158/0159 final validation: 통과
- contract holdout: 16/16, 회귀 0
- repository tests: 1,937 passed, 5 warnings
- WSL boundary: 통과

## 반입물

- code ZIP: `var/out/ship/8agent-genos-code-main-gen2-20260903.zip`
  - SHA-256: `c6d76ef4f95e57a2f5220bca3a78c9fb771f7d4d03e771537b8c8bb5efbee63f`
  - 12,841,138 bytes / 694 files / verify 통과
- external dataset set: `var/out/ship/dataset-sync-external-main-gen2-final-20260903`
  - `SYNC_SET.json` SHA-256: `dcbdfbb1d0677a2ab2da01e7625ec982b1b211aa268d7e6699f3c02f30505c5b`
  - 132,158,412 bytes / 21 files / verify 통과
  - common-runtime: `723f91fc57a6ccd895653c2086d9f98af8f185bbbee92f2f2cbcee4ae28d278c`
  - common-evaluation: `854d0e1dde1dc852d45988ad5b3ab82721a72869831f7e800a390c99c40dd70d`
  - overlay-mock contract: `4c49df90f51be57859c1e8fdf78d99b160c97d6e34a037678a5436e3500dc1d2`
- data-tier inventory: `var/reports/data-tier-inventory-main-gen2-20260903.json`
  - SHA-256: `67abf3b6645b599213064a2ace69ba4b171ea1504a1121a36d580509d0650a56`
  - 6,868/6,868 files classified

## 외부 환경에서 남은 단계

원격 배포 자체는 아직 수행하지 않았다. 현재 호스트에는 `genos` Git remote,
`LAWRAG_RELEASE_STORE`, 영속 볼륨 경로, GenOS LLM/Embedding endpoint·key가 없다.
GENOS 안에서 반입물을 설치하고 immutable release store와 검증 영수증을 만든 뒤 CAS pointer를
활성화해야 한다. 이 값 없이 `service.py` health가 fail-closed하는 것이 의도된 동작이다.
