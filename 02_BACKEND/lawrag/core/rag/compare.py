"""내규 ↔ 외규 비교기 — 내규 조 하나를 외규 조들과 나란히 놓고 상충/부합을 찍는다.

전체 그림은 docs/COMPARE_INTERNAL_EXTERNAL.md. 흐름 세 단계:

    ① 짝 찾기   문면 간선(내규 조가 인용한 외규 좌표 mandatory) + LegalClosure
                A/B/C/D·reference rescue — 외규 스코프만 진입한다. 내규는 입력이다.
    ② 판정      값이 있으면 숫자로(결정론 quant), 없으면 LLM 이 쌍마다 판정.
                결정론이 확정한 쌍은 LLM 이 뒤집지 못한다(stochastic 격리).
    ③ 출력      verdict + 양쪽 좌표 + 값비교·쌍판정 근거 + 회수 origin·legal_meta·
                article reachability. 원문 표기 그대로.

verdict 는 셋 + 하나다: 상충(내규가 완화·역행) · 부합(그대로거나 더 보수적) ·
재검토(짝이 없거나 하나라도 미해결) — 자동 확정 금지 원칙(§1-3 조용한 실패 금지)은
여기서도 산다. `부합`은 회수된 후보에 대한 조문 단위 판정이다. **미비**(외규가
"정하라" 한 것이 내규에 없음)는 방향이 반대
(외규 각 호 → 내규 순회)라 이 함수가 아니라 coverage 점검(후속)의 몫이다.

## 값 비교가 왜 축(비교어)을 요구하는가

"높으면 엄격"이 아니다 — 축이 방향을 뒤집는다:

    하한 축   "순자본비율 150% **미달** 시 중지" · "500% **이상** 유지"
              → 문턱이 높을수록 엄격. 내규 < 외규 = 완화(상충).
    상한 축   "자기자본의 100분의 35 **이내**로 관리" · "45일 **이내** 보고"
              → 낮을수록(짧을수록) 엄격. 내규 > 외규 = 완화(상충).

축이 다르거나 지표(비교 대상 명사)가 다르면 값 비교를 하지 않는다 — 그 쌍은
LLM 판정으로 넘어간다. 같은 "비율"이라도 분모가 다르면 견주면 안 된다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from lawrag.core.rag.index import Index

log = logging.getLogger("lawrag.core.rag.compare")

_JO = re.compile(r"^제\s*[\d\-]+\s*조(?:의\s*\d+)?$")
CAND_MAX = 20             # LegalClosure MAIN의 최종 조문 예산과 같은 계약
LEGACY_CAND_MAX = 6       # 롤백용 종전 간선→프레임→벡터 후보 예산
SNIPPET = 1800            # 판정 콜에 넣는 조문 본문 상한 (조 하나)

# ---------------------------------------------------------------- 값 추출
# 표기는 원문 그대로 두고 값은 비교 안에서만 쓴다 (grounding — tags.py 와 동일).
_RATIO = re.compile(r"(?:100|1천|1만|만|천)분의\s*([\d,]+(?:\.\d+)?)")
_PCT = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:%|퍼센트)")
_DAYS = re.compile(r"([\d,]+)\s*(년|개월|월|주|일)\s*(?:이내|안에|전까지)")
_IMMED = re.compile(r"지체\s*없이|즉시")
_DENOM = {"100": 100, "1천": 1000, "1만": 10000, "만": 10000, "천": 1000}
_DAY_UNIT = {"년": 365, "개월": 30, "월": 30, "주": 7, "일": 1}

# 축 — 표기 뒤 창에서 읽는다. 하한: 문턱보다 낮아지면 제재·의무(높을수록 엄격),
# 상한: 이 아래로 관리(낮을수록 엄격). 기한은 상한의 시간판.
_LOWER = re.compile(r"미달|이상|아래로\s*떨어")
_UPPER = re.compile(r"이내|이하|넘지|초과할\s*수\s*없|한도")


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def quants(text: str) -> list[dict]:
    """[{종류, 표기, 값, 축, 지표}] — 축·지표를 못 읽은 표기는 값 비교에 안 쓴다.

    지표는 표기 **앞 14자**의 원문 조각 — "무엇의" 값인지(순자본비율/총위험액)를
    쌍맞춤(2-그램 겹침)에 쓴다. 명사 사전이 아니라 원문 창이다(문서 무관)."""
    out = []
    t = " ".join((text or "").split())
    # 괄호 삽입구를 걷어낸다 — 법문은 "(겸영금융투자업자의 경우에는 … 말한다)"
    # 같은 삽입을 값과 술어 사이에 끼워 결과창을 잘라먹는다(실측 t5s2-01: §166의2
    # 쌍 겹침 5<6). 숫자가 든 괄호는 값일 수 있으니 남긴다.
    t = re.sub(r"[(（][^()（）\d]{1,40}[)）]", " ", t)
    t = " ".join(t.split())

    def push(kind, m, val):
        tail = t[m.end():m.end() + 14]
        axis = ("하한" if _LOWER.search(tail)
                else "상한" if _UPPER.search(tail) else "")
        # 문턱 술어가 창 밖(각 호 열거 뒤)에 오는 흔한 꼴 — "미달하는 경우 …
        # 중지/보고"는 문장 어디 있든 하한 문턱이다.
        if not axis and _LOWER.search(t[m.end():m.end() + 60]):
            axis = "하한"
        # 지표 = 값 바로 앞의 온전한 한글 덩어리(조사 제거) — 창(14자)으로 자르면
        # "영업용순자본비율"이 "순자본비율"로 잘려 다른 지표가 같은 지표로 읽힌다.
        head = re.search(r"([가-힣]+)\s*$", t[max(0, m.start() - 30):m.start()])
        ind = re.sub(r"[이가은는을를의]$", "", head.group(1)) if head else ""
        out.append({"종류": kind, "표기": m.group(0).strip(), "값": val,
                    "축": axis, "지표": ind,
                    # 결과창 — 문턱 뒤의 행위 문구. 지표가 침묵하는 산식 조문
                    # (§166의2 "…나눈 값이")과의 쌍맞춤에 쓴다.
                    "결과": t[m.end():m.end() + 30].strip()})

    for m in _RATIO.finditer(t):
        denom = next((v for k, v in _DENOM.items() if m.group(0).startswith(k)), 100)
        push("비율", m, _num(m.group(1)) / denom)
    for m in _PCT.finditer(t):
        push("비율", m, _num(m.group(1)) / 100)
    # 기한의 지표는 **뒤의 행위**다 — "45일 이내에 …보고한다" 와 "지체없이 …
    # 보고하여야 한다" 를 잇는 것은 앞말(분기 종료 후/미달하는 경우)이 아니라
    # 보고라는 행위다(실측: 앞 창으로는 v1 45일 ↔ 지체없이 쌍이 안 잡혔다).
    for m in _DAYS.finditer(t):
        w = t[m.end():m.end() + 18].strip()
        out.append({"종류": "기한", "표기": m.group(0).strip(),
                    "값": _num(m.group(1)) * _DAY_UNIT[m.group(2)],
                    "축": "상한", "지표": w, "결과": w})
    for m in _IMMED.finditer(t):
        w = t[m.end():m.end() + 18].strip()
        out.append({"종류": "기한", "표기": m.group(0), "값": 0.0, "축": "상한",
                    "지표": w, "결과": w})
    return out[:12]


def _grams2(s: str) -> set:
    x = re.sub(r"[\s·ㆍ의은는이가을를]+", "", s or "")
    return {x[i:i + 2] for i in range(len(x) - 1)} if len(x) >= 2 else set()


def _suffix_conflict(a: str, b: str) -> bool:
    """한쪽 지표가 다른쪽의 **진부분 접미**인가 — "순자본비율" ⊂ "영업용순자본비율".

    접두가 지표를 다른 것으로 만든다(1종 순자본비율 ↔ 3종 영업용순자본비율,
    실측 t5s2-03 오판). 2-그램 겹침으로는 영영 못 가르는 쌍이라 문자열로 자른다."""
    a, b = a.replace(" ", ""), b.replace(" ", "")
    if len(a) < 2 or len(b) < 2 or a == b:
        return False
    return a.endswith(b) or b.endswith(a)


def compare_quants(nae: str, oe: str) -> list[dict]:
    """내규 본문 × 외규 본문 → 견줄 수 있는 쌍의 방향 판정 (순수 결정론).

    쌍의 조건: 같은 종류 · 같은 축, 그리고 **지표 겹침(2-그램 ≥2) 또는 결과창
    겹침(≥6)** — 산식으로 풀어 쓴 조문("…나눈 값이 100분의 150에 미달")은
    지표 낱말이 없어 결과 문구("미달상태가 해소될 때까지 … 중지")로 잇는다.
    지표가 접미 관계면(영업용순자본비율 ↔ 순자본비율) 어느 쪽으로도 쌍이
    아니다. 조건을 못 채우면 그 값들은 **판정에 안 쓴다** — 억지 쌍이 오판을
    만든다."""
    out, seen = [], set()
    for qn in quants(nae):
        if not qn["축"]:
            continue
        for qo in quants(oe):
            if qo["종류"] != qn["종류"] or qo["축"] != qn["축"]:
                continue
            if qn["종류"] != "기한" and _suffix_conflict(qn["지표"], qo["지표"]):
                continue
            front = len(_grams2(qn["지표"]) & _grams2(qo["지표"])) >= 2
            rear = len(_grams2(qn.get("결과") or "")
                       & _grams2(qo.get("결과") or "")) >= 6
            if not (front or rear):
                continue
            key = (qn["표기"], qo["표기"])
            if key in seen:                 # 같은 표기 쌍이 여러 번 — 한 번만
                continue
            seen.add(key)
            if qn["값"] == qo["값"]:
                direction = "동일"
            elif qn["축"] == "하한":
                direction = "완화" if qn["값"] < qo["값"] else "강화"
            else:
                direction = "완화" if qn["값"] > qo["값"] else "강화"
            out.append({"축": qn["축"], "종류": qn["종류"],
                        "내규": {"표기": qn["표기"], "지표": qn["지표"]},
                        "외규": {"표기": qo["표기"], "지표": qo["지표"]},
                        "방향": direction})
    return out


# ---------------------------------------------------------------- 짝 찾기
def _article_of(v, node_id):
    """마디를 소속 조로 승격 — 간선 목적지는 항·호까지 내려가 있다."""
    n = v.by_id.get(node_id)
    while n is not None:
        if _JO.fullmatch((n.get("surface") or "").replace(" ", "")):
            return n["id"]
        n = v.by_id.get(n.get("parent")) if n.get("parent") is not None else None
    return node_id


def _subtree(v, node_id) -> set:
    kids: dict = {}
    for n in v.nodes:
        if n.get("parent") is not None:
            kids.setdefault(n["parent"], []).append(n["id"])
    out, stack = {node_id}, [node_id]
    while stack:
        for c in kids.get(stack.pop(), []):
            if c not in out:
                out.add(c)
                stack.append(c)
    return out


def find_counterparts_legacy(idx_scoped: Index, idx_all: Index, llm,
                             doc_id: str, node: int,
                             cap: int = LEGACY_CAND_MAX) -> list[dict]:
    """롤백용 종전 후보기: 간선 → 프레임 → 벡터를 선착순으로 합류한다.

    간선이 맨 앞이다 — 문서 자신의 인용이 가장 강한 신호(§2-3 ①과 같은 원리).
    idx_scoped 는 외규만 보이는 색인(진입용), idx_all 은 내규 좌표 되짚기용."""
    v = idx_all.docs[doc_id]
    sub = _subtree(v, node)
    text = v.section_text(v.by_id[node], cap=800)
    seen, out = set(), []

    def push(did, jo, via, why=""):
        tv = idx_scoped.docs.get(did)
        if tv is None or not idx_scoped.in_scope(did):
            return
        jo = _article_of(tv, jo)
        if (did, jo) in seen or len(out) >= cap:
            return
        seen.add((did, jo))
        out.append({"doc_id": did, "doc": tv.name, "node": jo,
                    "path": tv.path(jo), "via": via, "why": why[:60]})

    for e in idx_all.cross_ref_edges():
        if e.get("src_doc") == doc_id and e.get("src") in sub:
            push(e["dst_doc"], e["dst"], "간선", e.get("surface") or "")

    if llm is not None:
        try:
            from lawrag.core.rag import framequery
            hits, _ = framequery.lex_hits(idx_scoped, llm,
                                          f"다음 규정이 따라야 할 기준은? {text[:280]}")
            for h in hits:
                push(h["doc_id"], h["node"], "프레임", h.get("why") or "")
        except Exception:                                  # pragma: no cover
            log.exception("프레임 짝 찾기 실패 — 벡터로 계속")

    try:
        from lawrag.core.rag import vector as vector_mod
        for did, jo, cos in vector_mod.search(text[:600], topk=10,
                                              doc_ids=idx_scoped.scope):
            push(did, jo, "벡터", f"코사인 {cos:.2f}")
    except Exception as exc:                               # pragma: no cover
        from lawrag.runtime.content_snapshot import ContentSnapshotError

        if isinstance(exc, ContentSnapshotError):
            raise
        log.exception("벡터 짝 찾기 실패 — 간선·프레임만으로 계속")
    return out


def _comparison_query(cite: str, text: str) -> str:
    """내규를 사실 쪽에 고정하고 적용 외규만 찾게 하는 LegalClosure 질의."""
    return (
        "다음 회사 내규 조문에 적용되는 법률·시행령·감독규정·시행세칙의 기준을 "
        "찾아라. 내규와 외규의 행위자, 대상, 의무·금지·허용, 조건·예외, 수치·기한, "
        "위임·준용 관계를 함께 확인하라.\n\n"
        f"[내규 좌표]\n{cite}\n\n[내규 원문]\n{text[:4000]}"
    )


def _direct_counterparts(idx_scoped: Index, idx_all: Index,
                         doc_id: str, node: int) -> list[dict]:
    """내규가 직접 인용한 외규 좌표 — 검색 결과와 무관하게 mandatory로 보존."""
    sub = _subtree(idx_all.docs[doc_id], node)
    out, seen = [], set()
    for edge in idx_all.cross_ref_edges():
        if edge.get("src_doc") != doc_id or edge.get("src") not in sub:
            continue
        did = edge.get("dst_doc")
        view = idx_all.docs.get(did)
        if view is None or view.scope_kind != "외규":
            continue
        jo = _article_of(view, edge.get("dst"))
        if (did, jo) in seen:
            continue
        seen.add((did, jo))
        out.append({
            "doc_id": did, "doc": view.name, "node": jo,
            "path": view.path(jo), "via": "간선",
            "why": str(edge.get("surface") or "")[:60],
            "origin": "direct-reference", "mandatory": True,
            "scope_out": not idx_scoped.in_scope(did),
            "legal_meta": {}, "ref_src": {
                "doc_id": doc_id, "node": node,
                "via": str(edge.get("rel") or edge.get("via") or "인용"),
            },
        })
    return out


def retrieve_counterparts(idx_scoped: Index, idx_all: Index, llm,
                          doc_id: str, node: int,
                          cap: int = CAND_MAX) -> tuple[list[dict], dict]:
    """내규 조 → 외규 후보: 직접 인용을 보존하고 LegalClosure MAIN 계약을 재사용.

    LegalClosure는 정확 구조·Assertion·균등 BM25·관계 폐쇄·reference rescue를
    실행하고 canonical 조문 Section과 legal_meta/reachability를 반환한다. 스코프 밖
    관계 동반은 허용하되 외규가 아닌 문서는 비교 후보에서 제거한다. 런타임 실패는
    직접 인용만 남긴 degraded 결과로 드러내며 조용히 `부합`시키지 않는다.
    """
    from lawrag.core.rag import article_reachability
    from lawrag.core.rag import legalclosure_runtime
    from lawrag.core.rag import switches as switches_mod

    view = idx_all.docs[doc_id]
    text = view.section_text(view.by_id[node], cap=4000)
    cite = f"{view.name} ▸ {view.path(node)}"
    direct = _direct_counterparts(idx_scoped, idx_all, doc_id, node)
    out, positions = [], {}

    def push(row: dict) -> None:
        did, raw_node = row.get("doc_id"), row.get("node")
        target = idx_all.docs.get(did)
        if target is None or target.scope_kind != "외규" or raw_node is None:
            return
        jo = _article_of(target, raw_node)
        key = (did, jo)
        existing_at = positions.get(key)
        normalized = {
            "doc_id": did, "doc": target.name, "node": jo,
            "path": target.path(jo),
            "via": str(row.get("via") or "LegalClosure"),
            "why": str(row.get("why") or row.get("origin") or "")[:120],
            "origin": str(row.get("origin") or "legalclosure"),
            "mandatory": bool(row.get("mandatory")),
            "scope_out": bool(row.get("scope_out", not idx_scoped.in_scope(did))),
            "legal_meta": dict(row.get("legal_meta") or {}),
            "ref_src": row.get("ref_src"),
        }
        if existing_at is not None:
            existing = out[existing_at]
            existing["mandatory"] = existing["mandatory"] or normalized["mandatory"]
            if normalized["legal_meta"]:
                existing["legal_meta"] = normalized["legal_meta"]
            if not existing.get("ref_src") and normalized.get("ref_src"):
                existing["ref_src"] = normalized["ref_src"]
            origins = existing.setdefault("origins", [existing["origin"]])
            if normalized["origin"] not in origins:
                origins.append(normalized["origin"])
            return
        if len(out) >= cap:
            return
        positions[key] = len(out)
        out.append(normalized)

    for row in direct:
        push(row)

    trace = article_reachability.ArticleReachabilityTrace(
        idx_scoped, f"compare:{doc_id}:{node}", "legalclosure-comparison-v2")
    try:
        from lawrag.runtime import registry as runtime_registry

        sections, lc_meta = runtime_registry.retrieve(
            idx_scoped, _comparison_query(cite, text), llm=llm,
            assertion_llm=llm, cap=cap,
            shortcut_enabled=switches_mod.is_on("legalclosure_proof_shortcut"),
            feedback_enabled=switches_mod.is_on("legalclosure_feedback_explore"),
            graph_enabled=switches_mod.is_on("legal_graph_v1_closure"),
            semantic_graph_enabled=switches_mod.is_on(
                "legal_semantic_entity_search"),
            reachability_trace=trace)
        selected_meta = {
            (row.get("doc_id"), row.get("node")): row
            for row in lc_meta.get("selected") or []
        }
        mandatory_coordinates = {
            (row.get("doc_id"), row.get("node"))
            for row in lc_meta.get("closure") or [] if row.get("mandatory")
        }
        for section in sections:
            selected = selected_meta.get((section.doc_id, section.node), {})
            push({
                "doc_id": section.doc_id, "node": section.node,
                "via": "LegalClosure",
                "why": selected.get("origin") or section.matched,
                "origin": selected.get("origin") or section.matched,
                "mandatory": ((section.doc_id, section.node)
                              in mandatory_coordinates),
                "scope_out": section.scope_out,
                "legal_meta": section.legal_meta,
                "ref_src": section.ref_src,
            })
        return out, {
            "retriever": "legalclosure-v2", "status": "ok",
            "query": _comparison_query(cite, text),
            "scope": idx_scoped.scope_name or "외규",
            "candidate_cap": cap, "direct_count": len(direct),
            "selected_count": len(out),
            "strategy": lc_meta.get("strategy"),
            "article_reachability": lc_meta.get("article_reachability"),
            "legal_annotations": lc_meta.get("legal_annotations") or {},
            "runtime": lc_meta.get("runtime") or {},
        }
    except Exception as exc:                                  # pragma: no cover
        log.exception("LegalClosure 비교 후보 회수 실패 — 직접 인용만 보존")
        return out, {
            "retriever": "legalclosure-v2", "status": "degraded",
            "query": _comparison_query(cite, text),
            "scope": idx_scoped.scope_name or "외규",
            "candidate_cap": cap, "direct_count": len(direct),
            "selected_count": len(out),
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "article_reachability": None, "legal_annotations": {},
        }


# ---------------------------------------------------------------- LLM 쌍 판정
JUDGE_SYSTEM = (
    "너는 회사 내규가 법령·감독규정(외규)에 맞는지 점검하는 심사역이다. 내규 조문 "
    "하나와 외규 후보 조문들이 주어진다. **후보마다** 판정하라:\n"
    "상충 — 내규가 외규 기준보다 완화됐거나, 외규가 금지·요구한 것과 어긋난다\n"
    "부합 — 외규 그대로이거나 더 보수적이다 (강화는 상충이 아니다)\n"
    "무관 — 이 외규는 내규 조문의 주제와 다르다\n"
    "불명 — 관련은 있으나 이 본문만으로 판정할 수 없다\n"
    "규칙: ① 근거는 **주어진 본문의 문구만** 쓴다 — 조문 밖 지식으로 채우지 마라. "
    "② 인용은 원문 표기 그대로(예: '100분의 150', '지체없이'). ③ 확신이 없으면 "
    "불명이다 — 틀린 상충 판정 하나가 판정 전부의 신뢰를 무너뜨린다."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"pairs": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"},
                       "판정": {"type": "string",
                              "enum": ["상충", "부합", "무관", "불명"]},
                       "근거": {"type": "string"},
                       "인용": {"type": "string"}},
        "required": ["n", "판정", "근거", "인용"],
        "additionalProperties": False}}},
    "required": ["pairs"], "additionalProperties": False,
}


def judge_pairs(llm, nae_cite: str, nae_text: str, cands: list[dict],
                texts: dict) -> list[dict]:
    if llm is None or not cands:
        return []
    lines = [f"[내규] {nae_cite}\n{nae_text[:SNIPPET]}"]
    for i, c in enumerate(cands, start=1):
        meta = json.dumps(c.get("legal_meta") or {}, ensure_ascii=False,
                          separators=(",", ":"))[:1200]
        lines.append(f"[후보 {i}] {c['doc']} ▸ {c['path']}\n"
                     f"[회수] origin={c.get('origin', '')}; "
                     f"mandatory={bool(c.get('mandatory'))}; "
                     f"scope_out={bool(c.get('scope_out'))}\n"
                     f"[근거 메타] {meta}\n"
                     f"{texts.get((c['doc_id'], c['node']), '')[:SNIPPET]}")
    out = llm.structured("rag.compare", JUDGE_SYSTEM, "\n\n".join(lines),
                         JUDGE_SCHEMA, max_tokens=2500, effort=None)
    if out is None:
        return []
    pairs = []
    for p in out.get("pairs", []):
        n = p.get("n")
        if isinstance(n, int) and 1 <= n <= len(cands):
            pairs.append({"n": n, **{k: str(p.get(k, ""))[:400]
                                     for k in ("판정", "근거", "인용")}})
    return pairs


# ---------------------------------------------------------------- 본체
def compare_article(llm, idx: Index, doc_id: str, node: int,
                    scope: str = "외규",
                    retrieval_mode: str = "legalclosure") -> dict:
    """내규 조 하나의 비교 리포트. verdict: 상충 | 부합 | 재검토."""
    from lawrag.core.rag import scopes as scopes_mod

    idx_scoped, _ = scopes_mod.apply(idx, scope, None)
    v = idx.docs[doc_id]
    node = _article_of(v, node)
    n = v.by_id[node]
    nae_text = v.section_text(n, cap=4000)
    nae_cite = f"{v.name} ▸ {v.path(node)}"

    if retrieval_mode == "legacy":
        cands = find_counterparts_legacy(idx_scoped, idx, llm, doc_id, node)
        retrieval_meta = {
            "retriever": "legacy-frame-vector", "status": "ok",
            "scope": idx_scoped.scope_name or scope,
            "candidate_cap": LEGACY_CAND_MAX,
            "selected_count": len(cands),
        }
    elif retrieval_mode == "legalclosure":
        cands, retrieval_meta = retrieve_counterparts(
            idx_scoped, idx, llm, doc_id, node)
    else:
        raise ValueError(f"모르는 비교 후보기입니다: {retrieval_mode}")
    texts = {}
    for c in cands:
        tv = idx.docs[c["doc_id"]]
        texts[(c["doc_id"], c["node"])] = tv.section_text(tv.by_id[c["node"]],
                                                          cap=4000)

    # ② 판정 — 결정론 먼저, LLM 은 결정론이 침묵한 쌍만 뒤집을 수 있다
    quant_rows, quant_verdicts = [], {}
    for i, c in enumerate(cands, start=1):
        rows = compare_quants(nae_text, texts[(c["doc_id"], c["node"])])
        for r in rows:
            r["n"] = i
        quant_rows += rows
        if any(r["방향"] == "완화" for r in rows):
            quant_verdicts[i] = "상충"
        elif rows:
            quant_verdicts[i] = "부합"

    from lawrag.core.rag import switches as switches_mod

    if switches_mod.is_on("internal_compliance_compiler_v1"):
        from lawrag.core.rag import internal_compliance

        internal_id = internal_compliance.internal_evidence_id(doc_id, node)
        compiler_rows = []
        compiler_texts = {}
        candidate_number: dict[str, int] = {}
        for i, c in enumerate(cands, start=1):
            evidence_id = internal_compliance.external_evidence_id(
                str(c["doc_id"]), int(c["node"]))
            compiler_rows.append({**c, "evidence_id": evidence_id})
            compiler_texts[evidence_id] = texts[(c["doc_id"], c["node"])]
            candidate_number[evidence_id] = i
        compiler_question = (
            f"{nae_cite} 내규가 적용 외규에 부합하며 필수 통제를 빠짐없이 반영했는가?"
        )
        compilation = internal_compliance.compile_compliance(
            llm,
            question=compiler_question,
            internal_id=internal_id,
            internal_text=nae_text,
            external_rows=compiler_rows,
            external_texts=compiler_texts,
            retrieval_status=str(retrieval_meta.get("status") or "degraded"),
            deterministic_rows=quant_rows,
        )
        packet = compilation["packet"]
        requirements = {
            row["requirement_id"]: row for row in packet["requirements"]
        }
        status_to_pair = {
            "SATISFIED": "부합", "STRICTER": "부합", "CONFLICT": "상충",
            "MISSING": "불명", "UNRESOLVED": "불명",
        }
        pairs = []
        for binding in packet["bindings"]:
            requirement = requirements.get(binding["requirement_id"])
            n_value = candidate_number.get(
                str((requirement or {}).get("evidence_id") or ""))
            if n_value is None:
                continue
            pairs.append({
                "n": n_value,
                "판정": status_to_pair[binding["status"]],
                "근거": binding["reason"],
                "인용": str((requirement or {}).get("quote") or ""),
                "requirement_id": binding["requirement_id"],
                "binding_status": binding["status"],
            })
        assessment = dict(compilation["assessment"])
        deterministic_conflicts = sorted(
            i for i, value in quant_verdicts.items() if value == "상충")
        if deterministic_conflicts:
            assessment.update({
                "verdict": "상충", "status": "CONFLICT_DETERMINISTIC",
                "coverage_closed": False,
                "deterministic_conflict_candidates": deterministic_conflicts,
            })
        verdict = assessment["verdict"]
        return {
            "verdict": verdict,
            "내규": {"doc": v.name, "doc_id": doc_id, "node": node,
                    "path": v.path(node), "evidence_id": internal_id},
            "후보": compiler_rows, "값비교": quant_rows, "판정": pairs,
            "짝없음": not cands,
            "검색": retrieval_meta,
            "컴파일": compilation,
            "완전성": {
                "판정범위": "회수된 외규 원자요건과 내규 통제의 양방향 비교",
                "미해결후보": assessment["unresolved_requirement_ids"],
                "미비요건": assessment["missing_requirement_ids"],
                "상충요건": assessment["conflict_requirement_ids"],
                "coverage_closed": assessment["coverage_closed"],
                "미비점검": "구현 — 외규 requirement에서 내규 claim으로 역방향 결속",
            },
        }

    pairs = judge_pairs(llm, nae_cite, nae_text, cands, texts)
    for p in pairs:
        if p["n"] in quant_verdicts:
            det = quant_verdicts[p["n"]]
            if p["판정"] in ("상충", "부합") and p["판정"] != det:
                p["결정론우선"] = det       # 기록하고 결정론을 따른다
                p["판정"] = det

    effective = {p["n"]: p["판정"] for p in pairs}
    effective.update({i: v_ for i, v_ in quant_verdicts.items()
                      if i not in effective or effective[i] in ("무관", "불명")})
    unresolved = [i for i in range(1, len(cands) + 1)
                  if effective.get(i) in (None, "불명")]
    relevant = [i for i, value in effective.items() if value != "무관"]
    degraded = retrieval_meta.get("status") != "ok"
    verdict = ("상충" if any(x == "상충" for x in effective.values())
               else "재검토" if degraded or unresolved
               else "부합" if relevant and all(
                   effective.get(i) == "부합" for i in relevant)
               else "재검토")
    return {"verdict": verdict,
            "내규": {"doc": v.name, "doc_id": doc_id, "node": node,
                    "path": v.path(node)},
            "후보": cands, "값비교": quant_rows, "판정": pairs,
            "짝없음": not cands,
            "검색": retrieval_meta,
            "완전성": {
                "판정범위": "회수된 외규 후보에 대한 내규 조문 단위 비교",
                "미해결후보": unresolved,
                "coverage_closed": False,
                "미비점검": "미구현 — 외규 요구사항에서 내규로 향하는 역방향 점검 필요",
            }}
