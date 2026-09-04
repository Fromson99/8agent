"""질의 중 발견한 새 표현의 단일 승격 흐름.

LLM은 새 표현을 이미 존재하는 DB 객체에 연결하는 *제안*만 만든다. 런타임은
그 제안을 바로 검색 정본에 쓰지 않는다. 사람이 승인하면 문서 표현은
``aliases.json``에, Concept 표현은 ``canonical.json``의 aliases에 발행한다.

    LLM 제안(pending) -> 사람 승인(approved) | 기각(rejected)

질문-좌표 기억, 프레임 후보, Concept 후보처럼 서로 다른 이름의 장부를 새로
만들지 않고, 사용자 표현 -> 정본 객체 연결을 이 원장 하나로 다룬다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from lawrag.core.rag.index import store_path
from lawrag.platform.paths import data_path


KINDS = frozenset({"document", "concept"})
STATUSES = frozenset({"pending", "approved", "rejected"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _data_dir() -> Path:
    if os.environ.get("STRUCTURE_STORE"):
        return store_path().parent
    return data_path()


def proposals_path() -> Path:
    return Path(os.environ.get(
        "RAG_TERM_PROPOSALS",
        _data_dir() / "domain_graph" / "term_proposals.json",
    ))


def aliases_path() -> Path:
    return Path(os.environ.get("RAG_ALIASES_STORE", _data_dir() / "aliases.json"))


def canonical_path() -> Path:
    return Path(os.environ.get(
        "RAG_CONCEPT_REGISTRY",
        _data_dir() / "domain_graph" / "canonical.json",
    ))


def _load() -> dict:
    path = proposals_path()
    if not path.is_file():
        return {"schema_version": 1, "proposals": []}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "proposals": []}
    blob.setdefault("schema_version", 1)
    blob.setdefault("proposals", [])
    return blob


def _save(blob: dict) -> None:
    path = proposals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.writing")
    tmp.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _proposal_id(surface: str, target_kind: str, target_id: str) -> str:
    raw = "\x1f".join((_pack(surface), target_kind, str(target_id)))
    return "term_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def propose(surface: str, *, target_kind: str, target_id: str,
            target_label: str, question: str, role: str = "",
            proposed_by: str = "llm") -> dict | None:
    """LLM의 닫힌 메뉴 선택을 사람 검수 후보로 적재한다.

    동일한 표현-정본 쌍은 한 행으로 접고 관측 횟수와 최근 질문만 갱신한다.
    제안은 검색에 아무 영향도 주지 않는다.
    """
    from lawrag.core.rag.content_snapshot import current_content_snapshot

    # Product queries are read-only with respect to the semantic authority.
    # Observations may be exported through a separate feedback control plane,
    # but they cannot alter the active release during a request.
    if current_content_snapshot() is not None or os.environ.get(
        "LAWRAG_SERVING_SEALED", ""
    ).strip().casefold() in {"1", "true", "yes", "on"}:
        return None
    surface = str(surface or "").strip()
    target_kind = str(target_kind or "").strip()
    target_id = str(target_id or "").strip()
    target_label = str(target_label or "").strip()
    if not surface or not target_id or target_kind not in KINDS:
        return None
    if _pack(surface) == _pack(target_label):
        return None
    blob = _load()
    pid = _proposal_id(surface, target_kind, target_id)
    now = _now()
    row = next((item for item in blob["proposals"] if item.get("id") == pid), None)
    evidence = {"question": str(question or "")[:1000], "surface": surface,
                "role": str(role or "")[:40], "at": now}
    if row is None:
        row = {
            "id": pid, "surface": surface, "normalized": _pack(surface),
            "target": {"kind": target_kind, "id": target_id,
                       "label": target_label},
            "status": "pending", "proposed_by": proposed_by,
            "count": 0, "first_seen": now, "last_seen": now,
            "evidence": [], "review": None,
        }
        blob["proposals"].append(row)
    row["count"] = int(row.get("count") or 0) + 1
    row["last_seen"] = now
    if evidence not in row.setdefault("evidence", []):
        row["evidence"] = [*row["evidence"][-9:], evidence]
    # 기각된 같은 쌍은 자동으로 다시 pending이 되지 않는다. 사람 판정을 이긴다.
    _save(blob)
    return row


def queue(status: str = "pending") -> list[dict]:
    if status not in {*STATUSES, "all"}:
        raise ValueError(f"알 수 없는 제안 상태: {status}")
    rows = _load()["proposals"]
    if status != "all":
        rows = [row for row in rows if row.get("status") == status]
    return sorted(rows, key=lambda row: (-int(row.get("count") or 0),
                                         row.get("last_seen", "")))


def _publish_document_alias(surface: str, label: str) -> None:
    path = aliases_path()
    try:
        aliases = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except Exception as exc:
        raise ValueError(f"문서 별칭 정본을 읽을 수 없음: {exc}") from exc
    packed = _pack(surface)
    conflicts = {key: value for key, value in aliases.items()
                 if _pack(key) == packed and _pack(value) != _pack(label)}
    if conflicts:
        raise ValueError(f"같은 문서 표현이 다른 정본을 가리킴: {conflicts}")
    aliases[surface] = label
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.writing")
    tmp.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _publish_concept_alias(surface: str, target_id: str) -> None:
    from lawrag.core.domain_graph.tier1 import Tier1Registry, concept_id

    path = canonical_path()
    if not path.is_file():
        raise ValueError("Concept 정본이 없음")
    blob = json.loads(path.read_text(encoding="utf-8"))
    wanted = concept_id(target_id)
    found = None
    for row in blob.get("concepts") or []:
        cid = concept_id(row.get("id"))
        surfaces = [row.get("label"), *(row.get("aliases") or [])]
        if cid != wanted and any(_pack(value) == _pack(surface) for value in surfaces):
            raise ValueError(f"표현이 이미 다른 Concept에 연결됨: {cid}")
        if cid == wanted:
            found = row
    if found is None:
        raise ValueError(f"Concept 정본에 대상이 없음: {wanted}")
    aliases = list(found.get("aliases") or [])
    if not any(_pack(value) == _pack(surface) for value in aliases):
        aliases.append(surface)
    found["aliases"] = aliases
    tmp = path.with_name(f".{path.name}.term-approval")
    tmp.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        Tier1Registry.load(tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


def resolve(proposal_id: str, action: str, *, reviewer: str = "user",
            note: str = "") -> dict:
    """사람 판정을 적용한다. 승인만 검색 정본에 발행한다."""
    normalized = {"승인": "approved", "기각": "rejected",
                  "approve": "approved", "reject": "rejected"}.get(action, action)
    if normalized not in {"approved", "rejected"}:
        raise ValueError("action은 승인 또는 기각이어야 함")
    blob = _load()
    row = next((item for item in blob["proposals"]
                if item.get("id") == proposal_id), None)
    if row is None:
        raise ValueError("용어 제안을 찾을 수 없음")
    target = row.get("target") or {}
    if normalized == "approved":
        if target.get("kind") == "document":
            _publish_document_alias(row["surface"], str(target.get("label") or ""))
        elif target.get("kind") == "concept":
            _publish_concept_alias(row["surface"], str(target.get("id") or ""))
        else:
            raise ValueError("지원하지 않는 용어 대상")
    row["status"] = normalized
    row["review"] = {"by": reviewer or "user", "at": _now(),
                     "action": normalized, "note": str(note or "")[:500]}
    _save(blob)
    from lawrag.core.rag import approvals
    approvals.safe_record(
        kind="term_proposal", decision=normalized,
        effect="term_activate" if normalized == "approved" else "term_reject",
        failure="용어_누락" if normalized == "approved" else "용어_오염",
        subject={"proposal_id": proposal_id, "surface": row.get("surface"),
                 "target": target},
        before={"status": "pending"}, after={"status": normalized}, note=note,
        actor=reviewer or "user",
        source={"ledger": "term_proposals", "proposed_by": row.get("proposed_by")})
    return row
