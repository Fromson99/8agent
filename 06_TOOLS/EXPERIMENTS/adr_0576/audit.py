"""Join frozen synthetic gold to completed ADR-0576 product traces offline."""
import hashlib
import json
from pathlib import Path
import statistics

from harness import R, A, write, sha

RUN = A / "artifacts/run-001"
ARMS = ("baseline", "guide_direct", "guide_compact")
SOURCE_UNIT = {
    "article:bbb3b79da72c6250f25c3377": 0,
    "article:81a39be87217e43e1e1050ae": 1,
    "article:cb13b431255156f36ff5fdc4": 2,
}
SCHEMA = "retrieval-stage-ledger-v1"
UNIT = "case_id + canonical article-root coordinate"


def read(path):
    return json.loads(path.read_text())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identities(values):
    return [json.loads(value) for value in sorted(set(values))]


def coordinates(source_ids):
    return identities(encoded({"doc_id": "d", "node": SOURCE_UNIT[source_id]})
                      for source_id in source_ids if source_id in SOURCE_UNIT)


def stage(plan, before, after, gold, reason):
    before, after, gold = set(map(encoded, before)), set(map(encoded, after)), set(map(encoded, gold))
    added, discarded = after - before, before - after
    receipts = [{"identity": json.loads(value), "reason": reason} for value in sorted(discarded)]
    return {**plan, "executed": True, "skip_reason": "",
            "before": identities(before), "added": identities(added),
            "discarded": identities(discarded), "after": identities(after),
            "before_count": len(before), "added_count": len(added),
            "discarded_count": len(discarded), "after_count": len(after),
            "occurrence_counts": {"before": len(before), "after": len(after),
                                  "canonical_collapsed_before": 0, "canonical_collapsed_after": 0},
            "discard_receipts": receipts,
            "discard_reason_counts": {reason: len(discarded)} if discarded else {},
            "gold_total": len(gold), "gold_before": len(gold & before),
            "gold_added": len(gold & added), "gold_discarded": len(gold & discarded),
            "gold_after": len(gold & after),
            "golden_recall": len(gold & after) / len(gold) if gold else None,
            "gold_before_identities": identities(gold & before),
            "gold_added_identities": identities(gold & added),
            "gold_after_identities": identities(gold & after),
            "discarded_gold": [receipt for receipt in receipts
                               if encoded(receipt["identity"]) in gold]}


def main():
    m = read(A / "실험/manifest.json")
    cases = read(A / "artifacts/design/cases.json")
    gold = read(A / "artifacts/design/gold.json")["cases"]
    result = read(RUN / "result.json")
    assert result["status"] == "complete" and len(result["results"]) == 12
    rows = {(row["case_id"], row["arm"]):
            read(RUN / "cases" / row["case_id"] / row["arm"] / "result.json")
            for row in result["results"]}
    assert len(rows) == 12
    ledger = {"schema_version": SCHEMA, "adr_id": m["adr_id"],
              "experiment_id": m["experiment_id"], "accounting_unit": UNIT,
              "computed_post_selection": True, "gold_visible_to_product": False,
              "runs": [{"run_id": "run-001", "arms": []}],
              "audit": {"classification": "SYNTHETIC",
                        "gold_sha256": sha(A / "artifacts/design/gold.json"),
                        "source_units": SOURCE_UNIT,
                        "read_stage": "SOURCE_RECALL_POOL.read_complete",
                        "selection_stage": "BOUNDED_SOURCE_SELECTION.final_ids",
                        "answer_input_stage": "HTTP assembly.context"}}
    grades = []
    summary = {}
    retrieval = m["retrieval_accounting"]
    for arm in ARMS:
        plan = m["design"]["retrieval_stage_plan"]["stages_by_arm"][arm]
        ledger_cases = []
        arm_rows = []
        for case in cases:
            row = rows[(case["id"], arm)]
            arm_rows.append(row)
            required_ids = gold[case["id"]]["required_source_ids"]
            required = coordinates(required_ids)
            scope = coordinates(SOURCE_UNIT)
            scope_event = row.get("journal", {}).get("scope") or {}
            allowed = coordinates(scope_event.get("allowed_node_ids", SOURCE_UNIT))
            read_ids = row.get("journal", {}).get("read_complete", [])
            selected_ids = row.get("journal", {}).get("selected_ids", [])
            presented_ids = [value["id"] for value in row.get("assembly", {}).get("context", [])]
            cited_ids = {source_id for claim in row.get("answer", {}).get("claims", [])
                         for source_id in claim.get("source_ids", [])}
            evidence_pass = (row["status"] == "ANSWER"
                             and set(required_ids) <= set(read_ids)
                             and set(required_ids) <= set(presented_ids)
                             and set(required_ids) <= cited_ids)
            grade = {"case_id": case["id"], "arm": arm,
                     "status": row["status"], "required_source_ids": required_ids,
                     "read_complete_ids": read_ids, "presented_ids": presented_ids,
                     "cited_ids": sorted(cited_ids), "source_citation_pass": evidence_pass,
                     "answer_text": row.get("answer", {}).get("text"),
                     "unresolved": row.get("answer", {}).get("unresolved", []),
                     "direct_events": row.get("journal", {}).get("direct_events", 0),
                     "fallback_events": row.get("journal", {}).get("fallback_events", 0),
                     "fulltext_rank_calls": row["fulltext_rank_calls"]}
            grades.append(grade)
            source, ontology, recall, selection, answer_input = (
                scope, allowed, coordinates(read_ids), coordinates(selected_ids), coordinates(presented_ids))
            stages = [stage(plan[0], [], source, required, "REQUEST_DOCUMENT_SCOPE"),
                      stage(plan[1], source, ontology, required, "PURPOSE_SCOPE_FILTER"),
                      stage(plan[2], ontology, recall, required, "NOT_READ_BY_RECALL"),
                      stage(plan[3], recall, selection, required, "MODEL_NOT_SELECTED"),
                      stage(plan[4], selection, answer_input, required, "NOT_IN_ANSWER_INPUT")]
            ledger_cases.append({"schema_version": SCHEMA, "computed_post_selection": True,
                                 "gold_visible_to_product": False, "accounting_unit": UNIT,
                                 "arm_id": arm, "case_id": case["id"],
                                 "gold_total": len(required), "gold_identities": required,
                                 "stages": stages,
                                 "audit": {"result_path": str((RUN / "cases" / case["id"] / arm / "result.json").relative_to(R)),
                                           "direct_events": grade["direct_events"],
                                           "fallback_events": grade["fallback_events"],
                                           "fulltext_rank_calls": row["fulltext_rank_calls"]}})
        counts = [value["stages"][-1]["after_count"] for value in ledger_cases]
        total_gold = sum(value["gold_total"] for value in ledger_cases)
        metrics = {"presented_total": sum(counts), "presented_mean": statistics.mean(counts),
                   "presented_p50": statistics.median(counts),
                   "presented_p95": sorted(counts)[round((len(counts) - 1) * .95)],
                   "golden_recall": sum(value["stages"][-1]["gold_after"] for value in ledger_cases) / total_gold,
                   "selectivity": statistics.mean(counts) / len(SOURCE_UNIT)}
        ledger["runs"][0]["arms"].append({"arm_id": arm,
                                           "declared_stage_ids": [item["stage_id"] for item in plan],
                                           "cases": ledger_cases, "aggregate": metrics})
        for key, value in metrics.items():
            if not isinstance(retrieval.get(key), dict):
                retrieval[key] = {}
            retrieval[key][arm] = value
        usage = [item for row in arm_rows for item in row["usage"]]
        summary[arm] = {"completed": sum(row["status"] == "ANSWER" for row in arm_rows),
                        "source_citation_pass": sum(grade["source_citation_pass"] for grade in grades if grade["arm"] == arm),
                        "total_seconds": sum(row["seconds"] for row in arm_rows),
                        "mean_seconds": statistics.mean(row["seconds"] for row in arm_rows),
                        "calls": sum(row["calls"] for row in arm_rows),
                        "fulltext_rank_calls": sum(row["fulltext_rank_calls"] for row in arm_rows),
                        "direct_events": sum(row["journal"].get("direct_events", 0) for row in arm_rows),
                        "fallback_events": sum(row["journal"].get("fallback_events", 0) for row in arm_rows),
                        "first_call_input_tokens": sum(row["usage"][0]["input_tokens"] for row in arm_rows if row["usage"]),
                        "input_tokens": sum(item.get("input_tokens") or 0 for item in usage),
                        "output_tokens": sum(item.get("output_tokens") or 0 for item in usage),
                        "cost_usd": sum(item.get("cost_usd") or 0 for item in usage),
                        **metrics}
    ledger["artifact_sha256"] = hashlib.sha256(encoded(ledger).encode()).hexdigest()
    write(RUN / "retrieval-stage-ledger.json", ledger)
    retrieval.update(corpus_total=len(SOURCE_UNIT),
                     before_filter={arm: len(SOURCE_UNIT) * len(cases) for arm in ARMS},
                     after_filter={arm: sum(value["stages"][1]["after_count"] for value in next(a for a in ledger["runs"][0]["arms"] if a["arm_id"] == arm)["cases"]) for arm in ARMS})
    retrieval["stage_ledger"].update(artifact_path=str((RUN / "retrieval-stage-ledger.json").relative_to(R)),
                                      sha256=sha(RUN / "retrieval-stage-ledger.json"))
    guide_hit = {"S01", "S02", "S03"}
    guide_gate = {arm: all(rows[(case_id, arm)]["fulltext_rank_calls"] == 0
                               and rows[(case_id, arm)]["journal"].get("direct_events", 0) >= 1
                               for case_id in guide_hit) for arm in ARMS[1:]}
    control_gate = {arm: rows[("S04", arm)]["fulltext_rank_calls"] > 0
                             and rows[("S04", arm)]["journal"].get("direct_events", 0) == 0
                    for arm in ARMS[1:]}
    functional = {arm: summary[arm]["completed"] == 4 and summary[arm]["source_citation_pass"] == 4
                  for arm in ARMS}
    speed = {"guide_direct": summary["guide_direct"]["total_seconds"] <= summary["baseline"]["total_seconds"],
             "guide_compact": summary["guide_compact"]["total_seconds"] <= summary["guide_direct"]["total_seconds"]
             and summary["guide_compact"]["first_call_input_tokens"] < summary["guide_direct"]["first_call_input_tokens"]}
    decision = {"classification": "SYNTHETIC", "by_arm": summary, "grades": grades,
                "guide_hit_rank_zero": guide_gate, "purpose_mismatch_fallback": control_gate,
                "functional_source_citation": functional, "speed_gate": speed,
                "candidate_gate": {arm: functional[arm] and guide_gate[arm] and control_gate[arm] and speed[arm]
                                   for arm in ARMS[1:]},
                "answer_semantic_review": "PENDING_MANUAL_REVIEW",
                "large_corpus_speed_certified": False,
                "legal_quality_certified": False, "genos_speed_certified": False,
                "main_changed": False}
    write(RUN / "offline-grade.json", decision)
    m["runs"][0].update(status="complete", artifact_path=str((RUN / "result.json").relative_to(R)),
                         sha256=sha(RUN / "result.json"))
    m["results"].update(status="complete", by_arm=summary, comparisons=[decision],
                         judge_disagreements=0, usage={arm: {key: summary[arm][key] for key in
                             ("calls", "input_tokens", "output_tokens", "cost_usd")} for arm in ARMS},
                         latency={arm: {key: summary[arm][key] for key in
                             ("total_seconds", "mean_seconds")} for arm in ARMS},
                         error_taxonomy=[grade for grade in grades if not grade["source_citation_pass"]])
    for question, case in zip(m["questions"], cases):
        case_rows = {arm: rows[(case["id"], arm)] for arm in ARMS}
        case_ledger = [next(value for value in arm["cases"] if value["case_id"] == case["id"])
                       for arm in ledger["runs"][0]["arms"]]
        lines = ["# " + m["adr_id"] + " / " + case["id"], "",
                 "## 1. 실행 메타", "", "```json",
                 json.dumps({"run_id": "run-001", "case_id": case["id"], "arms": ARMS,
                             "source_status": "exact", "model": m["llm_policy"]["required_model"]},
                            ensure_ascii=False, indent=2), "```", "",
                 "## 2. 사용자 질문 원문", "", case["question"], "",
                 "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "", "```json",
                 json.dumps(gold[case["id"]], ensure_ascii=False, indent=2), "```", "",
                 "## 4. 제품 입력을 구성한 원값", "", "```json",
                 json.dumps({"source_units": SOURCE_UNIT, "results": case_rows},
                            ensure_ascii=False, indent=2), "```", "",
                 "### 회수·탈락 단계 원장 — run·arm별", "", "```json",
                 json.dumps(case_ledger, ensure_ascii=False, indent=2), "```", "",
                 "## 5. 제품 모델 호출 — run·arm별 실제 원문", ""]
        for arm in ARMS:
            calls = sorted((RUN / "cases" / case["id"] / arm / "calls").glob("call-*"))
            lines.extend(["### " + arm, ""])
            for call in calls:
                payload = {str(path.relative_to(R)): read(path) for path in sorted(call.glob("*.json"))}
                lines.extend(["```json", json.dumps(payload, ensure_ascii=False, indent=2), "```", ""])
        lines.extend(["## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
                      "별도 호출은 없다. 검색 계획·원문 선별·답변 작성의 실제 모델 요청과 응답은 위 제품 호출에 포함한다.", "",
                      "## 7. 채점 호출과 반복 판정", "",
                      "오프라인 결정적 원문·인용 검사 1회. 모델 판정 호출 없음.", "",
                      "## 8. 사례 최종 판정", "", "```json",
                      json.dumps([grade for grade in grades if grade["case_id"] == case["id"]],
                                 ensure_ascii=False, indent=2), "```", "",
                      "독립 법률 품질 판정은 수행하지 않았다.", ""])
        path = A / "실험" / question["file"]
        path.write_text("\n".join(lines))
        question["sha256"] = sha(path)
    write(A / "실험/manifest.json", m)
    print(json.dumps({key: value for key, value in decision.items() if key != "grades"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
