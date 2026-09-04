"""RAG 평가 규약 — 실행 결과를 저장하고 이전 구조와 같은 자로 비교한다.

골든 점수 한 줄만 남기면 무엇이 좋아지고 무엇이 나빠졌는지 알 수 없다. 이
모듈은 문항 결과, 데이터 슬라이스, 안전 지표, 비용 지표와 성능 손잡이 지문을
하나의 manifest로 만든다. 구조 변경 전후는 같은 suite SHA와 case 집합일 때만
유효한 A/B로 인정한다.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.rag import controls


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EvaluationAxis:
    key: str
    label: str
    purpose: str
    source: str


AXES: tuple[EvaluationAxis, ...] = (
    EvaluationAxis("outcome", "기대 결과", "찾아야 함과 막아야 함을 분리", "case"),
    EvaluationAxis("source_tier", "근거 등급", "수동 정본·Frame·무근거의 차이", "case"),
    EvaluationAxis("scope", "주소 범위", "무주소·문서·조·항 제약의 차이", "case"),
    EvaluationAxis("expression", "표현 방식", "정확·별칭·구어·바꿔쓰기 일반화", "case"),
    EvaluationAxis("challenge", "시험 난점", "오염·술어 반전·좌표 충돌 원인", "case"),
    EvaluationAxis("domain", "법률 도메인", "특정 법역 과적합 탐지", "case"),
    EvaluationAxis("entry_channel", "진입 채널", "Concept·기억·용어·Frame·벡터 기여", "runtime"),
    EvaluationAxis("context_count", "컨텍스트 수", "작은/큰 근거 집합의 품질·비용", "runtime"),
    EvaluationAxis("context_chars", "컨텍스트 글자", "구역 수가 숨기는 실제 입력 규모", "runtime"),
    EvaluationAxis("cap_overflow", "공유 상한 초과", "별도·가산 예산의 영향", "runtime"),
    EvaluationAxis("truncation", "본문 잘림", "상한으로 인한 요건·예외 누락", "runtime"),
    EvaluationAxis("issue_state", "쟁점 탐지 상태", "쟁점 빈손과 최종 판정 실패의 상관", "runtime"),
    EvaluationAxis("retrieval_state", "정답 근거 회수 상태", "검색 실패와 추론 실패 분리", "runtime"),
    EvaluationAxis("basis_state", "정밀 근거 선택 상태", "회수 성공 뒤 인용 선택 실패 분리", "runtime"),
    EvaluationAxis("mode", "질문 트랙", "법령 주소가 있는 A와 없는 B 분리", "case"),
    EvaluationAxis("material", "재료 상태", "회수 실패와 코퍼스 공백 분리", "case"),
    EvaluationAxis("text_kind", "질문 문체", "질의요지와 일반인 구어 분리", "case"),
    EvaluationAxis("direction_gold", "정답 방향", "긍정·부정·조건부 편향 탐지", "case"),
)
# Concept 진입 부품검사의 필수 여섯 축. 제품 E2E 축은 suite가 별도로 선언한다.
DEFAULT_AXES = ("outcome", "source_tier", "scope", "expression", "challenge", "domain")


@dataclass(frozen=True)
class EvaluationMethod:
    key: str
    label: str
    purpose: str


METHODS: tuple[EvaluationMethod, ...] = (
    EvaluationMethod("frozen_golden", "동결 골든",
                     "승인된 기대 근거와 차단 문항의 결정론 회귀 검사"),
    EvaluationMethod("development_holdout", "개발 홀드아웃",
                     "골든에 직접 맞춘 과적합을 별도 문항·근거로 탐지"),
    EvaluationMethod("blind_first_run", "최초 블라인드",
                     "정답을 보고 수정하기 전 일반화 성능을 보존"),
    EvaluationMethod("source_shadow", "근거 shadow",
                     "기존 질문의 허용 근거 좌표 밖 Concept 오염 탐지"),
    EvaluationMethod("one_variable_ablation", "한 변수 제거 A/B",
                     "채널·검문·가이드 하나의 한계 기여와 비용 측정"),
    EvaluationMethod("axis_slicing", "축별 슬라이스",
                     "전체 평균이 숨기는 표현·스코프·도메인 실패 탐지"),
    EvaluationMethod("repeated_trials", "반복 실행",
                     "LLM 변동성을 평균·최악값·분산으로 분리"),
    EvaluationMethod("cost_latency", "비용·지연 계측",
                     "호출 수·입출력 토큰·TTFT·총 지연의 구조 변화 측정"),
)


@dataclass(frozen=True)
class Ablation:
    key: str
    switch: str
    candidate_on: bool
    purpose: str


ABLATIONS: tuple[Ablation, ...] = (
    Ablation("without_concept", "concept_entry", False, "승인 Concept/OQL의 순증가"),
    Ablation("without_memory", "memory_entry", False, "승인 질문 기억의 순증가"),
    Ablation("without_keyword", "keyword_entry", False, "승인 용어 진입의 순증가"),
    Ablation("without_frame", "frame_entry", False, "Concept 빈손 시 Frame 폴백 기여"),
    Ablation("without_vector", "vector_entry", False, "패러프레이즈 벡터 진입 기여"),
    Ablation("without_doc_companion", "doc_companion", False, "문서 밖 인용 동반 기여"),
    Ablation("without_issue_rewrite", "issue_spot_pre", False, "검색 전 쟁점 재작성 기여"),
    Ablation("without_issue_respot", "issue_respot", False, "판정 재회수 기여"),
    Ablation("without_definition", "floor_definition", False, "정의 조 동반 기여"),
    Ablation("without_sanction", "floor_sanction", False, "제재 조 동반 기여"),
)


@dataclass(frozen=True)
class Measure:
    key: str
    label: str
    direction: str
    gate: str


MEASURES: tuple[Measure, ...] = (
    Measure("pass_rate", "전체 통과율", "higher", "report"),
    Measure("positive_recall", "찾아야 할 근거 회수율", "higher", "quality"),
    Measure("negative_block_rate", "막아야 할 오염 차단율", "higher", "safety"),
    Measure("source_accuracy", "근거 좌표 정확도", "higher", "safety"),
    Measure("contamination_rate", "오염 진입률", "lower", "safety"),
    Measure("fallback_rate", "일반검색 인계율", "context", "report"),
    Measure("calls_per_case", "문항당 LLM 호출", "lower", "efficiency"),
    Measure("input_tokens_per_case", "문항당 입력 토큰", "lower", "efficiency"),
    Measure("output_tokens_per_case", "문항당 출력 토큰", "lower", "efficiency"),
    Measure("duration_ms_p50", "지연 p50", "lower", "efficiency"),
    Measure("duration_ms_p95", "지연 p95", "lower", "efficiency"),
    Measure("ttft_ms_p95", "첫 토큰 지연 p95", "lower", "efficiency"),
    Measure("final_contexts_p95", "최종 컨텍스트 수 p95", "context", "report"),
    Measure("context_chars_p95", "컨텍스트 글자 p95", "context", "report"),
    Measure("shared_cap_overflow_rate", "공유 상한 초과율", "lower", "report"),
    Measure("truncated_section_rate", "본문 잘림 구역률", "lower", "report"),
    Measure("llm_truncation_rate", "LLM 출력 잘림 호출률", "lower", "safety"),
    Measure("lexicon_cache_coverage", "용어집 벡터 준비율", "higher", "readiness"),
    Measure("lexicon_runtime_compile_rate", "질의 중 용어집 컴파일률", "lower", "readiness"),
    Measure("shadow_clean_rate", "기존 근거 shadow 무오염률", "higher", "safety"),
    Measure("direction_accuracy", "최종 답 방향 일치율", "higher", "quality"),
    Measure("direction_basis_rate", "방향과 정밀 근거 동시 적중률", "higher", "safety"),
    Measure("semantic_accuracy", "최종 법률 명제 일치율", "higher", "quality"),
    Measure("semantic_basis_rate", "명제와 정밀 근거 동시 적중률", "higher", "safety"),
    Measure("article_recall", "정답 조문 회수율", "higher", "quality"),
    Measure("basis_recall", "최종 근거 좌표 회수율", "higher", "safety"),
    Measure("basis_stray_rate", "최종 근거 과잉률", "lower", "safety"),
    Measure("abstain_rate", "최종 판단 유보율", "lower", "report"),
    Measure("issue_fire_rate", "쟁점 발화율", "higher", "report"),
    Measure("required_channel_coverage", "필수 진입 채널 관측률", "higher", "report"),
    Measure("required_stage_coverage", "필수 처리 단계 관측률", "higher", "report"),
)


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _percentile(values: Iterable[int | float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    # 최근접 순위. 작은 canary에서도 실제 관측값을 반환해 해석이 쉽다.
    pos = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[pos], 3)


def result_row(case: Mapping[str, Any], *, got_sources: Iterable[tuple[str, str]],
               errors: Sequence[str], hit: bool, fallback: str = "",
               usage: Mapping[str, Any] | None = None,
               runtime: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """골든 실행 하나를 비교 가능한 문항 행으로 바꾼다."""
    expected_rows = case.get("expect_sources")
    if expected_rows is None and case.get("expect_source"):
        expected_rows = [case["expect_source"]]
    expected = sorted((str(row["doc_id"]), str(row["node"]))
                      for row in (expected_rows or []))
    got = sorted((str(doc_id), str(node)) for doc_id, node in got_sources)
    expected_set, got_set = set(expected), set(got)
    expect_hit = bool(case.get("expect_hit"))
    source_correct = (got_set == expected_set) if expected else (not got_set if not expect_hit else True)
    unexpected = sorted(got_set - expected_set) if expected else (got if not expect_hit else [])
    return {
        "id": str(case.get("id") or ""),
        "question": str(case.get("question") or ""),
        "expect_hit": expect_hit,
        "expected_sources": [{"doc_id": doc, "node": node} for doc, node in expected],
        "got_sources": [{"doc_id": doc, "node": node} for doc, node in got],
        "unexpected_sources": [{"doc_id": doc, "node": node} for doc, node in unexpected],
        "passed": not errors, "hit": bool(hit), "source_correct": source_correct,
        "contaminated": bool(unexpected) or (not expect_hit and bool(hit)),
        "fallback": fallback, "errors": list(errors),
        "axes": dict(case.get("axes") or {}), "usage": dict(usage or {}),
        "runtime": dict(runtime or {}),
    }


def _metrics(rows: Sequence[Mapping[str, Any]], shadow: Mapping[str, Any] | None = None
             ) -> dict[str, Any]:
    total = len(rows)
    positive = [row for row in rows if row.get("expect_hit")]
    negative = [row for row in rows if not row.get("expect_hit")]
    sourced = [row for row in rows if row.get("expected_sources")]
    usage_rows = [dict(row.get("usage") or {}) for row in rows]
    calls = sum(int(row.get("calls", 0)) for row in usage_rows)
    input_tokens = sum(int(row.get("input_tokens", 0)) for row in usage_rows)
    output_tokens = sum(int(row.get("output_tokens", 0)) for row in usage_rows)
    truncated_calls = sum(int(row.get("truncated_calls", 0)) for row in usage_rows)
    durations = [float(row.get("duration_ms", 0)) for row in usage_rows]
    ttfts = [float(row.get("ttft_ms", 0)) for row in usage_rows if row.get("ttft_ms")]
    runtime_rows = [dict(row.get("runtime") or {}) for row in rows]
    context_counts = [int(row.get("final_contexts", 0)) for row in runtime_rows]
    context_chars = [int(row.get("context_chars", 0)) for row in runtime_rows]
    truncated = sum(int(row.get("truncated_sections", 0)) for row in runtime_rows)
    lexicon_coverage = [float(row.get("lexicon_cache_coverage", 0.0))
                        for row in runtime_rows
                        if int(row.get("lexicon_cache_terms", 0)) > 0]
    channel_totals: dict[str, int] = {}
    for runtime in runtime_rows:
        for channel, count in (runtime.get("channel_counts") or {}).items():
            channel_totals[str(channel)] = channel_totals.get(str(channel), 0) + int(count)
    metrics = {
        "cases": total,
        "passed": sum(bool(row.get("passed")) for row in rows),
        "pass_rate": _rate(sum(bool(row.get("passed")) for row in rows), total),
        "positive_cases": len(positive),
        "positive_recall": _rate(sum(bool(row.get("passed")) for row in positive),
                                 len(positive)),
        "positive_hit_rate": _rate(sum(bool(row.get("hit")) for row in positive),
                                   len(positive)),
        "negative_cases": len(negative),
        "negative_block_rate": _rate(sum(bool(row.get("passed")) for row in negative),
                                     len(negative)),
        "source_cases": len(sourced),
        "source_accuracy": _rate(sum(bool(row.get("source_correct")) for row in sourced),
                                 len(sourced)),
        "contamination_rate": _rate(sum(bool(row.get("contaminated")) for row in rows), total),
        "fallback_rate": _rate(sum(bool(row.get("fallback")) for row in rows), total),
        "calls": calls, "calls_per_case": _rate(calls, total),
        "input_tokens": input_tokens,
        "input_tokens_per_case": _rate(input_tokens, total),
        "output_tokens": output_tokens,
        "output_tokens_per_case": _rate(output_tokens, total),
        "truncated_calls": truncated_calls,
        "llm_truncation_rate": _rate(truncated_calls, calls),
        "duration_ms_total": round(sum(durations), 3),
        "duration_ms_p50": _percentile(durations, 0.50),
        "duration_ms_p95": _percentile(durations, 0.95),
        "ttft_ms_p95": _percentile(ttfts, 0.95),
        "final_contexts_p50": _percentile(context_counts, 0.50),
        "final_contexts_p95": _percentile(context_counts, 0.95),
        "final_contexts_max": max(context_counts, default=0),
        "context_chars_p50": _percentile(context_chars, 0.50),
        "context_chars_p95": _percentile(context_chars, 0.95),
        "context_chars_max": max(context_chars, default=0),
        "shared_cap_overflow_rate": _rate(
            sum(bool(row.get("shared_cap_overflow")) for row in runtime_rows), total),
        "truncated_sections": truncated,
        "truncated_section_rate": _rate(truncated, sum(context_counts)),
        "lexicon_cache_coverage": min(lexicon_coverage) if lexicon_coverage else 0.0,
        "lexicon_runtime_compile_rate": _rate(
            sum(bool(row.get("lexicon_runtime_compiled")) for row in runtime_rows), total),
        "channel_totals": dict(sorted(channel_totals.items())),
    }
    if shadow:
        shadow_total = int(shadow.get("total", 0))
        shadow_bad = len(shadow.get("bad") or [])
        metrics.update(shadow_cases=shadow_total,
                       shadow_contamination=shadow_bad,
                       shadow_clean_rate=_rate(shadow_total - shadow_bad, shadow_total))
    else:
        metrics.update(shadow_cases=0, shadow_contamination=0,
                       shadow_clean_rate=0.0)
    return metrics


def summarize(rows: Sequence[Mapping[str, Any]], axis_order: Sequence[str], *,
              shadow: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """전체와 각 축/값을 같은 측정식으로 접는다."""
    axes = []
    for axis in axis_order:
        values = sorted({str((row.get("axes") or {}).get(axis, "")) for row in rows})
        for value in values:
            selected = [row for row in rows
                        if str((row.get("axes") or {}).get(axis, "")) == value]
            axes.append({"axis": axis, "value": value, **_metrics(selected)})
    operational_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        for axis, value in _operational_values(row):
            operational_groups.setdefault((axis, value), []).append(row)
    operational_axes = [
        {"axis": axis, "value": value, **_metrics(selected)}
        for (axis, value), selected in sorted(operational_groups.items())
    ]
    return {"metrics": _metrics(rows, shadow), "axes": axes,
            "operational_axes": operational_axes}


def _operational_values(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    runtime = dict(row.get("runtime") or {})
    channels = [str(key) for key, count in
                (runtime.get("channel_counts") or {}).items() if int(count) > 0]
    values = [("entry_channel", channel) for channel in channels or ["none"]]
    n_context = int(runtime.get("final_contexts", 0))
    count_bucket = ("0" if n_context == 0 else "1-4" if n_context <= 4
                    else "5-12" if n_context <= 12 else "13+")
    chars = int(runtime.get("context_chars", 0))
    char_bucket = ("0" if chars == 0 else "1-24k" if chars <= 24_000
                   else "24k-72k" if chars <= 72_000 else "72k+")
    values.extend([
        ("context_count", count_bucket), ("context_chars", char_bucket),
        ("cap_overflow", "yes" if runtime.get("shared_cap_overflow") else "no"),
        ("truncation", "yes" if int(runtime.get("truncated_sections", 0)) else "no"),
        ("issue_state", "fired" if int(row.get("issues", 0)) > 0 else "empty"),
    ])
    if "retrieval_complete" in row:
        values.append(("retrieval_state",
                       "complete" if row.get("retrieval_complete") else "incomplete"))
    if "basis_complete" in row:
        values.append(("basis_state",
                       "complete" if row.get("basis_complete") else "incomplete"))
    return values


def suite_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_snapshot() -> dict[str, Any]:
    """성능 손잡이와 별개인 채널/규칙 스위치의 재현 설정."""
    from lawrag.core.rag import switches

    rows = [{"key": row["key"], "on": bool(row["on"]),
             "default": bool(row.get("기본", True)),
             "stage": str(row.get("자리") or "")}
            for row in switches.snapshot()]
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return {"fingerprint": hashlib.sha256(raw).hexdigest()[:16], "values": rows}


def build_manifest(*, suite_path: Path, suite: Mapping[str, Any],
                   rows: Sequence[Mapping[str, Any]], mode: str,
                   shadow: Mapping[str, Any] | None = None,
                   run_label: str = "", trial: int = 1,
                   selected_case_ids: Sequence[str] | None = None) -> dict[str, Any]:
    control_rows = controls.snapshot()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run": {"label": run_label, "mode": mode, "trial": int(trial)},
        "suite": {
            "name": str(suite.get("name") or suite_path.stem),
            "version": suite.get("version"), "path": str(suite_path),
            "sha256": suite_sha256(suite_path), "case_count": len(rows),
            "case_ids": list(selected_case_ids or [str(row["id"]) for row in rows]),
            "axis_order": list(suite.get("axis_order") or DEFAULT_AXES),
        },
        "methods": [asdict(method) for method in METHODS],
        "axes": [asdict(axis) for axis in AXES],
        "measures": [asdict(measure) for measure in MEASURES],
        "controls": {"fingerprint": controls.fingerprint(control_rows),
                     "values": control_rows, "audit": controls.audit(control_rows)},
        "engine": engine_snapshot(),
        "results": list(rows), "shadow": dict(shadow or {}),
        "summary": summarize(rows, list(suite.get("axis_order") or DEFAULT_AXES),
                             shadow=shadow),
    }


def review_result_row(row: Mapping[str, Any], labels: Mapping[str, str], *,
                      flow: str = "legal_review") -> dict[str, Any]:
    """기존 ``review_golden.py`` 한 행을 통합 검토 평가 행으로 보존한다."""
    case_no = str(row.get("case_no") or "")
    gold = str(row.get("m_gold") or labels.get(case_no) or "")
    got = str(row.get("direction") or "미정")
    has_semantic_gold = "semantic_correct" in row
    if has_semantic_gold:
        # 부정형 질문의 "아니오, 해야 한다" 같은 답은 문장 극성 enum으로는
        # 안정적으로 채점할 수 없다. 사람이 확정한 명제 채점이 있는 직접 E2E는
        # 방향 점수를 적용하지 않는다.
        direction_status = "not_applicable"
    elif gold not in ("긍정", "부정", "조건부"):
        direction_status = "unlabeled"
    elif got == "미정" or (got == "조건부" and gold != "조건부"):
        direction_status = "abstain"
    elif got == gold:
        direction_status = "correct"
    else:
        direction_status = "wrong"
    denominator = int(row.get("m_n") or row.get("want_arts") or 0)
    retrieved = int(row.get("m_ret") if row.get("m_n") is not None
                    else row.get("got_arts") or 0)
    basis_hit = int(row.get("m_basis") if row.get("m_n") is not None
                    else row.get("basis_hit") or 0)
    basis_complete = denominator > 0 and basis_hit >= denominator
    retrieval_complete = denominator > 0 and retrieved >= denominator
    usage = dict(row.get("usage") or {})
    usage.setdefault("duration_ms", round(float(row.get("sec", 0)) * 1000, 3))
    runtime = dict(row.get("runtime") or {})
    runtime.setdefault("final_contexts", int(row.get("norms", 0)))
    runtime.setdefault("context_chars", 0)
    runtime.setdefault("truncated_sections", 0)
    runtime.setdefault("shared_cap_overflow", False)
    runtime.setdefault("channel_counts", {})
    if not runtime.get("stage_counts"):
        if flow == "ask":
            runtime["stage_counts"] = {
                "issue_spot": int(row.get("issues", 0)),
                "retrieval": int(row.get("norms", 0)),
                "answer_synthesis": int(bool(row.get("interp"))),
                "final_citation": int(row.get("basis_n", 0)),
            }
        else:
            # 이 행은 pipeline.run이 반환된 뒤에만 만들어지므로 과거 raw에도
            # 사실 추출 1회는 확정적으로 존재한다.
            runtime["stage_counts"] = {
                "fact_extraction": int(row.get("facts", 1)),
                "issue_spot": int(row.get("issues", 0)),
                "norm_retrieval": int(row.get("norms", 0)),
                "subsumption": int(row.get("subs", 0)),
                "final_decision": int(bool(row.get("interp"))),
            }
    if has_semantic_gold:
        strict_pass = bool(row.get("semantic_correct")) and (
            basis_complete if denominator else True)
    else:
        strict_pass = direction_status == "correct" and (
            basis_complete if denominator else True)
    case_axes = {
        "outcome": "positive", "mode": str(row.get("mode") or "?"),
        "material": str(row.get("material") or "?"),
        "text_kind": str(row.get("text_kind") or "?"),
        "direction_gold": gold or "unlabeled",
    }
    case_axes.update({str(key): str(value)
                      for key, value in dict(row.get("axes") or {}).items()})
    result = {
        "id": case_no, "case_no": case_no,
        "question": str(row.get("question") or row.get("label") or ""),
        "source_question": str(row.get("source_question") or ""),
        "reference_answer": str(row.get("reference_answer") or ""),
        "system_answer": str(row.get("answer") or ""),
        "reference_answer_kind": str(row.get("reference_answer_kind") or ""),
        "passed": strict_pass, "expect_hit": True,
        "hit": retrieval_complete, "source_correct": basis_complete,
        "contaminated": int(row.get("basis_stray", 0)) > 0,
        "fallback": "", "errors": [] if strict_pass else [direction_status],
        "expected_sources": [], "got_sources": [], "unexpected_sources": [],
        "expected_articles": list(row.get("want_arts_list") or []),
        "direction_gold": gold, "direction_got": got,
        "direction_status": direction_status,
        "decisive_n": denominator, "retrieved_n": retrieved,
        "basis_hit_n": basis_hit, "basis_complete": basis_complete,
        "retrieval_complete": retrieval_complete,
        "basis_n": int(row.get("basis_n", 0)),
        "basis_stray": int(row.get("basis_stray", 0)),
        "issues": int(row.get("issues", 0)),
        "facts": int(row.get("facts", 0)),
        "subs": int(row.get("subs", 0)),
        "interpreted": bool(row.get("interp")),
        "basis_raw": list(row.get("basis_raw") or []),
        "expected_articles_detail": list(row.get("expected_articles") or []),
        "axes": case_axes,
        "usage": usage, "runtime": runtime,
    }
    # 직접질문 E2E는 단순 긍정/부정 극성보다 사람이 확정한 법률 명제와의
    # 합치가 정답이다. 키가 없는 과거 법률검토 결과와 false를 구별해 보존한다.
    if has_semantic_gold:
        result["semantic_correct"] = bool(row.get("semantic_correct"))
        result["semantic_reason"] = str(row.get("semantic_reason") or "")
        result["semantic_grade"] = dict(row.get("semantic_grade") or {})
    return result


def _review_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    labeled = [row for row in rows if row.get("direction_status") in {
        "correct", "wrong", "abstain"}]
    semantic = [row for row in rows if "semantic_correct" in row]
    decisive = sum(int(row.get("decisive_n", 0)) for row in rows)
    basis_total = sum(int(row.get("basis_n", 0)) for row in rows)
    return {
        "direction_accuracy": _rate(
            sum(row.get("direction_status") == "correct" for row in labeled), len(labeled)),
        "direction_basis_rate": _rate(
            sum(row.get("direction_status") == "correct" and row.get("basis_complete")
                for row in labeled), len(labeled)),
        "semantic_cases": len(semantic),
        "semantic_accuracy": _rate(
            sum(bool(row.get("semantic_correct")) for row in semantic), len(semantic)),
        "semantic_basis_rate": _rate(
            sum(bool(row.get("semantic_correct")) and row.get("basis_complete")
                for row in semantic), len(semantic)),
        "article_recall": _rate(sum(int(row.get("retrieved_n", 0)) for row in rows),
                                decisive),
        "basis_recall": _rate(sum(int(row.get("basis_hit_n", 0)) for row in rows),
                              decisive),
        "basis_stray_rate": _rate(sum(int(row.get("basis_stray", 0)) for row in rows),
                                  basis_total),
        "abstain_rate": _rate(
            sum(row.get("direction_status") == "abstain" for row in labeled), len(labeled)),
        "issue_fire_rate": _rate(sum(int(row.get("issues", 0)) > 0 for row in rows),
                                 len(rows)),
    }


def _required_channel_coverage(rows: Sequence[Mapping[str, Any]],
                               required: Sequence[str]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    for row in rows:
        for channel, count in ((row.get("runtime") or {}).get("channel_counts") or {}).items():
            totals[str(channel)] = totals.get(str(channel), 0) + int(count)
    wanted = list(dict.fromkeys(str(channel) for channel in required))
    observed = [channel for channel in wanted if totals.get(channel, 0) > 0]
    return {
        "required": wanted,
        "observed": observed,
        "missing": [channel for channel in wanted if channel not in observed],
        "rate": _rate(len(observed), len(wanted)) if wanted else 1.0,
        "totals": dict(sorted(totals.items())),
    }


def _required_stage_coverage(rows: Sequence[Mapping[str, Any]],
                             required: Sequence[str]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    for row in rows:
        for stage, count in ((row.get("runtime") or {}).get("stage_counts") or {}).items():
            totals[str(stage)] = totals.get(str(stage), 0) + int(count)
    wanted = list(dict.fromkeys(str(stage) for stage in required))
    observed = [stage for stage in wanted if totals.get(stage, 0) > 0]
    return {
        "required": wanted,
        "observed": observed,
        "missing": [stage for stage in wanted if stage not in observed],
        "rate": _rate(len(observed), len(wanted)) if wanted else 1.0,
        "totals": dict(sorted(totals.items())),
    }


def review_summarize(rows: Sequence[Mapping[str, Any]],
                     axis_order: Sequence[str], *,
                     required_channels: Sequence[str] = (),
                     required_stages: Sequence[str] = ()) -> dict[str, Any]:
    summary = summarize(rows, axis_order)
    summary["metrics"].update(_review_metrics(rows))
    coverage = _required_channel_coverage(rows, required_channels)
    summary["metrics"]["required_channel_coverage"] = coverage["rate"]
    summary["channel_coverage"] = coverage
    stage_coverage = _required_stage_coverage(rows, required_stages)
    summary["metrics"]["required_stage_coverage"] = stage_coverage["rate"]
    summary["stage_coverage"] = stage_coverage
    for item in summary["axes"]:
        selected = [row for row in rows
                    if str((row.get("axes") or {}).get(item["axis"], ""))
                    == item["value"]]
        if selected:
            item.update(_review_metrics(selected))
    for item in summary["operational_axes"]:
        selected = [row for row in rows
                    if (item["axis"], item["value"]) in _operational_values(row)]
        if selected:
            item.update(_review_metrics(selected))
    return summary


def build_review_manifest(*, source_path: Path, source_rows: Sequence[Mapping[str, Any]],
                          labels: Mapping[str, str], run_label: str = "",
                          trial: int = 1,
                          source_flow: str = "legal_review",
                          source_suite: Mapping[str, Any] | None = None,
                          source_controls: Mapping[str, Any] | None = None,
                          source_engine: Mapping[str, Any] | None = None,
                          source_variant: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """기존/신규 법률검토 실행을 설정 지문이 있는 통합 manifest로 변환한다."""
    rows = [review_result_row(row, labels, flow=source_flow) for row in source_rows]
    expected = [{"id": row["id"], "gold": row["direction_gold"],
                 "articles": row["expected_articles"], "mode": row["axes"]["mode"]}
                for row in rows]
    suite_source = dict(source_suite or {})
    hash_subject: Any = suite_source if suite_source else expected
    suite_hash = hashlib.sha256(json.dumps(
        hash_subject, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    axis_order = [str(x) for x in (suite_source.get("axis_order") or
                                   ["mode", "material", "text_kind",
                                    "direction_gold"])]
    flow_requirements = dict((suite_source.get("flows") or {}).get(source_flow) or {})
    required_channels = [str(x) for x in (
        flow_requirements.get("required_channels")
        or suite_source.get("required_channels") or [])]
    required_stages = [str(x) for x in (
        flow_requirements.get("required_stages")
        or suite_source.get("required_stages") or [])]
    control_rows = controls.snapshot()
    control_block = dict(source_controls or {
        "fingerprint": controls.fingerprint(control_rows), "values": control_rows,
        "audit": controls.audit(control_rows)})
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run": {"label": run_label, "mode": source_flow, "trial": int(trial)},
        "suite": {"name": str(suite_source.get("name") or "legal-review-golden"),
                  "version": suite_source.get("version", 1),
                  "role": str(suite_source.get("role") or ""),
                  "path": str(source_path), "sha256": suite_hash,
                  "case_count": len(rows), "case_ids": [row["id"] for row in rows],
                  "axis_order": axis_order,
                  "required_channels": required_channels,
                  "required_stages": required_stages},
        "methods": [asdict(method) for method in METHODS],
        "axes": [asdict(axis) for axis in AXES],
        "measures": [asdict(measure) for measure in MEASURES],
        "controls": control_block,
        "engine": dict(source_engine or engine_snapshot()),
        "variant": dict(source_variant or {}),
        "results": rows, "shadow": {},
        "summary": review_summarize(
            rows, axis_order, required_channels=required_channels,
            required_stages=required_stages),
    }


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    blob = json.loads(path.read_text(encoding="utf-8"))
    if int(blob.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError(f"지원하지 않는 RAG 평가 manifest: {blob.get('schema_version')}")
    return blob


def compare_manifests(base: Mapping[str, Any], candidate: Mapping[str, Any], *,
                      quality_tolerance: float = 0.0,
                      efficiency_warn_ratio: float = 0.10,
                      require_one_change: bool = False) -> dict[str, Any]:
    """동일 suite의 전후 실행을 안전·품질·비용 축으로 비교한다."""
    b_suite, c_suite = base.get("suite") or {}, candidate.get("suite") or {}
    incompatible = []
    if b_suite.get("sha256") != c_suite.get("sha256"):
        incompatible.append("suite_sha256")
    if list(b_suite.get("case_ids") or []) != list(c_suite.get("case_ids") or []):
        incompatible.append("case_ids")
    b_controls = {str(row.get("key")): row.get("value") for row in
                  (base.get("controls") or {}).get("values") or []}
    c_controls = {str(row.get("key")): row.get("value") for row in
                  (candidate.get("controls") or {}).get("values") or []}
    b_switches = {str(row.get("key")): bool(row.get("on")) for row in
                  (base.get("engine") or {}).get("values") or []}
    c_switches = {str(row.get("key")): bool(row.get("on")) for row in
                  (candidate.get("engine") or {}).get("values") or []}
    b_variants = dict(base.get("variant") or {})
    c_variants = dict(candidate.get("variant") or {})
    configuration_diff = []
    for key in sorted(set(b_controls) | set(c_controls)):
        if b_controls.get(key) != c_controls.get(key):
            configuration_diff.append({"kind": "control", "key": key,
                                       "before": b_controls.get(key),
                                       "after": c_controls.get(key)})
    for key in sorted(set(b_switches) | set(c_switches)):
        if b_switches.get(key) != c_switches.get(key):
            configuration_diff.append({"kind": "switch", "key": key,
                                       "before": b_switches.get(key),
                                       "after": c_switches.get(key)})
    for key in sorted(set(b_variants) | set(c_variants)):
        if b_variants.get(key) != c_variants.get(key):
            configuration_diff.append({"kind": "variant", "key": key,
                                       "before": b_variants.get(key),
                                       "after": c_variants.get(key)})
    if require_one_change and len(configuration_diff) != 1:
        incompatible.append("one_variable_configuration")
    bm = (base.get("summary") or {}).get("metrics") or {}
    cm = (candidate.get("summary") or {}).get("metrics") or {}
    deltas = {measure.key: round(float(cm.get(measure.key, 0))
                                 - float(bm.get(measure.key, 0)), 6)
              for measure in MEASURES}
    regressions = []
    warnings = []
    for measure in MEASURES:
        before, after = float(bm.get(measure.key, 0)), float(cm.get(measure.key, 0))
        delta = deltas[measure.key]
        if measure.gate in ("safety", "quality"):
            tolerance = quality_tolerance if measure.gate == "quality" else 0.0
            regressed = ((measure.direction == "higher" and delta < -tolerance)
                         or (measure.direction == "lower" and delta > tolerance))
            if regressed:
                regressions.append({"measure": measure.key, "label": measure.label,
                                    "gate": measure.gate, "before": before,
                                    "after": after, "delta": delta})
        elif measure.gate == "efficiency" and before > 0:
            ratio = (after - before) / before
            if ratio > efficiency_warn_ratio:
                warnings.append({"measure": measure.key, "label": measure.label,
                                 "before": before, "after": after,
                                 "ratio": round(ratio, 6)})
    if incompatible:
        verdict = "invalid"
    elif regressions:
        verdict = "regressed"
    elif any(deltas[key] > 0 for key in
             ("positive_recall", "negative_block_rate", "source_accuracy")):
        verdict = "improved"
    elif any(deltas[key] < 0 for key in
             ("calls_per_case", "input_tokens_per_case", "duration_ms_p95")):
        verdict = "more_efficient"
    else:
        verdict = "non_regression"
    return {
        "verdict": verdict, "compatible": not incompatible,
        "incompatible": incompatible,
        "base": {"label": (base.get("run") or {}).get("label"),
                 "controls": (base.get("controls") or {}).get("fingerprint")},
        "candidate": {"label": (candidate.get("run") or {}).get("label"),
                      "controls": (candidate.get("controls") or {}).get("fingerprint")},
        "configuration_diff": configuration_diff,
        "deltas": deltas, "regressions": regressions, "warnings": warnings,
    }


def compare_search_benchmarks(base: Mapping[str, Any], candidate: Mapping[str, Any], *,
                              require_one_change: bool = False) -> dict[str, Any]:
    """``rag_search_benchmark.py`` 두 실행을 좌표 품질·오염·비용으로 비교한다.

    옛 Concept 음성은 제품의 빈 결과 골든이 아니라 구조 진입 차단 진단이다. 따라서
    음성의 최종 fallback 결과를 contamination으로 오해하지 않고, 양성 기대 좌표와
    기대 좌표가 최종 컨텍스트에서 차지한 비율을 품질 게이트로 쓴다.
    """
    base_rows = list(base.get("rows") or [])
    candidate_rows = list(candidate.get("rows") or [])
    base_ids = [str(row.get("id")) for row in base_rows]
    candidate_ids = [str(row.get("id")) for row in candidate_rows]
    incompatible = []
    if base_ids != candidate_ids:
        incompatible.append("case_ids")
    base_questions = [str(row.get("question")) for row in base_rows]
    candidate_questions = [str(row.get("question")) for row in candidate_rows]
    if base_questions != candidate_questions:
        incompatible.append("questions")
    if (base.get("controls") or {}).get("fingerprint") != \
            (candidate.get("controls") or {}).get("fingerprint"):
        incompatible.append("controls")

    b_variant = dict(base.get("variant") or {})
    c_variant = dict(candidate.get("variant") or {})
    configuration_diff = [
        {"kind": "variant", "key": key, "before": b_variant.get(key),
         "after": c_variant.get(key)}
        for key in sorted(set(b_variant) | set(c_variant))
        if b_variant.get(key) != c_variant.get(key)
    ]
    if require_one_change and len(configuration_diff) != 1:
        incompatible.append("one_variable_configuration")

    bs, cs = dict(base.get("summary") or {}), dict(candidate.get("summary") or {})
    cases = max(int(bs.get("cases") or len(base_rows)), 1)
    metric_paths = {
        "positive_case_source_recall": ("positive_case_source_recall",),
        "positive_coordinate_recall": ("positive_coordinate_recall",),
        "structured_entry_coordinate_recall": ("structured_entry_coordinate_recall",),
        "positive_expected_share_of_context": ("positive_expected_share_of_context",),
        "legacy_negative_structured_lock_rate": ("legacy_negative_structured_lock_rate",),
        "final_contexts_mean": ("final_contexts", "mean"),
        "latency_ms_p50": ("latency_ms", "p50"),
        "latency_ms_p95": ("latency_ms", "p95"),
        "latency_ms_max": ("latency_ms", "max"),
        "calls_per_case": ("usage", "calls"),
        "input_tokens_per_case": ("usage", "input_tokens"),
        "output_tokens_per_case": ("usage", "output_tokens"),
        "llm_duration_ms_per_case": ("usage", "duration_ms"),
        "llm_errors": ("usage", "errors"),
    }

    def read(blob, path):
        value: Any = blob
        for key in path:
            value = (value or {}).get(key) if isinstance(value, Mapping) else 0
        return float(value or 0)

    before, after, deltas = {}, {}, {}
    for key, path in metric_paths.items():
        left, right = read(bs, path), read(cs, path)
        if key.endswith("_per_case"):
            left, right = left / cases, right / cases
        before[key], after[key] = round(left, 6), round(right, 6)
        deltas[key] = round(right - left, 6)

    by_candidate = {str(row.get("id")): row for row in candidate_rows}
    case_changes = []
    quality_regressions = []
    for left in base_rows:
        cid = str(left.get("id"))
        right = by_candidate.get(cid)
        if right is None:
            continue
        expected = {tuple(row) for row in left.get("expected_sources") or []}
        b_final = {tuple(row) for row in left.get("final_sources") or []}
        c_final = {tuple(row) for row in right.get("final_sources") or []}
        b_hits = len(expected & b_final)
        c_hits = len(expected & c_final)
        b_excess = len(b_final - expected) if left.get("expect_hit") else 0
        c_excess = len(c_final - expected) if right.get("expect_hit") else 0
        if b_hits != c_hits or b_excess != c_excess or b_final != c_final:
            case_changes.append({
                "id": cid, "expect_hit": bool(left.get("expect_hit")),
                "expected_hits": {"before": b_hits, "after": c_hits},
                "excess_contexts": {"before": b_excess, "after": c_excess},
                "added_sources": sorted(c_final - b_final),
                "removed_sources": sorted(b_final - c_final),
            })
        if left.get("expect_hit") and c_hits < b_hits:
            quality_regressions.append(cid)

    guide_rows = [dict(row.get("query_guide") or {}) for row in candidate_rows]
    guide_stats = {
        "enabled_cases": sum(bool(row.get("enabled")) for row in guide_rows),
        "selected_cases": sum(bool(row.get("selected_ids")) for row in guide_rows),
        "truncated_cases": sum(bool(row.get("truncated")) for row in guide_rows),
        "mean_mentions": round(sum(int(row.get("mention_count", 0)) for row in guide_rows)
                               / max(len(guide_rows), 1), 3),
        "mean_readings": round(sum(int(row.get("reading_count", 0)) for row in guide_rows)
                               / max(len(guide_rows), 1), 3),
        "mean_selected": round(sum(len(row.get("selected_ids") or []) for row in guide_rows)
                               / max(len(guide_rows), 1), 3),
    }
    warnings = []
    for key in ("calls_per_case", "input_tokens_per_case", "output_tokens_per_case",
                "llm_duration_ms_per_case", "latency_ms_p50", "latency_ms_p95"):
        left, right = before[key], after[key]
        ratio = (right - left) / left if left else 0.0
        if ratio > .10:
            warnings.append({"measure": key, "before": left, "after": right,
                             "ratio": round(ratio, 6)})
    quality_keys = (
        "positive_case_source_recall", "positive_coordinate_recall",
        "structured_entry_coordinate_recall", "positive_expected_share_of_context",
    )
    aggregate_regressions = [key for key in quality_keys if deltas[key] < 0]
    if incompatible:
        verdict = "invalid"
    elif quality_regressions or aggregate_regressions or after["llm_errors"]:
        verdict = "regressed"
    elif any(deltas[key] > 0 for key in quality_keys):
        verdict = "improved"
    elif deltas["calls_per_case"] < 0 and deltas["latency_ms_p95"] < 0:
        verdict = "mixed_more_efficient"
    else:
        verdict = "non_regression"
    return {
        "kind": "rag_search_benchmark_comparison", "verdict": verdict,
        "compatible": not incompatible, "incompatible": incompatible,
        "configuration_diff": configuration_diff,
        "before": before, "after": after, "deltas": deltas,
        "aggregate_regressions": aggregate_regressions,
        "quality_regression_cases": quality_regressions,
        "changed_cases": len(case_changes), "case_changes": case_changes,
        "guide": guide_stats, "warnings": warnings,
    }
