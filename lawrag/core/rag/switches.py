"""엔진 규칙 스위치 — 자동 규칙은 전부 사용자가 켜고 끈다.

해소·확장이 기계적으로 적용하는 규칙들의 등록부다. 규칙은 코드가 갖고 있지만
**켜짐/꺼짐은 사용자 소유**다(2026-08-13 사용자 결정: "이런 것들은 전부
사용자가 선택하게") — data/rules/engine.json 에 남고, 화면(공리 루프)에서
스위치로 보인다. 기본값은 등록부의 `기본`(없으면 켜짐 — 기존 동작 그대로)
이고, 파일에는 기본값과 다른 것만 적는다(빈 파일 = 오늘의 시스템).
실험 성격이라 비용·지연을 얹는 규칙(예: issue_spot_llm)만 기본 꺼짐이다 —
issue_spot_pre 는 2026-08-18 부터 기본 켜짐(카드 조문 후보 좌표를 끊은 대가).

끄면 어떻게 되나: 확정 규칙(선언·추정·본문우선)은 그 간선이 보류로 내려가고,
동반 규칙(배제·위임·준용·수임)은 회수에서 빠지며, 항해는 돌지 않는다.
이미 저장된 판정(links.json·rel_fixes·억제)은 스위치와 무관하다 — 사람이
정한 것은 규칙이 아니라 판정이다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from lawrag.core.rag.index import store_path

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
    {"key": "floor_definition", "이름": "정의 동반",
     "설명": "착지 조문의 관할 정의 조(용어의 뜻)를 함께 회수 — 최근접 "
             "스코프 + 문서 대표. 실체 조문만 잡고 정의를 놓치는 실측 "
             "(casereview 4건)의 질의응답판 처방",
     "자리": "회수 바닥"},
    {"key": "floor_sanction", "이름": "제재 동반",
     "설명": "착지가 의무·금지 조문일 때, 그 조를 겨누는 벌칙·과태료 조를 "
             "역방향으로 회수 — 위반 리스크는 지어내지 않고 조문으로 보인다",
     "자리": "회수 바닥"},
    {"key": "navigate", "이름": "간선 항해",
     "설명": "바닥 뒤 남은 자리를 LLM 이 간선 카드를 보고 채움",
     "자리": "회수"},
    {"key": "wiki_context", "이름": "위키 맥락",
     "설명": "답 합성에 해석 지식 위키(data/wiki 아티클)를 배경으로 주입 — "
             "인용 근거는 여전히 조문 컨텍스트만",
     "자리": "답 합성"},
    {"key": "issue_spot", "이름": "쟁점 분해",
     "설명": "검색 전에 질문을 위키 쟁점 카드(트리거 매칭)에 비춰 걸린 "
             "카드를 세움 — 카드는 합성 배경이 되고, LLM 판(issue_spot_pre)"
             "이면 조문 문체 재작성(probe)이 벡터 질의가 된다",
     "자리": "회수 진입"},
    {"key": "review_binding", "이름": "검토 원장 적재",
     "설명": "적법성 검토 결과를 의존성 원장(자산↔조문)에 남김 — 나중에 그 "
             "조문이 개정되면 영향받는 자산을 역인덱스로 찾는다 "
             "(docs/REVIEW.md §Binding). 자산명을 준 검토만 적재된다",
     "자리": "검토"},
    {"key": "domain_recover", "이름": "도메인 회복 단",
     "설명": "회복 루프의 앞단에 도메인 지식 단(법령판: 쟁점 재회수·명칭 "
             "확장 — 결정론)을 세움 — 찾으면 범용 사다리(의미해석·깔때기)는 "
             "돌지 않는다",
     "자리": "회복"},
    # 기본 켜짐 (2026-08-18 사용자 결정): 카드 조문 후보의 좌표 직행을 끊은 뒤로,
    # 카드가 검색에 기여하는 길은 조문 문체 재작성(probe)뿐이다 — 트리거 판은
    # 재작성이 없어 벡터가 구어 원문을 그대로 문다. 라우팅 콜 1회가 그 값이다.
    {"key": "issue_spot_pre", "이름": "쟁점 분해 LLM", "기본": True,
     "설명": "검색 **전** 쟁점 분해를 트리거 매칭 대신 LLM 이 한다 — 질문만 "
             "보고 카드 메뉴에서 고르고 **조문 문체 재작성(probe)** 을 쓴다. 이 "
             "재작성이 벡터 채널의 질의가 된다(카드의 소임 — 좌표 연결이 아니라 "
             "문체 번역). 대가는 답변 앞에 얹히는 라우팅 콜 1회. 판정 불가면 "
             "트리거 결과로 폴백",
     "자리": "회수 진입"},
    {"key": "frame_entry", "이름": "프레임 진입",
     "설명": "질문을 '누가·무엇을·한다' 슬롯으로 옮겨(하이쿠 1콜) 조문 프레임의 "
             "행위 어휘와 렉시컬 대조 — 벡터가 낱말 겹침으로 이웃 조에 끌리는 "
             "자리를 문형이 가른다 (실측 2026-08-20: 자본시장법 제71조 미스 2건 회복)",
     "자리": "회수 진입"},
    {"key": "concept_entry", "이름": "1급 Concept 진입", "기본": True,
     "설명": "질문 표현을 승인된 Concept 메뉴에 정렬하고 자유 Cypher 없이 고정 OQL "
             "패턴에 ID 파라미터를 바인딩해 active Assertion의 근거 조항으로 진입. "
             "빈손·중의성이면 용어·프레임·벡터 사다리가 그대로 받는다",
     "자리": "회수 진입"},
    {"key": "doc_companion", "이름": "문서 동반",
     "설명": "밖 인용이 적은(≤20) 실무문서가 착지하면 그 문서의 밖 인용 전부를 "
             "동반 — 모범규준·내규는 법령 인용 모음이라 그 목록이 곧 법령 지도다. "
             "실측(2026-08-20): 대표주관 모범기준 +7 구역에 §125·시행령 §68 포함, "
             "법령·시행령(최대 1,795)은 게이트가 자동 배제",
     "자리": "회수"},
    {"key": "issue_respot", "이름": "판정 재회수", "기본": True,
     "설명": "판정된 쟁점 카드의 조문 후보로 2차 검색을 돌려 회수를 보충. "
             "두 실측이 갈린다(2026-08-20): 답변 본문 인용은 0/21이지만, 골든 "
             "회수 적중에는 기여한다(끄자 t3-08 상법 §418 미회수 — 벡터 모드는 "
             "회수 집합이 곧 출처라 인용 안 돼도 사용자에게 보인다). 인용률만 "
             "보고 끄면 안 되는 이유가 그것 — 기본 켜짐 유지",
     "자리": "회수"},
    {"key": "issue_spot_llm", "이름": "쟁점 판정 LLM", "기본": False,
     "설명": "컨텍스트 확보 후 LLM 이 질문+회수 조문을 보고 걸린 쟁점 "
             "카드를 판정 — 판정이 배경 주입을 이끈다(빈 판정 존중). 판정 "
             "콜 지연이 답변 앞에 얹히고, 판정 불가면 트리거 결과 유지",
     "자리": "답 합성"},
]
_KEYS = {r["key"] for r in REGISTRY}
_DEFAULTS = {r["key"]: bool(r.get("기본", True)) for r in REGISTRY}

_cache: dict = {"mtime": None, "ovr": {}}


def engine_path() -> Path:
    return Path(os.environ.get("RAG_ENGINE_RULES",
                               store_path().parent / "rules" / "engine.json"))


def _overrides() -> dict:
    """파일의 명시 값 — 기본값과 다른 것만 실재한다."""
    p = engine_path()
    if not p.exists():
        return {}
    mt = p.stat().st_mtime_ns
    if _cache["mtime"] == mt:
        return _cache["ovr"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ovr = {k: bool(v) for k, v in data.get("switches", {}).items()
               if k in _KEYS}
    except Exception:
        ovr = {}
    _cache.update(mtime=mt, ovr=ovr)
    return ovr


def is_on(key: str) -> bool:
    return _overrides().get(key, _DEFAULTS.get(key, True))


def snapshot() -> list[dict]:
    """화면용 — 등록부 + 현재 상태."""
    ovr = _overrides()
    return [{**r, "on": ovr.get(r["key"], _DEFAULTS[r["key"]])}
            for r in REGISTRY]


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
    if on == _DEFAULTS[key]:
        sw.pop(key, None)               # 기본값과 같으면 안 적는다
    else:
        sw[key] = on
    data["switches"] = sw
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["mtime"] = None              # 다음 조회가 다시 읽는다
