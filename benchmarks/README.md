# 독립 벤치마크 카탈로그

이 디렉터리는 재사용 가능한 **측정 계약**을 관리한다. ADR은 가설·판정·운영 결정을,
benchmark는 데이터셋·입력·채점·격리·비교 가능 범위와 실행 목록을 맡는다.

```text
benchmarks/
├── registry.json
├── SCHEMA.md
└── <benchmark-id>/
    ├── README.md
    ├── benchmark.json
    └── runs/
        └── <run-id>.json
```

## 책임 경계

- `benchmark.json`: 장기간 재사용할 데이터셋·입력·채점·격리 계약
- `runs/*.json`: 한 번의 실행이 사용한 정확한 ADR experiment/arm과 artifact hash
- ADR: 왜 실행했는지, 사전 기준, 결과 해석, 채택·기각·운영 결정
- 원시 답변·judge 출력: 실행 ADR의 artifacts에 단일 정본으로 보존
- `registry.json`: 현재 discoverable한 benchmark와 lifecycle 상태

benchmark 디렉터리에 원시 결과를 복제하지 않는다. 실행 영수증이 ADR 원본의 path, byte,
SHA-256을 가리킨다. 따라서 benchmark 카탈로그를 정리해도 ADR 감사 기록은 바뀌지 않고,
ADR을 완료해도 benchmark 정의는 후속 run에서 재사용할 수 있다.

## 특이 benchmark 분류

`specializations`는 한 benchmark의 비정상적 조건을 숨기지 않고 닫힌 태그로 드러낸다.

- `question_only`: system·검색·근거 문맥 없이 질문만 입력
- `oracle_context`: 정답 조문이나 oracle evidence를 직접 입력
- `model_knowledge_ceiling`: 제품이 아닌 모델 자체의 지식 상한
- `retrieval_only`: 답변 생성 없이 회수만 측정
- `stress`: 의도적으로 어려운 소표본
- `holdout`: 설계·튜닝에서 분리한 데이터
- `product_isolated`: 출력이 제품 context·사용자 답변에 들어갈 수 없음
- `dual_judge`: 둘 이상의 독립 judge 계약

새 태그가 필요하면 임의 문자열을 바로 추가하지 말고 `SCHEMA.md`와 validator를 먼저
개정한다. 특이조건은 이름만 붙이지 않고 `input_contract`, `scoring_contract`,
`isolation_contract`에 기계 판독 가능한 값으로도 기록한다.

## 새 benchmark와 run 추가 절차

1. 저장소 ADR 절차로 작업 범위를 선점하고 데이터·입력·채점 기준을 결과 전에 동결한다.
2. 새 `benchmark_id` 또는 기존 benchmark의 새 version을 만든다. 완료된 version은 덮어쓰지 않는다.
3. 실행은 ADR에서 수행하고 질문별 원문과 provider 응답을 ADR artifacts에 보존한다.
4. `runs/<run-id>.json`에 정확한 `experiment_id/arm_id`, ADR manifest hash, 모든 artifact hash를 기록한다.
5. `benchmark.json`과 `registry.json`에 run/manifest hash를 갱신한다.
6. 검증한다.

```bash
.venv/bin/python scripts/benchmark_registry.py validate
.venv/bin/python scripts/benchmark_registry.py list
```

## 점수 비교 규칙

두 run은 benchmark ID가 같아도 `comparability_key`, dataset combined hash, primary metric,
judge model·prompt contract가 모두 같을 때만 같은 리더보드 값으로 직접 비교한다. 하나라도
다르면 서로 다른 측정으로 표시하고 ADR에서 제한을 설명한다. in-sample, probe,
`decision_eligible=false`인 결과는 운영 승격 근거가 아니다.

