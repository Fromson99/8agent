"""T-A6.7 리포트·안내문·큐 (AGENT6 §5-7·§7).

세 파일이 나온다. 셋은 각각 다른 사람에게 간다.

    report.json         시스템·감사 — 활성 항목 전부가 정확히 한 행씩(§7)
    guidance.md         PB — "지금 다시 말해야 하는 것" 만. 그 외의 것은 싣지 않는다
    review_queue.jsonl  준법감시 — 사람이 해소하고, 해소 결과가 few_shot 으로 돌아온다(§6)

## guidance.md 에 준법감시큐 항목의 "권장 문구"를 적지 않는 이유

부재형 위반은 **이미 발화된 사실**이다. PB 가 지금 다시 말한다고 지워지지 않는다.
안내문에 "이렇게 다시 말하세요"를 적으면 그 항목이 재안내로 해소된다는 잘못된 신호를
준다. 그래서 준법감시큐 항목은 "검토 중"으로만 뜬다(schema.GuidanceEntry 가 이것을
검증한다).

## unclear_rate_history — 수렴을 보는 눈 (§6)

UNCLEAR 는 없애야 할 것이 아니라 **줄어들어야 할 것**이다. 한 번의 실행으로는 알 수
없으므로 실행마다 항목별 누적(활성 횟수·UNCLEAR 횟수)을 파일에 쌓고, 그 시점까지의
비율을 리포트에 싣는다. 우하향하지 않으면 스펙 개선이 필요하다는 신호다(§6 3단 경로).

## 점검하지 못한 항목이 있으면 종합 판정은 통과가 아니다

`recount()` 는 FAIL·UNCLEAR 만 세어 종합 판정을 낸다. 그 셈만으로는 근거 미해소로
활성이 차단된 항목(basis_policy=block)이나 스펙에서 꺼 둔 항목이 NOT_APPLICABLE 로
빠지면서 리포트가 **"완전판매요건충족"** 이 된다 — 실제로 그렇게 나왔다. 점검하지 못한
것은 통과의 근거가 아니므로 여기서 종합 판정을 끌어내리고 사유를 남긴다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, get_args

from lawrag.agents.agent6.src import aggregate, schema
from lawrag.agents.agent6.src.context_asm import ItemContext
from lawrag.agents.agent6.src.judge import Judged
from lawrag.agents.agent6.src.preprocess import Prepared

REPORT_NAME = "report.json"
GUIDANCE_NAME = "guidance.md"
QUEUE_NAME = "review_queue.jsonl"
HISTORY_NAME = "unclear_rate_history.json"

# 항목별 비율 이력의 보관 길이. 무한히 쌓으면 리포트가 이력 파일이 된다.
HISTORY_LIMIT = 24

# 종합 판정 어휘는 schema 가 정한다. '점검불가' 라는 별도 상태가 있으면 그것을 쓰고,
# 없으면 '보완필요' 로 떨어뜨린다 — 어느 쪽이든 낙관적 통과는 없다.
_OVERALL_VALUES = tuple(get_args(schema.Overall))
PASS_OVERALL = "완전판매요건충족"
UNCHECKED_OVERALL = "점검불가" if "점검불가" in _OVERALL_VALUES else "보완필요"


# ===========================================================================
# 안내문 재료
# ===========================================================================

def _missing_text(row: schema.ItemVerdict) -> str:
    """무엇이 빠졌는가 — PB 가 읽고 바로 행동할 수 있는 한 줄."""
    if row.verdict == "FAIL" and row.type == "존재형":
        head = f"'{row.name}' 에 해당하는 고지·설명이 전사에서 확인되지 않았습니다"
    elif row.verdict == "UNCLEAR":
        head = f"'{row.name}' 의 충족 여부를 판정하지 못했습니다"
    else:
        head = f"'{row.name}' 이 미비로 판정됐습니다"
    detail = (row.llm_reason or "").strip()
    return f"{head} — {detail}" if detail else head


def _own_script(item: schema.ChecklistItem) -> str:
    """항목 자신의 권장 문구. **지어내지 않고 스펙에서 가져온다.**

    1순위는 few_shot 의 PASS 예시다 — 사람이 "이렇게 말하면 충족"이라고 확정해 둔
    문장이고, 큐 해소 결과가 여기로 재적재되므로(§6) 시간이 갈수록 현장 문구로 수렴한다.
    2순위는 운영 정의의 첫 문장. 둘 다 없으면 빈 문자열을 둔다(빈 것이 지어낸 것보다 낫다).
    """
    passing = [fs for fs in item.few_shot if fs.verdict == "PASS"]
    if passing:
        return passing[0].utterance.strip()
    first = item.operational_definition.strip().split(". ")[0].strip()
    return f"({first}) 를 명확히 안내해 주세요" if first else ""


def _script_for(row: schema.ItemVerdict, item: schema.ChecklistItem,
                prepared: Prepared, rows: dict[str, schema.ItemVerdict]) -> str:
    """권장 안내 문구.

    파생 항목은 자기 문구가 없다 — 그 항목의 미비는 **구성 항목의 미비**이기 때문이다.
    F-29 의 운영정의가 요구하는 대로 실패한 구성 항목의 문구를 그대로 인용한다.
    """
    if item.derived is not None:
        parts = []
        for src in item.derived.sources():
            r = rows.get(src)
            if r is None or r.verdict not in ("FAIL", "UNCLEAR"):
                continue
            parts.append(f"[{src} {r.name}] {_own_script(prepared.item(src))}")
        if parts:
            return " / ".join(parts)
    return _own_script(item)


def _basis_line(row: schema.ItemVerdict, ctx: Optional[ItemContext]) -> list[str]:
    """근거 좌표. 발췌 원문이 있으면 첫 줄만 인용한다(안내문에 조문을 통째로 싣지 않는다)."""
    refs = list(row.basis_refs)
    if ctx is None:
        return refs
    out = []
    for ex in ctx.excerpts:
        if ex.present and ex.text.strip():
            head = ex.text.strip().splitlines()[0][:80]
            out.append(f"{ex.coordinate} — {head}")
        else:
            out.append(f"{ex.coordinate} (발췌 없음)")
    return out or refs


def build_guidance(rows: Sequence[schema.ItemVerdict], prepared: Prepared,
                   contexts: dict[str, ItemContext]) -> list[schema.GuidanceEntry]:
    """라우팅이 있는 행 전부를 안내문 항목으로. **행을 고르지 않는다** — 라우팅이 고른다."""
    out: list[schema.GuidanceEntry] = []
    by_id = {r.id: r for r in rows}
    for row in rows:
        if row.route is None:
            continue
        item = prepared.item(row.id)
        ctx = contexts.get(row.id)
        pb = row.route == "PB보완"
        out.append(schema.GuidanceEntry(
            item_id=row.id, name=row.name, verdict=row.verdict, route=row.route,
            missing=_missing_text(row),
            recommended_script=_script_for(row, item, prepared, by_id) if pb else "",
            basis_refs=_basis_line(row, ctx),
            status="재안내필요" if pb else "검토중"))
    return out


def guidance_markdown(report: schema.Report,
                      entries: Sequence[schema.GuidanceEntry]) -> str:
    pb = [e for e in entries if e.route == "PB보완"]
    queue = [e for e in entries if e.route == "준법감시큐"]
    lines = [
        f"# 미비사항 안내 — {Path(report.transcript).name}",
        "",
        f"- 생성: {report.generated_at}",
        f"- 체크리스트: {report.checklist_version}",
        f"- 종합 판정: **{report.overall}**",
        f"- 활성 {report.stats.get('active', 0)}항목 중 "
        f"통과 {report.stats.get('pass', 0)} / 미비 {report.stats.get('fail', 0)} / "
        f"판정보류 {report.stats.get('unclear', 0)}",
        "",
    ]

    lines += [f"## 지금 다시 안내해 주세요 (PB 보완 {len(pb)}건)", ""]
    if not pb:
        lines += ["재안내가 필요한 항목이 없습니다.", ""]
    for e in pb:
        lines += [f"### {e.item_id} {e.name}  [{e.verdict}]", ""]
        lines += [f"- 무엇이 빠졌는가: {e.missing}"]
        if e.recommended_script:
            lines += [f"- 권장 안내 문구: \"{e.recommended_script}\""]
        if e.basis_refs:
            lines += ["- 근거: " + "; ".join(e.basis_refs)]
        lines += [""]

    lines += [f"## 준법감시 검토 중 ({len(queue)}건)", ""]
    if not queue:
        lines += ["검토 대기 항목이 없습니다.", ""]
    else:
        lines += ["재안내로 해소되지 않는 항목입니다. 준법감시 큐에 적재했습니다.", "",
                  "| 항목 | 이름 | 판정 | 사유 |", "|---|---|---|---|"]
        for e in queue:
            reason = e.missing.replace("|", "/").replace("\n", " ")
            lines += [f"| {e.item_id} | {e.name} | {e.verdict} | {reason} |"]
        lines += [""]

    # 비활성을 두 갈래로 나눠 싣는다. "해당 없음"과 "못 봤음"은 전혀 다른 사실이고,
    # 한 표에 섞으면 읽는 사람이 뒤쪽을 앞쪽으로 읽는다.
    blocked = aggregate.unchecked(report.items)
    blocked_ids = {r.id for r in blocked}
    na = [r for r in report.items if not r.active and r.id not in blocked_ids]
    if blocked:
        lines += [f"## 점검하지 못한 항목 ({len(blocked)}건)", "",
                  "**통과로 읽지 마십시오.** 이 항목들은 판정 자체를 하지 못했습니다.", "",
                  "| 항목 | 이름 | 사유 |", "|---|---|---|"]
        for r in blocked:
            lines += [f"| {r.id} | {r.name} | {(r.inactive_reason or '').replace('|', '/')} |"]
        lines += [""]
    if na:
        lines += [f"## 이번 통화에 해당하지 않는 항목 ({len(na)}건)", "",
                  "| 항목 | 이름 | 사유 |", "|---|---|---|"]
        for r in na:
            lines += [f"| {r.id} | {r.name} | {(r.inactive_reason or '').replace('|', '/')} |"]
        lines += [""]

    if report.notes:
        lines += ["## 실행 비고", ""] + [f"- {n}" for n in report.notes] + [""]
    return "\n".join(lines)


# ===========================================================================
# 큐
# ===========================================================================

def build_queue(rows: Sequence[schema.ItemVerdict],
                prepared: Prepared) -> list[schema.QueueEntry]:
    """준법감시 큐 적재 대상 — 라우팅이 준법감시큐인 행 전부(§5-7)."""
    out: list[schema.QueueEntry] = []
    for row in rows:
        if row.route != "준법감시큐":
            continue
        out.append(schema.QueueEntry(
            transcript=prepared.transcript.path, item_id=row.id, name=row.name,
            type=row.type, verdict=row.verdict, route=row.route,
            reason=row.llm_reason or "", confidence=row.confidence,
            evidence=list(row.evidence or []), basis_refs=list(row.basis_refs)))
    return out


def write_queue(path: str | Path, entries: Sequence[schema.QueueEntry],
                *, append: bool = True) -> tuple[Path, int]:
    """큐 파일에 적재한다. 같은 전사·항목이 이미 있으면 다시 넣지 않는다.

    큐는 사람의 작업 목록이다. 같은 전사를 두 번 돌렸다고 같은 일이 두 줄로 늘어나면
    해소율 통계가 망가진다.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()
    if append and p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add((str(row.get("transcript")), str(row.get("item_id"))))
    fresh = [e for e in entries if (e.transcript, e.item_id) not in seen]
    mode = "a" if (append and p.exists()) else "w"
    with p.open(mode, encoding="utf-8") as fh:
        for e in fresh:
            fh.write(json.dumps(e.model_dump(exclude_none=True), ensure_ascii=False) + "\n")
    return p, len(fresh)


# ===========================================================================
# UNCLEAR 비율 이력 (§6 수렴 루프)
# ===========================================================================

def update_history(path: str | Path, rows: Sequence[schema.ItemVerdict],
                   *, persist: bool = True) -> dict[str, list[float]]:
    """항목별 누적 UNCLEAR 비율을 갱신하고 리포트에 실을 계열을 돌려준다."""
    p = Path(path)
    store: dict[str, Any] = {"version": 1, "runs": 0, "items": {}}
    if p.exists():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("items"), dict):
                store = loaded
        except json.JSONDecodeError:
            pass                      # 깨진 이력이 실행을 막지는 않는다 — 새로 시작한다
    store["runs"] = int(store.get("runs", 0)) + 1

    items: dict[str, Any] = store["items"]
    for row in rows:
        if not row.active:
            continue                  # 비활성은 분모에 넣지 않는다 (점검하지 않은 것이다)
        rec = items.setdefault(row.id, {"active": 0, "unclear": 0, "rates": []})
        rec["active"] = int(rec.get("active", 0)) + 1
        rec["unclear"] = int(rec.get("unclear", 0)) + (1 if row.verdict == "UNCLEAR" else 0)
        rate = round(rec["unclear"] / rec["active"], 4)
        rec["rates"] = (list(rec.get("rates", [])) + [rate])[-HISTORY_LIMIT:]

    if persist:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: list(v.get("rates", [])) for k, v in items.items() if v.get("rates")}


# ===========================================================================
# 조립·기록
# ===========================================================================

def build(prepared: Prepared, rows: Sequence[schema.ItemVerdict], judged: Judged,
          *, extra_notes: Iterable[str] = (), history: Optional[dict] = None
          ) -> schema.Report:
    notes: list[str] = []
    notes.append(f"판정 모드: {judged.mode}")
    notes.append(f"정규화: {prepared.transcript.normalizer.mode}")
    notes.extend(prepared.notes)
    notes.extend(judged.notes)
    notes.extend(extra_notes)
    notes.extend(f"경고: {w}" for w in prepared.warnings)
    notes.extend(f"경고: {w}" for w in judged.warnings)

    report = schema.Report(
        transcript=prepared.transcript.path,
        checklist_version=prepared.checklist_version,
        items=list(rows), meta=prepared.meta,
        unclear_rate_history=history or {},
        notes=[n for n in notes if n])
    report.recount()
    return _apply_unchecked(report, judged)


def _apply_unchecked(report: schema.Report, judged: Judged) -> schema.Report:
    """점검하지 못한 항목이 있으면 종합 판정을 끌어내린다(모듈 설명 참조).

    두 갈래를 본다. 활성이 차단된 행(`aggregate.unchecked`)과, LLM 을 쓰지 못해 판정을
    받지 못한 항목(`judged.unavailable`)이다. 뒤쪽은 이미 UNCLEAR 로 세어져 종합 판정이
    통과가 아니지만, **왜** 통과가 아닌지가 "판정보류 n건"으로만 남으면 점검 실패가
    보통의 애매함과 같은 무게로 읽힌다. 사유를 따로 적는다.
    """
    blocked = aggregate.unchecked(report.items)
    if blocked:
        if report.overall == PASS_OVERALL:
            report.overall = UNCHECKED_OVERALL
        report.notes.insert(0, (
            f"점검하지 못한 항목 {len(blocked)}개"
            f"({', '.join(r.id for r in blocked)}) — 종합 판정을 '{report.overall}' 로 둡니다. "
            f"점검하지 못한 것은 통과의 근거가 아닙니다"))
    if judged.unavailable:
        if report.overall == PASS_OVERALL:      # 방어적 — 보통은 UNCLEAR 로 이미 내려간다
            report.overall = UNCHECKED_OVERALL
        report.notes.insert(0, (
            f"LLM 판정을 받지 못한 항목 {len(judged.unavailable)}개"
            f"({', '.join(sorted(judged.unavailable))}) — **점검 실패**입니다. "
            f"이 실행의 결과를 통과로 읽지 마십시오"))
    return report


def write(bundle_report: schema.Report, entries: Sequence[schema.GuidanceEntry],
          queue: Sequence[schema.QueueEntry], out_dir: str | Path,
          *, append_queue: bool = True) -> dict[str, str]:
    """세 파일을 쓴다. 경로를 돌려준다 — CLI 가 사람에게 보여 준다."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    rp = d / REPORT_NAME
    rp.write_text(json.dumps(bundle_report.dump(), ensure_ascii=False, indent=2),
                  encoding="utf-8")
    gp = d / GUIDANCE_NAME
    gp.write_text(guidance_markdown(bundle_report, entries), encoding="utf-8")
    qp, added = write_queue(d / QUEUE_NAME, queue, append=append_queue)
    return {"report": str(rp), "guidance": str(gp), "queue": str(qp),
            "queue_added": str(added)}


def _pad(text: str, width: int) -> str:
    """한글은 두 칸을 차지한다. 문자 수로 맞추면 표가 어긋나 읽히지 않는다."""
    from unicodedata import east_asian_width
    shown = sum(2 if east_asian_width(c) in ("W", "F") else 1 for c in text)
    return text + " " * max(width - shown, 0)


def to_text(report: schema.Report) -> str:
    """사람이 읽는 요약 — CLI 표준 출력(§10)."""
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"전사       {report.transcript}",
        f"체크리스트 {report.checklist_version}    실행 {now}",
        f"종합 판정  {report.overall}",
        "",
        _pad("항목", 8) + _pad("유형", 10) + _pad("판정", 16)
        + _pad("라우팅", 12) + _pad("신뢰도", 8) + "근거/사유",
        "-" * 100,
    ]
    for r in report.items:
        if r.evidence:
            first = r.evidence[0]
            ev = f"[{first.section_id or '?'}] {first.text[:34]}"
        elif not r.active:
            ev = (r.inactive_reason or "")[:44]
        else:
            ev = (r.llm_reason or "")[:44]
        lines.append(_pad(r.id, 8) + _pad(r.type, 10) + _pad(r.verdict, 16)
                     + _pad(r.route or "-", 12) + _pad(r.confidence, 8) + ev)
    s = report.stats
    blocked = aggregate.unchecked(report.items)
    lines += [
        "-" * 96,
        f"활성 {s.get('active', 0)} / 전체 {s.get('total', 0)}    "
        f"통과 {s.get('pass', 0)}  미비 {s.get('fail', 0)}  "
        f"판정보류 {s.get('unclear', 0)}  비활성 {s.get('not_applicable', 0)}",
    ]
    if blocked:
        lines.append(f"점검불가 {len(blocked)}건 ({', '.join(r.id for r in blocked)}) "
                     f"— 통과로 세지 않습니다")
    if report.notes:
        lines += ["", "비고"] + [f"  · {n}" for n in report.notes]
    return "\n".join(lines)
