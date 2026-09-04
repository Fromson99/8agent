"""계보 원장 API — 수집→변환→구조화→연결 낙차를 보여준다 (docs/LINEAGE.md).

    GET /v1/lineage/summary   출처별 깔때기 + 연결 국면 + 고아 수 — 홈 카드용
    GET /v1/lineage           문서별 전체 계보(items·extras) — 감독 화면용

전부 읽기 전용이다 — 원장은 각 단계의 자기 기록에서 파생될 뿐, 여기서
무엇도 고치지 않는다. 경로 해석은 남이 굳힌 것을 빌린다: 구조화 스토어는
api.routers.structure 의 STORE, 연결은 core.rag.index.links_path() —
env 를 여기서 한 번 더 해석하면 두 해석이 어긋나는 날이 온다(lawrag/api/ops.py
와 같은 이유).
"""
from __future__ import annotations

from fastapi import APIRouter

from lawrag.api.routers.structure import STORE
from lawrag.core import lineage
from lawrag.core.rag.index import links_path

router = APIRouter(prefix="/v1/lineage", tags=["lineage"])


@router.get("/summary", summary="출처별 깔때기 — 수집·변환·구조화 수와 연결 국면")
def lineage_summary():
    return lineage.summary(lineage.build(STORE, links_path()))


@router.get("", summary="문서별 계보 전체 — 항목·고아·다음 걸음")
def lineage_full():
    return lineage.build(STORE, links_path())
