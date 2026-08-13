"""엔진 규칙 스위치 — 자동 규칙은 전부 사용자가 켜고 끈다.

해소·확장이 기계적으로 적용하는 규칙들의 등록부다. 규칙은 코드가 갖고 있지만
**켜짐/꺼짐은 사용자 소유**다(2026-08-13 사용자 결정: "이런 것들은 전부
사용자가 선택하게") — data/rules/engine.json 에 남고, 화면(공리 루프)에서
스위치로 보인다. 기본값은 전부 켜짐 — 기존 동작 그대로이고, 파일에는
기본값과 다른 것만 적는다(빈 파일 = 오늘의 시스템).

끄면 어떻게 되나: 확정 규칙(선언·추정·본문우선)은 그 간선이 보류로 내려가고,
동반 규칙(배제·위임·준용·수임)은 회수에서 빠지며, 항해는 돌지 않는다.
이미 저장된 판정(links.json·rel_fixes·억제)은 스위치와 무관하다 — 사람이
정한 것은 규칙이 아니라 판정이다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.rag.index import store_path

# 등록부 — key 는 코드가 부르는 이름, 나머지는 화면이 읽는 설명.
REGISTRY: list[dict] = [
    {"key": "declare", "이름": "선언 확정",
     "설명": "문서가 '이하 \"법\"이라 한다'로 선언한 대용어를 그 문서로 확정",
     "자리": "참조 해소"},
    {"key": "mainbody", "이름": "본문 우선",
     "설명": "한 문서 안 본문·부칙 번호 중복이면 본문 조로 확정 — 부칙 조는 "
             "밖에서 '부칙 제N조'로 부른다",
     "자리": "참조 해소"},
    {"key": "presume", "이름": "추정 연결",
     "설명": "후보가 하나뿐인 대용어 참조를 기본 연결 (2026-08-12 결정)",
     "자리": "참조 해소"},
    {"key": "floor_exclusion", "이름": "배제 동반",
     "설명": "착지 조문을 배제·제한하는 조항을 무조건 회수 (역방향 포함)",
     "자리": "회수 바닥"},
    {"key": "floor_delegation", "이름": "위임 동반",
     "설명": "착지 조문이 위임한 시행령·규정 조문을 무조건 회수",
     "자리": "회수 바닥"},
    {"key": "floor_junyong", "이름": "준용 동반",
     "설명": "착지 조문이 준용하는 조문을 무조건 회수",
     "자리": "회수 바닥"},
    {"key": "floor_reception", "이름": "수임 동반",
     "설명": "착지 조문의 위임을 받은 하위 규정 조문을 무조건 회수 (역방향)",
     "자리": "회수 바닥"},
    {"key": "navigate", "이름": "간선 항해",
     "설명": "바닥 뒤 남은 자리를 LLM 이 간선 카드를 보고 채움",
     "자리": "회수"},
]
_KEYS = {r["key"] for r in REGISTRY}

_cache: dict = {"mtime": None, "off": frozenset()}


def engine_path() -> Path:
    return Path(os.environ.get("RAG_ENGINE_RULES",
                               store_path().parent / "rules" / "engine.json"))


def _off_keys() -> frozenset:
    p = engine_path()
    if not p.exists():
        return frozenset()
    mt = p.stat().st_mtime_ns
    if _cache["mtime"] == mt:
        return _cache["off"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        off = frozenset(k for k, v in data.get("switches", {}).items()
                        if k in _KEYS and v is False)
    except Exception:
        off = frozenset()
    _cache.update(mtime=mt, off=off)
    return off


def is_on(key: str) -> bool:
    return key not in _off_keys()


def snapshot() -> list[dict]:
    """화면용 — 등록부 + 현재 상태."""
    off = _off_keys()
    return [{**r, "on": r["key"] not in off} for r in REGISTRY]


def set_switch(key: str, on: bool) -> None:
    if key not in _KEYS:
        raise ValueError(f"모르는 스위치: {key}")
    p = engine_path()
    data: dict = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    sw = data.get("switches", {})
    if on:
        sw.pop(key, None)               # 기본값(켜짐)과 같으면 안 적는다
    else:
        sw[key] = False
    data["switches"] = sw
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["mtime"] = None              # 다음 조회가 다시 읽는다
