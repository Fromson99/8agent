"""Render the completed ADR-0482 record from immutable run-002 artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import statistics


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
EXP = ADR / "실험"
ART = ADR / "artifacts"
RESULTS = ART / "run-002/results.json"
JUDGED = ART / "run-002/judged-results.json"
METRICS = ART / "run-002/metrics.json"
LEDGER = ART / "retrieval-stage-ledger-run-002.json"
ARMS = ("baseline", "source-first")


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, text: str) -> None:
    path.write_text(text if text.endswith("\n") else text + "\n")


def write_json(path: Path, value) -> None:
    write(path, json.dumps(value, ensure_ascii=False, indent=2))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def percentile(values, ratio):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))]


def stage_summary(arm_row: dict) -> list[dict]:
    output = []
    for sid in arm_row["declared_stage_ids"]:
        stages = [next(x for x in case["stages"] if x["stage_id"] == sid) for case in arm_row["cases"]]
        output.append(
            {
                "stage_id": sid,
                "kind": stages[0]["kind"],
                "before": sum(x["before_count"] for x in stages),
                "added": sum(x["added_count"] for x in stages),
                "discarded": sum(x["discarded_count"] for x in stages),
                "after": sum(x["after_count"] for x in stages),
                "gold_before": sum(x["gold_before"] for x in stages),
                "gold_added": sum(x["gold_added"] for x in stages),
                "gold_discarded": sum(x["gold_discarded"] for x in stages),
                "gold_after": sum(x["gold_after"] for x in stages),
                "gold_total": sum(x["gold_total"] for x in stages),
            }
        )
    return output


def make_manifest(results: dict, judged: dict, metrics: dict, ledger: dict) -> dict:
    manifest = read(EXP / "manifest.json")
    with sqlite3.connect(str(ROOT / "01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1/navigation/navigation.sqlite")) as con:
        scope = read(ADR / "product-cases.json")["public_scope_document_ids"]
        placeholders = ",".join("?" for _ in scope)
        corpus_total = con.execute(f"SELECT count(*) FROM source WHERE document_id IN ({placeholders})", scope).fetchone()[0]
    ledger_arms = {x["arm_id"]: x for x in ledger["runs"][0]["arms"]}
    retrieval = {}
    for arm in ARMS:
        cases = ledger_arms[arm]["cases"]
        # adr-experiment-v4 names these summary fields "presented", but its
        # validator binds them to the declared final stage (answer here).
        counts = [c["stages"][-1]["after_count"] for c in cases]
        retrieval[arm] = {
            "total": sum(counts),
            "mean": statistics.mean(counts),
            "p50": statistics.median(counts),
            "p95": percentile(counts, 0.95),
        }
    manifest["decision_eligible"] = True
    manifest["runs"][0].update(
        artifact_path=rel(ART / "run-001/results.partial.json"),
        sha256=sha(ART / "run-001/results.partial.json"),
    )
    manifest["runs"][1].update(purpose="repeat", status="complete", sha256=sha(RESULTS))
    manifest["dataset"]["legal_version_checked"] = False
    manifest["retrieval_accounting"].update(
        corpus_total=corpus_total,
        before_filter={arm: corpus_total for arm in ARMS},
        after_filter={arm: retrieval[arm]["total"] for arm in ARMS},
        presented_total={arm: retrieval[arm]["total"] for arm in ARMS},
        presented_mean={arm: round(retrieval[arm]["mean"], 4) for arm in ARMS},
        presented_p50={arm: retrieval[arm]["p50"] for arm in ARMS},
        presented_p95={arm: retrieval[arm]["p95"] for arm in ARMS},
        golden_recall={arm: metrics["by_arm"][arm]["answer_gold_recall"] for arm in ARMS},
        selectivity={arm: retrieval[arm]["mean"] / corpus_total for arm in ARMS},
    )
    manifest["retrieval_accounting"]["stage_ledger"].update(
        summary_run_id="run-002", artifact_path=rel(LEDGER), sha256=sha(LEDGER)
    )
    product_usage = {
        key: sum(metrics["by_arm"][arm]["usage"][key] for arm in ARMS)
        for key in ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens")
    }
    manifest["results"] = {
        "status": "complete",
        "by_arm": {
            arm: {
                key: metrics["by_arm"][arm][key]
                for key in (
                    "correct",
                    "total",
                    "errors",
                    "zero_claims",
                    "calls",
                    "latency_p50_seconds",
                    "latency_p95_seconds",
                    "presented_gold_recall",
                    "answer_gold_recall",
                    "failure_types",
                )
            }
            for arm in ARMS
        },
        "comparisons": [
            {
                "arms": list(ARMS),
                "metric": "blind_paired_semantic_correct",
                "baseline": metrics["by_arm"]["baseline"]["correct"],
                "candidate": metrics["by_arm"]["source-first"]["correct"],
                "delta": metrics["paired_delta"],
                "baseline_only_regressions": metrics["baseline_only_regressions"],
                "success": metrics["success"],
            }
        ],
        "judge_disagreements": None,
        "judge_disagreement_note": metrics["judge_note"],
        "usage": {
            "product_calls": sum(metrics["by_arm"][arm]["calls"] for arm in ARMS),
            "product": product_usage,
            "offline_evaluator": metrics["judge_usage"],
        },
        "latency": {
            arm: {
                "p50_seconds": metrics["by_arm"][arm]["latency_p50_seconds"],
                "p95_seconds": metrics["by_arm"][arm]["latency_p95_seconds"],
            }
            for arm in ARMS
        },
        "error_taxonomy": sorted(
            {
                failure
                for arm in ARMS
                for failure in metrics["by_arm"][arm]["failure_types"]
                if failure != "none"
            }
            | {"product_execution_error", "empty_selection_after_evidence"}
        ),
        "criteria": metrics["criteria"],
        "main_wiring": "unchanged",
    }
    return manifest


def raw_receipts(case_id: str, arm: str) -> str:
    base = ART / "run-002" / case_id / arm
    files = sorted(path for path in base.rglob("*.json") if path.is_file())
    return "\n".join(f"- `{rel(path)}` — `{sha(path)}`" for path in files)


def render_question(index: int, case: dict, gold: dict, result: dict, judged: dict, ledger: dict) -> str:
    cid = case["case_id"]
    gold_case = next(x for x in gold["cases"] if x["case_id"] == cid)
    ledger_arms = {x["arm_id"]: x for x in ledger["runs"][0]["arms"]}
    rows = []
    discarded = {}
    for arm in ARMS:
        case_row = next(x for x in ledger_arms[arm]["cases"] if x["case_id"] == cid)
        discarded[arm] = [x for stage in case_row["stages"] for x in stage["discarded_gold"]]
        for s in case_row["stages"]:
            rows.append(
                f"| run-002 | {arm} | {s['stage_id']} | {s['kind']} | {s['before_count']} | "
                f"{s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_before']} | "
                f"{s['gold_added']} | {s['gold_discarded']} | {s['gold_after']}/{s['gold_total']} | "
                f"{s['golden_recall'] if s['golden_recall'] is not None else 'N/A'} |"
            )
    answer_blocks = []
    receipt_blocks = []
    verdict_rows = []
    for arm in ARMS:
        row = result["cases"][cid][arm]
        answer = (((row.get("result") or {}).get("answer") or {}).get("text") or "[빈 답변]")
        if row.get("error"):
            answer = f"[실행 오류] {json.dumps(row['error'], ensure_ascii=False)}"
        answer_blocks.append(
            f"### run-002 / {arm} 최종 제품 출력\n\n```text\n{answer}\n```\n\n"
            f"- physical calls: `{row['physical_calls']}`\n- usage: `{json.dumps(row.get('usage', []), ensure_ascii=False)}`\n"
            f"- elapsed: `{row['seconds']}` seconds\n"
        )
        receipt_blocks.append(f"### run-002 / {arm} 원시 호출 파일과 SHA-256\n\n{raw_receipts(cid, arm)}\n")
        verdict = judged["cases"][cid]["by_arm"][arm]
        verdict_rows.append(
            f"| run-002 | {arm} | {'O' if verdict['correct'] else 'X'} | {verdict['reason']} | {verdict['failure_type']} |"
        )
    judge_base = ART / "run-002/judge" / cid
    judge_receipts = "\n".join(
        f"- `{rel(path)}` — `{sha(path)}`" for path in sorted(judge_base.rglob("*.json")) if path.is_file()
    )
    return f"""# 질문 {index:03d} — {cid}

## 1. 실행 메타

- ADR: `ADR-0482`
- experiment: `ADR-0482-experiment-v1`
- scored run: `run-002` (`run-001`은 adapter 결함으로 중단되어 미채점)
- 원본 상태: `exact`
- 제품·오프라인 평가 모델: `gemini-3.1-flash-lite`
- 실행 arm: `baseline`, `source-first`
- 제품 결과 hash: `{sha(RESULTS)}`

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{gold_case['reference_answer']}
```

- 결정 조문: `{json.dumps([{'law': x['law'], 'article': x['article']} for x in gold_case['gold_articles']], ensure_ascii=False)}`
- 기준답은 모든 제품 실행이 끝난 뒤 결합했다.

## 4. 제품 입력을 구성한 원값

- 제품 입력 정본: `{rel(ADR / 'product-cases.json')}` / `{sha(ADR / 'product-cases.json')}`
- gold 정본: `{rel(ADR / 'gold-cases.json')}` / `{sha(ADR / 'gold-cases.json')}`
- 현재 세대 좌표 변환: `{rel(ART / 'run-002/gold-coordinate-resolution.json')}`

### 회수·탈락 단계 원장 — run·arm별

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

```json
{json.dumps({'stage_ledger_artifact': rel(LEDGER), 'discarded_gold_and_reasons': discarded, 'gold_visible_to_product': False}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

{chr(10).join(answer_blocks)}

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

각 파일에 실제 system/user/schema, provider 원응답, structured output, usage가 보존되어 있다.

{chr(10).join(receipt_blocks)}

## 7. 채점 호출과 반복 판정

- 문항당 익명 A/B paired judge 1회, 반복·다수결 없음.
- 익명 순서: `{json.dumps(judged['cases'][cid]['anonymous_order'], ensure_ascii=False)}`
- 원시 judge 파일:

{judge_receipts}

## 8. 사례 최종 판정

| run | arm | 정답 | 판정 근거 | 실패 유형 |
|---|---|---:|---|---|
{chr(10).join(verdict_rows)}

- paired 분류: `둘 다 오답`
- 직접 관찰: source-first는 최종 선택·주장 0건이다. baseline도 기준답의 구체 결론 또는 핵심 조건을 완결하지 못했다.
- 다음 가설: 결정 조문을 제시한 뒤 선택 단계가 빈 결과로 붕괴하는 원인을 먼저 고치고, baseline은 질문별 법적 효과·예외 조건 종합을 강화해야 한다.
"""


def render_index(metrics: dict, ledger: dict) -> str:
    failures = []
    for cid in sorted(metrics["by_arm"]["baseline"]["by_case"], key=lambda x: x["case_id"]):
        case_id = cid["case_id"]
        b = next(x for x in metrics["by_arm"]["baseline"]["by_case"] if x["case_id"] == case_id)
        s = next(x for x in metrics["by_arm"]["source-first"]["by_case"] if x["case_id"] == case_id)
        failures.append((case_id, f"baseline={b['failure_type']}; source-first={s['failure_type']}"))
    question_rows = "\n".join(
        f"| {i:03d} | `{cid}` | `run-002` | baseline X / source-first X | 둘 다 오답 | {failure} | "
        f"[질문-{i:03d}-{cid}.md](질문-{i:03d}-{cid}.md) |"
        for i, (cid, failure) in enumerate(failures, 1)
    )
    stage_rows = []
    for arm in ledger["runs"][0]["arms"]:
        for row in stage_summary(arm):
            stage_rows.append(
                f"| run-002 | {arm['arm_id']} | {row['stage_id']} | {row['kind']} | "
                f"{row['before']}→{row['after']} | {row['gold_before']}→{row['gold_after']} | "
                f"+{row['gold_added']}/-{row['gold_discarded']} | {row['gold_after']}/{row['gold_total']} | "
                f"not_carried_to_next_recorded_stage |"
            )
    return f"""# ADR-0482 실험 질문 인덱스

> 비CM FSC 난문 10건의 제품 실행, 회수 단계, 익명 paired judge 기록이다.

## 계보와 상태

- experiment: `ADR-0482-experiment-v1`
- phase / sample: `holdout` / `in_sample=false`
- parent: `ADR-0480-experiment-v1/explicit-link`
- run-001: adapter 결함으로 중단·미채점
- run-002: 전체 10문항×2 arm 완료
- 결정: `Rejected`, MAIN unchanged

## Arm

| arm | 역할 | 변경점 | 고정 조건 |
|---|---|---|---|
| baseline | 기준 | frozen document-navigation-v1 | 질문·세대·범위·Gemini·예산 동일 |
| source-first | 후보 | frozen source-first action-feedback + linked evidence | 질문·세대·범위·Gemini·예산 동일, 문항별 reviewed coordinate 없음 |

## 질문 인덱스

| 번호 | case ID | run | 판정 | paired 분류 | 실패 유형 | 파일 |
|---:|---|---|---|---|---|---|
{question_rows}

## 집계

- baseline: `0/10`, source-first: `0/10`, delta `0`
- source-first 최종 주장 0건 문항: `10/10`
- baseline-only regressions: `0`; 둘 다 오답: `10`
- 단일 judge라 불일치율은 측정하지 않았다.

## 단계별 회수·탈락 집계

| run | arm | stage | kind | 후보 before→after | gold before→after | gold gain/loss | micro count | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---|
{chr(10).join(stage_rows)}

기계 판독 정본은 [manifest.json](manifest.json), 회수 원장은
[`retrieval-stage-ledger-run-002.json`](../artifacts/retrieval-stage-ledger-run-002.json)이다.
"""


def render_readme(manifest: dict, metrics: dict, ledger: dict) -> str:
    b = metrics["by_arm"]["baseline"]
    s = metrics["by_arm"]["source-first"]
    stages = []
    for arm in ledger["runs"][0]["arms"]:
        for row in stage_summary(arm):
            stages.append(
                f"| run-002 | {arm['arm_id']} | {row['stage_id']} | {row['kind']} | {row['before']}→{row['after']} | "
                f"+{row['added']} / -{row['discarded']} | {row['gold_before']}→{row['gold_after']} | "
                f"+{row['gold_added']} / -{row['gold_discarded']} | {row['gold_after']/row['gold_total']:.1%} |"
            )
    return f"""---
adr_id: ADR-0482
title: 원문 중심 RAG FSC 난문 10건 분리평가와 MAIN 승격 판정
status: Rejected
decision_date: 2026-09-21
phase: holdout
in_sample: false
decision_eligible: true
main_wiring: unchanged
created_at: 2026-09-20T15:05:08.563607Z
updated_at: {manifest['reservation']['updated_at']}
owner: Codex
work_status: in_progress
---

# ADR-0482: 원문 중심 RAG FSC 난문 10건 분리평가와 MAIN 승격 판정

## 1. 결정 요약

`source-first` 후보를 **Rejected**한다. 비CM FSC 난문 10건 holdout에서 후보와 baseline 모두
0/10이었고 후보는 10건 모두 최종 주장 0건이다. 사전 성공 기준 8개 중 정확도·delta·회귀·결정
조문 제시 recall 4개를 통과하지 못했다. 따라서 MAIN 승격 plan/apply를 만들지 않았고 로컬 활성
릴리스 `document-navigation-rag-20260917-v2` generation 16은 변경하지 않았다.

## 2. 문제와 변경 전 구조

직전 source-first 계열은 CM 문항 중심의 probe와 수동 관계 실험이었으며, CM 밖 난문에서 자동 탐색부터
최종 답변까지 검증되지 않았다. 현행 baseline은 document-navigation-v1, 후보는 frozen source-first
action-feedback 및 bounded-linked-evidence 경로다. 작업 코드·후보 snapshot과 활성 MAIN은 분리했다.

## 3. 가설과 사전 판정 기준

가설은 후보가 10문항 중 7건 이상 정답, baseline 대비 +2 이상, 회귀 1건 이하, 결정 조문 presented
recall 0.8 이상을 달성한다는 것이었다. arm별 실행 오류 1건 이하, 문항당 14호출·300초 이하,
gold leakage 0도 함께 동결했다. 하나라도 실패하면 승격하지 않는다고 첫 제품 호출 전에 고정했다.

## 4. 실험 설계

| arm | 변경점 | 고정 조건 | 목적 |
|---|---|---|---|
| baseline | frozen document-navigation-v1 | 동일 질문·세대·공개 법령 범위·Gemini·호출 예산 | 현행 작업 경로 기준 |
| source-first | frozen source-first action-feedback + linked evidence | 동일 조건, 문항별 reviewed coordinate 없음 | 최신 후보 자동 실행 |

제품 입력에는 질문과 공개 scope만 포함했고 gold는 제품 20회가 모두 끝난 뒤 결합했다. 문항별 A/B
순서를 번갈아 숨긴 paired Gemini judge를 1회 사용했다. run-001은 baseline 영수증 adapter 결함으로
중단해 미채점했고, 그 결함만 수정한 run-002를 새 출력 경로와 새 후보 binding으로 실행했다.

## 5. 데이터·모델·재현성

- 데이터: `adr0114-sealed-fsc-hard10`, CM과 겹치지 않는 FSC 난문 10건
- 제품 입력: `{rel(ADR/'product-cases.json')}` / `{sha(ADR/'product-cases.json')}`
- gold: `{rel(ADR/'gold-cases.json')}` / `{sha(ADR/'gold-cases.json')}`
- 세대: `navigation-source-20260918-body-v1`; 공개 문서 145개, 조문 source {manifest['retrieval_accounting']['corpus_total']}개
- 모델: 제품·judge 모두 `gemini-3.1-flash-lite`, fallback 없음, 반복 없음
- 기준답 version은 원 fixture hash로 확인했다. 2026-08-27 이후 현행 법령 자체의 독립 재검증은 하지 않아
  `legal_version_checked=false`다.

## 6. 결과

| arm | 정답/전체 | 정확도 | baseline 대비 | 입력 토큰 | p50/p95 |
|---|---:|---:|---:|---:|---:|
| baseline | 0/10 | 0% | - | {b['usage']['input_tokens']} | {b['latency_p50_seconds']:.1f}/{b['latency_p95_seconds']:.1f}초 |
| source-first | 0/10 | 0% | +0 | {s['usage']['input_tokens']} | {s['latency_p50_seconds']:.1f}/{s['latency_p95_seconds']:.1f}초 |

| paired outcome | 건수 | 비율 |
|---|---:|---:|
| 후보만 정답 | 0 | 0% |
| baseline만 정답(회귀) | 0 | 0% |
| 둘 다 정답 | 0 | 0% |
| 둘 다 오답 | 10 | 100% |

## 7. 사례별 오류 분석

| 실패 유형 | arm별 건수 | 대표 질문 | 해석 |
|---|---:|---|---|
| required_issue_omission | baseline 6 / 후보 4 | 겸직·대주주·업무위탁 | 조문 일반론은 찾았지만 질문의 법적 효과·조건을 결론내리지 못함 |
| retrieval_miss | baseline 1 / 후보 5 | 채무조정 전담인력·신용정보 위탁 | 정답 대신 확인 미완료를 반환 |
| governing_rule_selection | baseline 1 / 후보 1 | 국채 거래·후보 실행 오류 | 지배 규칙을 답변으로 연결하지 못함 |
| unsupported_inference | baseline 1 / 후보 0 | 사업보고서 면제 | 총 소유자 수가 아닌 모집·매출 취득자 수라는 반대 해석 |
| product execution error | arm별 1 | 안전지역 / 7천억원 겸직 | baseline `question_spans` KeyError, 후보 Gemini audited transport 실패 |

질문별 실제 답변·judge·모든 원시 호출 파일 hash는 [실험 인덱스](실험/README.md)에 있다.

## 8. 비용·지연·회수 규모

| 항목 | baseline | source-first |
|---|---:|---:|
| 제품 호출 | {b['calls']} | {s['calls']} |
| 제품 총 토큰 | {b['usage']['total_tokens']} | {s['usage']['total_tokens']} |
| presented source | 180 (평균 18.0) | 69 (평균 6.9) |
| 결정 조문 presented recall | {b['presented_gold_recall']:.1%} | {s['presented_gold_recall']:.1%} |
| 결정 조문 answer recall | {b['answer_gold_recall']:.1%} | {s['answer_gold_recall']:.1%} |

judge는 10호출, 입력 {metrics['judge_usage']['input_tokens']}·출력 {metrics['judge_usage']['output_tokens']}토큰이었다.
후보는 결정 조문 15개 중 6개를 모델에 제시했지만 선택 단계에서 전부 버려 answer recall 0%가 됐다.

### 단계별 회수·탈락 원장

| run | arm | stage | kind | 후보 before→after | added / discarded | gold before→after | gold gain / loss | recall |
|---|---|---|---|---:|---:|---:|---:|---:|
{chr(10).join(stages)}

## 9. 해석

관찰 사실은 후보가 빠르고 적은 호출을 사용했지만 답을 만들지 못했다는 것이다. 특히 gold 6/15가
presented까지 도달했으므로 실패를 전부 검색 문제로 볼 수 없다. 선택/action 전이 또는 composer 계약이
제시된 원문을 채택하지 못한 것이 직접 병목이다. baseline 역시 presented recall 8/15와 answer recall
5/15만으로 부족했고, 답변이 일반론·미확인에 머물러 난문 처리 능력이 인증되지 않았다.

## 10. 한계와 일반화 가능 범위

공개 FSC 질문 10건의 단일 holdout이며 단일 Gemini judge라 평가자 변동성은 측정하지 않았다. 기준답은
2026-08-27 fixture를 고정했지만 현재 법령 원문을 별도 법률 검토하지 않았다. 외부 로컬 환경의 Gemini
결과이고 망분리 GENOS 내부 모델 성능을 뜻하지 않는다. 따라서 0/10은 이 두 frozen 경로의 이번 조건에
대한 판정이며 전체 아키텍처의 불가능성을 뜻하지 않는다.

## 11. 운영 결정·롤백 조건

MAIN 승격 조건을 충족하지 못했으므로 `rag_main_promotion.py prepare/apply --confirm-main`은 실행하지
않았다. 활성 포인터는 `document-navigation-rag-20260917-v2`, generation 16, quality_certified=false다.
다음 후보는 새 ADR에서 (1) presented→selected 빈 선택, (2) Gemini JSON schema/transport 호환,
(3) baseline `question_spans` 초기화, (4) 법적 효과·예외 종합을 고친 뒤 같은 비CM holdout과 별도
out-of-sample로 재검증해야 한다.

## 12. 재현 명령

```bash
bash 06_TOOLS/check_wsl_dev_environment.sh
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0482/run_holdout_run002.py        # preflight only
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0482/score_run002.py              # append-only; 이미 실행됨
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py status
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout --final
```

- 제품 정본: [results.json](artifacts/run-002/results.json)
- 점수 정본: [metrics.json](artifacts/run-002/metrics.json)
- 회수 원장: [retrieval-stage-ledger-run-002.json](artifacts/retrieval-stage-ledger-run-002.json)
- 산출물 hash: [artifacts/manifest.json](artifacts/manifest.json)
"""


def artifact_manifest() -> dict:
    paths = [
        ART / "frozen-design.json",
        ART / "frozen-design-run-002.json",
        ART / "run-001/results.partial.json",
        RESULTS,
        JUDGED,
        METRICS,
        ART / "run-002/gold-coordinate-resolution.json",
        LEDGER,
    ]
    descriptions = {
        "frozen-design.json": "run-001 pre-call frozen design",
        "frozen-design-run-002.json": "run-002 frozen design and adapter-only delta",
        "results.partial.json": "failed run-001 partial product results",
        "results.json": "sealed run-002 paired product results",
        "judged-results.json": "anonymous paired offline judgments",
        "metrics.json": "success criteria and arm metrics",
        "gold-coordinate-resolution.json": "post-selection legacy-to-current coordinate receipts",
        "retrieval-stage-ledger-run-002.json": "case-stage retrieval accounting",
    }
    return {
        "schema_version": "adr-artifacts-v1",
        "adr_id": "ADR-0482",
        "created_at": "2026-09-20T15:05:08.563607Z",
        "files": [
            {
                "path": rel(path),
                "sha256": sha(path),
                "bytes": path.stat().st_size,
                "description": descriptions[path.name],
                "contains_raw_prompts_and_outputs": path.name in {"results.json", "judged-results.json"},
            }
            for path in paths
        ],
        "raw_call_trees": [
            {
                "path": rel(ART / "run-002"),
                "description": "Per-case product and judge request/schema/response/output/usage files; enumerated with hashes in question records.",
            }
        ],
    }


def main() -> None:
    results = read(RESULTS)
    judged = read(JUDGED)
    metrics = read(METRICS)
    ledger = read(LEDGER)
    product = read(ADR / "product-cases.json")
    gold = read(ADR / "gold-cases.json")
    manifest = make_manifest(results, judged, metrics, ledger)
    write_json(EXP / "manifest.json", manifest)
    write(ADR / "README.md", render_readme(manifest, metrics, ledger))
    write(EXP / "README.md", render_index(metrics, ledger))
    for index, case in enumerate(product["cases"], 1):
        write(
            EXP / f"질문-{index:03d}-{case['case_id']}.md",
            render_question(index, case, gold, results, judged, ledger),
        )
    write_json(ART / "manifest.json", artifact_manifest())
    print("ADR-0482 run-002 rendered; reservation remains in_progress until final validation")


if __name__ == "__main__":
    main()
