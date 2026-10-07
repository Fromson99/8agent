"""진단 튜플 — 질의마다 남기는 관측 기록 (ontology_kg §5.2 의 최소 구현).

지금까지 /ask 는 사다리·탐험 경로·필터 결과를 응답 JSON 에 실어 보내고
**버렸다.** 루프 2(질의 구동 진화)는 그 기록이 연료다 — 루프는 나중에
만들어도 데이터는 첫날부터 쌓여야 한다.

## 왜 append-only jsonl 인가

튜플은 관측이다. 관측을 고쳐 쓰기 시작하면 "그때 시스템이 뭘 봤나"가
사라진다. 질의 기록과 피드백 기록을 **따로 append** 하고, 읽을 때 qid 로
합친다 — links.json 처럼 파일이 정본이고 DB 는 없다.

## 승격 후보는 세는 장부다

탐험이 성공하면 (질의 정규형 → 착지 좌표) 쌍을 적재만 한다. 승격은
동형 착지가 쌓인 뒤 게이트(Phase 3)가 한다 — 표본 1 즉시 승격은
과잉일반화다(§5.5). 같은 쌍이 다시 오면 개수를 올려야 하므로 이 파일만은
읽고-고쳐-쓴다(candidates.json).
"""

from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import json
import hashlib
import os
import re
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.runtime.content_snapshot import (
    ContentSnapshotError,
    artifact_provenance_receipt,
    current_content_snapshot,
    current_retrieval_runtime_receipt,
)
from lawrag.platform.paths import data_path
from lawrag.core.rag.index import norm, store_path


def rag_dir() -> Path:
    """진단 기록의 자리 — glossary.json·links.json 과 같은 규약(스토어 옆)."""
    return Path(os.environ.get("RAG_LOG_DIR", data_path("FEEDBACK", "RUNTIME")))


def _feedback_disabled() -> bool:
    return os.environ.get("LAWRAG_FEEDBACK_DISABLED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _sealed_feedback_mode() -> bool:
    return (
        not _feedback_disabled()
        and os.environ.get("LAWRAG_SERVING_SEALED", "").strip().casefold()
        in {"1", "true", "yes", "on"}
    )


def _feedback_root_fd() -> int:
    """Open the admitted feedback root without following path aliases."""

    root = Path(os.environ.get("LAWRAG_FEEDBACK_ROOT", ""))
    if not root.is_absolute():
        raise ContentSnapshotError("sealed feedback root is not absolute")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory is None:
        raise ContentSnapshotError("sealed feedback requires no-follow directory opens")
    try:
        descriptor = os.open(
            root,
            os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ContentSnapshotError("cannot open admitted feedback root") from exc
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise ContentSnapshotError("admitted feedback root ownership/mode changed")
    return descriptor


def _child_dir_fd(parent: int, name: str, *, create: bool) -> int:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in {".", ".."}:
        raise ContentSnapshotError("invalid feedback child directory")
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
    except OSError as exc:
        raise ContentSnapshotError("cannot open feedback child directory") from exc
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise ContentSnapshotError("feedback child ownership/mode is unsafe")
    return descriptor


def _read_regular_at(parent: int, name: str) -> bytes | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise ContentSnapshotError("cannot safely read feedback file") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o077
        ):
            raise ContentSnapshotError("feedback file ownership/mode is unsafe")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise ContentSnapshotError("feedback file changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _atomic_write_root(name: str, data: bytes) -> None:
    root_fd = _feedback_root_fd()
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=root_fd,
        )
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        os.fsync(root_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=root_fd)
        except FileNotFoundError:
            pass
        os.close(root_fd)


def append_feedback_jsonl(name: str, record: dict) -> None:
    """Append one JSON record to a fixed root-level feedback ledger."""

    if re.fullmatch(r"[A-Za-z0-9._-]+\.jsonl", name) is None:
        raise ContentSnapshotError("invalid feedback ledger name")
    root_fd = _feedback_root_fd()
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=root_fd,
        )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ContentSnapshotError("feedback ledger ownership/mode is unsafe")
        payload = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if descriptor >= 0:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        os.close(root_fd)


def feedback_file_bytes(name: str) -> bytes | None:
    """Read one fixed root-level feedback ledger without following aliases."""

    if re.fullmatch(r"[A-Za-z0-9._-]+(?:\.jsonl|\.json)", name) is None:
        raise ContentSnapshotError("invalid feedback file name")
    root_fd = _feedback_root_fd()
    try:
        return _read_regular_at(root_fd, name)
    finally:
        os.close(root_fd)


@contextmanager
def _candidate_update_lock():
    if not _sealed_feedback_mode():
        yield
        return
    root_fd = _feedback_root_fd()
    descriptor = -1
    try:
        descriptor = os.open(
            ".candidates.lock",
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=root_fd,
        )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ContentSnapshotError("candidate lock ownership/mode is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if descriptor >= 0:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        os.close(root_fd)


def _candidate_bytes() -> bytes | None:
    if not _sealed_feedback_mode():
        path = candidate_observations_path()
        return path.read_bytes() if path.is_file() else None
    root_fd = _feedback_root_fd()
    try:
        return _read_regular_at(root_fd, "candidates.json")
    finally:
        os.close(root_fd)


def _write_candidate_rows(rows: list[dict]) -> None:
    data = json.dumps(
        {"candidates": rows}, ensure_ascii=False, indent=2
    ).encode("utf-8")
    if _sealed_feedback_mode():
        _atomic_write_root("candidates.json", data)
        return
    path = candidate_observations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def tuples_dir() -> Path:
    return rag_dir() / "tuples"


def candidates_path() -> Path:
    """Reviewed, serving-visible question-memory store.

    In legacy mode this deliberately remains the historical candidates file.
    A sealed SourceSet may point at a separately reviewed, deployment-pinned
    copy; query-time observations never write this path.
    """

    configured = os.environ.get("RAG_QUERY_SHORTCUT_STORE", "").strip()
    return Path(configured) if configured else rag_dir() / "candidates.json"


def candidate_observations_path() -> Path:
    """Writable proposal ledger, never a serving authority in SourceSet mode."""

    return rag_dir() / "candidates.json"


def reviewed_candidates() -> list[dict]:
    """Read the deployment-pinned question memory without a TOCTOU fallback."""

    path = candidates_path()
    snapshot_bound = _snapshot_adapter_enabled()
    if not path.exists():
        if snapshot_bound:
            raise ContentSnapshotError("reviewed shortcut store disappeared")
        return []
    if not snapshot_bound:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            rows = value.get("candidates", []) if isinstance(value, dict) else []
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    expected = os.environ.get("LAWRAG_QUERY_SHORTCUT_STORE_SHA256", "").strip()
    if len(expected) != 64:
        raise ContentSnapshotError("reviewed shortcut store has no pinned SHA-256")
    runtime_receipt = current_retrieval_runtime_receipt(required=True)
    shortcut_binding = (
        runtime_receipt.get("query_shortcuts")
        if isinstance(runtime_receipt, dict) else None
    )
    if (
        not isinstance(shortcut_binding, dict)
        or shortcut_binding.get("enabled") is not True
        or shortcut_binding.get("store_sha256") != expected
    ):
        raise ContentSnapshotError(
            "reviewed shortcut store differs from the process runtime receipt"
        )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ContentSnapshotError("reviewed shortcut reads require no-follow opens")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow,
        )
    except OSError as exc:
        raise ContentSnapshotError("cannot safely open reviewed shortcut store") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ContentSnapshotError("reviewed shortcut store is not an admitted file")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise ContentSnapshotError("reviewed shortcut store changed during read")
    finally:
        os.close(descriptor)
    if digest.hexdigest() != expected:
        raise ContentSnapshotError("reviewed shortcut store SHA-256 mismatch")
    try:
        value = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentSnapshotError("reviewed shortcut store is not valid JSON") from exc
    rows = value.get("candidates") if isinstance(value, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ContentSnapshotError("reviewed shortcut store has an invalid contract")
    return rows


def _snapshot_adapter_enabled() -> bool:
    """Read the rollback switch lazily to avoid the index/switch import cycle."""

    from lawrag.core.rag import switches as switches_mod

    return switches_mod.is_on("sourceset_content_snapshot")


def _active_snapshot_context():
    """Return the mandatory process snapshot and receipt only in the ON path."""

    if not _snapshot_adapter_enabled():
        return None
    snapshot = current_content_snapshot(required=True)
    assert snapshot is not None  # narrowed by required=True
    return snapshot, snapshot.compact_receipt()


def _document_provenance(snapshot, doc_id) -> dict | None:
    """Return the current structure-artifact receipt for an exact document ID."""

    if not isinstance(doc_id, str) or not doc_id:
        return None
    try:
        return artifact_provenance_receipt(
            snapshot.provenance_for_document(doc_id)
        )
    except ContentSnapshotError:
        return None


def _artifact_matches_snapshot(value, snapshot) -> bool:
    if not isinstance(value, dict):
        return False
    expected = _document_provenance(snapshot, value.get("doc_id"))
    return expected is not None and value.get("content_provenance") == expected


def _coordinate_matches_snapshot(value, snapshot, receipt: dict) -> bool:
    """Accept only a coordinate carrying both current global and artifact proof."""

    return (
        isinstance(value, dict)
        and value.get("content_snapshot") == receipt
        and _artifact_matches_snapshot(value, snapshot)
    )


def _candidate_matches_snapshot(value, snapshot, receipt: dict) -> bool:
    return _coordinate_matches_snapshot(value, snapshot, receipt)


def _ask_matches_snapshot(value, snapshot, receipt: dict) -> bool:
    runtime_receipt = current_retrieval_runtime_receipt(required=True)
    if (
        not isinstance(value, dict)
        or value.get("content_snapshot") != receipt
        or value.get("retrieval_runtime") != runtime_receipt
    ):
        return False
    refs = value.get("refs")
    context = value.get("context")
    if not isinstance(refs, list) or not isinstance(context, list):
        return False
    return all(
        _artifact_matches_snapshot(row, snapshot)
        for row in [*refs, *context]
    )


def _feedback_matches_snapshot(value, snapshot, receipt: dict) -> bool:
    runtime_receipt = current_retrieval_runtime_receipt(required=True)
    if (
        not isinstance(value, dict)
        or value.get("content_snapshot") != receipt
        or value.get("retrieval_runtime") != runtime_receipt
    ):
        return False
    expected = value.get("기대")
    return expected is None or _artifact_matches_snapshot(expected, snapshot)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _month_file(ts: Optional[str] = None) -> Path:
    ym = (ts or _now())[:7].replace("-", "")
    return tuples_dir() / f"{ym}.jsonl"


def _append(rec: dict) -> None:
    if _feedback_disabled():
        return
    payload = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    if _sealed_feedback_mode():
        root_fd = _feedback_root_fd()
        tuples_fd = -1
        descriptor = -1
        try:
            tuples_fd = _child_dir_fd(root_fd, "tuples", create=True)
            name = f"{str(rec.get('ts') or _now())[:7].replace('-', '')}.jsonl"
            if re.fullmatch(r"[0-9]{6}\.jsonl", name) is None:
                raise ContentSnapshotError("feedback timestamp produced an invalid file")
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_APPEND | os.O_CREAT
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=tuples_fd,
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
            ):
                raise ContentSnapshotError("feedback ledger ownership/mode is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            if descriptor >= 0:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
            if tuples_fd >= 0:
                os.close(tuples_fd)
            os.close(root_fd)
        return
    p = _month_file(rec.get("ts"))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(payload.decode("utf-8"))


def _sealed_tuple_rows() -> list[dict]:
    root_fd = _feedback_root_fd()
    tuples_fd = -1
    try:
        try:
            tuples_fd = _child_dir_fd(root_fd, "tuples", create=False)
        except ContentSnapshotError:
            return []
        rows: list[dict] = []
        for name in sorted(os.listdir(tuples_fd)):
            if re.fullmatch(r"[0-9]{6}\.jsonl", name) is None:
                continue
            raw = _read_regular_at(tuples_fd, name)
            if raw is None:
                continue
            for line in raw.decode("utf-8").splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
        return rows
    finally:
        if tuples_fd >= 0:
            os.close(tuples_fd)
        os.close(root_fd)


def _snapshot_receipt(value=None) -> dict | None:
    process_snapshot = current_content_snapshot(
        required=_snapshot_adapter_enabled()
    )
    snapshot = value if value is not None else process_snapshot
    if snapshot is None:
        return None
    if hasattr(snapshot, "compact_receipt"):
        receipt = snapshot.compact_receipt()
    elif isinstance(snapshot, dict):
        receipt = dict(snapshot)
    else:
        raise TypeError("content_snapshot must be a mapping or ContentSnapshot")
    if (process_snapshot is not None
            and receipt != process_snapshot.compact_receipt()):
        raise ValueError("tuple content snapshot disagrees with process snapshot")
    return receipt


# ---------------------------------------------------------------- 질의 기록
def log_ask(out: dict, prompt: Optional[dict] = None,
            calls: Optional[list] = None) -> str:
    """/ask 응답에서 진단 튜플을 뽑아 적재한다. 응답에 실을 qid 를 돌려준다.

    "어떻게 찾았는가"(사다리·탐험 경로·좌표)에 더해 **무엇이 나갔는가**(답
    전문·회수 구역 목록)도 남긴다 — 최근 질의를 눌러 그때의 전모(질문·답·
    회수 경위)를 다시 보는 것이 검수의 입구다(2026-08-11 사용자 결정.
    LLM 답은 재실행해도 같은 문장이 아니라서 "재현 가능"이 성립하지 않았다).

    prompt 는 답 합성 호출에 실제로 들어간 {"system","user"} — 지식이 어떻게
    주입됐는지를 그대로 남긴다(재구성은 문서가 다시 서면 어긋난다). 컨텍스트
    상한(12구역×6k자) 덕에 커야 수십 KB 다.
    """
    qid = uuid.uuid4().hex[:12]
    rec = {
        "kind": "질의", "qid": qid, "ts": _now(),
        "질의": out.get("question", ""),
        "mode": out.get("mode"),
        "ladder": out.get("ladder"),
        "filter": out.get("filter"),
        "answerable": out.get("answerable"),
        "답": out.get("answer") or "",
        # 회수 구역 — 어느 단(벡터·용어·참조·탐색)이 무엇을 데려왔는지 그대로.
        "context": out.get("context") or [],
        # 모델이 실제 인용한 컨텍스트 번호(벡터 모드) — 회수≠인용을 가른다.
        "cited": out.get("cited") or [],
        "refs": [{k: r.get(k) for k in
                  ("n", "doc_id", "doc", "node", "block", "page", "path",
                   "kind", "matched", "content_provenance") if k in r}
                 for r in out.get("refs", [])],
    }
    snapshot = _snapshot_receipt(out.get("content_snapshot"))
    if snapshot is not None:
        rec["content_snapshot"] = snapshot
    if out.get("retrieval_runtime") is not None:
        rec["retrieval_runtime"] = dict(out["retrieval_runtime"])
    if prompt:
        rec["프롬프트"] = {"system": prompt.get("system", ""),
                           "user": prompt.get("user", "")}
    # 쟁점기의 전모(트리거 적중·판정·질의 확장)와 **모든 LLM 콜의 원문**.
    # 답 합성 프롬프트만으로는 "판정이 무엇을 보고 섰나"가 안 보인다 —
    # 검수는 결론이 아니라 그 앞의 입력을 봐야 성립한다.
    if out.get("쟁점"):
        rec["쟁점"] = out["쟁점"]
    if out.get("scope"):
        # 질의 스코프 — 어느 문서 묶음만 봤나. 피드백·벤치가 스코프별로 갈린다.
        rec["scope"] = {k: out["scope"].get(k) for k in ("name", "count", "out_of_scope")}
    if calls:
        rec["콜"] = calls
    if out.get("timing") is not None:
        rec["timing"] = out["timing"]
    if out.get("recovery") is not None:
        rec["recovery"] = out["recovery"]
    if out.get("ask_user"):
        rec["ask_user"] = out["ask_user"]
    if out.get("usage"):
        rec["usage"] = out["usage"]
    snapshot_context = _active_snapshot_context()
    if snapshot_context is not None and not _ask_matches_snapshot(
        rec, *snapshot_context
    ):
        raise ValueError(
            "question record is not bound to the current content snapshot"
        )
    legal_graph = (out.get("legalclosure") or {}).get("legal_graph") or {}
    if legal_graph:
        # The adapter bounds decisions before they reach this durable record.
        rec["legal_graph"] = {
            key: legal_graph.get(key) for key in (
                "enabled", "status", "fallback", "reasons", "generation_id",
                "content_sha256", "authority_generation", "query_frame",
                "hypotheses", "active_family_ids", "allowed_predicates", "policy",
                "trace_id", "before_count", "residual_slots", "considered_count",
                "eligible_target_count", "added_count", "after_count",
                "reason_counts", "decisions", "decisions_truncated", "selected",
                "load", "elapsed_ms",
            ) if key in legal_graph
        }
    ontology_rag = (out.get("legalclosure") or {}).get("ontology_rag") or {}
    if ontology_rag:
        rec["ontology_rag"] = {
            key: ontology_rag.get(key) for key in (
                "schema_version", "profile_id", "status", "reason", "detail",
                "fallback", "projection_id", "matched_surface", "clause_span_ids",
                "canonical_evidence_ids", "rule_ids", "baseline_count",
                "final_count", "added_count", "added_coordinates",
                "baseline_floor_preserved", "direct_conclusion_allowed",
                "quality_status", "definition_generation",
                "definition_content_sha256", "graph_generation",
                "graph_content_sha256", "store_binding", "knowledge_cache",
                "knowledge_cache_key_sha256",
            ) if key in ontology_rag
        }
    runtime = (out.get("legalclosure") or {}).get("runtime") or {}
    if runtime:
        rec["runtime"] = dict(runtime)
    _append(rec)
    return qid


def log_feedback(qid: str, verdict: str, expected: Optional[dict] = None,
                 note: str = "", *, ontology_feedback: Optional[dict] = None) -> dict:
    """사용자 신호 — "A 를 물었는데 B 가 나왔다. A 가 나와야 한다."

    실패_원인(a~d)은 여기서 판정하지 않는다(§5.1 책임 귀속은 Phase 2).
    미판정으로 남겨야 나중에 귀속기가 "아직 안 본 것"을 찾을 수 있다.
    """
    snapshot_context = _active_snapshot_context()
    original = find(qid)
    if snapshot_context is not None and original is None:
        raise ValueError(
            "feedback question is not in the current content snapshot"
        )
    rec = {"kind": "피드백", "qid": qid, "ts": _now(), "판정": verdict,
           "기대": expected, "메모": note, "실패_원인": None}
    if ontology_feedback is not None:
        from lawrag.feedback.lifecycle import validate_feedback_event

        validate_feedback_event(ontology_feedback)
        rec["ontology_feedback"] = dict(ontology_feedback)
    if snapshot_context is not None:
        rec["content_snapshot"] = dict(snapshot_context[1])
        rec["retrieval_runtime"] = current_retrieval_runtime_receipt(required=True)
        if not _feedback_matches_snapshot(rec, *snapshot_context):
            raise ValueError(
                "feedback coordinate is not bound to the current content snapshot"
            )
    elif original and original.get("content_snapshot") is not None:
        rec["content_snapshot"] = dict(original["content_snapshot"])
        if original.get("retrieval_runtime") is not None:
            rec["retrieval_runtime"] = dict(original["retrieval_runtime"])
    _append(rec)
    from lawrag.core.rag import approvals
    correct = verdict == "정답"
    source = {"ledger": "tuples"}
    if snapshot_context is not None:
        source.update({
            "content_snapshot": rec["content_snapshot"],
            **(
                {"content_provenance": expected["content_provenance"]}
                if expected is not None else {}
            ),
        })
    approvals.safe_record(
        kind="answer_feedback", decision=verdict,
        effect="confirmed" if correct else "answer_overturn",
        failure="" if correct else "답변_오류",
        subject={"qid": qid},
        before={"verdict": None}, after={"verdict": verdict, "expected": expected},
        note=note, actor="human", qids=[qid], source=source)
    return rec


def read(limit: int = 200) -> list[dict]:
    """질의 기록에 피드백을 합쳐 최신순으로. 화면(튜플 브라우저)용.

    피드백이 여럿이면 마지막 것이 남는다 — 사람이 판단을 고친 것이다.
    """
    if _feedback_disabled():
        return []
    d = tuples_dir()
    if not d.exists():
        return []
    snapshot_context = _active_snapshot_context()
    asks: dict[str, dict] = {}
    order: list[str] = []
    if _sealed_feedback_mode():
        records = _sealed_tuple_rows()
    else:
        records = []
        for p in sorted(d.glob("*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    records.append(rec)
    for rec in records:
        if snapshot_context is not None:
            kind = rec.get("kind")
            if kind == "질의" and not _ask_matches_snapshot(
                rec, *snapshot_context
            ):
                continue
            if kind == "피드백" and not _feedback_matches_snapshot(
                rec, *snapshot_context
            ):
                continue
        qid = rec.get("qid")
        if rec.get("kind") == "질의":
            asks[qid] = rec
            order.append(qid)
        elif rec.get("kind") == "피드백" and qid in asks:
            asks[qid]["피드백"] = {k: rec.get(k)
                                   for k in (
                                       "판정", "기대", "메모", "실패_원인", "ts",
                                       "ontology_feedback",
                                   ) if k in rec}
    rows = [asks[q] for q in reversed(order) if q in asks]
    return rows[:limit]


def find(qid: str) -> Optional[dict]:
    for rec in read(limit=10_000):
        if rec.get("qid") == qid:
            return rec
    return None


# ---------------------------------------------------------------- 승격 후보
def _record_candidates_locked(query: str, coords: list[dict], cap: int = 3) -> int:
    """탐험 성공을 승격 후보로 적재 — (질의 정규형, 착지 좌표)별로 센다.

    상위 cap 개 좌표만 적는다. 탐험이 넓게 긁어 온 꼬리까지 다 적으면
    장부가 노이즈로 비대해진다 — 첫 몇 좌표가 실제로 답변에 실린 것들이다.
    """
    if _feedback_disabled():
        return 0
    qkey = norm(query)
    if not qkey or not coords:
        return 0
    rows: list[dict] = []
    raw_candidates = _candidate_bytes()
    if raw_candidates is not None:
        try:
            rows = json.loads(raw_candidates.decode("utf-8")).get("candidates", [])
        except Exception:
            rows = []
    snapshot_context = _active_snapshot_context()
    snapshot = (
        snapshot_context[0]
        if snapshot_context is not None
        else current_content_snapshot()
    )
    snapshot_receipt = _snapshot_receipt(snapshot)
    snapshot_sha256 = str(
        (snapshot_receipt or {}).get("content_snapshot_sha256") or "")

    def candidate_key(row: dict) -> tuple:
        row_snapshot = row.get("content_snapshot") or {}
        return (row.get("qkey"), row.get("doc_id"), row.get("node"),
                str(row_snapshot.get("content_snapshot_sha256") or ""))

    eligible_rows = rows
    if snapshot_context is not None:
        eligible_rows = [
            row for row in rows
            if _candidate_matches_snapshot(row, *snapshot_context)
        ]
    by_key = {candidate_key(r): r for r in eligible_rows}
    now = _now()
    fresh = 0
    for c in coords[:cap]:
        if snapshot_context is not None and not _coordinate_matches_snapshot(
            c, *snapshot_context
        ):
            continue
        doc_id, node = c.get("doc_id"), c.get("node")
        if not doc_id or node is None:
            continue
        k = (qkey, doc_id, node, snapshot_sha256)
        row = by_key.get(k)
        current_provenance = (artifact_provenance_receipt(
            snapshot.provenance_for_document(str(doc_id)))
            if snapshot is not None else None)
        if row is not None and snapshot_receipt is not None:
            if row.get("content_snapshot") != snapshot_receipt:
                raise ValueError("candidate content snapshot receipt mismatch")
            if row.get("content_provenance") != current_provenance:
                raise ValueError("candidate artifact provenance receipt mismatch")
        if row is None:
            # status: 잠정(자동 적재) → 활성(사람 승인) | tombstone(기각).
            # 착지 한 번으로 굳히지 않는다 — 오답 착지도 착지다(18-0124 에서
            # 벡터가 찾은 제81조의13 도 착지였다). 활성만 다음 회수의 직행
            # 좌표·별칭·카드 연결이 된다 (용어 사전과 같은 승인형 규율).
            row = {"qkey": qkey, "surfaces": [query], "doc_id": doc_id,
                   "node": node, "via": c.get("via", ""),
                   "count": 0, "first": now, "last": now, "status": "잠정",
                   "cards": [], "issues": []}
            if snapshot_receipt is not None:
                row["content_snapshot"] = snapshot_receipt
                row["content_provenance"] = current_provenance
                row["observed_retrieval_runtime"] = (
                    current_retrieval_runtime_receipt(required=True)
                )
            by_key[k] = row
            rows.append(row)
            fresh += 1
        if query not in row["surfaces"]:
            row["surfaces"].append(query)
        row["count"] += 1
        row["last"] = now
        row["via"] = c.get("via", row.get("via", ""))
        # 착지 때의 쟁점 카드·쟁점 문장 — 카드↔조문 승인 연결의 재료
        for key, val in (("cards", c.get("card")), ("issues", c.get("issue"))):
            if val:
                row.setdefault(key, [])
                if val not in row[key]:
                    row[key].append(val)
    _write_candidate_rows(rows)
    return fresh


def record_candidates(query: str, coords: list[dict], cap: int = 3) -> int:
    """Serialize candidate RMW and publish it with an atomic replacement."""

    with _candidate_update_lock():
        return _record_candidates_locked(query, coords, cap)


def candidates() -> list[dict]:
    if _feedback_disabled():
        return []
    raw = _candidate_bytes()
    if raw is None:
        return []
    try:
        rows = json.loads(raw.decode("utf-8")).get("candidates", [])
    except Exception:
        return []
    snapshot_context = _active_snapshot_context()
    if snapshot_context is None:
        return rows
    return [
        row for row in rows
        if _candidate_matches_snapshot(row, *snapshot_context)
    ]
