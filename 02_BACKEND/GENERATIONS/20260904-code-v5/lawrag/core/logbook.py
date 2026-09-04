"""공통 로깅 — 한 번 설정하고 어디서나 `logging.getLogger(__name__)` 로 쓴다.

세 갈래로 남는다:

    ① 콘솔          사람이 지금 보는 터미널. LOG_LEVEL 로 조절 (기본 INFO).
    ② 회전 파일     logs/{app}.log — 프로세스가 죽어도 남는 정본. 5MB × 3.
    ③ 링버퍼        프로세스 안 최근 N건 — /v1/logs/app 이 읽어 화면에 준다.
                    파일 tail 파싱보다 정확하고(레벨·로거가 구조로 남는다) 싸다.

그리고 RAG 만의 네 번째 갈래:

    ④ RAG 이벤트    var/logs/rag_events.jsonl — 질의 하나가 한 줄. 사다리·소요·
                    토큰·오류가 구조로 남아 /logs/ 화면이 그대로 그린다.
                    append-only — 관측을 고쳐 쓰면 "그때 뭘 봤나"가 사라진다
                    (tuples.py 와 같은 규율).

lawrag/sources/common.py 의 수집 로그(logs/{source}_{stamp}.log)는 그대로 둔다 —
수집은 실행 단위 스냅샷이 맞고, 서비스는 회전 파일이 맞다.
"""

from __future__ import annotations

import collections
import json
import logging
import logging.handlers
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.platform.paths import runtime_path

LOG_DIR = Path(os.environ.get("LOG_DIR") or runtime_path("logs"))
RAG_EVENTS_PATH = Path(os.environ.get("RAG_EVENTS_LOG", LOG_DIR / "rag_events.jsonl"))

FMT = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

RING_MAX = 2000
_ring: collections.deque = collections.deque(maxlen=RING_MAX)
_lock = threading.Lock()
_configured: dict = {}


def _feedback_disabled() -> bool:
    return os.environ.get("LAWRAG_FEEDBACK_DISABLED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _sealed() -> bool:
    return os.environ.get("LAWRAG_SERVING_SEALED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def now_iso() -> str:
    """로컬 시각 ISO — 사람이 읽는 로그다. 비교·정렬용은 아니고 표시용."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ms(t0: float) -> int:
    """perf_counter 시점부터 지금까지 밀리초 — 계측 자리마다 한 줄로 쓴다."""
    return int((time.perf_counter() - t0) * 1000)


class _RingHandler(logging.Handler):
    """최근 로그를 구조로 쥔다 — 로그 화면의 '앱 로그' 패널이 읽는다."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:                    # 포맷 인자 불일치가 로깅을 죽이면 안 된다
            msg = str(record.msg)
        if record.exc_info and record.exc_text:
            msg = f"{msg}\n{record.exc_text}"
        _ring.append({"ts": now_iso(), "level": record.levelname,
                      "logger": record.name, "msg": msg})


def setup(app: str = "app", level: Optional[str] = None) -> None:
    """루트 로거 설정 — 엔트리포인트(API 앱·CLI)가 첫 줄에서 부른다.
    멱등이다: 같은 프로세스에서 두 번 불러도 핸들러가 늘지 않는다."""
    if _configured.get("done"):
        return
    _configured["done"] = True

    lvl = getattr(logging, (level or os.environ.get("LOG_LEVEL", "INFO")).upper(),
                  logging.INFO)
    root = logging.getLogger()
    root.setLevel(lvl)
    fmt = logging.Formatter(FMT, datefmt=DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Sealed serving keeps application logs on stderr/ring only.  Durable RAG
    # observations use the dirfd/no-follow ledger below instead of a rotating
    # pathname handler that could be retargeted after bootstrap.
    if not _feedback_disabled() and not _sealed():
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                LOG_DIR / f"{app}.log", maxBytes=5 * 1024 * 1024, backupCount=3,
                encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:                      # 읽기 전용 컨테이너 — 콘솔·링만으로 간다
            root.warning("로그 디렉터리를 쓸 수 없습니다 — 파일 로그 없이 갑니다: %s", LOG_DIR)

    ring = _RingHandler()
    ring.setLevel(logging.DEBUG)             # 화면은 레벨 필터를 조회 시점에 건다
    root.addHandler(ring)

    # 시끄러운 서드파티는 한 단 눌러 둔다 — 우리 로그가 묻히면 로깅이 없느니만 못하다.
    for noisy in ("httpx", "httpcore", "anthropic", "urllib3", "PIL",
                  "sentence_transformers", "transformers", "filelock"):
        logging.getLogger(noisy).setLevel(max(lvl, logging.WARNING))

    logging.getLogger("lawrag.core.logbook").info(
        "로깅 시작 — app=%s level=%s file=%s", app, logging.getLevelName(lvl),
        LOG_DIR / f"{app}.log")


def recent(limit: int = 500, level: Optional[str] = None,
           q: Optional[str] = None) -> list[dict]:
    """링버퍼 조회 — 최신이 앞. level 은 하한(INFO 면 INFO 이상)."""
    floor = getattr(logging, (level or "DEBUG").upper(), logging.DEBUG)
    out = []
    for rec in reversed(_ring):
        if getattr(logging, rec["level"], 0) < floor:
            continue
        if q and q.casefold() not in (rec["msg"] + rec["logger"]).casefold():
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- RAG 이벤트
def rag_event(kind: str, **fields) -> dict:
    """RAG 관측 한 건을 적재한다 — 질의응답·검색·피드백이 한 줄씩.
    적재 실패가 질의응답을 죽이면 안 된다: 실패는 로그로만 남긴다."""
    rec = {"ts": now_iso(), "kind": kind, **fields}
    if _feedback_disabled():
        return rec
    line = json.dumps(rec, ensure_ascii=False, default=str)
    try:
        if _sealed():
            from lawrag.core.rag.tuples import append_feedback_jsonl

            append_feedback_jsonl("rag_events.jsonl", rec)
            return rec
        with _lock:
            RAG_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with RAG_EVENTS_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as exc:
        logging.getLogger("lawrag.core.rag.event").warning("이벤트 적재 실패: %s", exc)
    return rec


def read_rag_events(limit: int = 200, kind: Optional[str] = None,
                    q: Optional[str] = None) -> list[dict]:
    """이벤트 조회 — 최신이 앞. 파일 꼬리만 읽는다(2MB) — 로그가 커져도 싸다."""
    if _feedback_disabled():
        return []
    if _sealed():
        from lawrag.core.rag.tuples import feedback_file_bytes

        blob = feedback_file_bytes("rag_events.jsonl")
        if blob is None:
            return []
        raw = blob[-2 * 1024 * 1024:].decode("utf-8", errors="replace")
        if len(blob) > 2 * 1024 * 1024:
            raw = raw.partition("\n")[2]
    else:
        p = RAG_EVENTS_PATH
        if not p.exists():
            return []
        try:
            size = p.stat().st_size
            with p.open("rb") as f:
                if size > 2 * 1024 * 1024:
                    f.seek(-2 * 1024 * 1024, os.SEEK_END)
                    f.readline()                 # 잘린 첫 줄은 버린다
                raw = f.read().decode("utf-8", errors="replace")
        except OSError:
            return []
    out = []
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind and rec.get("kind") != kind:
            continue
        if q:
            hay = (str(rec.get("q", "")) + str(rec.get("error", ""))
                   + str(rec.get("mode", ""))).casefold()
            if q.casefold() not in hay:
                continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out
