"""작업 큐 — 무거운 단계를 백그라운드로 돌린다.

## 왜 큐인가

도클링 파싱은 40초 안팎, LLM 대사는 문서 크기에 따라 몇 분이 걸린다.
그런데 대부분의 리버스 프록시(코드스페이스 포트 포워딩·클라우드 LB)는 30~60초에서
연결을 끊는다. 동기 응답으로 만들면 **끝난 작업의 결과를 못 받는** 상황이 나온다.

그래서 제출 → 폴링이 기본이고, `wait` 파라미터로 그 시간까지는 동기처럼 기다린다.
짧게 끝나는 요청(마크다운 요약서 대사 등)은 한 번의 호출로 결과가 나오고,
오래 걸리는 요청은 자동으로 job id 로 떨어진다. 호출자는 한 가지 방식만 알면 된다.

작업 결과는 메모리에만 있다. 컨테이너를 재시작하면 사라진다 —
영속이 필요하면 결과를 받아서 호출자가 저장한다(§감사 로그는 이 계층의 책임이 아니다).
"""
from __future__ import annotations

import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import settings

QUEUED, RUNNING, DONE, ERROR = "queued", "running", "done", "error"


@dataclass
class Job:
    id: str
    kind: str
    params: dict = field(default_factory=dict)
    status: str = QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    logs: list[str] = field(default_factory=list)
    workdir: Optional[Path] = None
    _done: threading.Event = field(default_factory=threading.Event, repr=False)

    def log(self, message: str) -> None:
        self.logs.append(f"{time.strftime('%H:%M:%S')} {message}")

    def wait(self, timeout: float) -> bool:
        return self._done.wait(timeout=max(0.0, timeout))

    @property
    def elapsed(self) -> Optional[float]:
        if self.started_at is None:
            return None
        return round((self.finished_at or time.time()) - self.started_at, 2)

    def to_dict(self, include_result: bool = True) -> dict:
        d = {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "params": self.params,
            "created_at": self.created_at,
            "elapsed_sec": self.elapsed,
            "logs": self.logs,
        }
        if self.status == ERROR:
            d["error"] = self.error
            d["error_type"] = self.error_type
        if include_result and self.status == DONE:
            d["result"] = self.result
        return d


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pools = {
            "parser": ThreadPoolExecutor(max_workers=settings.PARSER_WORKERS,
                                         thread_name_prefix="parser"),
            # 스냅샷·용어집 파일을 공유하므로 기본 1 — 동시 실행하면 서로 덮어쓴다
            "agent": ThreadPoolExecutor(max_workers=settings.AGENT_WORKERS,
                                        thread_name_prefix="agent"),
        }

    # --- 제출 -------------------------------------------------------------
    def submit(self, pool: str, kind: str, fn: Callable[[Job], Any],
               params: Optional[dict] = None, workdir: Optional[Path] = None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, params=params or {}, workdir=workdir)
        with self._lock:
            self._jobs[job.id] = job
            self._prune_locked()
        self._pools[pool].submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[Job], Any]) -> None:
        job.status = RUNNING
        job.started_at = time.time()
        try:
            job.result = fn(job)
            job.status = DONE
        except Exception as exc:                      # 작업 하나가 죽어도 서버는 산다
            job.status = ERROR
            job.error_type = type(exc).__name__
            job.error = str(exc) or repr(exc)
            job.log(f"실패 {job.error_type}: {job.error}")
            job.logs.extend(traceback.format_exc().splitlines()[-6:])
        finally:
            job.finished_at = time.time()
            # 업로드 임시본은 결과를 만든 뒤 즉시 지운다 — 계약서 원본을 디스크에 남기지 않는다
            if job.workdir:
                shutil.rmtree(job.workdir, ignore_errors=True)
                job.workdir = None
            job._done.set()

    # --- 조회 -------------------------------------------------------------
    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and job.workdir:
            shutil.rmtree(job.workdir, ignore_errors=True)
        return job is not None

    def stats(self) -> dict:
        c = {QUEUED: 0, RUNNING: 0, DONE: 0, ERROR: 0}
        for j in self._jobs.values():
            c[j.status] = c.get(j.status, 0) + 1
        return {"total": len(self._jobs), **c}

    def _prune_locked(self) -> None:
        """오래된 것부터 버린다 — 메모리에 리포트를 무한정 쌓지 않는다."""
        now = time.time()
        stale = [i for i, j in self._jobs.items()
                 if j.status in (DONE, ERROR) and now - j.created_at > settings.JOB_TTL_SECONDS]
        for i in stale:
            self._jobs.pop(i, None)
        if len(self._jobs) > settings.MAX_JOBS:
            done = sorted((j for j in self._jobs.values() if j.status in (DONE, ERROR)),
                          key=lambda j: j.created_at)
            for j in done[: len(self._jobs) - settings.MAX_JOBS]:
                self._jobs.pop(j.id, None)


STORE = JobStore()
