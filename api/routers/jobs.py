"""작업 조회 — 무거운 엔드포인트가 낸 job_id 를 여기서 따라간다.

    GET    /v1/jobs               목록 (결과 본문은 빼고 상태만)
    GET    /v1/jobs/{id}          상태 + 끝났으면 결과
    GET    /v1/jobs/{id}/wait     끝날 때까지 대기 (long-poll)
    DELETE /v1/jobs/{id}          결과 폐기 — 계약서 리포트를 서버에 남기지 않는다
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import http
from ..jobs import STORE

router = APIRouter(prefix="/v1/jobs", tags=["jobs"],
                   dependencies=[Depends(http.require_token)])


def _get(job_id: str):
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(404, detail={"message": f"작업을 찾을 수 없습니다: {job_id}"})
    return job


@router.get("", summary="작업 목록")
def list_jobs(limit: int = Query(50, ge=1, le=500)):
    return {"stats": STORE.stats(),
            "jobs": [j.to_dict(include_result=False) for j in STORE.list()[:limit]]}


@router.get("/{job_id}", summary="작업 상태 + 결과")
def get_job(job_id: str):
    return http.job_response(_get(job_id))


@router.get("/{job_id}/wait", summary="끝날 때까지 대기")
def wait_job(job_id: str, timeout: float = Query(60, ge=0)):
    job = _get(job_id)
    job.wait(http.clamp_wait(timeout))
    return http.job_response(job)


@router.delete("/{job_id}", summary="작업·결과 폐기")
def delete_job(job_id: str):
    _get(job_id)
    STORE.delete(job_id)
    return {"deleted": job_id}
