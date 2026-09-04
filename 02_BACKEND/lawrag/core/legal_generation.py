"""공식 법령 정본 세대 계약.

수집 순서나 디렉터리 mtime이 아니라 manifest가 가리키는 본문 해시 집합으로
canonical generation을 만든다. 이 값은 structure meta, law_index,
delegation, domain graph가 공유한다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SCHEMA_VERSION = "legal-authority-generation-v1"


class GenerationError(ValueError):
    pass


def _body_sha(item: dict) -> str:
    value = str(item.get("body_sha256") or item.get("body_html_sha256") or "").strip().lower()
    if not value:
        value = str(next((row.get("sha256") for row in item.get("attachments", ())
                          if row.get("role") == "body" and row.get("sha256")), "")).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise GenerationError(f"{item.get('name')}: canonical body_sha256가 없음")
    return value


def build_contract(manifest: dict, *, as_of: str | None = None) -> dict:
    """manifest의 현재 항목 하나씩으로 안정적인 세대 계약을 만든다."""
    seen: set[tuple[str, str]] = set()
    docs = []
    for item in manifest.get("items") or ():
        if item.get("status") not in ("ok", "partial", None):
            continue
        name = str(item.get("name") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not name or kind not in {"law", "admrul"}:
            continue
        key = (kind, "".join(name.split()))
        if key in seen:
            raise GenerationError(f"canonical 법령 중복: {kind}:{name}")
        seen.add(key)
        sha = _body_sha(item)
        docs.append({
            "name": name,
            "kind": kind,
            "doc_id": sha[:16],
            "body_sha256": sha,
            "official_id": str(item.get("law_id") or ""),
            "official_serial": str(item.get("doc_no") or ""),
            "authority_mode": str(item.get("authority_mode") or "manifest-canonical"),
            "authority_as_of": str(item.get("authority_as_of") or ""),
        })
    if not docs:
        raise GenerationError("canonical 법령 문서가 없음")
    docs.sort(key=lambda row: (row["kind"], "".join(row["name"].split()), row["doc_id"]))
    effective = str(as_of or manifest.get("authority_as_of") or "").replace("-", "")
    if not effective:
        dates = {row["authority_as_of"].replace("-", "") for row in docs
                 if row["authority_as_of"]}
        if len(dates) == 1:
            effective = dates.pop()
        else:
            raise GenerationError("manifest authority_as_of가 없거나 항목 기준일이 갈림")
    payload = {"schema_version": SCHEMA_VERSION, "as_of": effective,
               "documents": docs}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    payload["generation_id"] = hashlib.sha256(encoded).hexdigest()
    payload["canonical_document_ids"] = [row["doc_id"] for row in docs]
    return payload


def atomic_json(path: Path, value: dict, *, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=indent) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def synchronize_structure(store: Path, contract: dict) -> dict:
    """canonical 집합을 기준으로 동일 계열 meta status를 원자 갱신한다."""
    canonical = {(row["kind"], row["name"]): row for row in contract["documents"]}
    generation = contract["generation_id"]
    as_of = contract["as_of"]
    changed = current = old = 0
    for meta_path in sorted(store.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        key = (str(meta.get("kind") or ""),
               str(meta.get("series") or meta.get("name") or ""))
        row = canonical.get(key)
        if row is None or meta.get("source_kind") != "lawxml":
            continue
        is_current = meta_path.parent.name == row["doc_id"]
        desired = {
            "series": row["name"],
            "status": "현행" if is_current else "구판",
            "canonical": is_current,
            "authority_generation": generation,
            "canonical_as_of": as_of,
        }
        if is_current:
            desired.update({"authority_as_of": as_of,
                            "authority_mode": row["authority_mode"]})
        else:
            desired["superseded_by"] = row["doc_id"]
        if any(meta.get(k) != v for k, v in desired.items()):
            meta.update(desired)
            atomic_json(meta_path, meta, indent=2)
            changed += 1
        current += int(is_current)
        old += int(not is_current)
    expected = len(contract["documents"])
    missing = [row["doc_id"] for row in contract["documents"]
               if not (store / row["doc_id"] / "meta.json").is_file()]
    if missing:
        raise GenerationError(f"canonical structure 문서 누락: {missing}")
    if current != expected:
        raise GenerationError(f"canonical current meta 수 불일치: {current} != {expected}")
    return {"changed": changed, "current": current, "old": old,
            "generation_id": generation, "as_of": as_of}


def validate_consumers(data_dir: Path, store: Path, graph: Path | None = None) -> dict:
    """발행된 세대 소비자가 한 generation인지 fail-closed 검증한다."""
    law_index = json.loads((data_dir / "law_index.json").read_text(encoding="utf-8"))
    generation = law_index.get("generation_id")
    if not generation:
        raise GenerationError("law_index generation_id 없음")
    delegation = json.loads((data_dir / "delegation.json").read_text(encoding="utf-8"))
    if delegation.get("generation_id") != generation:
        raise GenerationError("delegation generation 불일치")
    canonical_ids = set(law_index.get("canonical_document_ids") or ())
    for doc_id in canonical_ids:
        meta = json.loads((store / doc_id / "meta.json").read_text(encoding="utf-8"))
        if (meta.get("authority_generation") != generation
                or meta.get("status") != "현행" or not meta.get("canonical")):
            raise GenerationError(f"canonical meta generation/status 불일치: {doc_id}")
    graph_generation = None
    if graph is not None and graph.is_file():
        import sqlite3
        with sqlite3.connect(f"file:{graph}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT value FROM build_meta WHERE key='authority_generation'").fetchone()
        graph_generation = json.loads(row[0]) if row else None
        if graph_generation != generation:
            raise GenerationError("graph generation 불일치")
    return {"generation_id": generation, "canonical_documents": len(canonical_ids),
            "graph_generation": graph_generation, "status": "ok"}
