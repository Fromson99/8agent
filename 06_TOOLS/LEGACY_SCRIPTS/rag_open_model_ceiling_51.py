#!/usr/bin/env python3
"""ADR-0056: cm-core 51건의 정답 조문 전문 입력 모델 상한 비교."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.llm import LLM, load_env  # noqa: E402
from lawrag.core.rag.index import Index  # noqa: E402
from scripts import rag_open_model_ceiling as pilot  # noqa: E402


ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0056-cm-core-51-open-model-ceiling"
ART = ADR / "artifacts"
EXP = ADR / "실험"
SOURCE = ROOT / "01_DATA/review/cm_core_e2e_v1.json"
MODELS = pilot.MODELS
QWEN_MODEL = pilot.QWEN_MODEL
JUDGE_MODEL = pilot.JUDGE_MODEL
JUDGE_SYSTEM = pilot.JUDGE_SYSTEM
JUDGE_SCHEMA = pilot.JUDGE_SCHEMA
LOCK = threading.Lock()
PROGRESS = {"answers": 0, "judges": 0}

ANSWER_SYSTEM = (
    "너는 문서 질의응답 보조자다. [컨텍스트]는 이번 질문에 해당하는 정답 조문의 "
    "전문이다. 이것만 근거로 한국어로 답한다.\n"
    "지켜야 할 규칙(위반은 곧 오답):\n"
    "① 수치·조항·명칭은 컨텍스트에 실제로 있을 때만 인용한다. 없으면 일반 지식으로 "
    "채우지 말고 '제공된 조문에는 없다'고 밝힌다.\n"
    "② 결론을 먼저 1~3문장으로 쓰고, 그 뒤에 근거와 필요한 조건·예외를 설명한다.\n"
    "③ 질문이 요구한 수치·기간·요건·예외를 빠뜨리지 않는다.\n"
    "④ 문서 좌표나 refs 목록을 출력하지 말고 답변 문장만 작성한다.\n"
    "⑤ 제공된 조문만으로 답할 수 없을 때만 answerable=false로 두고, 어떤 자료가 더 "
    "필요한지 짧게 안내한다."
)
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answerable": {"type": "boolean"},
    },
    "required": ["answer", "answerable"],
    "additionalProperties": False,
}

# cm-045/046의 동결 corpus에는 이 신설 조문만 빠져 있다. 51건을 제외 없이
# 실행하기 위해 국가법령정보센터 현행 조문(시행 2026-07-23)을 전문 그대로 고정한다.
COMMERCIAL_ACT_341_4 = """제341조의4(자기주식의 소각의무 등) ① 회사가 자기주식을 취득한 때에는 그 취득한 날부터 1년 이내에 소각하여야 한다.

② 제1항에도 불구하고 다음 각 호의 어느 하나에 해당하는 경우로서 회사가 자기주식보유처분계획을 작성하여 주주총회의 승인을 받은 때에는 그 승인된 계획에 따라 자기주식을 보유 또는 처분할 수 있다.

1. 회사가 각 주주에게 그가 가진 주식 수에 비례하여 균등한 조건으로 처분하는 경우

2. 회사가 제340조의2 또는 제542조의3에 따라 주식매수선택권을 부여하는 등 임직원 보상의 목적으로 활용하는 경우

3. 회사가 「근로복지기본법」에 따라 우리사주매수선택권을 부여하는 등 우리사주제도 실시의 목적으로 활용하는 경우

4. 회사가 제360조의2제2항, 제360조의15제2항, 제523조제3호 등 법령에서 정하는 바에 따라 활용하는 경우

5. 회사가 신기술의 도입, 재무구조의 개선 등 회사의 경영상 목적을 달성하기 위하여 필요한 경우로서 제434조에 따른 주주총회의 결의로 정관에 그 사유를 규정한 경우

③ 회사는 제2항에 따른 자기주식보유처분계획을 매년 주주총회에서 승인받아야 한다.

④ 제2항에 따른 자기주식보유처분계획에는 다음 각 호의 사항을 기재하고 이사 전원이 기명날인 또는 서명하여야 한다.

1. 자기주식의 보유 또는 처분 목적

2. 보유 또는 처분 대상이 되는 자기주식의 종류와 수, 취득방법

3. 보유 개시시점 및 예정된 처분시점을 기준으로 하는 다음 각 목의 사항

가. 자기주식의 종류와 수, 취득방법

나. 발행주식총수에서 자기주식을 제외한 나머지 주식의 종류와 수

다. 발행주식총수 대비 자기주식 비율의 변화

4. 예정된 보유 기간

5. 예정된 처분 시기

[본조신설 2026. 3. 6.]"""
COMMERCIAL_ACT_SOURCE = (
    "https://www.law.go.kr/LSW/lsLinkCommonInfo.do?"
    "chrClsCd=010202&lsJoLnkSeq=1032337703"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def full_node_text(view, node: dict) -> str:
    lo, hi = node.get("span") or [0, 0]
    rows = []
    for block_id in range(lo, max(hi, lo + 1)):
        text = ((view.block_by_idx.get(block_id) or {}).get("text") or "").strip()
        if text:
            rows.append(text)
    return "\n".join(rows)


def resolve_evidence(idx: Index, case_id: str, article: dict) -> dict[str, Any]:
    view = idx.docs.get(str(article.get("doc_id") or ""))
    node = None
    if view is not None and article.get("node") is not None:
        node = view.by_id.get(int(article["node"]))
    if node is not None:
        text = full_node_text(view, node)
        if not text:
            raise RuntimeError(f"empty gold article: {case_id} {article}")
        return {
            "law": article["law"], "article": article["article"],
            "doc_id": article["doc_id"], "node": node["id"],
            "path": view.path(node["id"]), "text": text,
            "chars": len(text), "sha256": text_sha(text),
            "source_type": "frozen_structure_store",
            "revision": article.get("document_revision"),
            "enforcement": article.get("document_enforcement"),
        }
    if article.get("law") == "상법" and article.get("article") == "제341조의4":
        return {
            "law": "상법", "article": "제341조의4",
            "doc_id": article.get("doc_id"), "node": None,
            "path": "제4편 주식회사 ▸ 제2장 주식 ▸ 제341조의4 자기주식의 소각의무 등",
            "text": COMMERCIAL_ACT_341_4, "chars": len(COMMERCIAL_ACT_341_4),
            "sha256": text_sha(COMMERCIAL_ACT_341_4),
            "source_type": "official_law_go_kr_supplement",
            "source_url": COMMERCIAL_ACT_SOURCE,
            "revision": article.get("document_revision"),
            "enforcement": article.get("document_enforcement"),
        }
    raise RuntimeError(f"missing gold article: {case_id} {article}")


def prepare() -> None:
    load_env()
    for key, rel in (
        ("STRUCTURE_STORE", "01_DATA/structure"),
        ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
        ("GLOSSARY_STORE", "01_DATA/glossary.json"),
        ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ):
        os.environ.setdefault(key, str(ROOT / rel))
    idx = Index.load()
    source = read_json(SOURCE)
    cases = []
    source_counts: dict[str, int] = {}
    evidence_count = 0
    for source_case in source["cases"]:
        evidence = [resolve_evidence(idx, source_case["id"], row)
                    for row in source_case["expected_articles"]]
        for row in evidence:
            source_counts[row["source_type"]] = source_counts.get(row["source_type"], 0) + 1
        evidence_count += len(evidence)
        context = []
        for number, row in enumerate(evidence, 1):
            context.append(f"[{number}] {row['law']} ▸ {row['path']}\n{row['text']}")
        user = f"[질문]\n{source_case['question']}\n\n[컨텍스트]\n" + "\n\n".join(context)
        if "[기준답변]" in user or "[기준답변]" in ANSWER_SYSTEM:
            raise RuntimeError(f"reference label leak: {source_case['id']}")
        cases.append({
            "case_id": source_case["id"],
            "question": source_case["question"],
            "reference_answer": source_case["reference_answer"],
            "reference_answer_visibility": "offline_evaluator_only",
            "expected_articles": source_case["expected_articles"],
            "gold_evidence": evidence,
            "product_request": {
                "system": ANSWER_SYSTEM, "user": user, "schema": ANSWER_SCHEMA,
                "max_tokens": 12000, "effort": None,
                "temperature": {"openrouter": 0, "anthropic": "provider_default"},
            },
        })
    if len(cases) != 51 or evidence_count != 70:
        raise RuntimeError(f"unexpected suite size: {len(cases)} cases, {evidence_count} articles")
    frozen = {
        "schema_version": "open-model-ceiling-cm-core-51-frozen-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_rule": "cm_core_e2e_v1의 51건 전수; 각 case expected_articles 전문만 입력",
        "in_sample": True, "decision_eligible": False,
        "source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha(SOURCE),
        "case_count": 51, "expected_article_instances": 70,
        "evidence_source_counts": source_counts,
        "models": MODELS, "judge": JUDGE_MODEL, "judge_repeats": 1,
        "provider_error_retry": 1, "output_cap_tokens": 12000,
        "answer_schedule": "모델별 4 lane; case index modulo 4; global worker pool",
        "judge_order": "seed 5601 deterministic shuffle; model identity blind",
        "cases": cases,
    }
    write_json(ART / "frozen-cases.json", frozen)
    inventory = pilot.model_inventory()
    if {row["id"] for row in inventory["openrouter"]} != {QWEN_MODEL}:
        raise RuntimeError("Qwen inventory mismatch")
    expected_claude = {m["model"] for m in MODELS if m["provider"] == "anthropic"}
    if {row["id"] for row in inventory["anthropic"]} != expected_claude:
        raise RuntimeError("Anthropic inventory mismatch")
    write_json(ART / "model-inventory.json", inventory)
    coverage = {
        "cases": 51, "expected_article_instances": 70,
        "full_text_present": 70, "structure_store": source_counts.get("frozen_structure_store", 0),
        "official_supplement": source_counts.get("official_law_go_kr_supplement", 0),
        "excluded_cases": [], "reference_answer_leaks": 0,
    }
    write_json(ART / "coverage-preflight.json", coverage)
    print(json.dumps({
        "frozen_cases_sha256": sha(ART / "frozen-cases.json"),
        "model_inventory_sha256": sha(ART / "model-inventory.json"),
        "coverage_sha256": sha(ART / "coverage-preflight.json"),
        **coverage,
    }, ensure_ascii=False, indent=2))


def make_clients(lanes: int) -> dict[str, list[LLM]]:
    clients: dict[str, list[LLM]] = {}
    for spec in MODELS:
        os.environ["LLM_BACKEND"] = spec["provider"]
        clients[spec["arm_id"]] = [LLM(model=spec["model"]) for _ in range(lanes)]
    os.environ["LLM_BACKEND"] = "anthropic"
    return clients


def call_with_retry(client: LLM, **kwargs: Any) -> dict[str, Any]:
    attempts: list[dict] = []
    parsed = None
    thrown = None
    for _ in range(2):
        before = len(client.log)
        try:
            parsed = client.structured(**kwargs)
            attempts.extend(ex.dump() for ex in client.log[before:])
        except Exception as exc:  # provider transport error is part of the run record
            attempts.extend(ex.dump() for ex in client.log[before:])
            thrown = f"{type(exc).__name__}: {exc}"
        if parsed is not None:
            break
    error = None if parsed is not None else (
        thrown or (attempts[-1].get("error") if attempts else "unknown error"))
    return {"parsed": parsed, "attempts": attempts, "error": error}


def run_answers(workers: int, lanes: int) -> None:
    frozen = read_json(ART / "frozen-cases.json")
    out_path = ART / "product-results.json"
    out = read_json(out_path, {
        "schema_version": "open-model-ceiling-cm-core-51-products-v1",
        "run_id": "run-001", "results": {},
    })
    llms = make_clients(lanes)

    def one_lane(spec: dict[str, str], lane: int) -> str:
        arm = spec["arm_id"]
        client = llms[arm][lane]
        for idx in range(lane, len(frozen["cases"]), lanes):
            case = frozen["cases"][idx]
            key = f"{case['case_id']}::{arm}"
            with LOCK:
                if key in out["results"]:
                    continue
            req = case["product_request"]
            result = call_with_retry(
                client, kind=f"adr0056.{case['case_id']}.{arm}",
                system=req["system"], user=req["user"], schema=req["schema"],
                max_tokens=req["max_tokens"], effort=None,
            )
            row = {
                "case_id": case["case_id"], "arm_id": arm,
                "model": spec["model"], "provider": spec["provider"],
                "request_sha256": text_sha(json.dumps(req, ensure_ascii=False, sort_keys=True)),
                "output": result["parsed"], "provider_exchanges": result["attempts"],
                "error": result["error"],
            }
            with LOCK:
                out["results"][key] = row
                write_json(out_path, out)
                PROGRESS["answers"] += 1
                if PROGRESS["answers"] % 25 == 0:
                    print(f"answers: {len(out['results'])}/561", flush=True)
        return f"{arm}/lane-{lane}"

    tasks = [(spec, lane) for spec in MODELS for lane in range(lanes)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_lane, spec, lane) for spec, lane in tasks]
        for future in as_completed(futures):
            print(f"answer lane complete: {future.result()}", flush=True)
    print(f"answers complete: {len(out['results'])}/561", flush=True)


def judge_user(question: str, reference: str, answer: str) -> str:
    return (f"[질문]\n{question}\n\n[기준답변]\n{reference}\n\n"
            f"[시스템 답변]\n{answer}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")


def run_judges(workers: int) -> None:
    frozen = read_json(ART / "frozen-cases.json")
    products = read_json(ART / "product-results.json")
    out_path = ART / "judged-results.json"
    out = read_json(out_path, {
        "schema_version": "open-model-ceiling-cm-core-51-judges-v1",
        "run_id": "run-001", "judge_model": JUDGE_MODEL, "results": {},
    })
    cases = {row["case_id"]: row for row in frozen["cases"]}
    keys = sorted(products["results"])
    random.Random(5601).shuffle(keys)
    buckets = [keys[i::workers] for i in range(workers)]
    os.environ["LLM_BACKEND"] = "anthropic"
    clients = [LLM(model=JUDGE_MODEL) for _ in range(workers)]

    def one_bucket(bucket: list[str], worker_no: int) -> int:
        client = clients[worker_no]
        count = 0
        for key in bucket:
            product = products["results"][key]
            with LOCK:
                if key in out["results"]:
                    continue
            if product["error"] or not product["output"]:
                row = {
                    "case_id": product["case_id"], "arm_id": product["arm_id"],
                    "model": product["model"], "judge_model": JUDGE_MODEL,
                    "request": None, "output": None, "provider_exchanges": [],
                    "error": "product_call_failed",
                }
            else:
                case = cases[product["case_id"]]
                user = judge_user(case["question"], case["reference_answer"],
                                  product["output"]["answer"])
                result = call_with_retry(
                    client, kind=f"adr0056.judge.{product['case_id']}.{product['arm_id']}",
                    system=JUDGE_SYSTEM, user=user, schema=JUDGE_SCHEMA,
                    max_tokens=1800, effort="low",
                )
                row = {
                    "case_id": product["case_id"], "arm_id": product["arm_id"],
                    "model": product["model"], "judge_model": JUDGE_MODEL,
                    "request": {"system": JUDGE_SYSTEM, "user": user,
                                "schema": JUDGE_SCHEMA, "max_tokens": 1800,
                                "effort": "low"},
                    "output": result["parsed"], "provider_exchanges": result["attempts"],
                    "error": result["error"],
                }
            with LOCK:
                out["results"][key] = row
                write_json(out_path, out)
                PROGRESS["judges"] += 1
                if PROGRESS["judges"] % 25 == 0:
                    print(f"judges: {len(out['results'])}/561", flush=True)
            count += 1
        print(f"judge worker {worker_no} complete: {count}", flush=True)
        return count

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_bucket, bucket, i) for i, bucket in enumerate(buckets)]
        for future in as_completed(futures):
            future.result()
    print(f"judges complete: {len(out['results'])}/561", flush=True)


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))]


def exchange_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exchanges = [ex for row in rows for ex in row.get("provider_exchanges", [])]
    successful = [ex for ex in exchanges if not ex.get("error")]
    durations = [int(ex.get("dur_ms", 0)) for ex in successful]
    return {
        "calls": len(exchanges), "successful_calls": len(successful),
        "errors": sum(bool(ex.get("error")) for ex in exchanges),
        "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0))
                            for ex in exchanges),
        "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0))
                             for ex in exchanges),
        "duration_ms": sum(durations),
        "p50_ms": int(statistics.median(durations)) if durations else None,
        "p95_ms": percentile(durations, 0.95),
    }


def render_questions(frozen: dict, products: dict, judged: dict) -> list[dict]:
    questions = []
    EXP.mkdir(parents=True, exist_ok=True)
    for number, case in enumerate(frozen["cases"], 1):
        lines = [
            f"# ADR-0056 질문 {number:03d}: {case['case_id']}", "",
            "## 1. 실행 메타", "", "- run: `run-001`", "- phase: `probe/in_sample`",
            "- 비교 class: `offline_benchmark_candidate`", "- judge: `claude-opus-5`", "",
            "## 2. 사용자 질문 원문", "", case["question"], "",
            "## 3. 기준답변 — 채점 전용, 제품 입력 비공개", "", case["reference_answer"], "",
            "## 4. 제품 입력을 구성한 원값", "", "### system", "", "```text",
            case["product_request"]["system"], "```", "", "### user", "", "```text",
            case["product_request"]["user"], "```", "", "### schema", "", "```json",
            json.dumps(case["product_request"]["schema"], ensure_ascii=False, indent=2), "```", "",
            "## 5. 제품 모델 호출 — run·arm별 실제 원문", "",
        ]
        for spec in MODELS:
            key = f"{case['case_id']}::{spec['arm_id']}"
            p = products["results"][key]
            lines.extend([
                f"### arm `{spec['arm_id']}` — `{spec['model']}`", "", "```json",
                json.dumps(p, ensure_ascii=False, indent=2), "```", "",
            ])
        lines.extend([
            "## 6. 중간 LLM 호출 — router/compiler/verifier/repair", "",
            "없음. 정답 조문 전문을 답변 모델에 직접 제공한 격리 benchmark다.", "",
            "## 7. 채점 호출과 반복 판정", "",
        ])
        for spec in MODELS:
            key = f"{case['case_id']}::{spec['arm_id']}"
            j = judged["results"][key]
            lines.extend([
                f"### arm `{spec['arm_id']}` — Opus 5 blind judge", "", "```json",
                json.dumps(j, ensure_ascii=False, indent=2), "```", "",
            ])
        lines.extend(["## 8. 사례 최종 판정", "",
                      "| arm | correct | failure_type |", "|---|---:|---|"])
        for spec in MODELS:
            key = f"{case['case_id']}::{spec['arm_id']}"
            j = judged["results"][key]
            lines.append(
                f"| `{spec['arm_id']}` | `{(j.get('output') or {}).get('correct')}` | "
                f"`{(j.get('output') or {}).get('failure_type', 'call_error')}` |")
        lines.append("")
        path = EXP / f"질문-{number:03d}-{case['case_id']}.md"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        questions.append({"number": number, "case_id": case["case_id"],
                          "file": path.name, "sha256": sha(path)})
    return questions


def finalize() -> None:
    frozen = read_json(ART / "frozen-cases.json")
    products = read_json(ART / "product-results.json")
    judged = read_json(ART / "judged-results.json")
    if len(products["results"]) != 561 or len(judged["results"]) != 561:
        raise RuntimeError("cannot finalize before all 561 product and judge rows exist")
    by_arm: dict[str, Any] = {}
    for spec in MODELS:
        prows = [row for row in products["results"].values() if row["arm_id"] == spec["arm_id"]]
        jrows = [row for row in judged["results"].values() if row["arm_id"] == spec["arm_id"]]
        valid = [row for row in jrows if row.get("output") is not None]
        correct = sum(bool(row["output"].get("correct")) for row in valid)
        failure_types: dict[str, int] = {}
        for row in valid:
            ft = row["output"].get("failure_type", "other")
            failure_types[ft] = failure_types.get(ft, 0) + 1
        by_arm[spec["arm_id"]] = {
            "model": spec["model"], "provider": spec["provider"],
            "correct": correct, "total": 51, "judged": len(valid),
            "accuracy": round(correct / 51, 4),
            "product_errors": sum(bool(row.get("error")) for row in prows),
            "judge_errors": sum(bool(row.get("error")) for row in jrows),
            "product_usage": exchange_usage(prows), "judge_usage": exchange_usage(jrows),
            "failure_types": failure_types,
        }
    baseline = {row["case_id"]: bool((row.get("output") or {}).get("correct"))
                for row in judged["results"].values() if row["arm_id"] == "baseline"}
    comparisons = {}
    for spec in MODELS[1:]:
        rows = {row["case_id"]: bool((row.get("output") or {}).get("correct"))
                for row in judged["results"].values() if row["arm_id"] == spec["arm_id"]}
        counts = {"candidate_only": 0, "baseline_only_regression": 0,
                  "both_correct": 0, "both_wrong": 0}
        for case_id, b in baseline.items():
            c = rows[case_id]
            key = ("both_correct" if b and c else "baseline_only_regression" if b
                   else "candidate_only" if c else "both_wrong")
            counts[key] += 1
        counts["delta"] = counts["candidate_only"] - counts["baseline_only_regression"]
        comparisons[spec["arm_id"]] = counts
    qwen = by_arm["baseline"]["correct"]
    best_claude = max(row["correct"] for arm, row in by_arm.items() if arm != "baseline")
    run_complete = all(row["judged"] >= 50 for row in by_arm.values())
    summary = {
        "schema_version": "open-model-ceiling-cm-core-51-summary-v1",
        "run_id": "run-001",
        "definition": "OPEN 모델 성능 = 정답 조문 전문만 포함한 51건 입력에서 Opus 5가 판정한 정답률",
        "cases": 51, "models": 11, "answer_rows": 561, "judge_rows": 561,
        "hypothesis": {
            "qwen_at_least_40_of_51": qwen >= 40,
            "qwen_within_3_of_best_claude": best_claude - qwen <= 3,
            "each_arm_at_least_50_judged": run_complete,
            "supported": qwen >= 40 and best_claude - qwen <= 3 and run_complete,
            "qwen_correct": qwen, "best_claude_correct": best_claude,
        },
        "by_arm": by_arm, "comparisons_vs_qwen": comparisons,
        "judge_disagreements": None,
        "limitations": [
            "cm-core-51은 반복 사용된 인샘플 업무 질문 집합",
            "Opus 5 단일 judge이며 사람 확정 재감사 없음",
            "Opus 5 답변 arm은 동일 모델 judge의 self-preference 가능",
            "68개 조문 인스턴스는 frozen structure store, 누락 2개는 국가법령정보센터 현행 전문 보완",
        ],
    }
    write_json(ART / "summary.json", summary)
    questions = render_questions(frozen, products, judged)

    manifest_path = EXP / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["runs"][0].update({"status": "complete", "sha256": sha(ART / "summary.json")})
    manifest["results"] = {
        "status": "complete", "by_arm": by_arm,
        "comparisons": [{"baseline_arm": "baseline", "candidate_arm": arm, **row}
                        for arm, row in comparisons.items()],
        "judge_disagreements": None,
        "usage": {"answer_rows": 561, "judge_rows": 561},
        "latency": {arm: row["product_usage"] for arm, row in by_arm.items()},
        "error_taxonomy": sorted({ft for row in by_arm.values() for ft in row["failure_types"]}),
    }
    manifest["questions"] = questions
    write_json(manifest_path, manifest)

    index_lines = ["# ADR-0056 실험 기록", "", "- run: `run-001`", "- 51건 전수 × 11개 모델", ""]
    index_lines.extend(f"- [{q['case_id']}]({q['file']}) — `{q['sha256']}`" for q in questions)
    (EXP / "README.md").write_text("\n".join(index_lines) + "\n", "utf-8")

    artifact_files = [
        ("coverage-preflight.json", "51건·70개 정답 조문 전문 사전검사", False),
        ("frozen-cases.json", "동결된 51건 제품 입력과 evaluator-only 기준답변", True),
        ("model-inventory.json", "실행 전 OpenRouter·Anthropic 모델 inventory", False),
        ("product-results.json", "561개 답변 호출 원기록", True),
        ("judged-results.json", "Opus 5 blind judge 561개 원기록", True),
        ("summary.json", "모델별 성능·사용량·오류 집계", False),
    ]
    artifact_manifest = {
        "schema_version": "adr-artifacts-v1", "adr_id": "ADR-0056",
        "files": [{"path": str((ART / name).relative_to(ROOT)), "sha256": sha(ART / name),
                   "bytes": (ART / name).stat().st_size, "description": desc,
                   "contains_raw_prompts_and_outputs": raw}
                  for name, desc, raw in artifact_files],
    }
    write_json(ART / "manifest.json", artifact_manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "answers", "judge", "finalize"])
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--lanes", type=int, default=4)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "answers":
        run_answers(args.workers, args.lanes)
    elif args.command == "judge":
        run_judges(args.workers)
    else:
        finalize()


if __name__ == "__main__":
    main()
