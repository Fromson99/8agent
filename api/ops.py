"""망분리 운반 — 스냅샷 · 아웃박스 · 재생.

폐쇄망(GenOS 류)에 올라간 이 앱은 브라우저가 닿지 않는다 — 내부 back 단
curl 만 된다. 화면은 로컬에서 띄우고, 상태와 조작을 파일로 나른다:

    그쪽:  curl -o snap.tar.gz  http://…/v1/ops/snapshot
    이쪽:  OPS_RECORD=1 scripts/serve.sh
           curl -F file=@snap.tar.gz "localhost:5566/v1/ops/restore"
           → 브라우저로 평소처럼 작업 (쓰기 조작이 아웃박스에 쌓인다)
           curl -o outbox.tar.gz  localhost:5566/v1/ops/outbox/export
    그쪽:  curl -F file=@outbox.tar.gz http://…/v1/ops/apply -o report.json

원칙 세 가지:
  멱등 — 조작마다 id 가 있고, 적용한 id 는 다시 적용하지 않는다. 같은 파일을
         두 번 돌려도 안전하다.
  기준 — 아웃박스는 "어느 스냅샷을 보고 내린 결정"인지(rev)를 들고 간다.
         그 사이 서버 상태가 움직였으면 409 — force=1 로만 덮는다.
  정직 — LLM 이 개입하는 조작(규칙 시험, 참조 정리, 표제 수집)은 재생 때
         **그쪽에서 다시 실행**된다. 로컬에서 본 결과와 다를 수 있고, 건별
         리포트가 그걸 그대로 보여 준다. 여기서 결과를 위조해 맞추지 않는다.

기록 대상은 화면 여섯이 쓰는 라우터의 쓰기 메서드뿐이다. /v1/rag/ask 와
/feedback 은 기록은 하되(그쪽 진단 튜플로 남는 게 맞다) rev 는 올리지
않는다 — 조회·라벨은 큐레이션 충돌의 근거가 아니다.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
import tarfile
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

# 저장 경로는 라우터가 이미 env 에서 굳혀 둔 값을 그대로 빌린다 — env 해석을
# 여기서 한 번 더 하면 두 해석이 어긋나는 날이 온다.
from api.routers.structure import STORE

log = logging.getLogger("api.ops")

OPS_DIR = Path(os.environ.get("OPS_DIR", str(STORE.parent / "ops")))
RECORD = os.environ.get("OPS_RECORD", "").strip().lower() in ("1", "true", "yes", "on")
ALLOW_RESTORE = os.environ.get("OPS_ALLOW_RESTORE", "").strip().lower() in (
    "1", "true", "yes", "on")
INBOX_DIR = os.environ.get("OPS_INBOX_DIR") or None

_OUTBOX = OPS_DIR / "outbox"
_BODIES = _OUTBOX / "bodies"
_OPS_FILE = _OUTBOX / "ops.jsonl"
_APPLIED = OPS_DIR / "applied.jsonl"
_REV_FILE = OPS_DIR / "rev.json"
_BASE_FILE = OPS_DIR / "base.json"
_LOCK = threading.Lock()

_INLINE_BODY_MAX = 256 * 1024          # 이보다 크면 bodies/{id}.bin 으로 뺀다
_RESP_HEAD_MAX = 2000                  # 기록해 두는 로컬 응답 머리 — 디버깅용

# 기록·rev 의 범위 — 화면 여섯이 쓰는 라우터. parser/agent/jobs/chat 은
# 인메모리·스크래치라 나를 것이 없다.
_JOURNAL_PREFIXES = ("/v1/structure", "/v1/formats", "/v1/glossary",
                     "/v1/rag", "/v1/agent6")
_REV_EXEMPT = ("/v1/rag/ask", "/v1/rag/feedback")
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

_SNAPSHOT_FORMAT = "8agent-snapshot/1"
_OUTBOX_FORMAT = "8agent-ops/1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rev() -> int:
    try:
        return int(json.loads(_REV_FILE.read_text(encoding="utf-8"))["rev"])
    except Exception:
        return 0


def _set_rev(n: int) -> None:
    _REV_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _REV_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"rev": n}), encoding="utf-8")
    os.replace(tmp, _REV_FILE)


def _bump_rev() -> None:
    with _LOCK:
        _set_rev(_rev() + 1)


def _base() -> dict | None:
    try:
        return json.loads(_BASE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------- 상태 목록
def _state_targets() -> dict[str, Path]:
    """스냅샷이 나르는 것 전부. 경로의 정본은 각 소유 모듈이다 — 여기서는
    빌려 읽기만 한다. 선택 의존(agent6·rag·glossary)이 빠진 배포에서는 그
    키가 조용히 빠진다."""
    t: dict[str, Path] = {"structure": STORE}
    try:
        from api.routers.glossary import TERMS_FILE
        t["glossary"] = Path(TERMS_FILE)
    except Exception:
        pass
    try:
        from api.routers.formats import BINDINGS_FILE, CANVAS_FILE, FORMATS_DIR
        t["bindings"] = Path(BINDINGS_FILE)
        t["canvas"] = Path(CANVAS_FILE)
        t["formats"] = Path(FORMATS_DIR)
    except Exception:
        pass
    try:
        from api.routers.structure import _ledger_path
        t["ledger"] = _ledger_path()
    except Exception:
        pass
    try:
        from core.structure_fixes import fixes_path
        t["fixes"] = fixes_path()
    except Exception:
        pass
    try:
        from core.structure.proposers import custom
        t["custom"] = Path(custom.DEFAULT_DIR)
    except Exception:
        pass
    try:
        from core import router as core_router
        t["registry"] = Path(core_router.DEFAULT_REGISTRY)
    except Exception:
        pass
    try:
        from core.rag.index import links_path
        t["links"] = links_path()
    except Exception:
        pass
    try:
        from core.rag.tuples import rag_dir
        t["rag"] = rag_dir()
    except Exception:
        pass
    try:
        from core.rag.verdicts import rules_path
        t["rules"] = rules_path().parent
    except Exception:
        pass
    try:
        from core.rag.vector import sections_dir
        t["embeddings"] = sections_dir()
    except Exception:
        pass
    try:
        from api.routers.agent6 import ITEMS_DIR
        t["agent6_items"] = Path(ITEMS_DIR)
    except Exception:
        pass
    return t


def _drop_caches() -> None:
    """복원 뒤 프로세스 안 캐시를 턴다. rag 색인은 mtime 서명이라 스스로
    갈리지만, 형식 레지스트리는 lru_cache 라 손으로 털어야 한다."""
    try:
        from core import router as core_router
        core_router.load.cache_clear()
    except Exception:
        pass


# ------------------------------------------------------------------- 기록
def _journal(method: str, path: str, query: str, content_type: str,
             body: bytes, status: int, resp_head: str) -> str:
    op_id = f"{int(time.time() * 1000):x}-{uuid.uuid4().hex[:8]}"
    entry: dict = {"id": op_id, "ts": _now(), "method": method, "path": path,
                   "query": query, "content_type": content_type,
                   "status": status, "resp_head": resp_head[:_RESP_HEAD_MAX]}
    _BODIES.mkdir(parents=True, exist_ok=True)
    if len(body) <= _INLINE_BODY_MAX:
        entry["body_b64"] = base64.b64encode(body).decode()
    else:                                  # 업로드 원본 등 — 줄이 MB 가 되면 안 된다
        (_BODIES / f"{op_id}.bin").write_bytes(body)
        entry["body_file"] = f"bodies/{op_id}.bin"
    with _LOCK:
        with _OPS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return op_id


def _read_ops(ops_file: Path) -> list[dict]:
    if not ops_file.exists():
        return []
    out = []
    for line in ops_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _op_body(op: dict, root: Path) -> bytes:
    if op.get("body_file"):
        return (root / op["body_file"]).read_bytes()
    return base64.b64decode(op.get("body_b64") or "")


def _applied_ids() -> set[str]:
    if not _APPLIED.exists():
        return set()
    ids = set()
    for line in _APPLIED.read_text(encoding="utf-8").splitlines():
        try:
            ids.add(json.loads(line)["id"])
        except Exception:
            pass
    return ids


def _mark_applied(op_id: str, status: int) -> None:
    _APPLIED.parent.mkdir(parents=True, exist_ok=True)
    with _APPLIED.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": op_id, "ts": _now(), "status": status}) + "\n")


def _archive_outbox(reason: str) -> int:
    """아웃박스를 history/ 로 치운다 — 지우지 않는다. 복원(새 기준) 직후나
    반출 완료 뒤에 부른다."""
    ops = _read_ops(_OPS_FILE)
    if not ops:
        return 0
    dst = OPS_DIR / "history" / f"outbox-{time.strftime('%Y%m%d-%H%M%S')}-{reason}"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.move(str(_OPS_FILE), str(dst / "ops.jsonl"))
    if _BODIES.is_dir() and any(_BODIES.iterdir()):
        shutil.move(str(_BODIES), str(dst / "bodies"))
    return len(ops)


# ------------------------------------------------------------- 미들웨어
class OpsMiddleware:
    """쓰기 조작을 지나가는 자리에서 붙잡는다 — 라우터 수십 개를 고치지 않는
    이유다. 몸통은 기록 모드에서만 복사한다(평상시엔 40MB 업로드를 한 번 더
    들고 있을 이유가 없다)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope["method"]
        path = scope["path"]
        if method not in _MUTATING or not path.startswith(_JOURNAL_PREFIXES):
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        replay = headers.get("x-ops-replay") == "1"
        capture = RECORD and not replay
        chunks: list[bytes] = []
        resp: dict = {"status": None, "head": b""}

        async def tee_receive():
            msg = await receive()
            if capture and msg["type"] == "http.request":
                chunks.append(msg.get("body", b""))
            return msg

        async def tee_send(msg):
            if msg["type"] == "http.response.start":
                resp["status"] = msg["status"]
            elif capture and msg["type"] == "http.response.body":
                if len(resp["head"]) < _RESP_HEAD_MAX:
                    resp["head"] += msg.get("body", b"")[:_RESP_HEAD_MAX]
            await send(msg)

        await self.app(scope, tee_receive, tee_send)

        status = resp["status"] or 500
        if status < 400 and path not in _REV_EXEMPT:
            _bump_rev()                     # 재생도 상태를 바꾸므로 rev 는 올린다
        # 4xx 는 기록하지 않는다 — 그쪽에서도 똑같이 거절당할 요청이다.
        # 5xx 는 기록한다 — "로컬에 LLM 키가 없어 실패, 그쪽에서 실행" 이 이 길이다.
        if capture and (status < 400 or status >= 500):
            query = scope.get("query_string", b"").decode("latin-1")
            op_id = _journal(method, path, query,
                             headers.get("content-type", ""),
                             b"".join(chunks), status,
                             resp["head"].decode("utf-8", "replace"))
            log.info("기록 %s — %s %s → %d", op_id, method, path, status)


# --------------------------------------------------------------- 자기 호출
async def _call_self(app, method: str, path: str, query: str,
                     content_type: str, body: bytes) -> tuple[int, bytes]:
    """재생은 네트워크가 아니라 ASGI 로 자기 자신을 부른다 — 포트·토큰·httpx
    가 전부 필요 없어지고, 미들웨어(접근 로그·rev)도 평소처럼 지나간다."""
    headers = [(b"host", b"ops-replay"), (b"x-ops-replay", b"1"),
               (b"content-length", str(len(body)).encode())]
    if content_type:
        headers.append((b"content-type", content_type.encode("latin-1")))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
             "http_version": "1.1", "scheme": "http", "method": method,
             "path": path, "raw_path": path.encode(), "query_string": query.encode(),
             "root_path": "", "headers": headers,
             "client": ("127.0.0.1", 0), "server": ("ops-replay", 0), "state": {}}
    sent = {"done": False}
    out: dict = {"status": 500, "body": b""}

    async def _receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def _send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    await app(scope, _receive, _send)
    return out["status"], out["body"]


def _resp_view(body: bytes):
    text = body[:_INLINE_BODY_MAX].decode("utf-8", "replace")
    try:
        return json.loads(text)
    except Exception:
        return text[:_RESP_HEAD_MAX]


async def _apply_archive(app, tar_path: Path, force: bool,
                         stop_on_error: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="ops-apply-") as td:
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(td, filter="data")
        root = Path(td)
        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(400, "아웃박스 묶음이 아닙니다 — manifest.json 이 없습니다")
        if manifest.get("format") != _OUTBOX_FORMAT:
            raise HTTPException(400, f"모르는 묶음 형식입니다: {manifest.get('format')}")
        ops = _read_ops(root / "ops.jsonl")

        base = manifest.get("base")
        rev0 = _rev()
        warning = None
        if base is None:
            warning = "기준 없음 — 복원 없이 기록된 아웃박스라 rev 검사를 건너뜁니다"
        elif int(base.get("rev", -1)) != rev0 and not force:
            raise HTTPException(409, detail={
                "message": "기준이 낡았습니다 — 스냅샷 이후 서버 상태가 바뀌었습니다. "
                           "새 스냅샷으로 다시 보거나, 감수하려면 force=1 로 다시 보내세요.",
                "base_rev": base.get("rev"), "server_rev": rev0})

        seen = _applied_ids()
        report: dict = {"format": _OUTBOX_FORMAT, "applied_at": _now(),
                        "base": base, "warning": warning, "force": force,
                        "server_rev_before": rev0,
                        "total": len(ops), "applied": 0, "skipped": 0,
                        "failed": 0, "ops": []}
        for op in ops:
            row = {"id": op["id"], "method": op["method"], "path": op["path"]}
            if op["id"] in seen:
                row["skipped"] = True
                report["skipped"] += 1
                report["ops"].append(row)
                continue
            t0 = time.perf_counter()
            status, body = await _call_self(
                app, op["method"], op["path"], op.get("query", ""),
                op.get("content_type", ""), _op_body(op, root))
            row.update(status=status, ok=status < 400,
                       ms=round((time.perf_counter() - t0) * 1000),
                       response=_resp_view(body))
            report["ops"].append(row)
            if status < 400:
                _mark_applied(op["id"], status)   # 실패는 남겨 둔다 — 재시도 길
                report["applied"] += 1
            else:
                report["failed"] += 1
                if stop_on_error:
                    row["stopped_here"] = True
                    break
        report["server_rev_after"] = _rev()

        rp = OPS_DIR / "reports" / f"apply-{time.strftime('%Y%m%d-%H%M%S')}.json"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                      encoding="utf-8")
        report["report_file"] = str(rp)
        return report


# ------------------------------------------------------------------ 라우터
router = APIRouter(prefix="/v1/ops", tags=["ops"])


@router.get("/status", summary="운반 상태 — 기록 여부·rev·아웃박스")
def status():
    return {"record": RECORD, "rev": _rev(), "outbox": len(_read_ops(_OPS_FILE)),
            "base": _base(), "allow_restore": ALLOW_RESTORE,
            "inbox": INBOX_DIR, "state_keys": sorted(_state_targets())}


def build_snapshot() -> tuple[Path, dict]:
    """상태 전부를 tar.gz 하나로 만들어 (임시 경로, meta) 를 돌려준다.
    라우트와 GenOS 진입점(service.py)이 같은 것을 쓴다. 구조 저장소는
    pages/ 렌더 캐시를 뺀다 — 원본에서 다시 그려지는 것이고 스냅샷 무게의
    대부분이다. 지우는 책임은 부른 쪽에 있다."""
    targets = _state_targets()
    snap_id = uuid.uuid4().hex[:12]
    meta = {"format": _SNAPSHOT_FORMAT, "snapshot_id": snap_id,
            "created_at": _now(), "rev": _rev(), "keys": []}

    def _skip_pages(ti: tarfile.TarInfo):
        return None if "/pages/" in ti.name or ti.name.endswith("/pages") else ti

    OPS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz", prefix="snapshot-",
                               dir=str(OPS_DIR))
    os.close(fd)
    with tarfile.open(tmp, "w:gz") as tar:
        for key, p in sorted(targets.items()):
            if not p.exists():
                continue
            tar.add(str(p), arcname=f"state/{key}",
                    filter=_skip_pages if key == "structure" else None)
            meta["keys"].append(key)
        raw = json.dumps(meta, ensure_ascii=False, indent=1).encode()
        ti = tarfile.TarInfo("meta.json")
        ti.size = len(raw)
        ti.mtime = int(time.time())
        tar.addfile(ti, io.BytesIO(raw))
    log.info("스냅샷 %s — rev=%d keys=%s (%.1fMB)", snap_id, meta["rev"],
             ",".join(meta["keys"]), os.path.getsize(tmp) / 1e6)
    return Path(tmp), meta


@router.get("/snapshot", summary="상태 전부를 tar.gz 하나로")
def snapshot():
    tmp, meta = build_snapshot()
    return FileResponse(tmp, media_type="application/gzip",
                        filename=f"snapshot-{meta['snapshot_id']}.tar.gz",
                        background=BackgroundTask(os.remove, str(tmp)))


@router.post("/restore", summary="스냅샷으로 상태를 통째로 바꾼다 (로컬 전용)")
async def restore(file: UploadFile):
    """OPS_ALLOW_RESTORE=1 인 프로세스에서만 열린다 — 그쪽(정본)에서 실수로
    부르면 정본이 미러로 덮이는 사고라서, 기본은 잠근다."""
    if not ALLOW_RESTORE:
        raise HTTPException(403, "복원이 잠겨 있습니다 — OPS_ALLOW_RESTORE=1 "
                                 "로 띄운 로컬 미러에서만 쓰세요")
    targets = _state_targets()
    with tempfile.TemporaryDirectory(prefix="ops-restore-") as td:
        tar_path = Path(td) / "snap.tar.gz"
        with tar_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(td, filter="data")
        root = Path(td)
        try:
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(400, "스냅샷이 아닙니다 — meta.json 이 없습니다")
        if meta.get("format") != _SNAPSHOT_FORMAT:
            raise HTTPException(400, f"모르는 스냅샷 형식입니다: {meta.get('format')}")

        restored, unknown = [], []
        for key in meta.get("keys", []):
            src = root / "state" / key
            dst = targets.get(key)
            if dst is None:
                unknown.append(key)
                continue
            if not src.exists():
                continue
            if dst.is_dir():
                shutil.rmtree(dst)
            elif dst.exists():
                dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            restored.append(key)

    archived = _archive_outbox("restore")     # 옛 기준으로 쌓인 기록은 치운다
    _set_rev(int(meta.get("rev", 0)))
    _BASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BASE_FILE.write_text(json.dumps(
        {"snapshot_id": meta.get("snapshot_id"), "rev": int(meta.get("rev", 0)),
         "created_at": meta.get("created_at"), "restored_at": _now()},
        ensure_ascii=False), encoding="utf-8")
    _drop_caches()
    log.info("복원 %s — rev=%s keys=%s", meta.get("snapshot_id"),
             meta.get("rev"), ",".join(restored))
    return {"restored": restored, "unknown_keys": unknown,
            "snapshot_id": meta.get("snapshot_id"), "rev": _rev(),
            "outbox_archived": archived}


@router.get("/outbox", summary="쌓인 조작 목록 (몸통 제외)")
def outbox():
    ops = []
    for op in _read_ops(_OPS_FILE):
        o = {k: v for k, v in op.items() if k not in ("body_b64", "body_file")}
        o["body_bytes"] = (len(base64.b64decode(op["body_b64"]))
                           if op.get("body_b64") else
                           (_BODIES / Path(op["body_file"]).name).stat().st_size
                           if op.get("body_file") else 0)
        ops.append(o)
    return {"count": len(ops), "base": _base(), "ops": ops}


@router.delete("/outbox/{op_id}", summary="조작 하나를 아웃박스에서 뺀다")
def outbox_drop(op_id: str):
    ops = _read_ops(_OPS_FILE)
    keep = [o for o in ops if o["id"] != op_id]
    if len(keep) == len(ops):
        raise HTTPException(404, f"그런 조작이 없습니다: {op_id}")
    with _LOCK:
        _OPS_FILE.write_text(
            "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in keep),
            encoding="utf-8")
    (_BODIES / f"{op_id}.bin").unlink(missing_ok=True)
    return {"dropped": op_id, "count": len(keep)}


@router.post("/outbox/clear", summary="아웃박스 비우기 (history/ 로 보존)")
def outbox_clear():
    return {"archived": _archive_outbox("clear")}


@router.get("/outbox/export", summary="아웃박스를 tar.gz 하나로 — 그쪽 apply 에 넣는다")
def outbox_export():
    ops = _read_ops(_OPS_FILE)
    if not ops:
        raise HTTPException(404, "아웃박스가 비어 있습니다")
    manifest = {"format": _OUTBOX_FORMAT, "exported_at": _now(),
                "base": _base(), "count": len(ops)}
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz", prefix="outbox-", dir=str(OPS_DIR))
    os.close(fd)
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(str(_OPS_FILE), arcname="ops.jsonl")
        if _BODIES.is_dir():
            tar.add(str(_BODIES), arcname="bodies")
        raw = json.dumps(manifest, ensure_ascii=False, indent=1).encode()
        ti = tarfile.TarInfo("manifest.json")
        ti.size = len(raw)
        ti.mtime = int(time.time())
        tar.addfile(ti, io.BytesIO(raw))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return FileResponse(tmp, media_type="application/gzip",
                        filename=f"outbox-{stamp}-{len(ops)}ops.tar.gz",
                        background=BackgroundTask(os.remove, tmp))


@router.post("/apply", summary="아웃박스 묶음을 이 서버에 재생한다")
async def apply(file: UploadFile, request: Request,
                force: bool = Query(False),
                stop_on_error: bool = Query(False)):
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
        shutil.copyfileobj(file.file, f)
        tmp = Path(f.name)
    try:
        return await _apply_archive(request.scope["app"], tmp, force, stop_on_error)
    finally:
        tmp.unlink(missing_ok=True)


# ------------------------------------------------------------- 정적 현황 리포트
# 서버 없이 브라우저로만 여는 파일 하나 — 운반 수단이 전부 막혀도 "지금 데이터가
# 어떤 상태인가"는 이것으로 나른다. 화면(뷰어)의 대체가 아니라 현황판이다.
_REPORT_SOURCES = [
    ("ops", "GET", "/v1/ops/status", ""),
    ("documents", "GET", "/v1/structure/documents", ""),
    ("folders", "GET", "/v1/structure/folders", ""),
    ("glossary", "GET", "/v1/glossary/review", "limit=1"),
    ("links", "GET", "/v1/rag/links/summary", ""),
    ("verdicts", "GET", "/v1/rag/verdicts", ""),
    ("rules", "GET", "/v1/rag/rules", ""),
    ("formats", "GET", "/v1/formats", ""),
]


async def build_report(app) -> str:
    """앱 자신에게 GET 을 돌려 현황을 모으고, 의존이 빠진 배포에서는 그 단락만
    조용히 빠진다. 데이터는 요약 표 + <details> 원본 JSON — 요약이 감춘 것을
    원본이 보증한다."""
    from html import escape

    data: dict = {}
    for key, method, path, query in _REPORT_SOURCES:
        try:
            status, body = await _call_self(app, method, path, query, "", b"")
            if status < 400:
                data[key] = json.loads(body.decode("utf-8"))
        except Exception:                    # 라우터가 없는 배포 — 단락만 빠진다
            pass

    def chip(label: str, value) -> str:
        return (f'<span class="chip">{escape(label)} '
                f'<b>{escape(str(value))}</b></span>') if value is not None else ""

    ops_s = data.get("ops") or {}
    docs = (data.get("documents") or {}).get("documents") or []
    folders = (data.get("folders") or {}).get("folders") or []
    links = data.get("links") or {}
    verdicts = data.get("verdicts") or {}
    backlog = sum(len(verdicts.get(k) or []) for k in
                  ("edges", "fixes", "struct", "misses"))
    rules = (data.get("rules") or {}).get("rules") or []
    formats = (data.get("formats") or {}).get("formats") or []

    chips = "".join([
        chip("문서", len(docs)), chip("폴더", len(folders)),
        chip("용어 검수대기", (data.get("glossary") or {}).get("total")),
        chip("참조 확정", links.get("cross")), chip("참조 보류", links.get("pending")),
        chip("판정 백로그", backlog if "verdicts" in data else None),
        chip("규칙", len(rules) if "rules" in data else None),
        chip("형식", len(formats) if "formats" in data else None),
        chip("rev", ops_s.get("rev")),
    ])

    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            escape(str(d.get("name") or d.get("doc_id") or "?")),
            escape(str(d.get("folder") or "—")),
            escape(str(d.get("score") if d.get("score") is not None else "—")),
            escape(str(d.get("source_kind") or "—")),
            escape(str(d.get("at") or "—")))
        for d in docs)
    folder_rows = "".join(
        f"<tr><td>{escape(str(f.get('name')))}</td>"
        f"<td>{escape(str(f.get('docs')))}</td></tr>" for f in folders)

    raw = "".join(
        f"<details><summary>{escape(k)}</summary><pre>"
        f"{escape(json.dumps(v, ensure_ascii=False, indent=1)[:100_000])}"
        f"</pre></details>" for k, v in data.items())

    base = ops_s.get("base") or {}
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>8-AGENT 데이터 현황</title>
<style>
 body {{ font: 14px/1.6 -apple-system, "Malgun Gothic", sans-serif; color: #1a1d24;
        background: #f6f7f9; max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
 h1 {{ font-size: 20px; }} h2 {{ font-size: 15px; margin: 24px 0 8px; }}
 .meta {{ color: #6b7280; font-size: 12px; }}
 .chip {{ display: inline-block; background: #fff; border: 1px solid #d9dde3;
         border-radius: 14px; padding: 3px 10px; margin: 3px 4px 3px 0; }}
 table {{ border-collapse: collapse; background: #fff; width: 100%; }}
 th, td {{ border: 1px solid #e2e5ea; padding: 5px 9px; text-align: left;
          font-size: 13px; }}
 th {{ background: #eef0f4; }}
 details {{ margin: 6px 0; }} summary {{ cursor: pointer; color: #2563eb; }}
 pre {{ background: #fff; border: 1px solid #e2e5ea; padding: 10px;
       overflow-x: auto; font-size: 12px; }}
</style></head><body>
<h1>8-AGENT 데이터 현황</h1>
<p class="meta">만든 시각 {escape(_now())} · rev {escape(str(ops_s.get("rev", "?")))}
 · 기준 스냅샷 {escape(str(base.get("snapshot_id") or "—"))}
 · 이 파일은 서버 없이 열립니다 — 만든 시각의 상태다</p>
<p>{chips}</p>
<h2>문서 ({len(docs)})</h2>
<table><tr><th>이름</th><th>폴더</th><th>점수</th><th>원본</th><th>시각</th></tr>
{rows or '<tr><td colspan="5">문서 없음</td></tr>'}</table>
<h2>폴더 ({len(folders)})</h2>
<table><tr><th>이름</th><th>문서 수</th></tr>
{folder_rows or '<tr><td colspan="2">폴더 없음</td></tr>'}</table>
<h2>원본 JSON</h2>
{raw}
</body></html>"""


@router.get("/report", summary="정적 현황 리포트 — 서버 없이 여는 HTML 한 장")
async def report(request: Request):
    return HTMLResponse(await build_report(request.scope["app"]))


# ------------------------------------------------------------- 반입 폴더 감시
_WATCHER_STARTED = False


def _watch_inbox(app) -> None:
    """망간 전송이 파일을 떨어뜨려 주는 경로가 있으면 curl 조차 필요 없다 —
    OPS_INBOX_DIR 에 *.tar.gz 가 오면 적용하고 리포트를 옆에 쓴다."""
    inbox = Path(INBOX_DIR)
    done = inbox / "done"
    poll = float(os.environ.get("OPS_INBOX_POLL", "10"))
    log.info("반입 감시 시작 — %s (%.0f초)", inbox, poll)
    import asyncio
    while True:
        try:
            inbox.mkdir(parents=True, exist_ok=True)
            done.mkdir(parents=True, exist_ok=True)
            for p in sorted(inbox.glob("*.tar.gz")) + sorted(inbox.glob("*.tgz")):
                try:
                    report = asyncio.run(_apply_archive(app, p, False, False))
                except HTTPException as exc:
                    report = {"error": exc.detail, "status_code": exc.status_code}
                except Exception as exc:
                    report = {"error": f"{type(exc).__name__}: {exc}"}
                (done / f"{p.name}.report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=1),
                    encoding="utf-8")
                shutil.move(str(p), str(done / p.name))
                log.info("반입 적용 — %s (applied=%s failed=%s)", p.name,
                         report.get("applied"), report.get("failed"))
        except Exception:
            log.exception("반입 감시 순회 실패 — 다음 순회에 다시 본다")
        time.sleep(poll)


# ------------------------------------------------------------------- 설치
def install(app) -> None:
    """두 앱(api.app · api.structure_app)이 같은 한 줄로 붙인다."""
    global _WATCHER_STARTED
    app.add_middleware(OpsMiddleware)
    app.include_router(router)
    if INBOX_DIR and not _WATCHER_STARTED:
        _WATCHER_STARTED = True
        threading.Thread(target=_watch_inbox, args=(app,), daemon=True,
                         name="ops-inbox").start()
    log.info("ops 설치 — record=%s restore=%s inbox=%s dir=%s",
             RECORD, ALLOW_RESTORE, INBOX_DIR or "-", OPS_DIR)
