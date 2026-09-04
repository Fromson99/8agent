"""배치 파이프라인 API — 라인업(무엇이 빠졌나) · 실행(딸깍) · 진행 · 이력.

실행은 프로세스 안 스레드 하나(lawrag/core/batch.RUNNER)다 — 단계마다 기존 증분
모듈을 부르므로 중간에 죽어도 다음 실행이 라인업을 다시 세고 이어 간다.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from lawrag.core import batch as batch_mod

log = logging.getLogger("lawrag.api.pipeline")

router = APIRouter(prefix="/v1/pipeline", tags=["pipeline"])


@router.get("/lineup", summary="라인업 — 단계별로 무엇이 빠졌나 (돌리지 않는다)")
def pipeline_lineup():
    lu = batch_mod.lineup()
    lu["order"] = list(batch_mod.STAGES)
    lu["labels"] = batch_mod.LABELS
    lu["kinds"] = batch_mod.KIND
    return lu


@router.get("/status", summary="현재(또는 마지막) 실행의 진행")
def pipeline_status():
    return batch_mod.RUNNER.status()


class Run(BaseModel):
    stages: Optional[list[str]] = None     # 비우면 전부(순서대로)
    workers: Optional[int] = None          # 프레임 LLM 동시성
    chunk: Optional[int] = None            # 임베딩 진행 단위
    force: bool = False                    # 위임 간선 강제 재생성


@router.post("/run", summary="딸깍 — 빠진 것만 순서대로 돌린다 (백그라운드)")
def pipeline_run(body: Run):
    try:
        return batch_mod.RUNNER.start(body.stages, {k: v for k, v in body.model_dump().items()
                                                    if k != "stages" and v is not None})
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/stop", summary="중지 — 단계·문서 경계에서 멈춘다")
def pipeline_stop():
    return batch_mod.RUNNER.stop()


@router.get("/runs", summary="실행 이력")
def pipeline_runs(limit: int = Query(20, ge=1, le=100)):
    return {"runs": batch_mod.RUNNER.runs(limit)}


@router.get("/runs/{run_id}/log", summary="실행 로그 꼬리")
def pipeline_log(run_id: str, n: int = Query(200, ge=1, le=2000)):
    return {"run_id": run_id, "events": batch_mod.RUNNER.log_tail(run_id, n)}
