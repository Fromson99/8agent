"""격리 실험 모듈과 저장 평가 산출물의 읽기 전용 API."""

import json

from fastapi import APIRouter, HTTPException, Query

from lawrag.core.rag import experiment_catalog


router = APIRouter(prefix="/v1/experiments", tags=["experiments"])


@router.get("/catalog", summary="실험 모듈·실행 산출물 카탈로그")
def catalog():
    return experiment_catalog.catalog()


@router.get("/artifact", summary="실험 산출물 요약·설정·대표 문항")
def artifact(path: str = Query(...)):
    try:
        return experiment_catalog.detail(path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(404, f"실험 산출물을 읽을 수 없습니다: {path}") from exc
