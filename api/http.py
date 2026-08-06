"""라우터 공용 — 제출·대기 응답 규약과 인증.

## 응답 규약 (모든 비동기 엔드포인트가 동일)

    202 {"status":"queued"|"running", "job_id":"..."}    아직 안 끝남 → 폴링
    200 {"status":"done",  "job_id":"...", "result":{}}  끝남 → 결과 동봉
    200 {"status":"error", "job_id":"...", "error":"..."} 작업 실패

`wait=<초>` 를 주면 그만큼 기다렸다가 위 규약대로 낸다. 기본값은 엔드포인트마다 다르다 —
빨리 끝날 가능성이 높으면 크게(대사 30초), 무조건 오래 걸리면 0(파싱·LLM 대사).

작업 **실패**는 HTTP 500 이 아니라 200 + status:error 다. 요청 자체는 성공했고,
실패한 것은 작업이다. 폴링 호출자가 두 층위를 구분할 수 있어야 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse

from . import settings
from .jobs import DONE, ERROR, STORE, Job


async def require_token(authorization: Optional[str] = Header(default=None)) -> None:
    """API_TOKEN 이 설정된 배포에서만 동작한다. 없으면 무인증(로컬·사내망 기본)."""
    if not settings.API_TOKEN:
        return
    expected = f"Bearer {settings.API_TOKEN}"
    if authorization != expected:
        raise HTTPException(401, detail={"message": "유효한 Bearer 토큰이 필요합니다"})


def job_response(job: Job) -> JSONResponse:
    body = job.to_dict()
    code = 200 if job.status in (DONE, ERROR) else 202
    return JSONResponse(body, status_code=code)


def submit(pool: str, kind: str, fn: Callable[[Job], Any], *,
           params: Optional[dict] = None, workdir: Optional[Path] = None,
           wait: float = 0.0) -> JSONResponse:
    job = STORE.submit(pool, kind, fn, params=params, workdir=workdir)
    if wait > 0:
        job.wait(min(wait, settings.MAX_WAIT_SECONDS))
    return job_response(job)


def clamp_wait(wait: float) -> float:
    return max(0.0, min(float(wait), settings.MAX_WAIT_SECONDS))
