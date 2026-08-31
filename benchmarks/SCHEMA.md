# Benchmark registry v1 계약

## `registry.json`

- `schema_version`: `benchmark-registry-v1`
- `benchmarks[]`: `benchmark_id`, `version`, `status`, `manifest_path`, `manifest_sha256`,
  `manifest_bytes`, `benchmark_class`, `specializations`, `latest_run_id`

registry에 없는 `benchmarks/*/benchmark.json`은 orphan으로 거부한다. 같은 ID/version 또는
manifest path 중복도 거부한다.

## `benchmark.json`

- identity: `benchmark_id`, 양의 정수 `version`, `title`, `status`, `owner`
- classification: `benchmark_class`, 닫힌 `specializations`, `comparability_key`
- scope: `purpose`, `decision_eligible`, `limitations`
- contracts: `dataset`, `input_contract`, `scoring_contract`, `isolation_contract`
- provenance: `adr_links[]`
- executions: `runs[]`의 path·SHA-256·byte

`dataset.sources[]`는 source path·SHA-256·byte·case count를 가진다. `adr_links[]`의
`execution_provenance`는 정확한 ADR experiment와 `arm_id` 또는 닫힌 `arm_ids`를 가져야 하며
validator가 실제 manifest의 모든 arm 존재와 hash를 확인한다.

## `runs/*.json`

- identity: `benchmark_id`, `benchmark_version`, `run_id`, `status`
- provenance: `adr_ref`의 ADR manifest path·hash·`experiment_id`와 `arm_id` 또는 `arm_ids`
- artifacts: 원본 path·SHA-256·byte와 역할
- metrics: benchmark scoring contract에 따른 결과
- decision: 결과의 기준 충족 여부; 채택·기각 결정의 정본은 ADR

run은 원시 답변을 담지 않는다. 원시 결과를 가진 ADR artifact를 hash로 참조한다.
