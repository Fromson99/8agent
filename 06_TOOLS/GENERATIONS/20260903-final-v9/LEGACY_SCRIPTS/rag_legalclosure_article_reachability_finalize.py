#!/usr/bin/env python3
"""Finalize ADR-0091 manifests and human-readable indexes from sealed run-002."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger"
ARTIFACTS = ADR / "artifacts"
EXPERIMENT = ADR / "실험"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_dump(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def failure_label(row: dict) -> str:
    misses = [
        fate["fate"]
        for fate in row["graded_trace"]["article_fates"]
        if fate["fate"] != "PRESENTED"
    ]
    if not misses:
        return "없음"
    generated = misses.count("GENERATED_NOT_SELECTED")
    absent = misses.count("NOT_GENERATED")
    parts = []
    if generated:
        parts.append(f"생성 후 미선택 {generated}")
    if absent:
        parts.append(f"미생성 {absent}")
    return ", ".join(parts)


def update_experiment_manifest(run: dict, ledger_path: Path) -> None:
    path = EXPERIMENT / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    summary = run["summary"]
    run2 = next(item for item in manifest["runs"] if item["id"] == "run-002")
    run2["status"] = "complete"
    run2["sha256"] = sha256(ARTIFACTS / "run-002.json")

    manifest["retrieval_accounting"] = {
        "changed": True,
        "corpus_total": summary["corpus_article_roots"],
        "before_filter": 1018,
        "after_filter": 1000,
        "presented_total": summary["presented_total"],
        "presented_mean": summary["presented_mean"],
        "presented_p50": summary["presented_p50"],
        "presented_p95": summary["presented_p95"],
        "golden_recall": summary["article_instance_recall_at_20"],
        "selectivity": summary["selectivity"],
        "not_applicable_reason": None,
        "stage_ledger": {
            "mode": "measured",
            "schema_version": "retrieval-stage-ledger-v1",
            "accounting_unit": "case_id + canonical article-root coordinate",
            "summary_run_id": "run-002",
            "artifact_path": str(ledger_path.relative_to(ROOT)),
            "sha256": sha256(ledger_path),
            "not_applicable_reason": None,
        },
    }
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            "baseline": {
                "status": "historical-context-only",
                "source": "ADR-0088 corrected ADR-0064 baseline regrade",
                "gold_article_hits": 72,
                "gold_article_instances": 90,
                "case_all_gold_hits": 48,
                "cases": 61,
            },
            "traced-v2": {
                "status": "complete",
                "gold_article_hits": summary["gold_article_hits"],
                "gold_article_instances": summary["gold_article_instances"],
                "article_recall_at_20": summary["article_instance_recall_at_20"],
                "case_all_gold_hits": summary["case_all_gold_hits"],
                "cases": summary["cases"],
                "case_all_gold_recall_at_20": summary["case_all_gold_recall_at_20"],
                "gold_fates": summary["gold_fates"],
                "channels": summary["channels"],
                "criteria": summary["criteria"],
            },
        },
        "comparisons": [
            {
                "metric": "article_recall_at_20_historical_context",
                "baseline_value": 0.8,
                "candidate_value": summary["article_instance_recall_at_20"],
                "delta": round(summary["article_instance_recall_at_20"] - 0.8, 6),
                "causal_claim_allowed": False,
            },
            {
                "metric": "case_all_gold_recall_at_20_historical_context",
                "baseline_value": round(48 / 61, 6),
                "candidate_value": summary["case_all_gold_recall_at_20"],
                "delta": round(summary["case_all_gold_recall_at_20"] - 48 / 61, 6),
                "causal_claim_allowed": False,
            },
        ],
        "judge_disagreements": None,
        "usage": {
            "product_calls": summary["provider_usage"]["calls"],
            "judge_calls": 0,
            "input_tokens": summary["provider_usage"]["input_tokens"],
            "output_tokens": summary["provider_usage"]["output_tokens"],
            "provider_errors": summary["provider_usage"]["errors"],
        },
        "latency": {
            "wall_ms_p50": summary["wall_ms_p50"],
            "wall_ms_p95": summary["wall_ms_p95"],
            "trace_ms_p50": summary["trace_ms_p50"],
            "trace_ms_p95": summary["trace_ms_p95"],
            "provider_duration_ms_total": summary["provider_usage"]["provider_duration_ms"],
        },
        "error_taxonomy": [
            {"kind": key, "count": value}
            for key, value in sorted(summary["event_reason_counts"].items())
        ],
    }
    json_dump(path, manifest)


def update_artifact_manifest() -> None:
    descriptions = {
        "input-lock.json": "동결 데이터셋·좌표·실행 조건",
        "run-001.json": "61건 원시 제품 호출·capture·초기 사후 집계(집계 오류로 invalid)",
        "retrieval-stage-ledger-run-001.json": "run-001 초기 단계 원장",
        "run-002.json": "봉인 capture를 교정 집계한 정본",
        "retrieval-stage-ledger-run-002.json": "run-002 canonical 단계별 회수·탈락 원장",
        "channel-metrics-run-002.json": "채널별 raw·selected·first-touch·단독 기여",
        "failure-metrics-run-002.json": "표준 실패 사유 및 gold 운명 집계",
        "reachability-report-run-002.md": "사람이 읽는 V2 Golden 도달성 보고서",
        "test-results.md": "구현 및 직접 소비 경로 회귀 테스트 결과",
    }
    names = list(descriptions)
    files = []
    for name in names:
        path = ARTIFACTS / name
        files.append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "description": descriptions[name],
                "contains_raw_prompts_and_outputs": name == "run-001.json",
            }
        )
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text("utf-8"))
    manifest["files"] = files
    json_dump(ARTIFACTS / "manifest.json", manifest)


def update_experiment_index(run: dict) -> None:
    rows = []
    for row in run["rows"]:
        number = row["number"]
        case_id = row["case_id"]
        hits = sum(item["hit"] for item in row["gold_results"])
        total = len(row["gold_results"])
        verdict = "전부 도달" if row["case_all_gold_hit"] else "일부/미도달"
        filename = f"질문-{number:03d}-{case_id}.md"
        rows.append(
            f"| {number:03d} | `{case_id}` | `run-002` | {hits}/{total} ({verdict}) | "
            f"비짝 역사비교 | {failure_label(row)} | [{filename}]({filename}) |"
        )
    content = f"""# ADR-0091 실험 질문 인덱스

> 61개 질문의 실제 제품 입력·출력·호출 usage·canonical stage 원장·사후 exact 채점을 보존한다.

## 작업과 계보

- owner: `Codex`
- scope key: `legalclosure-v2-article-reachability-ledger`
- experiment ID: `ADR-0091-experiment-v1`
- parent arm: `ADR-0088-experiment-v1/corrected-v2-regrade`
- `run-001`: 제품 호출 61건의 봉인 capture 정본. D 선택 기여 사후 집계 오류 때문에 run 상태는 invalid.
- `run-002`: 제품·judge 재호출 없이 동일 capture를 교정 재집계한 최종 채점 정본.

## 질문 인덱스

| 번호 | case ID | run | traced-v2 판정 | 비교 성격 | 실패 유형 | 파일 |
|---:|---|---|---|---|---|---|
{chr(10).join(rows)}

## 집계

- decisive 조항: **{run['summary']['gold_article_hits']}/{run['summary']['gold_article_instances']}**
  (`recall@20={run['summary']['article_instance_recall_at_20']:.6f}`)
- 모든 decisive 조항을 회수한 질문: **{run['summary']['case_all_gold_hits']}/{run['summary']['cases']}**
  (`{run['summary']['case_all_gold_recall_at_20']:.6f}`)
- gold 운명: 제시 71, 생성 후 미선택 14, 미생성 5
- 판정은 LLM judge가 아닌 `doc_id + canonical article-root node` exact join이다.
- 기준선 72/90·48/61은 다른 시점의 역사적 frozen 실행이므로 paired 인과 비교로 사용하지 않는다.

## 정본

- 기계 판독 실행: `../artifacts/run-002.json`
- 단계 원장: `../artifacts/retrieval-stage-ledger-run-002.json`
- 채널·실패 요약: `../artifacts/reachability-report-run-002.md`
- 설계·계보·hash: [manifest.json](manifest.json)
"""
    (EXPERIMENT / "README.md").write_text(content, encoding="utf-8")


def update_reachability_report(run: dict, ledger_path: Path) -> None:
    summary = run["summary"]
    channel_rows = []
    for channel, metric in summary["channels"].items():
        density = (
            metric["selected_gold_hits"] / metric["selected_candidates"]
            if metric["selected_candidates"]
            else 0.0
        )
        channel_rows.append(
            f"| {channel} | {metric['raw_candidates']:,} | {metric['selected_candidates']:,} | "
            f"{metric['raw_gold_hits']} | {metric['selected_gold_hits']} | "
            f"{metric['first_touch']} | {metric['unique_contribution']} | {density:.2%} |"
        )

    miss_rows = []
    for row in run["rows"]:
        gold_meta = {
            (item["doc_id"], item["node"]): item for item in row["gold_results"]
        }
        stages = row["graded_trace"]["stage_ledger"]["stages"]
        for fate in row["graded_trace"]["article_fates"]:
            if fate["fate"] == "PRESENTED":
                continue
            identity = (fate["identity"]["doc_id"], fate["identity"]["node"])
            drops = []
            for stage in stages:
                for receipt in stage.get("discard_receipts", []):
                    candidate = receipt["identity"]
                    if (candidate["doc_id"], candidate["node"]) == identity:
                        drops.append(f"{stage['stage_id']}:{receipt['reason']}")
            meta = gold_meta[identity]
            raw = ", ".join(fate["raw_channels"]) or "없음"
            reason = "; ".join(drops) or "모든 채널에서 canonical 후보 미생성"
            miss_rows.append(
                f"| `{row['case_id']}` | {meta['law']} {meta['article']} | {fate['fate']} | "
                f"{raw} | {reason} |"
            )

    ledger = json.loads(ledger_path.read_text("utf-8"))
    stages = ledger["runs"][0]["arms"][0]["aggregate"]["stages"]
    stage_order = ledger["runs"][0]["arms"][0]["aggregate"]["stage_ids"]
    stage_rows = []
    for stage_id in stage_order:
        stage = stages[stage_id]
        reasons = ", ".join(
            f"{key}={value:,}" for key, value in stage["discard_reason_counts"].items()
        ) or "-"
        stage_rows.append(
            f"| {stage_id} | {stage['kind']} | {stage['before_count']:,}→{stage['after_count']:,} | "
            f"+{stage['added_count']:,}/-{stage['discarded_count']:,} | "
            f"{stage['gold_before']}→{stage['gold_after']} | "
            f"+{stage['gold_added']}/-{stage['gold_discarded']} | "
            f"{stage['golden_recall']:.2%} | {reasons} |"
        )

    content = f"""# LegalClosure v2 V2 Golden 조항 도달 보고서

## 최종 점수

- 질문: {summary['cases']}건
- decisive gold: **{summary['gold_article_hits']}/{summary['gold_article_instances']}**
- article recall@20: **{summary['article_instance_recall_at_20']:.6f}**
- all-gold case recall@20: **{summary['case_all_gold_hits']}/{summary['cases']}**
  ({summary['case_all_gold_recall_at_20']:.6f})
- 지연 p50/p95: {summary['wall_ms_p50']:.3f}/{summary['wall_ms_p95']:.3f}ms
- trace p50/p95: {summary['trace_ms_p50']:.3f}/{summary['trace_ms_p95']:.3f}ms

## 채널 기여

`선택 gold 밀도`는 selected 후보 중 이 90개 decisive gold가 차지한 비율이며 일반적인
relevance precision은 아니다. 여러 채널이 같은 gold를 잡을 수 있어 채널별 gold 합은 90을 넘는다.

| 채널 | raw 후보 | 선택 후보 | raw gold | 선택 gold | first-touch | 단독 기여 | 선택 gold 밀도 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(channel_rows)}

## 단계별 회수·탈락

| stage | kind | 후보 before→after | added/discarded | gold before→after | gold gain/loss | recall | 주요 탈락 이유 |
|---|---|---:|---:|---:|---:|---:|---|
{chr(10).join(stage_rows)}

## 최종 미도달 19개 조항 전수

| case | 미도달 정답 조항 | 운명 | raw 도달 채널 | 실제 탈락 단계와 표준 사유 |
|---|---|---|---|---|
{chr(10).join(miss_rows)}

## 해석

- 제시 71, 생성 후 미선택 14, 미생성 5다.
- D 관계 확장은 ABC 합집합의 gold를 69→81로 늘렸지만 relation cap에서 10개를 다시
  잃어 최종 71이 됐다. D가 새로 생성한 gold 12개 중 채널 선택 생존은 2개다.
- required merge의 20개 cap은 일반 후보 18개를 제거했지만 gold 손실은 0이다.
- reference rescue는 이 61건에서 후보·gold 기여가 모두 0이다. 다른 질문군에서의 무용성을
  뜻하지는 않으며 이 데이터셋에 한정된 관찰이다.
- 역사 기준 72/90·48/61과 현재 71/90·44/61의 차이는 서로 다른 시점의 실행이므로
  trace 자체의 회귀라는 인과 결론을 내릴 수 없다. trace on/off 결정론 fixture는 동일 좌표다.

## 호출·비용 계측

- 제품 호출 {summary['provider_usage']['calls']:,}회, judge 호출 0회
- 입력 {summary['provider_usage']['input_tokens']:,} tokens, 출력 {summary['provider_usage']['output_tokens']:,} tokens
- provider 오류 {summary['provider_usage']['errors']}건, provider 누적 duration
  {summary['provider_usage']['provider_duration_ms']:,}ms
"""
    (ARTIFACTS / "reachability-report-run-002.md").write_text(content, encoding="utf-8")


def main() -> None:
    run_path = ARTIFACTS / "run-002.json"
    ledger_path = ARTIFACTS / "retrieval-stage-ledger-run-002.json"
    run = json.loads(run_path.read_text("utf-8"))
    update_experiment_manifest(run, ledger_path)
    update_experiment_index(run)
    update_reachability_report(run, ledger_path)
    update_artifact_manifest()
    print("finalized ADR-0091 manifests and experiment index")


if __name__ == "__main__":
    main()
