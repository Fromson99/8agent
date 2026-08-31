# AX Experiment Studio

8-AGENT와 완전히 분리된 프론트엔드 프로젝트다. 저장소의 법률 RAG 데이터와 ADR 실험을
`Dataset → Target → Evaluator → Run → Gate → Release` 계약으로 읽어 실험 계보를 보여준다.

## 현재 데이터 연결

- `data/review/golden_holdout_formal.json` — formal-v3, 113 cases
- `data/review/golden_mix2080_v3.json` — mix-v3, 51 cases
- `data/review/golden_v2_run7.json` — legacy run import, 44 cases
- `data/corpus` — 3,118 canonical corpus artifacts
- `data/wiki` — 1,218 wiki artifacts + 129 ledger events

현재 Sites 배포판에는 위 경로의 metadata snapshot만 포함된다. 실제 평가 실행은 기존
8-AGENT API 또는 별도 on-prem runner adapter가 맡고, Studio는 실행 전에 ADR과 frozen
manifest가 존재하는지 확인하는 제어계층으로 동작해야 한다.

## 실행 계약

실제 runner를 연결할 때는 저장소 루트의 `docs/adr/EXPERIMENT_AGENT_PROMPT.md`와
`docs/adr/STANDARD.md`를 반드시 적용한다. Studio의 새 실험 UI는 다음 정보가 모두 고정되지
않으면 Run 요청을 만들지 않는다.

1. ADR / experiment ID
2. falsifiable hypothesis
3. primary metric and guardrails
4. dataset version and split
5. baseline and candidate arm
6. code, model, prompt, ontology lineage
7. immutable run record path

## Local

```bash
npm run dev
npm run build
```

`GET /api/catalog`은 현재 연결된 workspace data catalog snapshot을 반환한다.
