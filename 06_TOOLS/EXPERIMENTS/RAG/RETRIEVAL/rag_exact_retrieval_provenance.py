#!/usr/bin/env python3
"""ADR-0050: test exact retrieval provenance in the final Haiku prompt."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
from typing import Any

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.llm import LLM  # noqa: E402
from scripts.adr_structure import HAIKU_MODEL, OPUS_MODEL, scaffold_adr  # noqa: E402
from scripts.rag_evaluator_calibration import SCHEMA as JUDGE_SCHEMA, SYSTEM as JUDGE_SYSTEM  # noqa: E402

ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0050-exact-retrieval-provenance"
SOURCE = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0048-legal-reasoning-causal-portfolio/artifacts/frozen-cases.json"
PARENT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0048-legal-reasoning-causal-portfolio/실험/manifest.json"
FROZEN = ADR / "artifacts/frozen-cases.json"
PRODUCT = ADR / "artifacts/product-results.json"
JUDGED = ADR / "artifacts/judged-results.json"
CORPUS = 17_370
ARMS = ("baseline", "exact-provenance")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_exchange(ex: Any) -> dict[str, Any]:
    value = ex.dump(); value["parsed"] = ex.parsed; return value


def call(llm: LLM, name: str, system: str, user: str, schema: dict[str, Any], model: str) -> dict[str, Any]:
    logs = []
    for _ in range(3):
        start = len(llm.log)
        parsed = llm.structured(name, system, user, schema, max_tokens=1800, effort="medium", model=model)
        logs.extend(dump_exchange(ex) for ex in llm.log[start:])
        if isinstance(parsed, dict):
            return {"request": {"call_name": name, "system": system, "user": user, "schema": schema, "model": model},
                    "output": dict(parsed), "exchanges": logs}
    raise RuntimeError(f"{name} failed")


def exact_trace(evidence: list[dict[str, Any]]) -> str:
    lines = [
        "[검색 provenance — 원 실행에 저장된 메타데이터; 법적 근거 아님]",
        f"- 현재 corpus 조문 root: {CORPUS:,}개",
        f"- 이 답변에 최종 제시된 조문: {len(evidence)}개 ({len(evidence)/CORPUS:.4%})",
        "- 아래 found_by_role·relation_reason·document·path는 최종 evidence 객체에 실제 저장된 값이다.",
    ]
    for ev in evidence:
        lines.append(
            f"- {ev.get('id')}: found_by_role={ev.get('role') or 'unrecorded'}; "
            f"relation_reason={ev.get('relation_reason') or 'unrecorded'}; "
            f"source={ev.get('experiment_source') or 'unrecorded'}; "
            f"document={ev.get('document')}; path={ev.get('path')}"
        )
    lines.extend([
        "- 최종 제시 전에 탈락한 전체 후보의 좌표·수·탈락 사유: unknown — 당시 전수 로그가 보존되지 않음.",
        "사용 규칙: provenance는 조문을 찾은 경로의 설명일 뿐 법률효과·권위·정답을 보증하지 않는다. "
        "role 이름만으로 결론을 내리지 말고 반드시 위 [컨텍스트] 원문에서 actor·조건·예외를 확인한다.",
    ])
    return "\n".join(lines)


def prepare() -> None:
    source = json.loads(SOURCE.read_text("utf-8"))
    cases = source["cases"]
    if not ADR.exists():
        scaffold_adr(ROOT / "07_DOCS/REFERENCE/adr", 50, "exact-retrieval-provenance", "최종 프롬프트 exact 검색 provenance",
                     "probe", [row["case_no"] for row in cases], branch_id="exact-provenance",
                     candidate_arms=["exact-provenance"], parent_manifest=PARENT,
                     parent_arm="retrieval-trace", parent_relation="extends", judge_model=OPUS_MODEL)
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps({"schema_version": "exact-provenance-frozen-v1",
                                  "source": str(SOURCE.relative_to(ROOT)), "source_sha256": sha(SOURCE),
                                  "selection_rule": "ADR-0048 동일 8건 전수", "cases": cases}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    path = ADR / "실험/manifest.json"; manifest = json.loads(path.read_text("utf-8"))
    manifest["experiment_id"] = "ADR-0050-exact-retrieval-provenance-v1"
    manifest["lineage"]["hypothesis_delta"] = "사후 분류가 아닌 실제 저장 role·relation_reason 검색 경로를 최종 prompt에 주면 지배규범 선택이 나아진다."
    manifest["design"].update({
        "hypothesis": "Haiku가 조문 원문뿐 아니라 왜 선택됐는지 exact provenance를 보면 검색 잡음에서 지배규범을 더 잘 고른다.",
        "primary_metric": "Opus 의미 정답/8, baseline 대비 신규정답·회귀, 입력 토큰",
        "success_criteria": "exact-provenance 신규정답 2 이상, 회귀 0, 오류 0",
        "failure_criteria": "신규정답 1 이하 또는 회귀 발생",
        "criteria_frozen_before_run": True,
    })
    for arm in manifest["design"]["arms"]:
        arm["changes"] = "full 원문" if arm["id"] == "baseline" else "동일 full 원문 + 저장된 role/relation_reason/document/path"
        arm["controls"] = "같은 질문·evidence·Haiku·Opus judge; provenance 유무만 변경"
    manifest["dataset"].update({"name": "ADR-0048 same frozen 8", "version": "v1", "frozen_source": str(FROZEN.relative_to(ROOT)),
                                "sha256": sha(FROZEN), "legal_version_checked": False, "reference_version_checked": False})
    manifest["llm_policy"]["llm_calls"] = [
        {"role": "answer", "class": "product", "model": HAIKU_MODEL, "repeats": 1},
        {"role": "semantic-judge", "class": "offline_evaluator", "model": OPUS_MODEL, "repeats": 1},
    ]
    manifest["runs"][0].update({"arm_ids": list(ARMS), "selection_rule": "동결 8건 × 2 arms contemporaneous generation",
                                  "artifact_path": str(JUDGED.relative_to(ROOT))})
    counts = [len(row["variants"]["full_original"]["evidence"]) for row in cases]
    manifest["retrieval_accounting"].update({"changed": True, "corpus_total": CORPUS, "before_filter": CORPUS,
        "after_filter": sum(counts), "presented_total": sum(counts), "presented_mean": statistics.mean(counts),
        "presented_p50": statistics.median(counts), "presented_p95": max(counts), "golden_recall": "8/8 diagnostic subset",
        "selectivity": round(statistics.mean(counts)/CORPUS, 8),
        "not_applicable_reason": "검색 재실행 없음; 탈락 전수 사유 unknown을 명시"})
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"prepared {ADR}")


def generate_case(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"): local.llm = LLM(model=HAIKU_MODEL)
    llm = local.llm; source = row["variants"]["full_original"]; req = source["request"]
    baseline = call(llm, f"adr50.{row['case_no']}.baseline", req["system"], req["user"], req["schema"], HAIKU_MODEL)
    baseline["evidence"] = source["evidence"]
    system = req["system"] + "\n⑦ [검색 provenance]는 근거가 아닌 경로 메타데이터다. 탈락 사유 unknown을 추정하지 않는다."
    user = req["user"] + "\n\n" + exact_trace(source["evidence"])
    trace = call(llm, f"adr50.{row['case_no']}.exact_provenance", system, user, req["schema"], HAIKU_MODEL)
    trace["evidence"] = source["evidence"]
    return {"case_no": row["case_no"], "question": row["question"], "reference_answer": row["reference_answer"],
            "arms": {"baseline": baseline, "exact-provenance": trace}}


def generate(workers: int) -> None:
    cases = json.loads(FROZEN.read_text("utf-8"))["cases"]; local = threading.local(); rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(generate_case, row, local): row for row in cases}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = future.result(); rows.append(item); print(f"[{i}/8] {item['case_no']} generated", flush=True)
    rows.sort(key=lambda row: row["case_no"])
    PRODUCT.write_text(json.dumps({"schema_version": "exact-provenance-product-v1", "rows": rows}, ensure_ascii=False, indent=2) + "\n", "utf-8")


def judge_case(row: dict[str, Any], local: threading.local) -> dict[str, Any]:
    if not hasattr(local, "llm"): local.llm = LLM(model=OPUS_MODEL)
    result = copy.deepcopy(row)
    for arm in ARMS:
        answer = result["arms"][arm]["output"]
        user = (f"[질문]\n{row['question']}\n\n[기준답변]\n{row['reference_answer']}\n\n"
                f"[시스템 답변]\nanswerable={answer.get('answerable')}\n{answer.get('answer')}\n\n법률 명제의 동일성을 판정한다.")
        result["arms"][arm]["judge"] = call(local.llm, f"adr50.{row['case_no']}.{arm}.judge", JUDGE_SYSTEM, user, JUDGE_SCHEMA, OPUS_MODEL)
    return result


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = {arm: [bool(row["arms"][arm]["judge"]["output"].get("correct")) for row in rows] for arm in ARMS}
    b, c = labels["baseline"], labels["exact-provenance"]
    usage = {}
    for arm in ARMS:
        exs = [ex for row in rows for ex in row["arms"][arm]["exchanges"]]
        usage[arm] = {"calls": len(exs), "input_tokens": sum(int((ex.get("usage") or {}).get("input_tokens", 0)) for ex in exs),
                      "output_tokens": sum(int((ex.get("usage") or {}).get("output_tokens", 0)) for ex in exs)}
    return {"correct": {arm: sum(v) for arm, v in labels.items()},
            "paired": {"new_correct": sum(y and not x for x, y in zip(b, c)), "regression": sum(x and not y for x, y in zip(b, c)),
                       "both_correct": sum(x and y for x, y in zip(b, c)), "both_wrong": sum(not x and not y for x, y in zip(b, c))},
            "usage": usage}


def judge(workers: int) -> None:
    source = json.loads(PRODUCT.read_text("utf-8"))["rows"]; local = threading.local(); rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(judge_case, row, local): row for row in source}
        for i, future in enumerate(concurrent.futures.as_completed(jobs), 1):
            item = future.result(); rows.append(item); print(f"[{i}/8] {item['case_no']} judged", flush=True)
    rows.sort(key=lambda row: row["case_no"]); result = summarize(rows)
    JUDGED.write_text(json.dumps({"schema_version": "exact-provenance-judged-v1", "summary": result, "rows": rows}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def question_md(row: dict[str, Any], number: int) -> str:
    calls = [{"arm": arm, "request": row["arms"][arm]["request"], "output": row["arms"][arm]["output"], "exchanges": row["arms"][arm]["exchanges"]} for arm in ARMS]
    judges = [{"arm": arm, **row["arms"][arm]["judge"]} for arm in ARMS]
    decisions = "\n".join(f"| run-001 | {arm} | {row['arms'][arm]['judge']['output'].get('correct')} | {row['arms'][arm]['judge']['output'].get('reason')} | {'-' if row['arms'][arm]['judge']['output'].get('correct') else 'governing_rule_selection'} |" for arm in ARMS)
    return f"""# 질문 {number:03d} — {row['case_no']}

## 1. 실행 메타

- ADR: `ADR-0050`; experiment: `ADR-0050-exact-retrieval-provenance-v1`; case: `{row['case_no']}`; run: `run-001`
- 원본 상태: 질문·evidence·role·relation_reason·호출은 exact; 탈락 전수 사유는 unavailable
- 제품 `{HAIKU_MODEL}`; 평가 `{OPUS_MODEL}`

## 2. 사용자 질문 원문

```text
{row['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{row['reference_answer']}
```

## 4. 제품 입력을 구성한 원값

```json
{json.dumps({'corpus_total': CORPUS, 'evidence': row['arms']['baseline']['evidence'], 'dropped_candidates_and_reasons': None, 'reason': 'not preserved'}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

```json
{json.dumps(calls, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

```json
{json.dumps(judges, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{decisions}

- 사전 비교: exact-provenance vs baseline
- 공통 실패: `governing_rule_selection`
- 사람 직접원인: 없음
- 다음 분기: holdout에서 실제 selector 전수 trace를 새로 계측
"""


def finalize() -> None:
    blob = json.loads(JUDGED.read_text("utf-8")); rows = blob["rows"]; result = blob["summary"]
    mp = ADR / "실험/manifest.json"; manifest = json.loads(mp.read_text("utf-8")); qmap = {q["case_id"]: q for q in manifest["questions"]}
    for i, row in enumerate(rows, 1):
        path = ADR / "실험" / qmap[row["case_no"]]["file"]; path.write_text(question_md(row, i), "utf-8"); qmap[row["case_no"]]["sha256"] = sha(path)
    manifest["runs"][0].update({"status": "complete", "sha256": sha(JUDGED)})
    manifest["results"] = {"status": "complete", "by_arm": result["correct"], "comparisons": result["paired"],
                           "judge_disagreements": None, "usage": result["usage"], "latency": {},
                           "error_taxonomy": ["governing_rule_selection", "condition_exception", "unsupported_inference", "judge_or_gold_error"]}
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    write_docs(rows, result)
    files=[]
    for path, role in ((FROZEN,"frozen"),(PRODUCT,"product"),(JUDGED,"judged"),(Path(__file__),"runner")):
        files.append({"path":str(path.relative_to(ROOT)),"sha256":sha(path),"bytes":path.stat().st_size,"role":role})
    (ADR/"artifacts/manifest.json").write_text(json.dumps({"schema_version":"adr-artifacts-v1","adr_id":"ADR-0050","files":files},ensure_ascii=False,indent=2)+"\n","utf-8")


def write_docs(rows: list[dict[str, Any]], result: dict[str, Any]) -> None:
    matrix="\n".join(f"| `{row['case_no']}` | {row['arms']['baseline']['judge']['output']['correct']} | {row['arms']['exact-provenance']['judge']['output']['correct']} |" for row in rows)
    text=f"""---
adr_id: ADR-0050
title: 최종 프롬프트 exact 검색 provenance
status: Proposed
decision_date: 2026-08-26
phase: probe
in_sample: true
decision_eligible: false
main_wiring: unchanged
---

# ADR-0050: 최종 프롬프트 exact 검색 provenance

## 1. 결정 요약

같은 8건에서 실제 저장된 검색 role·relation_reason·문서 경로를 최종 prompt에 추가했다. 결과에 따라 메인 배선은 유지한다.

## 2. 문제와 변경 전 구조

ADR-0048 trace는 제시 여부 exact와 사후 Haiku 탈락 분류가 섞였다. 원래 검색 경로 메타데이터만의 효과를 분리해야 했다.

## 3. 가설과 사전 판정 기준

### 가설

exact provenance가 지배규범 선택을 돕는다.

### 성공 기준

신규정답 2 이상·회귀 0.

### 반증 기준

신규정답 1 이하 또는 회귀 발생.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | full 원문 | 질문·evidence·모델 | 기준 |
| exact-provenance | 저장 role/relation_reason/document/path 추가 | 동일 | 검색 과정 효과 |

탈락 후보의 전수 사유는 보존되지 않아 `unknown`으로 명시했다.

## 5. 데이터·모델·재현성

ADR-0048 동일 8건, 두 arm 모두 같은 실행창에서 Haiku 생성, Opus 단일 평가다.

## 6. 결과

| arm | 정답/8 | 입력 토큰 |
|---|---:|---:|
| baseline | {result['correct']['baseline']}/8 | {result['usage']['baseline']['input_tokens']} |
| exact-provenance | {result['correct']['exact-provenance']}/8 | {result['usage']['exact-provenance']['input_tokens']} |

- 신규정답 {result['paired']['new_correct']}, 회귀 {result['paired']['regression']}, 둘 다 정답 {result['paired']['both_correct']}, 둘 다 오답 {result['paired']['both_wrong']}.

## 7. 사례별 오류 분석

| case | baseline | exact provenance |
|---|---:|---:|
{matrix}

질문별 원문은 [실험 인덱스](실험/README.md)에 있다.

## 8. 비용·지연·회수 규모

조문 root {CORPUS:,}개 중 평균 16.25개(0.0936%)를 제시했다. provenance arm의 추가 토큰은 결과표에 기록했다.

## 9. 해석

role·relation_reason는 검색 경로 설명이지 법률의 지배관계 자체가 아니다. 개선이 없으면 최종 prompt 장식보다 selector 단계에서 증명형 관계를 사용해야 한다.

## 10. 한계와 일반화 가능 범위

인샘플 8건 단회다. 탈락 후보 전수 trace가 없어 '무엇이 왜 탈락했는지'의 완전한 실험은 아니다.

## 11. 운영 결정·롤백 조건

성공선 미달이면 배선하지 않는다. 실제 selector 전수 계측을 새 데이터 수집 때 추가한다.

## 12. 재현 명령

```bash
.venv/bin/python scripts/rag_exact_retrieval_provenance.py prepare
.venv/bin/python scripts/rag_exact_retrieval_provenance.py generate --workers 2
.venv/bin/python scripts/rag_exact_retrieval_provenance.py judge --workers 1
.venv/bin/python scripts/rag_exact_retrieval_provenance.py finalize
.venv/bin/python scripts/adr_structure.py validate --path docs/adr/ADR-0050-exact-retrieval-provenance --final
```

- 원시 산출물: [artifacts/manifest.json](artifacts/manifest.json)
- 질문 hash: [실험/manifest.json](실험/manifest.json)
"""
    (ADR/"README.md").write_text(text,"utf-8")
    manifest=json.loads((ADR/"실험/manifest.json").read_text("utf-8")); files={q["case_id"]:q["file"] for q in manifest["questions"]}
    lines=["# ADR-0050 질문 인덱스","","| 번호 | case | baseline | provenance | 파일 |","|---:|---|---:|---:|---|"]
    for i,row in enumerate(rows,1): lines.append(f"| {i:03d} | `{row['case_no']}` | {row['arms']['baseline']['judge']['output']['correct']} | {row['arms']['exact-provenance']['judge']['output']['correct']} | [{files[row['case_no']]}]({files[row['case_no']]}) |")
    lines.extend(["","- exact metadata만 사용했고 탈락 사유는 unknown으로 보존했다.","- phase=probe, in_sample=true, decision_eligible=false."])
    (ADR/"실험/README.md").write_text("\n".join(lines)+"\n","utf-8")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("prepare"); g=sub.add_parser("generate"); g.add_argument("--workers",type=int,choices=range(1,5),default=2)
    j=sub.add_parser("judge"); j.add_argument("--workers",type=int,choices=range(1,3),default=1); sub.add_parser("finalize")
    args=parser.parse_args()
    if args.command=="prepare": prepare()
    elif args.command=="generate": generate(args.workers)
    elif args.command=="judge": judge(args.workers)
    else: finalize()
    return 0

if __name__=="__main__": raise SystemExit(main())
