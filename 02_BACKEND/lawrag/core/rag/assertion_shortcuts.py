"""검증된 Assertion 탐색 trace를 법률 부품→조문 shortcut으로 물질화한다.

질문 문자열이나 임베딩을 저장하지 않는다. 런타임의 결정론 Assertion matcher가 다시
찾은 assertion id만 키로 사용하며, 컴파일 때 선택된 조문과 source span 증명을 함께
보존한다. 이 모듈은 저장 정책을 정하지 않는 작은 읽기 전용 색인이다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path

from lawrag.core.domain_graph.model import stable_id
from lawrag.core.rag.index import store_path


Coordinate = tuple[str, object]


@dataclass(frozen=True)
class ShortcutProof:
    assertion_id: str
    coordinate: Coordinate
    slots: dict


@dataclass(frozen=True)
class ShortcutEntry:
    required_assertions: tuple[str, ...]
    targets: tuple[Coordinate, ...]
    proofs: tuple[ShortcutProof, ...]
    corpus_fingerprint: str
    query_assertions: tuple[str, ...] = ()
    source_trace: str = ""
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            object.__setattr__(self, "id", stable_id(
                "assertion-shortcut", self.required_assertions, self.targets,
                self.query_assertions, self.corpus_fingerprint))

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ShortcutHit:
    entry_id: str
    target: Coordinate
    matched_assertions: tuple[str, ...]
    source_trace: str


class ShortcutIndex:
    def __init__(self, entries: list[ShortcutEntry] | tuple[ShortcutEntry, ...]):
        self.entries = tuple(entries)
        self.by_id = {entry.id: entry for entry in self.entries}
        inverted: dict[str, set[str]] = {}
        for entry in self.entries:
            for assertion_id in entry.required_assertions:
                inverted.setdefault(assertion_id, set()).add(entry.id)
        self.inverted = {key: frozenset(value) for key, value in inverted.items()}

    def lookup(self, assertion_ids, *, cap: int = 8,
               exclude_traces: set[str] | None = None,
               require_unambiguous: bool = False,
               require_query_signature: bool = False) -> list[ShortcutHit]:
        """현재 질문에서 추출된 assertion id로 증명이 완성되는 경로만 연다."""
        ordered = tuple(dict.fromkeys(str(value) for value in assertion_ids if value))
        present = set(ordered)
        position = {value: pos for pos, value in enumerate(ordered)}
        candidates = set()
        for assertion_id in ordered:
            candidates.update(self.inverted.get(assertion_id, ()))
        excluded = exclude_traces or set()
        entries = [self.by_id[entry_id] for entry_id in candidates
                   if self.by_id[entry_id].source_trace not in excluded
                   and set(self.by_id[entry_id].required_assertions).issubset(present)]
        if require_query_signature:
            entries = [entry for entry in entries
                       if entry.query_assertions
                       and tuple(ordered[:len(entry.query_assertions)])
                       == entry.query_assertions]
        entries.sort(key=lambda entry: (
            min(position[value] for value in entry.required_assertions),
            -len(entry.required_assertions), entry.id))
        if require_unambiguous:
            routes = {entry.targets for entry in entries}
            # 같은 추출 부품이 서로 다른 조문 묶음을 열면 컴파일 경로가 아직
            # 식별되지 않은 것이다. cap으로 임의 절단하지 않고 깊은 탐색에 넘긴다.
            if len(routes) != 1:
                return []

        out: list[ShortcutHit] = []
        seen: set[Coordinate] = set()
        for entry in entries:
            for target in entry.targets:
                if target in seen:
                    continue
                seen.add(target)
                out.append(ShortcutHit(
                    entry.id, target, entry.required_assertions, entry.source_trace))
                if len(out) >= max(1, int(cap)):
                    return out
        return out


def runtime_store_path() -> Path:
    """사람이 승인한 proof shortcut 저장소. 평가 결과 경로를 기본값으로 쓰지 않는다."""
    return Path(os.environ.get(
        "RAG_ASSERTION_SHORTCUT_STORE",
        store_path().parent / "assertion_shortcuts.json"))


@dataclass(frozen=True)
class ShortcutLoadResult:
    """승인 저장소 로드 결과와 fallback 사유를 함께 보존한다."""

    index: ShortcutIndex
    status: str
    path: str
    accepted: int = 0
    rejected: int = 0
    reasons: tuple[str, ...] = ()
    schema_version: int | None = None
    approved_by: str = ""
    approved_at: str = ""

    @property
    def entries(self):
        return self.index.entries

    def lookup(self, *args, **kwargs):
        return self.index.lookup(*args, **kwargs)

    def as_dict(self) -> dict:
        return {
            "status": self.status, "path": self.path,
            "accepted": self.accepted, "rejected": self.rejected,
            "reasons": list(self.reasons), "schema_version": self.schema_version,
            "approved_by": self.approved_by, "approved_at": self.approved_at,
        }


_runtime_cache: dict[tuple[str, int, int, str], ShortcutLoadResult] = {}
_fingerprint_cache: dict[tuple[str, int, int], str] = {}


def canonical_fingerprint(path: Path) -> str:
    """86MB canonical을 요청마다 다시 해시하지 않고 파일 판본별로 한 번 계산한다."""
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _fingerprint_cache.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _fingerprint_cache.clear()
    _fingerprint_cache[key] = digest
    return digest


def _empty(path: Path, status: str, reason: str = "", **values) -> ShortcutLoadResult:
    return ShortcutLoadResult(
        ShortcutIndex([]), status, str(path),
        reasons=(reason,) if reason else (), **values)


def load_runtime(*, corpus_fingerprint: str,
                 path: Path | None = None) -> ShortcutLoadResult:
    """현재 canonical fingerprint와 일치하는 승인 경로만 읽는다.

    스키마·사람 승인·corpus 판본·proof 완결성 중 하나라도 맞지 않는 entry는
    발행하지 않는다. 어떤 실패도 예외 대신 빈 색인으로 내려가 B1 탐색을 실행한다.
    """
    path = path or runtime_store_path()
    try:
        stat = path.stat()
    except OSError:
        return _empty(path, "missing", "store_not_found")
    cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size,
                 corpus_fingerprint)
    cached = _runtime_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _empty(path, "corrupt", "invalid_json")
    if not isinstance(blob, dict):
        return _empty(path, "corrupt", "root_must_be_object")
    schema_version = blob.get("schema_version")
    approval = blob.get("approval") or {}
    if not isinstance(approval, dict):
        return _empty(path, "corrupt", "approval_must_be_object")
    approved_by = str(approval.get("approved_by") or "").strip()
    approved_at = str(approval.get("approved_at") or "").strip()
    common = {"schema_version": schema_version if isinstance(schema_version, int) else None,
              "approved_by": approved_by, "approved_at": approved_at}
    if schema_version != 1:
        return _empty(path, "rejected", "unsupported_schema_version", **common)
    if not approved_by or not approved_at:
        return _empty(path, "rejected", "human_approval_required", **common)
    rows = blob.get("entries", blob.get("shortcuts", []))
    if not isinstance(rows, list):
        return _empty(path, "corrupt", "entries_must_be_list", **common)
    if not rows:
        return _empty(path, "empty", "no_entries", **common)
    entries = []
    reasons = []
    stale = 0
    seen_ids: dict[str, ShortcutEntry] = {}
    for pos, row in enumerate(rows):
        if not isinstance(row, dict):
            reasons.append(f"entry_{pos}:not_object")
            continue
        if str(row.get("corpus_fingerprint") or "") != corpus_fingerprint:
            stale += 1
            continue
        raw_proofs = row.get("proofs") or []
        raw_targets = row.get("targets") or []
        if not isinstance(raw_proofs, list) or not isinstance(raw_targets, list):
            reasons.append(f"entry_{pos}:route_fields_must_be_lists")
            continue
        proofs = tuple(ShortcutProof(
            assertion_id=str(proof.get("assertion_id") or ""),
            coordinate=tuple(proof.get("coordinate") or ()),
            slots=dict(proof.get("slots") or {}),
        ) for proof in raw_proofs
            if isinstance(proof, dict)
            and isinstance(proof.get("coordinate"), (list, tuple))
            and len(proof["coordinate"]) == 2
            and isinstance(proof.get("slots") or {}, dict))
        targets = tuple(tuple(value) for value in raw_targets
                        if isinstance(value, (list, tuple)) and len(value) == 2)
        required = tuple(str(value) for value in row.get("required_assertions") or []
                         if value)
        signature = tuple(str(value) for value in row.get("query_assertions") or []
                          if value)
        if not targets or not required or not signature or not proofs:
            reasons.append(f"entry_{pos}:incomplete_route")
            continue
        if len(proofs) != len(raw_proofs) or len(targets) != len(raw_targets):
            reasons.append(f"entry_{pos}:malformed_proof_or_target")
            continue
        if any(not proof.assertion_id or not proof.slots for proof in proofs):
            reasons.append(f"entry_{pos}:incomplete_proof")
            continue
        grades = [str(value.get("grade") or "")
                  for proof in proofs for value in proof.slots.values()
                  if isinstance(value, dict)]
        if (sum(len(proof.slots) for proof in proofs) != len(grades)
                or any(grade not in {"G1", "G2", "G3"} for grade in grades)):
            reasons.append(f"entry_{pos}:invalid_grounding_grade")
            continue
        if not set(required).issubset({proof.assertion_id for proof in proofs}):
            reasons.append(f"entry_{pos}:required_assertion_unproved")
            continue
        if not set(targets).issubset({proof.coordinate for proof in proofs}):
            reasons.append(f"entry_{pos}:target_unproved")
            continue
        entry = ShortcutEntry(
            required_assertions=required, targets=targets, proofs=proofs,
            corpus_fingerprint=corpus_fingerprint,
            query_assertions=signature,
            source_trace=str(row.get("source_trace") or ""),
        )
        supplied_id = str(row.get("id") or "")
        if supplied_id and supplied_id != entry.id:
            reasons.append(f"entry_{pos}:id_mismatch")
            continue
        previous = seen_ids.get(entry.id)
        if previous is not None and previous != entry:
            reasons.append(f"entry_{pos}:conflicting_duplicate_id")
            continue
        if previous is None:
            seen_ids[entry.id] = entry
            entries.append(entry)
    index = ShortcutIndex(entries)
    rejected = len(rows) - stale - len(entries)
    status = "ready" if entries else ("stale" if stale == len(rows) else "rejected")
    result = ShortcutLoadResult(
        index, status, str(path), accepted=len(entries), rejected=rejected,
        reasons=tuple(dict.fromkeys(reasons or (
            ("corpus_fingerprint_mismatch",) if status == "stale" else ()))),
        **common)
    _runtime_cache.clear()
    _runtime_cache[cache_key] = result
    return result
