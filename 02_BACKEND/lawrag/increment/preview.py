"""신구조문 대비표 — 승인자가 보는 내용과 그 해시.

승인은 대비표 해시를 함께 보내야 통과한다. 비교 결과가 그 사이 바뀌었으면
(수동 연결·재적재) 해시가 달라져 옛 화면으로 승인할 수 없다.
"""
from __future__ import annotations

import difflib
import hashlib
import html
import json

_GATE_FIELDS = ("counts", "change_rate", "old_content", "new_content", "warnings", "stop",
                "stop_reason", "effective", "promulgation_no")
_TYPE_LABEL = {"AMEND": "개정", "MOVE": "이동", "MOVE_AMEND": "이동·개정", "REF_ONLY": "인용번호만",
               "ADD": "신설", "DELETE": "삭제", "SAME": "동일"}


def build_preview(doc_cd: str, name: str, source_sha256: str, effective: str, gate: dict,
                  rows: list[dict], olds: dict) -> dict:
    changes = []
    for row in rows:
        payload = json.loads(row["CMPR_ADDN_IFMN_CTNT"]) if row.get("CMPR_ADDN_IFMN_CTNT") else None
        old = olds.get(row.get("OLD_ARTC_VER_ID")) if row.get("OLD_ARTC_VER_ID") else None
        changes.append({
            "seq": int(row["CMPR_SEQ"]),
            "type": row["CHG_TYPE_CD"],
            "old_key": row.get("OLD_ARTC_KEY_VALU"),
            "new_key": row.get("NEW_ARTC_KEY_VALU"),
            "lineage": row["LNG_ID"],
            "similarity": round(float(row["SMLR_RATE"] or 0), 4),
            "reason": row.get("JDGM_RSN_CTNT") or "",
            "effective_from": row.get("ENFC_STRT_DT") or "",
            "rule_review": row["RULE_RVW_YN"],
            "old_title": old.title if old else None,
            "old_text": old.text if old else None,
            "old_effective_from": old.effective_from if old else None,
            "new_title": payload["title"] if payload else None,
            "new_text": payload["text"] if payload else None,
            "official_note": (payload or {}).get("official_note", ""),
        })
    schedule = gate.get("schedule") or {}
    return {
        "doc_cd": doc_cd, "name": name, "source_sha256": source_sha256, "effective": effective,
        "gate": {k: gate.get(k) for k in _GATE_FIELDS},
        "addendum_schedule": {"per_article": schedule.get("per_article", {}),
                              "unparsed": schedule.get("unparsed", []),
                              "source": schedule.get("source_key", "")},
        "rule_reviews": [c["new_key"] or c["old_key"] for c in changes if c["rule_review"] == "Y"],
        "changes": changes,
    }


def preview_hash(preview: dict) -> str:
    encoded = json.dumps(preview, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _label(key: str) -> str:
    number, _, branch = key.partition("의")
    return f"제{number}조" + (f"의{branch}" if branch else "")


def _diff_cells(old: str, new: str) -> tuple[str, str]:
    a, b = old.split("\n"), new.split("\n")
    left, right = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        for line in a[i1:i2]:
            left.append(f'<div class="{"" if tag == "equal" else "del"}">{html.escape(line)}</div>')
        for line in b[j1:j2]:
            right.append(f'<div class="{"" if tag == "equal" else "ins"}">{html.escape(line)}</div>')
    return "".join(left), "".join(right)


def render_html(preview: dict, digest: str) -> str:
    gate = preview["gate"]
    counts = " · ".join(f"{_TYPE_LABEL.get(k, k)} {v}" for k, v in (gate.get("counts") or {}).items() if v)
    warnings = "".join(
        f'<li class="{"strong" if w["strong"] else ""}">{html.escape(w["code"])}: {html.escape(w["message"])}</li>'
        for w in gate.get("warnings") or [])
    rows = []
    for c in preview["changes"]:
        old = html.escape(c["old_text"] or "")
        new = html.escape(c["new_text"] or "")
        if c["old_text"] and c["new_text"]:
            old, new = _diff_cells(c["old_text"], c["new_text"])
        label = _TYPE_LABEL.get(c["type"], c["type"])
        keys = f'{c["old_key"] or "—"} → {c["new_key"] or "—"}'
        rows.append(
            f'<tr class="t-{c["type"]}"><td>{c["seq"]}</td><td><b>{label}</b><br>{html.escape(keys)}'
            f'<br>유사도 {c["similarity"]:.2f}<br>시행 {c["effective_from"]}'
            f'{"<br>룰 재검토" if c["rule_review"] == "Y" else ""}</td>'
            f'<td>{old}</td><td>{new}</td><td>{html.escape(c["reason"])}'
            f'{"<br><i>" + html.escape(c["official_note"]) + "</i>" if c["official_note"] else ""}</td></tr>')
    schedule = preview["addendum_schedule"]
    per_article = ", ".join(f"{_label(k)} {v}" for k, v in schedule["per_article"].items()) or "없음"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>신구조문 대비표 — {html.escape(preview["name"])}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;width:100%;table-layout:fixed}}
td,th{{border:1px solid #bbb;padding:6px;vertical-align:top;font-size:13px;word-break:break-all}}
th{{background:#f2f2f2}} .del{{background:#fde2e2;text-decoration:line-through}} .ins{{background:#dff5e1}}
li.strong{{color:#b00020;font-weight:bold}} code{{background:#f4f4f4;padding:2px 4px}}
</style></head><body>
<h2>신구조문 대비표 — {html.escape(preview["name"])}</h2>
<p>문서코드 <code>{html.escape(preview["doc_cd"])}</code> · 공포번호 {html.escape(str(gate.get("promulgation_no") or ""))}
· 시행일 {html.escape(preview["effective"])} · 원문 sha256 <code>{preview["source_sha256"][:16]}…</code></p>
<p>{html.escape(counts)} · 변경률 {float(gate.get("change_rate") or 0):.1%} (이동·인용번호·부칙 제외)</p>
<p>부칙 조문별 시행일: {html.escape(per_article)}</p>
<ul>{warnings or "<li>경고 없음</li>"}</ul>
{f'<p><b>멈춤: {html.escape(gate["stop"])}</b> — {html.escape(gate.get("stop_reason") or "")}</p>' if gate.get("stop") else ""}
<p>승인할 때 대비표 해시: <code>{digest}</code></p>
<table><tr><th style="width:3%">#</th><th style="width:12%">판정</th><th style="width:35%">구조문</th>
<th style="width:35%">신조문</th><th style="width:15%">이유</th></tr>{"".join(rows)}</table>
</body></html>"""
