"""엔진 규칙 스위치 — 자동 규칙은 전부 사용자가 켜고 끈다.

해소·확장이 기계적으로 적용하는 규칙들의 등록부다. 규칙은 코드가 갖고 있지만
**켜짐/꺼짐은 사용자 소유**다(2026-08-13 사용자 결정: "이런 것들은 전부
사용자가 선택하게") — data/rules/engine.json 에 남고, 화면(공리 루프)에서
스위치로 보인다. 기본값은 등록부의 `기본`(없으면 켜짐 — 기존 동작 그대로)
이고, 파일에는 기본값과 다른 것만 적는다(빈 파일 = 오늘의 시스템).
실험 성격이라 비용·지연을 얹는 규칙(예: navigate, issue_spot_llm)만 기본 꺼짐이다 —
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
from threading import RLock

from lawrag.core.rag.index import store_path

# 등록부 — key 는 코드가 부르는 이름, 나머지는 화면이 읽는 설명.
REGISTRY: list[dict] = [
    {"key": "legalclosure_main", "이름": "LegalClosure 운영 기본",
     "기본": True,
     "설명": "POST /v1/rag/ask의 기본 회수기를 정확 구조→Assertion→균등 BM25→"
             "직접 관계 폐쇄 LegalClosure로 사용. 끄면 보관된 legacy-vector 경로로 "
             "즉시 롤백하며 응답 retriever에 rollback 상태를 표시",
     "자리": "회수 진입"},
    {"key": "sourceset_content_snapshot", "이름": "SourceSet 불변 콘텐츠 스냅샷",
     "기본": False,
     "설명": "검증된 active release와 SourceSet lock의 동일 세대만 색인·벡터·"
             "관계·인용·피드백에서 함께 사용. 켜진 상태에서 무결성이나 문서별 "
             "artifact 좌표가 없으면 mutable legacy 경로로 우회하지 않고 실패. "
             "끄면 기존 경로를 그대로 쓰는 독립 롤백 스위치",
     "자리": "데이터·회수 진입"},
    {"key": "legalclosure_proof_shortcut", "이름": "LegalClosure 증명 단축경로",
     "기본": True,
     "설명": "현재 canonical fingerprint와 일치하고 모든 source proof가 보존된 "
             "승인 Assertion 경로만 B0에서 재사용. miss·중의·버전 불일치는 기존 "
             "Assertion LLM 트리 B1로 즉시 fallback",
     "자리": "LegalClosure Assertion"},
    {"key": "legalclosure_definition_compaction", "이름": "정의 조 압축 부록",
     "기본": False,
     "설명": "일반 질문의 정의 조를 최종 인용 근거에서 빼고, 실제 제거된 규정의 "
             "질문 관련 정의만 원문 좌표가 있는 비인용 부록으로 제공. ADR-0038 "
             "fresh/fresh 27건 3표에서 13→12로 비열등성 실패하여 기본 OFF",
     "자리": "LegalClosure 최종 근거"},
    {"key": "legalclosure_feedback_explore", "이름": "LegalClosure 부족 재탐색",
     "기본": False,
     "설명": "최종 top 20을 Haiku가 충분성 판정하고 부족할 때 관계·구조·키워드·"
             "벡터 점프를 최대 3걸음 실행. 추가 모델 호출과 지연이 있으므로 실험 "
             "승인 전에는 기본 OFF이며, 실패하면 근거 없음으로 닫힘",
     "자리": "LegalClosure 최종 회수"},
    {"key": "legal_graph_v1_closure", "이름": "Legal Graph v1 조건부 폐쇄",
     "기본": False,
     "설명": "검증된 Legal Graph CURRENT를 질문·ProvisionCard·exact source "
             "endpoint와 모두 맞는 REQUIRED_WHEN_ACTIVATED 1-hop에만 사용. "
             "기존 LegalClosure 결과를 삭제하지 않고 잔여 슬롯에만 붙이며 "
             "missing·hash·schema·authority 불일치는 기존 결과로 fail-open. "
             "ADR-0101 in-sample probe만 완료되어 별도 out-of-sample 승격 전까지 "
             "repository 기본 OFF",
     "자리": "LegalClosure 최종 조문 동반"},
    {"key": "legal_semantic_entity_search", "이름": "법 의미 엔티티 검색 v2",
     "기본": False,
     "설명": "원문 근거가 있는 Formula·Time·Document·Authority·Classification "
             "등의 의미 엔티티 카드로 항·호·목에 먼저 착지한 뒤, 타입 관계를 최대 "
             "2-hop 닫고 DecisionBundle 단위로 최종 20건을 재선정. 상위 12건은 "
             "보호하고 최대 8건만 교체하며, 부정 결론은 조문 관계가 아닌 검토 필요 "
             "LegalAssessment로 분리. ADR-0103 검증·승격 전까지 기본 OFF",
     "자리": "LegalClosure 의미 착지·최종 근거"},
    {"key": "legal_research_integrated_v1", "이름": "통합 법률 조사 상태 머신",
     "기본": False,
     "설명": "레거시 UI 호환 표시 전용. ADR 연구 구현은 운영 API에서 직접 실행되지 "
             "않으며 lawrag.research에서 명시적으로 주입한다. 검증된 후보는 production "
             "component로 복사·등록하고 MAIN runtime profile 승격으로만 운영에 반영한다.",
     "자리": "연구 격리(운영 직접 실행 금지)"},
    {"key": "internal_compliance_compiler_v1", "이름": "내규·외규 원자명제 비교",
     "기본": False,
     "설명": "POST /v1/rag/compare에서 회수된 외규 후보를 삭제하지 않고 closed "
             "evidence ID·exact quote의 원자 requirement로 컴파일한 뒤 내규 claim과 "
             "결속한다. 상충·부합 외에 외규 요건의 내규 누락을 미비로 분리하고, "
             "degraded·미검증·미결속 coverage에서는 부합을 차단. 끄면 ADR-0125의 "
             "쌍별 비교기로 즉시 롤백",
     "자리": "내규·외규 비교"},
    {"key": "role_predicate_feedback_recovery", "이름": "오답 역할·판단축 복구 제안",
     "기본": False,
     "설명": "POST /v1/rag/feedback에서 정확 위치 없이 오답을 준 경우 저장된 질문의 "
             "행위자 역할과 허용·금지 판단술어를 함께 확인하고, 원문 검증된 규율법 "
             "조항만 add-only 복구 후보로 제시. 기존 답과 MAIN 회수는 바꾸지 않으며 "
             "문제가 있으면 이 스위치로 즉시 기록 전용 경로로 롤백",
     "자리": "오답 피드백"},
    {"key": "query_guide", "이름": "DB 역매칭 해석 안내", "기본": False,
     "설명": "질문 문자열에 실제로 맞은 문서·구조·Concept·저자 정의·본문 조각을 "
             "한 해석 후보표로 Span 분해기에 제시. 같은 문자열 해석은 OR로 고르고 "
             "서로 다른 문자열 착지는 기존처럼 좌표 AND로 결합",
     "자리": "단서 분해"},
    {"key": "assertion_tree_entry", "이름": "Assertion-first 구조 탐색", "기본": False,
     "설명": "명시 문서·TOC·Heading·조문을 DB 좌표 루트로 확정하고, 정본 Concept "
             "표현과 Assertion query cue를 정확 구·형태소로 역매칭한다. 임베딩 없이 "
             "DB 역할과 canonical 신호를 따라 문서군→문서→조·항을 최대 32개 닫힌 "
             "메뉴로 지연 선택. 문서군 라우팅 후 51건 실험 20/70으로 기본 OFF",
     "자리": "회수 진입"},
    {"key": "combination_entry", "이름": "구조 제약 지연 트리", "기본": True,
     "설명": "명시 문서·TOC·Heading·조문을 DB 좌표 루트로 확정하고, 질문의 역할 "
             "Span을 같은 Assertion 역할의 Concept 벡터 후보로 연다. LegalClosure 전환 "
             "뒤에는 legacy-vector/legacy-auto 롤백 모드에서만 사용하는 보관 경로",
     "자리": "회수 진입"},
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
    {"key": "navigate", "이름": "간선 항해", "기본": False,
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
    {"key": "memory_entry", "이름": "승인 질문 기억", "기본": True,
     "설명": "사람이 승인한 질문↔근거 좌표를 같은·유사 질문에서 직행으로 엶 — "
             "한 변수 A/B를 위해 독립 스위치로 둔다",
     "자리": "회수 진입"},
    {"key": "keyword_entry", "이름": "승인 용어 진입", "기본": True,
     "설명": "질문에 통째로 든 활성 용어의 대표 근거로 진입 — 낮은 독립 기여를 "
             "한 변수 A/B로 검증",
     "자리": "회수 진입"},
    {"key": "vector_entry", "이름": "벡터 진입", "기본": True,
     "설명": "구역 임베딩 의미 검색으로 진입 — 패러프레이즈·미발행 영역의 독립 "
             "회수 기여를 A/B로 검증",
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
_sealed_lock = RLock()
_sealed_promotions: tuple[tuple[str, bool], ...] | None = None
_sealed_main_state_sha256: str | None = None


def _sealed() -> bool:
    return os.environ.get("LAWRAG_SERVING_SEALED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def bind_sealed_promotion_overrides(
    values: dict[str, bool], *, main_state_sha256: str
) -> None:
    """Pin the already verified MAIN switch map once for a serving process."""

    global _sealed_promotions, _sealed_main_state_sha256
    if not _sealed():
        raise RuntimeError("sealed MAIN switches require sealed serving mode")
    if (
        not isinstance(main_state_sha256, str)
        or len(main_state_sha256) != 64
        or any(character not in "0123456789abcdef" for character in main_state_sha256)
    ):
        raise RuntimeError("sealed MAIN state SHA-256 is invalid")
    if not isinstance(values, dict):
        raise RuntimeError("sealed MAIN switches must be an object")
    unknown = sorted(set(values) - _KEYS)
    if unknown or any(not isinstance(value, bool) for value in values.values()):
        raise RuntimeError(
            "sealed MAIN switches are invalid"
            + (": " + ", ".join(unknown) if unknown else "")
        )
    normalized = tuple(sorted((str(key), value) for key, value in values.items()))
    with _sealed_lock:
        if _sealed_promotions is not None and (
            _sealed_promotions != normalized
            or _sealed_main_state_sha256 != main_state_sha256
        ):
            raise RuntimeError("sealed MAIN switch binding cannot be replaced")
        _sealed_promotions = normalized
        _sealed_main_state_sha256 = main_state_sha256


def engine_path() -> Path:
    return Path(os.environ.get("RAG_ENGINE_RULES",
                               store_path().parent / "rules" / "engine.json"))


def _user_overrides() -> dict:
    """사용자·운영자의 명시 override. MAIN promotion보다 우선한다."""
    if _sealed():
        # A sealed release is already an immutable, hash-verified decision.
        # Ambient authoring-plane files must not be able to turn its promoted
        # adapter off (or enable another unbound content path) after bootstrap.
        return {}
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


def _promotion_overrides() -> dict:
    """검증된 ADR arm이 MAIN generation에 승격한 switch 값."""
    if _sealed():
        with _sealed_lock:
            if _sealed_promotions is None:
                raise RuntimeError("sealed MAIN switch map was not bound at bootstrap")
            return dict(_sealed_promotions)
    try:
        from lawrag.platform import main_promotion
        return {
            key: value for key, value in main_promotion.switch_overrides().items()
            if key in _KEYS
        }
    except Exception:
        # 손상된 promotion manifest가 repository default나 사람 override를 막지 않는다.
        return {}


def _overrides() -> dict:
    """MAIN promotion 위에 사람의 emergency override를 합친 최종 명시 값."""
    return {**_promotion_overrides(), **_user_overrides()}


def is_on(key: str) -> bool:
    return _overrides().get(key, _DEFAULTS.get(key, True))


def snapshot() -> list[dict]:
    """화면용 — 등록부 + 현재 상태."""
    promoted = _promotion_overrides()
    user = _user_overrides()
    return [{
        **r,
        "on": user.get(r["key"], promoted.get(r["key"], _DEFAULTS[r["key"]])),
        "source": ("user_override" if r["key"] in user else
                   "main_promotion" if r["key"] in promoted else "default"),
    } for r in REGISTRY]


def set_switch(key: str, on: bool) -> None:
    if _sealed():
        raise PermissionError("sealed release MAIN switches are read-only")
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
    promoted_base = _promotion_overrides().get(key, _DEFAULTS[key])
    if on == promoted_base:
        sw.pop(key, None)               # 기본값과 같으면 안 적는다
    else:
        sw[key] = on
    data["switches"] = sw
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["mtime"] = None              # 다음 조회가 다시 읽는다
