"""새 표 없이 비교·판단 — 지금 판본(Gold에서 읽은 구조) vs 새 판본(떨어진 파일의 구조화 결과).

판단 (자동 반영, 사람 승인 없음)
- NO_CHANGE: 조문 변화 없음
- HOLD: 게이트 차단(BLOCKED·BLOCKED_PENDING) 또는 강한 경고(조문 수 급감·대량 삭제·변경률 50% 초과·
  별표 소실·시행일 못 읽음) — 파일이 잘렸거나 판본 순서가 꼬였을 가능성. 이번 세대에 넣지 않는다.
- WAIT_EFFECTIVE: 문서 시행일이 아직 오지 않음. Gold는 조문별 시행일이 없어 넣는 순간 서빙되므로
  시행일까지 기다린다 (다음 실행에서 다시 판단).
- APPROVED: 그 밖. 일부 조문만 늦게 시행되는 부칙 예외는 경고로 남긴다 (Gold는 판본 통째로 서빙).
"""
from __future__ import annotations

from .addenda import schedule_for
from .diff import BaseArticle, diff_snapshot
from .gate import assign_effective, evaluate, today_kst
from .lawgo_parse import KIND_ADDENDUM, DocumentSnapshot
from .preview import build_preview, preview_hash, render_html
from .service import comparison_rows

APPROVED, HOLD, WAIT_EFFECTIVE, NO_CHANGE = "APPROVED", "HOLD", "WAIT_EFFECTIVE", "NO_CHANGE"


def base_of(snapshot: DocumentSnapshot) -> list[BaseArticle]:
    return [BaseArticle(a.key, a.kind, a.title, a.text, "L:" + a.key, "old:" + a.key, snapshot.effective,
                        a.seq, a.attachment_sha256) for a in snapshot.articles if not a.deleted]


def compare(old: DocumentSnapshot | None, new: DocumentSnapshot, *, today: str | None = None,
            hold_on_strong: bool = True) -> dict:
    today = today or today_kst()
    base = base_of(old) if old is not None else []
    diff = diff_snapshot(base, new.articles, doc_cd=new.doc_cd, version_id="new:" + new.source_sha256[:16])
    schedule = schedule_for(new)
    effective = assign_effective(diff, new, schedule)
    gate = evaluate(diff, new, schedule, base_effective=old.effective if old is not None else "",
                    base_count=len(base), today=today)
    strong = [w for w in gate.warnings if w.strong]
    later = sorted({c.effective_from for c in diff.changes
                    if c.effective_from and effective and c.effective_from > effective and c.kind != KIND_ADDENDUM})
    gate_dict = {**gate.as_dict(), "effective": effective, "schedule": schedule.__dict__, "doc_name": new.name,
                 "promulgation_no": new.promulgation_no}
    if gate.no_change:
        decision, reasons = NO_CHANGE, []
    elif gate.stop:
        decision, reasons = HOLD, [gate.stop_reason or gate.stop]
    elif strong and hold_on_strong:
        decision, reasons = HOLD, [f"{w.code}: {w.message}" for w in strong]
    elif effective and effective > today:
        decision, reasons = WAIT_EFFECTIVE, [f"문서 시행일 {effective} 전 — 그날 이후 실행에서 반영"]
    else:
        decision, reasons = APPROVED, []
    warnings = [f"{w.code}: {w.message}" for w in gate.warnings if not w.strong]
    if later:
        warnings.append(f"일부 조문 시행일이 더 늦음 {later[:5]} — Gold는 판본 통째로 서빙하므로 그 조문도 바로 보임")
    rows = comparison_rows("cmp", "new:" + new.source_sha256[:16], diff.changed())
    preview = build_preview(new.doc_cd, new.name, new.source_sha256, effective, gate_dict, rows,
                            {a.version_id: a for a in base})
    digest = preview_hash(preview) if decision != NO_CHANGE else ""
    changes = [{"type": c.change_type, "old": c.old.key if c.old else None, "new": c.new.key if c.new else None,
                "effective_from": c.effective_from, "similarity": round(float(c.similarity), 4),
                "old_text": c.old.text if c.old else None, "new_text": c.new.text if c.new else None}
               for c in diff.changed()]
    return {"doc_cd": new.doc_cd, "name": new.name, "decision": decision, "reasons": reasons,
            "warnings": warnings, "effective": effective, "counts": gate.counts,
            "promulgation_no": new.promulgation_no, "new_sha256": new.source_sha256,
            "old_sha256": old.source_sha256 if old is not None else "",
            "preview_hash": digest, "preview_html": render_html(preview, digest) if decision != NO_CHANGE else "",
            "changes": changes}
