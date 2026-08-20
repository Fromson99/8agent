"""프레임 질의 — 구어를 "누가·무엇을·누구에게·한다 + 문형·기능" 슬롯으로 옮겨 조문
프레임(frames.py)과 대조한다. 온톨로지 질의의 축소판.

왜 슬롯인가. 조문 프레임의 필드는 성격이 둘로 갈린다:
    닫힌 것   mode(의무·금지·허용·절차·위임·간주·정의) · function(근거·권한·제한·
             절차·위임·정의·효과) — enum 이라 LLM 이 고르기 쉽고 **정확 필터**가
             된다. 실측 18-0124: 국세기본법 제81조의13(금지·제한)과 제84조(허용·
             근거·권한)는 같은 "정보" 주제라 벡터 하나로는 안 갈렸다 — 기능이
             가른다.
    열린 것   actor·act·target·object — 표면형이라 어휘 격차(국세청↔세무공무원,
             받아가다↔협조 요청)가 그대로 있다. 슬롯화는 그 격차를 없애는 게
             아니라 **필드 단위로 가둔다** — 문장 전체가 아니라 그 칸끼리 잰다.

규율 (oql.py 에서 빌림): 슬롯은 선언된 것만, 값은 바인딩(치환 아님), 결과 상한.
LLM 은 슬롯을 채울 뿐 대조는 결정론이다.

임베딩 판(FrameIndex)은 실험 채널로 남아 있다 — 전 코퍼스 프레임 15만 텍스트를
CPU 로 임베딩하는 비용(실측 2026-08-20: 2건/초)이 커서, 배선된 것은 **렉시컬
판**(lex_hits)이다: LLM 이 슬롯을 채우면 3-그램 포함도로 행위 어휘와 맞춘다.
임베딩이 아니라 포함도인 이유 — 질의 act("성과보수를 지급")는 조문 act("조사분석
자료 작성을 담당하는 자에 대하여 … 성과보수를 지급하는 행위")의 **부분**이라,
대칭 유사도가 아니라 "질의가 행 안에 얼마나 담기나"를 재야 한다. 실측(2026-08-20
골든 미스): t3-07·t3-06 모두 자본시장법 제71조가 1위로 회복됐다 — 벡터 채널은
'성과보수' 겹침으로 제98조의2(투자일임)에 끌리던 질문들이다. vecfirst 의 진입
채널(스위치 frame_entry)로 배선.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

def _np():
    """numpy 지연 로드 — 무거운 의존은 모듈 수준 금지(tests/architecture).
    np 를 쓰는 메서드가 첫 줄에서 `np = _np()` 로 받는다 — 전역 주입이 아니라
    지역 바인딩이라, 테스트가 __new__ 로 __init__ 을 우회해도 성립한다."""
    import numpy
    return numpy

from lawrag.core.rag import frames as frames_mod
from lawrag.core.rag.index import Index

log = logging.getLogger("lawrag.core.rag.framequery")

MODES = ["의무", "금지", "허용", "절차", "위임", "간주", "정의", "기타"]
FUNCS = ["근거·권한", "제한", "절차", "위임", "정의", "효과", "기타"]

QUERY_SYSTEM = (
    "너는 법령 질문을 **프레임 질의**로 옮기는 번역기다. 질문에서 '누가(actor) → "
    "무엇을(object) → 누구에게(target) → 한다(act)'를 뽑고, 묻는 규범의 문형(mode)"
    "과 기능(function)을 고른다.\n"
    "규칙: ① actor·act·target·object 는 **법령 조문이 쓸 법한 낱말**로 옮긴다 — "
    "'국세청'이면 조문은 '세무공무원'이나 '국세청장'이라 쓴다, '받아가다'는 '요청'"
    "·'제공받다'·'제출받다', '넘겨주다'는 '제공'. 확신이 없으면 질문의 낱말을 그대로 "
    "둔다(지어내지 마라). ② mode 는 질문이 묻는 규범의 문형 — '할 수 있나요'는 허용, "
    "'해야 하나요'는 의무, '하면 안 되나요'는 금지, '무엇인가요'는 정의, 모르면 "
    "기타. ③ function 은 그 규범이 하는 일 — 행위의 근거·권한을 묻는가, 제한을 "
    "묻는가, 절차를 묻는가, 위임을 묻는가, 뜻을 묻는가, 효과를 묻는가. 모르면 기타. "
    "④ 없는 칸은 빈 문자열. ⑤ 질문 하나에 프레임은 1~2개 — 두 법이 걸리면 둘. "
    "⑥ alts 에는 act 를 **조문이 쓸 법한 다른 표현**으로 1~3개 더 적는다 — "
    "'성과급을 주다'면 '성과보수를 지급', '보고서를 내다'면 '조사분석자료를 공표'처럼 "
    "법령 술어로. 떠오르지 않으면 빈 배열."
)
QUERY_SCHEMA = {
    "type": "object",
    "properties": {"frames": {"type": "array", "items": {
        "type": "object",
        "properties": {"actor": {"type": "string"}, "act": {"type": "string"},
                       "alts": {"type": "array", "items": {"type": "string"}},
                       "target": {"type": "string"}, "object": {"type": "string"},
                       "mode": {"type": "string", "enum": MODES},
                       "function": {"type": "string", "enum": FUNCS}},
        "required": ["actor", "act", "alts", "target", "object", "mode", "function"],
        "additionalProperties": False}}},
    "required": ["frames"], "additionalProperties": False,
}


MENU_RULE = (
    "\n⑥ [행위 어휘 메뉴]가 주어지면 picks 에 **번호를 1~3개** 넣는다 — 질문이 "
    "묻는 행위일 가능성이 있는 항목을, 확실한 것부터. 맞는 것이 없으면 빈 배열. "
    "각 항목은 「문서 ▸ 조」 좌표와 그 조의 술어다 — 술어 낱말이 질문과 달라도 "
    "**그 조가 질문의 상황을 다루면** 고른다('IB'는 '기업금융업무', '애널리스트'는 "
    "'조사분석자료 작성을 담당하는 자', '리서치 보고서'는 '조사분석자료'다)."
)
MENU_SCHEMA = {
    "type": "object",
    "properties": {"frames": {"type": "array", "items": {
        "type": "object",
        "properties": {"actor": {"type": "string"},
                       # 번호로 답한다 — 술어를 되베끼게 하면 라벨까지 딸려 온다.
                       # maxItems 는 구조화 출력이 안 받는다(실측 400) — 코드가 자른다
                       "picks": {"type": "array", "items": {"type": "integer"}},
                       "target": {"type": "string"}, "object": {"type": "string"},
                       "mode": {"type": "string", "enum": MODES},
                       "function": {"type": "string", "enum": FUNCS}},
        "required": ["actor", "picks", "target", "object", "mode", "function"],
        "additionalProperties": False}}},
    "required": ["frames"], "additionalProperties": False,
}


def to_frames(llm, question: str, menu: Optional[list[str]] = None) -> list[dict]:
    """구어 → 프레임 질의 목록. 실패면 빈 목록(호출부가 다른 채널로 간다).

    menu 를 주면 **닫힌 선택**이다(frames.py 머리의 설계 의도): act 를 지어내지
    않고 코퍼스에서 뽑아 둔 행위 어휘 중에서 고른다. 실측(2026-08-20): 열린
    생성은 '성과급'·'지급' 같은 구어·한 낱말을 내서 조문 어휘와 안 만났다."""
    user = f"[질문]\n{question}"
    if menu:
        user += "\n\n[행위 어휘 메뉴]\n" + "\n".join(
            f"{i}. {m}" for i, m in enumerate(menu, start=1))
        # 고르기가 이 채널의 승부처다 — 열린 슬롯(low)과 달리 기본 노력으로 간다.
        out = llm.structured("rag.framequery", QUERY_SYSTEM + MENU_RULE, user,
                             MENU_SCHEMA, max_tokens=600, effort=None)
    else:
        out = llm.structured("rag.framequery", QUERY_SYSTEM, user,
                             QUERY_SCHEMA, max_tokens=500, effort="low")
    if out is None:
        return []
    frames = []
    for f in out.get("frames", [])[:2]:
        if "picks" in f:
            f = {**f, "picks": [n for n in f.get("picks") or []
                                if isinstance(n, int) and 1 <= n <= len(menu or [])][:3],
                 "act": ""}          # 좌표는 picks 가 정한다 — act 는 표시용
        if f.get("picks") or any((f.get(k) or "").strip()
                                 for k in ("actor", "act", "target", "object")):
            frames.append(f)
    return frames


# ---------------------------------------------------------------- 색인
class FrameIndex:
    """파일럿용 메모리 색인 — 프레임의 열린 필드를 **칸별로** 임베딩해 둔다.
    문장 하나로 접은 임베딩(sent)도 같이 두어 두 방식을 비교한다."""

    FIELDS = ("actor", "act", "target", "object")

    def __init__(self, index: Index, doc_ids: Optional[set] = None,
                 cache: Optional[str] = None):
        """cache 를 주면 그 npz 에 임베딩을 저장·재사용한다 — CPU 임베딩은 프레임
        4천 개 × 5필드에 분 단위라, 실험이 매번 다시 재면 안 된다. 프레임 파일이
        바뀌면(행 수·내용 해시) 다시 잰다."""
        np = _np()
        import hashlib
        from lawrag.core import embedding
        self.rows: list[dict] = []
        for did, v in index.entry_docs.items():
            if doc_ids and did not in doc_ids:
                continue
            for r in frames_mod.load(did):
                if not (r.get("actor") or r.get("act")):
                    continue
                self.rows.append({**r, "doc_id": did})
        n = len(self.rows)
        # 한 배치로 — 필드 4 + 문장 1 을 이어 붙여 encode 한 번
        texts: list[str] = []
        for k in self.FIELDS:
            texts += [((r.get(k) or "").strip() or "·") for r in self.rows]
        texts += [sentence(r) for r in self.rows]
        sig = hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()[:16]
        emb = None
        if cache:
            try:
                z = np.load(cache, allow_pickle=False)
                if str(z["sig"]) == sig:
                    emb = z["emb"]
            except Exception:
                emb = None
        if emb is None:
            emb = np.asarray(embedding.encode(texts), dtype=np.float32)
            emb /= (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
            if cache:
                np.savez_compressed(cache, emb=emb, sig=np.array(sig))
        self.field_vec = {}
        self.field_has = {}
        for i, k in enumerate(self.FIELDS):
            self.field_vec[k] = emb[i * n:(i + 1) * n]
            self.field_has[k] = np.array([bool((r.get(k) or "").strip()) for r in self.rows])
        self.sent_vec = emb[4 * n:5 * n]
        self.mode = np.array([r.get("mode") or "" for r in self.rows])
        self.func = np.array([r.get("function") or "" for r in self.rows])

    def _q(self, text: str) -> np.ndarray:
        np = _np()
        from lawrag.core import embedding
        q = np.asarray(embedding.encode_one(text), dtype=np.float32)
        return q / (np.linalg.norm(q) + 1e-9)

    def match(self, qf: dict, topk: int = 40, enum_boost: float = 0.08,
              weights: Optional[dict] = None) -> list[tuple[int, float]]:
        """프레임 질의 하나 → [(row idx, score)]. 열린 칸은 칸별 코사인의 가중 평균
        (질의에 있는 칸만), 닫힌 칸(mode·function)은 일치하면 가산·불일치면 감산.
        기타는 무조건(필터 안 함)."""
        np = _np()
        w = weights or {"actor": 1.0, "act": 1.4, "target": 0.8, "object": 1.0}
        score = np.zeros(len(self.rows), dtype=np.float32)
        wsum = 0.0
        for k in self.FIELDS:
            val = (qf.get(k) or "").strip()
            if not val or self.field_vec.get(k) is None:
                continue
            sims = self.field_vec[k] @ self._q(val)
            sims = np.where(self.field_has[k], sims, 0.0)   # 그 칸이 빈 프레임은 0
            score += w[k] * sims
            wsum += w[k]
        if wsum == 0:
            return []
        score /= wsum
        for val, arr in ((qf.get("mode"), self.mode), (qf.get("function"), self.func)):
            if val and val != "기타":
                score += np.where(arr == val, enum_boost, -enum_boost / 2)
        order = np.argsort(-score)[:topk]
        return [(int(i), float(score[i])) for i in order]

    def match_sentence(self, text: str, topk: int = 40) -> list[tuple[int, float]]:
        np = _np()
        sims = self.sent_vec @ self._q(text)
        order = np.argsort(-sims)[:topk]
        return [(int(i), float(sims[i])) for i in order]


# ---------------------------------------------------------------- 렉시컬 매칭
# 임베딩 없이 — 3-그램 포함도(질의 칸이 행 칸 안에 얼마나 담기나) + 닫힌 칸 가감.

_LEX_W = {"act": 0.55, "object": 0.2, "actor": 0.15, "target": 0.1}
_LEX_FLOOR = 0.5          # 이 아래는 버린다 — 실측에서 잡음은 0.47 아래였다
_ENUM_BOOST = 0.06


def _grams(s: str, n: int = 3) -> frozenset:
    t = re.sub(r"\s+", "", s or "")
    if len(t) < n:
        return frozenset({t}) if t else frozenset()
    return frozenset(t[i:i + n] for i in range(len(t) - n + 1))


def _contain(qg: frozenset, rg: frozenset) -> float:
    return len(qg & rg) / len(qg) if qg else 0.0


_lex_cache: dict = {"sig": None, "rows": None}


def _lex_rows(index: Index) -> list[dict]:
    """스코프 안 문서의 프레임 행 + 칸별 3-그램 집합. 서명 = (doc_id, 파일 mtime)
    집합 — 프레임을 다시 뽑거나 스코프가 바뀌면 다시 만든다."""
    d = frames_mod.frames_dir()
    sig = frozenset((did, (d / f"{did}.jsonl").stat().st_mtime_ns)
                    for did in index.entry_docs
                    if (d / f"{did}.jsonl").is_file())
    if _lex_cache["sig"] == sig:
        return _lex_cache["rows"]
    rows = []
    for did, v in index.entry_docs.items():
        for r in frames_mod.load(did):
            if not (r.get("actor") or r.get("act")):
                continue
            rows.append({**r, "doc_id": did, "doc": v.name,
                         "_g": {k: _grams(r.get(k)) for k in _LEX_W}})
    _lex_cache.update(sig=sig, rows=rows)
    return rows


def score_rows(qf: dict, rows: list[dict]) -> list[tuple[float, dict]]:
    """프레임 질의 하나 × 행 전부 — 순수 함수. 열린 칸은 포함도 가중 평균(질의에
    있는 칸만), 닫힌 칸(mode·function)은 일치 가산·불일치 감산, 기타는 중립."""
    qg = {k: _grams(qf.get(k)) for k in _LEX_W}
    active = [(k, w) for k, w in _LEX_W.items() if qg[k]]
    if not active:
        return []
    wsum = sum(w for _, w in active)
    out = []
    for r in rows:
        sc = sum(w * _contain(qg[k], r["_g"][k]) for k, w in active) / wsum
        for k in ("mode", "function"):
            qv = qf.get(k)
            if qv and qv != "기타":
                sc += _ENUM_BOOST if r.get(k) == qv else -_ENUM_BOOST / 2
        if sc >= _LEX_FLOOR:
            out.append((sc, r))
    out.sort(key=lambda x: (-x[0], x[1].get("doc_id") or "", x[1].get("jo") or 0))
    return out


MENU_CAP = 60             # 메뉴에 올릴 행위 어휘 수 상한
MENU_ROWS_MAX = 8         # 이보다 여러 행에 나오는 행위는 좌표가 아니라 상투구다


def _grams2(s: str) -> frozenset:
    t = re.sub(r"[\s·ㆍ,.'\"()]+", "", s or "")
    return frozenset(t[i:i + 2] for i in range(len(t) - 1)) if len(t) >= 2 else frozenset()


def act_menu(question: str, rows: list[dict], cap: int = MENU_CAP,
             index: Optional[Index] = None) -> list[tuple[str, list[dict]]]:
    """질문과 2-그램이 겹치는 행위 어휘 후보 — LLM 이 번호로 고를 닫힌 메뉴.

    반환 [(표시줄, 그 행위의 행들)]. 표시줄에 「문서 ▸ 조 제목」 좌표를 붙인다 —
    술어 낱말만으로는 같은 '성과보수 지급'이 보수체계 조인지 불건전영업행위 조인지
    모델이 가를 수 없다(실측 2026-08-20: 라벨 없이 두 번 다 오답 픽).

    3-그램이 아니라 2-그램인 이유: 구어와 조문은 낱말이 달라도("성과급" ↔
    "성과보수를 지급") 형태소 조각("성과"·"지급")은 겹친다. 상투구(정한다·
    준용한다·제출하여야 한다 — 수백 행)는 골라도 좌표가 수백 개라 메뉴에서
    뺀다(MENU_ROWS_MAX)."""
    qg = _grams2(question)
    if not qg:
        return []
    by_act: dict[str, list[dict]] = {}
    for r in rows:
        a = (r.get("act") or "").strip()
        if a:
            by_act.setdefault(a, []).append(r)
    scored = []
    for a, rs in by_act.items():
        if len(rs) > MENU_ROWS_MAX:
            continue
        ag = _grams2(a)
        hit = len(qg & ag)
        if hit >= 2:
            scored.append((hit / (len(ag) ** 0.5), a, rs))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for _, a, rs in scored[:cap]:
        r0 = rs[0]
        label = r0.get("doc") or ""
        if index is not None:
            v = index.docs.get(r0["doc_id"])
            n = v.by_id.get(r0["jo"]) if v else None
            if v is not None and n is not None:
                t = (n.get("title") or "").strip()
                label = (f"{v.name} ▸ {(n.get('surface') or '').strip()}"
                         + (f" {t}" if t else ""))
        line = f"[{label[:52]}] {a}" if label else a
        out.append((line, rs))
    return out


def lex_hits(index: Index, llm, question: str, per_frame: int = 2,
             cap: int = 3) -> tuple[list[dict], dict]:
    """질문 → 행위 어휘 메뉴 → 프레임 슬롯(LLM 1콜, 닫힌 선택) → 조 좌표.

    act 가 메뉴에서 그대로 골라졌으면 그 act 의 행이 곧 좌표다(결정론) —
    actor·object 포함도와 문형 인접도는 그 행들 사이의 순위만 정한다. 메뉴
    밖 act(모델이 빈칸을 못 참은 경우)는 포함도 채점(score_rows)으로 넘긴다.
    좌표는 **조 단위**로 접는다(같은 조의 여러 행은 최고점만).
    실패·빈손은 ([], 관측) — 호출부(vecfirst)는 다른 채널로 그냥 간다."""
    meta: dict = {"frames": [], "hits": [], "menu": 0}
    if llm is None:
        return [], meta
    rows = _lex_rows(index)
    # 1콜 — 열린 슬롯. 구어를 조각("성과급"→'지급')으로라도 벌려 놓아야 메뉴가
    # 잡힌다: 질문만으로는 "성과급"과 "성과보수를 지급"이 2-그램 하나('성과')
    # 밖에 안 겹쳐 메뉴 게이트(≥2)를 못 넘는다(실측 2026-08-20 t3-07).
    open_frames = to_frames(llm, question)
    slot_text = " ".join(
        [(f.get(k) or "") for f in open_frames
         for k in ("actor", "act", "target", "object")]
        + [a for f in open_frames for a in (f.get("alts") or [])[:3]])
    menu = act_menu(question + " " + slot_text, rows, index=index)
    meta["menu"] = len(menu)
    if not menu:
        return [], meta                  # 겹치는 어휘가 없으면 이 채널의 일이 아니다
    # 2콜 — 닫힌 선택. 실제 조문 술어 중에서 번호로 고른다.
    qframes = to_frames(llm, question, menu=[line for line, _ in menu])
    meta["frames"] = qframes
    best: dict[tuple, dict] = {}

    def offer(sc, r, qf, exact):
        key = (r["doc_id"], r["jo"])
        cur = best.get(key)
        if cur is None or sc > cur["score"]:
            tag = "메뉴" if exact else "포함도"
            best[key] = {"doc_id": r["doc_id"], "node": r["jo"],
                         "score": round(sc, 3), "act": r.get("act") or "",
                         "why": f"행위({tag}) '{(r.get('act') or '')[:44]}'"}

    for qf in qframes:
        for ai, num in enumerate((qf.get("picks") or [])[:3]):
            for r in menu[num - 1][1]:
                sc = 1.0 - 0.05 * ai            # 확실한 것부터 — 순서가 순위다
                for k, w in (("actor", 0.1), ("object", 0.1)):
                    qv = _grams(qf.get(k))
                    if qv:
                        sc += w * _contain(qv, r["_g"][k])
                for k in ("mode", "function"):
                    qv, rv = qf.get(k), r.get(k)
                    if qv and qv != "기타" and rv:
                        if rv == qv:
                            sc += _ENUM_BOOST
                        elif {qv, rv} == {"허용", "금지"}:
                            sc += _ENUM_BOOST / 2   # 가부는 같은 축 — 묻는 건 허용, 정하는 건 금지
                offer(sc, r, qf, exact=True)
        act = (qf.get("act") or "").strip()
        if not qf.get("picks") and act:
            for sc, r in score_rows(qf, rows)[:per_frame * 4]:
                offer(sc, r, qf, exact=False)
    hits = sorted(best.values(), key=lambda h: -h["score"])[:cap]
    meta["hits"] = [{k: h[k] for k in ("doc_id", "node", "score")} for h in hits]
    return hits, meta


def sentence(r: dict) -> str:
    parts = []
    if r.get("actor"):
        parts.append(r["actor"] + "은")
    if r.get("target"):
        parts.append(r["target"] + "에게")
    if r.get("object"):
        parts.append(r["object"] + "을")
    parts.append(r.get("act") or "")
    return " ".join(p for p in parts if p).strip()
