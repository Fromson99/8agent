"""로그 조회 API — /logs/ 화면이 읽는다.

    GET /v1/logs/rag      RAG 이벤트 (질의·검색·피드백) — var/logs/rag_events.jsonl
    GET /v1/logs/app      이 프로세스의 최근 로그 — 링버퍼 (lawrag/core/logbook)
    GET /v1/logs/files    logs/ 의 파일 목록 (수집 로그·회전 파일 포함)
    GET /v1/logs/file     파일 하나의 꼬리 — 이름은 logs/ 안으로만 제한

전부 읽기 전용이다 — 로그를 고치는 API 는 없다(관측을 고쳐 쓰지 않는다,
tuples.py 와 같은 규율). 앱 로그는 프로세스 안 링버퍼라 재시작하면 비지만,
파일 로그(logs/*.log)가 정본으로 남아 있어 /file 로 되짚을 수 있다.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from lawrag.core import logbook

router = APIRouter(prefix="/v1/logs", tags=["logs"])

_NAME_RE = re.compile(r"^[\w.\-]+$")      # 경로 탈출 차단 — 이름만 받는다


@router.get("/rag", summary="RAG 이벤트 — 질의·검색·피드백 관측 기록")
def rag_events(limit: int = Query(100, ge=1, le=1000),
               kind: str = Query("", description="ask | search | feedback"),
               q: str = Query("", description="질의·오류·모드 부분 일치")):
    events = logbook.read_rag_events(limit=limit, kind=kind or None, q=q or None)
    # 요약은 조회된 창 기준이다 — 전체 집계가 필요해지면 그때 누적 장부를 만든다.
    asks = [e for e in events if e.get("kind") == "ask"]
    durs = [e["dur_ms"] for e in asks if isinstance(e.get("dur_ms"), (int, float))]
    stats = {
        "asks": len(asks),
        "searches": sum(1 for e in events if e.get("kind") == "search"),
        "feedbacks": sum(1 for e in events if e.get("kind") == "feedback"),
        "errors": sum(1 for e in events if e.get("error")),
        "unanswerable": sum(1 for e in asks if e.get("answerable") is False),
        "avg_ms": int(sum(durs) / len(durs)) if durs else 0,
        "max_ms": max(durs) if durs else 0,
        "input_tokens": sum((e.get("usage") or {}).get("input_tokens", 0)
                            for e in asks),
        "output_tokens": sum((e.get("usage") or {}).get("output_tokens", 0)
                             for e in asks),
    }
    return {"events": events, "count": len(events), "stats": stats,
            "file": str(logbook.RAG_EVENTS_PATH)}


@router.get("/app", summary="앱 로그 — 이 프로세스의 최근 기록 (링버퍼)")
def app_log(limit: int = Query(300, ge=1, le=2000),
            level: str = Query("INFO", description="DEBUG | INFO | WARNING | ERROR"),
            q: str = Query("", description="메시지·로거 부분 일치")):
    records = logbook.recent(limit=limit, level=level or None, q=q or None)
    return {"records": records, "count": len(records), "ring_max": logbook.RING_MAX}


@router.get("/files", summary="로그 파일 목록 — 수집 로그·회전 파일 포함")
def log_files():
    d = logbook.LOG_DIR
    out = []
    if d.is_dir():
        for p in sorted(d.iterdir(), key=lambda p: -p.stat().st_mtime):
            if not p.is_file() or p.suffix not in (".log", ".jsonl", ".json"):
                continue
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size,
                        "mtime": st.st_mtime})
    return {"dir": str(d), "files": out}


@router.get("/file", summary="파일 꼬리 — logs/ 안의 파일만")
def log_file(name: str = Query(...),
             lines: int = Query(200, ge=1, le=2000)):
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(400, "이름만 받습니다 — 경로는 안 됩니다")
    p = logbook.LOG_DIR / name
    if not p.is_file():
        raise HTTPException(404, f"파일이 없습니다: {name}")
    # 꼬리만 읽는다 — 큰 파일을 통째로 올리지 않는다 (read_rag_events 와 같은 규율).
    try:
        import os

        size = p.stat().st_size
        with p.open("rb") as f:
            if size > 1024 * 1024:
                f.seek(-1024 * 1024, os.SEEK_END)
                f.readline()
            tail = f.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(500, f"읽기 실패: {exc}")
    rows = tail.splitlines()[-lines:]
    return {"name": name, "lines": rows, "count": len(rows),
            "size": p.stat().st_size}
