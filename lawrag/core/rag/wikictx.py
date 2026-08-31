"""위키 맥락 — 답 합성에 "어떻게 읽는가"를 끼워 넣는다.

조문 컨텍스트(회수 구역)는 "무엇이라 쓰였나"까지만 안다. 해석의 방향 —
문턱이 좁은지, 준용이 어디까지 따라가는지 — 은 법령해석 지식 베이스
(data/wiki, llm-wiki 형태)가 갖고 있다. 이 모듈은 질의마다 그 위키에서
맞는 아티클을 골라 답 합성 프롬프트의 배경 블록으로 준다.

고르기는 **코드 결정론**이다 (llm-wiki 의 index 라우팅을 축약):
- 회수된 구역의 문서명이 아티클 본문에 등장하면 강한 신호 (가중 2)
- 질의의 낱말(2자 이상)이 아티클 제목·요약에 등장하면 약한 신호 (가중 1)
LLM 라우팅 콜을 더 얹지 않는 이유: 답변 지연에 라우팅 비용이 얹힌다 —
같은 이유로 판정을 답변 콜에서 뺐다(answer.py 머리). 신호가 없으면 빈손
그대로 간다 — 억지로 채우지 않는다.

위키는 배경일 뿐 근거가 아니다 — 인용(refs)은 여전히 조문 컨텍스트 번호만
쓴다는 규칙이 답 합성 시스템 프롬프트에 있다(answer.ANSWER_SYSTEM ⑥).
켜고 끄기는 사용자 몫 — 엔진 스위치 wiki_context (switches.py).

쟁점 분해(spot)는 다른 시점에 선다 — **검색 전**이다. 쟁점/ 갈래의 카드는
머리에 `> 트리거:`(질문을 깨우는 낱말) · `> 판단 축:` · `> 조문 후보:` 를
달고 있고, spot 은 질의를 트리거에 비춰 카드를 고른다. 고른 카드의 조문
후보를 질의 뒤에 덧붙이면(expand_query) 검색 사다리 ①(색인값 ⊂ 질의)이
그 법령명을 문다 — 질문이 법령명을 몰라도 쟁점이 조문을 데려온다.
같은 코드 결정론이다: 트리거 무매칭이면 빈손, LLM 콜 없음. 스위치는
issue_spot. pick 은 쟁점 카드를 건너뛴다 — 쟁점기는 검색 전, 해석기는
합성 안이 제자리다 (spot 이 고른 카드는 합성 배경에도 같이 끼워 준다 —
answer.synthesize 의 spots 인자).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from lawrag.core.rag.controls import value as control_value

ROOT = Path(__file__).resolve().parents[3]

ARTICLE_MAX_CHARS = int(control_value("wiki.article_chars"))
PICK_LIMIT = int(control_value("wiki.articles_max"))
ISSUE_DIR = "쟁점"           # 쟁점기 갈래 — spot 만 읽고 pick 은 건너뛴다
SPOT_LIMIT = int(control_value("wiki.issue_cards_max"))
# 판정 콜 출력 예산 — 카드마다 slug+why(120자)+조문질의가 실리므로 300 은 애초에
# 모자랐다(실측 2026-08-20: 하루 62콜 중 16콜 잘림, fail-open 이라 쟁점 확장 없이
# 진행돼 실행 간 변동의 원인이 됐다). 잘리면 3배로 1회만 재시도한다(frames 와 동형).
SPOT_MAX_TOKENS = int(os.environ.get("RAG_SPOT_MAX_TOKENS", "1000"))
PROBE_MAX_CHARS = 300        # 조문질의 한 장의 상한 — 질의문이지 조문 원문이 아니다

# index.md 표 행: | [제목](주제/파일.md) | 요약 | 날짜 |  (lawrag/api/routers/expc.py 와 같은 규약)
_ROW_RE = re.compile(
    r"^\|\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+\.md)\)\s*\|"
    r"\s*(?P<summary>[^|]*)\|", re.M)
_WORD_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_WORD_SUFFIXES = ("으로부터", "에게서", "에서는", "으로", "에서", "에게",
                  "까지", "부터", "처럼", "보다", "과", "와", "의", "을",
                  "를", "이", "가", "은", "는", "에", "로")
_PROVENANCE_RE = re.compile(
    r"^>\s*(?:Sources|Raw|Updated)\s*:\s*.*(?:\n|$)", re.M | re.I)
# 카드 머리의 기계 가독 메타 — `> 트리거: a · b` 꼴 (가운뎃점 구분).
# `신호`는 방법 갈래의 라우팅 키다 — 질의 낱말이 아니라 **회수 결과의 성격**
# (동반 kind: 정의·제재·위임·준용·배제·수임, 본문의 단서)이 깨운다.
_META_RE = re.compile(r"^>\s*(?P<key>트리거|판단 축|조문 후보|신호):\s*(?P<val>.+)$", re.M)

_cache: dict = {"key": None, "rows": []}       # key = (경로, mtime)


def wiki_dir() -> Path:
    return Path(os.environ.get("WIKI_STORE") or ROOT / "data" / "wiki") / "wiki"


def _pack(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _question_words(question: str) -> set[str]:
    """제목·요약 대조용 어절 — 조사만 접고 의미어 자체는 만들지 않는다."""
    out = set()
    for raw in _WORD_RE.findall(question):
        word = raw
        for suffix in _WORD_SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                word = word[:-len(suffix)]
                break
        out.add(word)
    return out


def prompt_text(text: str) -> str:
    """저장·감사용 provenance를 보존한 채 모델에 줄 본문에서만 제거한다."""
    cleaned = _PROVENANCE_RE.sub("", str(text or ""))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _prompt_slice(text: str) -> str:
    value = prompt_text(text)
    if len(value) > ARTICLE_MAX_CHARS:
        value = value[:ARTICLE_MAX_CHARS] + "\n…(잘림 — 전문은 위키)"
    return value


def _rows() -> list[dict]:
    """index.md 의 아티클 행 + 본문 — index mtime 이 같으면 다시 읽지 않는다.

    본문도 여기서 같이 읽는다(전체 수십 KB 수준). 아티클만 고쳐지고 index 가
    안 바뀌는 편집은 다음 index 갱신 때 따라온다 — 컴파일 절차가 index 의
    Updated 갱신을 의무로 두므로(docs/expc.md §위키) 실제로는 함께 움직인다.
    """
    idx = wiki_dir() / "index.md"
    if not idx.is_file():
        return []
    key = (str(idx), idx.stat().st_mtime)
    if _cache["key"] == key:
        return _cache["rows"]
    rows = []
    for m in _ROW_RE.finditer(idx.read_text("utf-8")):
        title = m.group("title").strip()
        if title == "Article":                    # 표 머리행
            continue
        p = wiki_dir() / m.group("file")
        if not p.is_file():
            continue
        text = p.read_text("utf-8")
        rows.append({"slug": m.group("file").removesuffix(".md"),
                     "title": title, "summary": m.group("summary").strip(),
                     "text": text,
                     # provenance에 우연히 등장한 법령·기관명은 라우팅 강신호가
                     # 아니다. 모델 입력과 같은 정제 본문으로 문서명도 대조한다.
                     "packed": _pack(prompt_text(text)),
                     "head": title + " " + m.group("summary")})
    _cache["key"], _cache["rows"] = key, rows
    return rows


def pick(question: str, doc_names: set[str],
         limit: int = PICK_LIMIT) -> list[dict]:
    """질의·회수 문서명에 맞는 아티클 — [{slug, title, text, why}] 점수순.

    점수 0 은 안 낸다 — 위키가 모르는 주제에 배경을 끼워 넣지 않는다.
    """
    scored = []
    words = _question_words(question)
    for row in _rows():
        if row["slug"].startswith(ISSUE_DIR + "/"):
            continue                     # 쟁점 카드는 spot 의 몫 — 이중 경쟁 금지
        why = []
        score = 0
        for dn in sorted(doc_names):
            if dn and _pack(dn) in row["packed"]:
                score += 2
                why.append(dn)
        hit_words = sorted(w for w in words if w in row["head"])
        # 질문 낱말 하나만 맞는 Wiki는 ``업무``·``합산`` 같은 우연 일치가 너무
        # 쉽다. 회수 문서명은 강신호로 유지하고, 문서명이 없으면 서로 다른 두
        # 낱말이 제목·요약에서 함께 확인될 때만 일반 아티클을 연다.
        lexical_ok = len(hit_words) >= 2
        score += len(hit_words) if lexical_ok else 0
        if lexical_ok:
            why.extend(hit_words)
        if score > 0:
            scored.append((score, row, why))
    scored.sort(key=lambda t: -t[0])
    out = []
    for score, row, why in scored[:limit]:
        out.append({"slug": row["slug"], "title": row["title"],
                    "text": _prompt_slice(row["text"]),
                    "why": why[:6], "score": score})
    return out


def block(picks: list[dict]) -> str:
    """프롬프트 블록 — 합성 콜의 user 에 그대로 붙는다."""
    if not picks:
        return ""
    parts = [f"《{p['title']}》\n{p['text']}" for p in picks]
    return "\n\n[해석 맥락 — 지식 위키]\n" + "\n\n---\n\n".join(parts)


def _meta(text: str) -> dict[str, str]:
    return {m.group("key"): m.group("val").strip()
            for m in _META_RE.finditer(text)}


# ---------------------------------------------------------------- 방법 갈래
# 방법 아티클은 질의가 아니라 **회수 결과**가 깨운다 — 단서 있는 구역이
# 실렸으면 단서 읽는 법을, 제재 동반이 실렸으면 제재 연결 읽는 법을 배경에
# 끼운다. 외부 설계 검토(docs/TAGS.md 파이프라인 10-B: "spots +
# condition_type + content_type 기반 선정")의 착지 — 선택은 코드 결정론이다
# (pick 과 같은 이유: 라우팅 콜을 답변 지연에 얹지 않는다).
METHOD_LIMIT = 2             # 질의 하나에 방법 아티클 최대 두 편
_COMPANION_KINDS = {"정의", "제재", "위임", "수임", "준용", "배제"}


def section_signals(sections) -> set[str]:
    """회수 구역들이 내는 신호 — 동반 kind + 본문의 단서. 전부 결정론."""
    sig: set[str] = set()
    for s in sections:
        kind = getattr(s, "kind", "") or ""
        if kind in _COMPANION_KINDS:
            sig.add(kind)
        if "다만," in (getattr(s, "text", "") or ""):
            sig.add("단서")
    return sig


def methods_for(sections, limit: int = METHOD_LIMIT) -> list[dict]:
    """신호에 걸린 방법 아티클 — [{slug, title, text, why, score}] 겹침순.

    `> 신호:` 메타를 단 아티클만 후보다(방법 갈래 + 신호를 단 해석원칙).
    신호가 없으면 빈손 — 방법을 억지로 끼우지 않는다.
    """
    sig = section_signals(sections)
    if not sig:
        return []
    scored = []
    for row in _rows():
        wants = {w.strip() for w in _meta(row["text"]).get("신호", "").split("·")
                 if w.strip()}
        hit = sorted(wants & sig)
        if hit:
            scored.append((len(hit), row, hit))
    scored.sort(key=lambda t: -t[0])
    out = []
    for score, row, hit in scored[:limit]:
        out.append({"slug": row["slug"], "title": row["title"],
                    "text": _prompt_slice(row["text"]),
                    "why": hit[:6], "score": score})
    return out


def _issue_rows() -> list[dict]:
    return [r for r in _rows() if r["slug"].startswith(ISSUE_DIR + "/")]


TITLES_PER_CARD = int(control_value("wiki.titles_per_card_max"))
_PROV_RE = re.compile(r"「(?P<law>[^」]+)」\s*(?P<coord>.*)")
# 조번호 — 법률·시행령의 `제34조의2` 와 규정·세칙류의 **편-조 체계**
# `제4-19조`·`제3-70조의2` 를 함께 문다 (docs/LEGAL_DOMAIN §2 함정 ①).
# 좁게 잡으면 조용히 빠진다 — 실측: 「이해관계인 거래」 카드의
# 「금융투자업규정」 제4-19조가 해소되지 않고 있었다.
_ART_RE = re.compile(r"제\d+(?:-\d+)?조(?:의\d+)?")
_titles_cache: dict = {"key": None, "map": {}}


def card_titles(index, rows: Optional[list] = None) -> dict[str, list[str]]:
    """카드 slug → 그 카드의 조문 후보가 실제로 가리키는 **조 제목** 목록.

    조문 **전문**이 아니라 제목만 캐는 것이 요점이다. 제목은 벡터 색인이
    담고 있는 바로 그 어휘이면서(그래서 재작성이 코퍼스에 착지한다) 값이
    싸다 — 실측 15장 전체 55개·987자(≈493토큰). 같은 조문을 전문으로 넣으면
    174,707자(≈87k토큰)라 컨텍스트가 터진다.

    좌표 해소는 결정론이다: 문서명 완전일치 → 경로에 그 조번호 → 부칙 여부
    일치(본문 '제2조'와 부칙 '제2조'는 다른 조다, docs/LEGAL_DOMAIN §2).
    """
    rows = rows if rows is not None else _issue_rows()
    key = (id(index), tuple(r["slug"] for r in rows))
    if _titles_cache["key"] == key:
        return _titles_cache["map"]
    docnames = {v.name: d for d, v in index.entry_docs.items()}   # 카드 후보도 진입 — 스코프 안만
    out: dict[str, list[str]] = {}
    for row in rows:
        titles: list[str] = []
        for prov in _meta(row["text"]).get("조문 후보", "").split("·"):
            m = _PROV_RE.match(prov.strip())
            if not m or m.group("law") not in docnames:
                continue                      # 코퍼스에 없는 법령은 건너뛴다
            v = index.docs[docnames[m.group("law")]]
            art = _ART_RE.search(m.group("coord"))
            if not art:
                continue
            want_buchik = "부칙" in m.group("coord")
            for node in v.by_id:
                path = v.path(node) or ""
                if art.group(0) not in path:
                    continue
                if ("부칙" in path) != want_buchik:
                    continue
                seg = [x.strip() for x in path.split(" ▸ ") if art.group(0) in x]
                if seg and seg[0] not in titles:
                    titles.append(seg[0])     # 조 수준 꼬리만 — 항·호·목은 버린다
        out[row["slug"]] = titles[:TITLES_PER_CARD]
    _titles_cache["key"], _titles_cache["map"] = key, out
    return out


def _card_pick(row: dict, why: list[str], score: int, via: str,
               probe: str = "") -> dict:
    """spot·spot_llm 공용 — 카드 행을 픽 형태로 접는다 (pick 과 같은 모양 + 쟁점 메타).

    probe(조문질의)는 LLM 판이 채운다 — 질문을 그 쟁점의 법률용어로 옮긴
    조문 문체 문장. 트리거 판은 빈 값이다(코드는 문체를 못 바꾼다).
    """
    meta = _meta(row["text"])
    return {"slug": row["slug"], "title": row["title"],
            "text": _prompt_slice(row["text"]),
            "why": why[:6], "score": score, "via": via,
            "probe": (probe or "").strip()[:PROBE_MAX_CHARS],
            "provisions": [p.strip() for p in
                           meta.get("조문 후보", "").split("·") if p.strip()],
            "axis": meta.get("판단 축", "")}


def spot(question: str, limit: int = SPOT_LIMIT) -> list[dict]:
    """쟁점 분해 — 질의를 쟁점 카드의 트리거에 비춘다 (검색 전, 코드 결정론).

    반환 [{slug, title, text, why, score, provisions, axis}] 점수순.
    트리거 무매칭이면 빈손 — 쟁점을 억지로 세우지 않는다.
    """
    pq = _pack(question)
    scored = []
    for row in _issue_rows():
        trig = [t.strip() for t in _meta(row["text"]).get("트리거", "").split("·")
                if len(t.strip()) >= 2]
        hits = [t for t in trig if _pack(t) in pq]
        if hits:
            scored.append((len(hits), row, hits))
    scored.sort(key=lambda t: -t[0])
    return [_card_pick(row, hits, score, via="트리거")
            for score, row, hits in scored[:limit]]


SPOT_SYSTEM = (
    "너는 법령 질의의 쟁점 판정기다. 질문과 이번 검색으로 회수된 조문 "
    "컨텍스트를 함께 읽고, 카드 목록에서 이 사안에 실제로 걸린 쟁점 카드만 "
    "slug 로 고른다 — 최대 2장, 걸린 쟁점이 없으면 빈 배열(억지로 고르지 "
    "않는다). 낱말 겹침이 아니라 사안의 법적 구조로 판단하라 — 회수된 "
    "조문들 사이에서 어떤 판단 축이 결론을 가르겠는가. 고른 카드마다 왜 이 "
    "쟁점인지 한 문장으로 적는다.\n"
    "카드마다 `조문질의`도 쓴다 — 질문을 그 쟁점의 법률용어로 옮긴 조문 "
    "문체의 한두 문장이다(구어·물음표 없이, 질문의 구체 사실을 담아). "
    "회수가 부족할 때 이 문장으로 다시 검색한다.")

# 검색 **전** 판(컨텍스트 없음) — 조문을 아직 못 봤으니 판단 재료는 질문뿐이다.
# 트리거 매칭이 낱말 하나("등록")로 엉뚱한 카드를 무는 자리를 이 콜이 대신한다.
SPOT_SYSTEM_PRE = (
    "너는 법령 질의의 쟁점 분해기다. 아직 검색 전이라 조문은 없고 질문만 "
    "있다. 카드 목록에서 이 질문이 실제로 묻는 쟁점만 slug 로 고른다 — "
    "최대 2장, 해당 없으면 빈 배열(억지로 고르지 않는다). **낱말 겹침으로 "
    "고르지 마라** — 질문에 '등록'이 있다고 인허가 쟁점인 것이 아니다. "
    "질문자가 다투는 것이 무엇인지(무엇이 결론을 가르는지)로 판단하고, "
    "고른 카드마다 왜 이 쟁점인지 한 문장으로 적는다.\n"
    "그리고 카드마다 `조문질의`를 쓴다 — **질문을 그 쟁점의 법률용어로 "
    "옮긴, 조문 문체의 한두 문장**이다. 이것이 벡터 검색에 그대로 들어가고, "
    "벡터 색인은 조문 텍스트로 만들어져 있어 **질의도 조문처럼 쓰여야 "
    "맞물린다**. 규칙:\n"
    "  · 조문·부칙이 쓰는 표현을 쓴다 — '이 법 시행 당시', '종전의 규정에 "
    "따라', '…에 대한 경과조치', '…로 본다', '…하여야 한다'.\n"
    "  · 질문의 구체 사실(무엇이 바뀌었나·누가·무엇을)을 반드시 담는다 — "
    "일반론만 쓰면 엉뚱한 조문이 온다.\n"
    "  · 구어("
    "'되나요', '어떻게 하죠')·질문부호는 쓰지 않는다. 조문 제목과 본문을 "
    "흉내 낸 서술문으로 쓴다.\n"
    "  · 법령 이름을 지어내지 마라 — 확실하지 않으면 이름 없이 요건만 쓴다.\n"
    "  · **카드에 달린 `조문 제목`의 어휘를 빌려 써라** — 그것이 코퍼스에 "
    "실재하는 표현이고, 벡터 색인이 담고 있는 바로 그 말이다. 없는 표현을 "
    "새로 지어내면 아무 데도 착지하지 않는다.")

SPOT_SCHEMA = {
    "type": "object",
    "properties": {"cards": {"type": "array", "items": {
        "type": "object",
        "properties": {"slug": {"type": "string"}, "why": {"type": "string"},
                       # 조문 문체로 옮긴 질의 — 벡터 색인이 조문 텍스트라
                       # 질의도 조문처럼 써야 맞물린다(실측 코사인 0.58→0.68).
                       "조문질의": {"type": "string"}},
        "required": ["slug", "why", "조문질의"], "additionalProperties": False}}},
    "required": ["cards"], "additionalProperties": False,
}

_JUDGE_SECTIONS_MAX = 12       # 판정 콜에 넘기는 구역 상한 — 판정은 답변이 아니다
_JUDGE_SNIPPET_CHARS = 240     # 구역당 본문 발췌 — 계층·주제 파악에 족하다


def spot_llm(llm, question: str, sections: Optional[list] = None,
             limit: int = SPOT_LIMIT, index=None) -> Optional[list[dict]]:
    """쟁점 판정의 LLM 판 — **컨텍스트 확보 후** 사안 전체를 보고 카드를 고른다.

    검색 전 트리거 매칭(spot)과 시점이 다르다: 회수·확장이 끝난 뒤 질문 +
    회수된 조문을 함께 보고 "이 사안에 걸린 쟁점"을 판정한다 — 질문만 보고는
    모르는 쟁점(조문이 드러낸 준용·부칙 구조)이 여기서 잡힌다. 카드는 그
    판정의 메뉴이자, 고른 뒤에는 합성 배경으로 들어갈 도메인 정식화다.

    반환 계약: 판정이 섰으면 목록(빈 배열 = "걸린 쟁점 없음"이라는 판정),
    판정 자체가 불가능하면(무LLM·콜 실패) None — 폴백 여부는 호출자가
    정한다(라우터는 트리거 결과를 유지한다). 스위치 issue_spot_llm, 기본
    꺼짐 — 판정 콜 지연이 답변 앞에 얹히므로 켜는 것은 사용자다.
    """
    rows = _issue_rows()
    if llm is None or not rows:
        return None
    # 메뉴에 **조 제목**을 태운다 — 재작성이 빌려 쓸 어휘이자, 카드를 고를 때
    # "이 카드가 실제로 어느 조를 가리키나"를 보여 주는 재료다(고르기도 정확해진다).
    titles = card_titles(index, rows) if index is not None else {}
    lines = []
    for r in rows:
        line = (f"- {r['slug']} | {r['title']} | 판단 축: "
                f"{_meta(r['text']).get('판단 축', '')} | {r['summary']}")
        ts = titles.get(r["slug"]) or []
        if ts:
            line += "\n    조문 제목: " + " · ".join(ts)
        lines.append(line)
    menu = "\n".join(lines)
    ctx = ""
    if sections:
        parts = [f"[{s.n}] {s.doc} ▸ {s.path}\n{(s.text or '')[:_JUDGE_SNIPPET_CHARS]}"
                 for s in sections[:_JUDGE_SECTIONS_MAX]]
        ctx = "\n\n[회수된 조문 컨텍스트]\n" + "\n\n".join(parts)
    # 시점이 콜의 이름과 규칙을 가른다 — 검색 전(질문만)이면 분해, 회수 뒤면 판정.
    kind = "rag.issue_spot" if sections else "rag.issue_spot_pre"
    system = SPOT_SYSTEM if sections else SPOT_SYSTEM_PRE
    via = "llm" if sections else "llm(검색전)"
    user = f"[질문]\n{question}{ctx}\n\n[쟁점 카드 목록]\n{menu}"
    out = llm.structured(kind, system, user, SPOT_SCHEMA,
                         max_tokens=SPOT_MAX_TOKENS, effort="low")
    _log = getattr(llm, "log", None)     # 테스트 대역은 log 가 없다
    if out is None and _log and "잘림" in str(_log[-1].error or ""):
        out = llm.structured(kind, system, user, SPOT_SCHEMA,
                             max_tokens=SPOT_MAX_TOKENS * 3, effort="low")
    if out is None:
        return None
    by_slug = {r["slug"]: r for r in rows}
    picks: list[dict] = []
    for c in out.get("cards", []):
        row = by_slug.get(str(c.get("slug", "")).strip())
        if row is None or any(p["slug"] == row["slug"] for p in picks):
            continue                     # 모른 slug·중복은 버린다 — 메뉴가 정본
        picks.append(_card_pick(row, [str(c.get("why", ""))[:120]],
                                score=0, via=via,
                                probe=str(c.get("조문질의", ""))))
        if len(picks) >= limit:
            break
    return picks


def vector_query(question: str, spots: list[dict]) -> str:
    """**벡터 채널 전용** 질의 — 조문 문체로 옮긴 법률문장만. 좌표·법령명은 뺀다.

    규칙 하나로 줄이면: **찾으려는 조문에 실제로 쓰여 있을 법한 문장만 넣는다.**
    문서명·조 좌표 같은 메타데이터는 넣지 않는다 — 그것을 나열하는 다른 조문
    (부칙의 「다른 법령의 개정」은 법령명을 수십 개 나열한다)과 표면이 겹쳐
    코사인만 올리고 엉뚱한 데로 데려간다.

    같은 질문 실측 (상위 20을 **무엇을 데려왔나**로 채점 — 코사인이 아니라):

        질의 구성                코사인   경과조치 조   개정 조
        구어 원문                 0.582     0/20        1/20   (전부 본문 회사법)
        법률문장 + 법령명          0.706     0/20       16/20   ← 코사인 최고, 내용 최악
        법률문장만                0.619     6/20        3/20   ← 이것

    코사인 평균으로 고르면 정확히 틀린 것을 고른다(2026-08-14 실측으로 뒤집힘).
    법령명은 어휘 사다리(문자열 매칭)에 남긴다 — 거기서는 제 역할을 한다.

    재작성이 없으면(트리거 판) 빈 문자열 — 호출부가 원 질의로 벡터를 돌린다.
    """
    parts = [(s.get("probe") or "").strip() for s in spots]
    probes = [p for i, p in enumerate(parts) if p and p not in parts[:i]]
    return " ".join(probes)


def expand_query(question: str, spots: list[dict]) -> str:
    """질의를 쟁점으로 넓힌다 — 조문질의(probe)만 붙인다.

    쟁점 카드의 소임은 **질문을 조문 문체로 옮겨 벡터가 착지하게 하는 것**이다
    (2026-08-18 사용자 결정). 사용자의 구어는 조문 문체와 어긋나 벡터가
    헛돈다(실측: 같은 질문이 구어면 코사인 0.58로 상법 회사해산에 착지, 조문
    문체로 옮기면 0.68로 부칙 경과조치에 착지). 조문 **원문**은 넣지 않는다 —
    그건 컨텍스트를 태운다.

    카드의 `조문 후보`는 **질의에 넣지 않는다.** 그것은 카드를 컴파일할 때 본
    사례의 좌표라 사안이 다르면 다른 조를 가리킨다 — 실측 18-0124: 「다른
    법률 근거의 문턱」 후보가 국세기본법 제81조의13(비밀 유지)인데 사안의
    정답은 제84조(국세행정에 대한 협조). 후보를 질의에 실으면 어휘 사다리가
    그 조를 물어 정답이 밀린다. 조문 후보는 사람이 읽는 참고이자 재작성의
    어휘 재료(card_titles)일 뿐, 회수 좌표가 아니다. 사용자가 직접 또는
    피드백 루프에서 승인한 연결만이 좌표가 될 수 있다 — 그 고리는 아직 없다.

    회수만 이 확장 질의로 간다. 합성·기록은 원 질의다.
    """
    pq = _pack(question)
    probes = []
    for s in spots:
        pr = (s.get("probe") or "").strip()
        if pr and _pack(pr) not in pq and pr not in probes:
            probes.append(pr)
    if not probes:
        return question
    return question + "\n[법률용어 질의] " + " ".join(probes)
