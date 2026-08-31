# Repository agent instructions

Read `CLAUDE.md` for repository architecture, legal-wiki grounding, and operational constraints.

## Mandatory experiment workflow

Before running any experiment, evaluation, A/B test, ablation, probe, holdout, replay, regrade, or
model/prompt/router/retrieval effectiveness comparison, read both files completely and follow them:

1. `docs/adr/EXPERIMENT_AGENT_PROMPT.md`
2. `docs/adr/STANDARD.md`

Before editing implementation files or running the first experimental call, create the ADR with
`scripts/adr_structure.py new` to atomically claim its number and scope. Check active reservations
first; never create another ADR for a scope already marked `in_progress`. Preserve the generated
owner, Codex task/session ID, `created_at`, `work_started_at`, `updated_at`, status, and append-only
reservation events. Then freeze the hypothesis, criteria, dataset, arms, lineage, and run record.
When combining completed ADR branches, create a new multi-parent ADR: reference every exact
`experiment_id/arm_id` with `merged_from`, and record per-parent adopted/excluded parts, conflicts,
resolutions, invariants, and rollback parent. Record non-lineage dependencies or conflicts in the
hashed `relationships` list rather than pretending they are experiment parents.
Merging ADRs never changes MAIN by itself. Promote only an Accepted, out-of-sample,
decision-eligible completed arm through `scripts/rag_main_promotion.py`; freeze source/code/receipt
hashes, require explicit `--confirm-main`, keep every promoted code path behind a rollback switch,
and preserve the generation and append-only apply/rollback receipt.
Every product-path LLM role must use
`claude-haiku-4-5-20251001`; offline evaluators may use only the role-separated allowlist in the
standard and may never change a user-visible answer.
ADR-0054의 `role-separated-v2`로 사전 동결한 `offline_benchmark_candidate`는 제품과 완전히
격리된 모델 상한 비교에만 허용하며, 그 출력은 제품 context나 사용자 답변을 바꿀 수 없다.

This rule applies to the primary agent and any delegated agent. A delegated run must return its exact
inputs, outputs, usage, latency, and artifact paths to the primary agent for the same ADR; it must not
create an unlinked experiment record.
