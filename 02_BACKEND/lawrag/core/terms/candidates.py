"""Tier 2 후보 생성 — 형태소 분석 + 품사 패턴 (ontology_kg §4.2 ①②, §4.8).

Kiwi 로 문장을 가르고, 명사 연쇄(NNG·NNP·SL)에서 모든 연속 부분열을
후보로 낸다 — 부분열까지 내는 이유는 C-value 다: "압력 안전 밸브"가 나올 때
"안전 밸브"의 출현도 세어져야 중첩 보정이 성립한다.

같은 스캔에서 **문장 공기 쌍**(§5.8b)도 거둔다 — 추가 스캔 없이 부산물로.
공기 쌍은 최대 명사구(부분열이 아니라)끼리만 만든다. 부분열끼리 쌍을 만들면
"안전"과 "밸브"가 공기했다는 무의미한 증거가 폭발한다.

사용자 사전: 수기 용어집 + Tier 1 산출을 Kiwi 에 주입한다 — 분석기가
도메인 용어를 쪼개는 것(§4.8 "원금보장안" 문제의 반대 방향)을 막는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from lawrag.core.rag.index import DocView

# 후보가 될 수 있는 품사 — 일반명사·고유명사·로마자.
_NOUN_TAGS = {"NNG", "NNP", "SL"}
_MAX_RUN = 6            # 최대 명사 연쇄 길이 (이보다 길면 나열이지 용어가 아니다)
_MAX_SPAN = 5           # 후보의 최대 토큰 수
_COOC_MAX_DIST = 15     # 공기 쌍의 최대 토큰 거리 (§5.8b)

# 홀로는 용어가 못 되는 문법성 명사 — 분포 기반 lift 게이트가 있지만,
# 뻔한 것까지 LLM 판정 자리를 차지하게 둘 이유가 없다.
STOP_SOLO = {
    "것", "등", "경우", "때", "수", "중", "내", "외", "시", "년", "월", "일",
    "위", "아래", "다음", "이상", "이하", "미만", "초과", "사항", "내용",
    "관련", "기타", "해당", "당해", "이용", "사용", "여부", "부분", "정도",
    "말", "뜻", "바", "점", "면", "쪽", "간", "별", "및",
}
# 조문 마커·번호는 구조지 용어가 아니다 (구조 엣지 ①의 몫).
_MARKER = re.compile(r"^제?\d+(조|항|호|절|관|장|편)(의\d+)?$|^별[지표]\d*$|^\d+$")


def norm(s: str) -> str:
    """후보 묶음 키 — transcribe·glossary 와 같은 규칙(공백만 지운다)."""
    return re.sub(r"\s+", "", s or "")


@dataclass
class Mention:
    """후보 하나의 출현 — 좌표가 곧 앵커(엣지 ②)다."""
    surface: str
    key: str
    tokens: tuple                 # 형태소 형(form)의 열 — 어휘포함(⑥) 판정용
    doc_id: str
    doc: str
    node: Optional[int]
    block: int
    page: Optional[int]
    sent: int                     # 블록 안 문장 번호 — 공기 쌍의 좌표
    in_heading: bool
    text: str = ""                # 문장 발췌 (판정 스니펫용, 최대후보에만 채운다)


@dataclass
class Cooccur:
    """문장 공기 증거 한 건 (§5.8b). a·b 는 정규형 사전순."""
    a: str
    b: str
    pattern: str                  # 두 후보 사이의 연결 표현 (조사 보존)
    kind: str                     # "cooccur" | "enum" (나열 — ⑥ 형제 증거로 분기)
    doc_id: str
    block: int
    sent: int


@dataclass
class HarvestResult:
    mentions: dict = field(default_factory=dict)     # key -> [Mention]
    cooccurs: list = field(default_factory=list)     # [Cooccur]
    unigram: dict = field(default_factory=dict)      # 토큰 form -> 빈도 (G² 용)
    bigram: dict = field(default_factory=dict)       # (form, form) -> 빈도
    n_tokens: int = 0                                # 명사 연쇄 안 토큰 총수
    n_sents: int = 0
    n_blocks: int = 0
    sent_terms: dict = field(default_factory=dict)   # (doc,block,sent) -> set(key)


# 나열 구분자만으로 이어졌는가 — "펌프, 압축기 및 송풍기" 는 공기가 아니라
# 형제 나열이다 (§5.8b "나열 문장 필터가 품질의 절반").
_ENUM_SEP = re.compile(r"^[\s,·ㆍ、и및과와또는등의()\d.]*$")


def _kiwi(user_words: Iterable[str]):
    from kiwipiepy import Kiwi

    kiwi = Kiwi()
    for w in sorted({w for w in user_words if w and len(w) >= 2}):
        try:
            kiwi.add_user_word(w, "NNP", 0.0)
        except Exception:
            continue
    return kiwi


def harvest(views: list[DocView], user_words: Iterable[str] = ()) -> HarvestResult:
    """문서들을 한 번 훑어 후보 출현·공기 쌍·토큰 통계를 모두 거둔다."""
    kiwi = _kiwi(user_words)
    out = HarvestResult()

    for v in views:
        title_blocks = {n.get("block") for n in v.nodes}
        for b in v.blocks:
            text = b.get("text") or ""
            if len(text) < 2:
                continue
            out.n_blocks += 1
            owner = v.owner(b.get("idx")) or {}
            in_heading = b.get("idx") in title_blocks
            try:
                sents = kiwi.split_into_sents(text, return_tokens=True)
            except Exception:
                continue
            for si, sent in enumerate(sents):
                out.n_sents += 1
                runs = _noun_runs(sent.tokens or [])
                maximal: list[tuple] = []          # (start_char, end_char, key)
                for run in runs:
                    out.n_tokens += len(run)
                    for i, t in enumerate(run):
                        out.unigram[t.form] = out.unigram.get(t.form, 0) + 1
                        if i + 1 < len(run):
                            pair = (t.form, run[i + 1].form)
                            out.bigram[pair] = out.bigram.get(pair, 0) + 1
                    spans = _spans(run, sent.text, sent.start)
                    for (sfc, toks, s0, s1, is_max) in spans:
                        key = norm(sfc)
                        if not _ok(key, toks):
                            continue
                        m = Mention(surface=sfc, key=key, tokens=toks,
                                    doc_id=v.doc_id, doc=v.name,
                                    node=owner.get("id"), block=b.get("idx"),
                                    page=b.get("page"), sent=si,
                                    in_heading=in_heading,
                                    text=sent.text[:160] if is_max else "")
                        out.mentions.setdefault(key, []).append(m)
                        if is_max:
                            maximal.append((s0, s1, key))
                            out.sent_terms.setdefault(
                                (v.doc_id, b.get("idx"), si), set()).add(key)
                _pairs(out, maximal, sent.text, sent.start, v.doc_id,
                       b.get("idx"), si)
    return out


def _noun_runs(tokens) -> list[list]:
    runs, cur = [], []
    for t in tokens:
        if t.tag in _NOUN_TAGS:
            cur.append(t)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [r[:_MAX_RUN] for r in runs if r]


def _spans(run, sent_text: str, sent_start: int) -> list[tuple]:
    """연쇄의 모든 연속 부분열 → (표면, 토큰열, 시작, 끝, 최대인가).

    표면은 **원문 그대로** 자른다 — 형태소 form 을 이어붙이면 원문 띄어쓰기가
    사라져 출현 좌표와 표면형이 어긋난다.
    """
    out = []
    n = len(run)
    for i in range(n):
        for j in range(i, min(n, i + _MAX_SPAN)):
            s0 = run[i].start - sent_start
            s1 = run[j].start + run[j].len - sent_start
            sfc = sent_text[s0:s1].strip()
            if not sfc:
                continue
            toks = tuple(t.form for t in run[i:j + 1])
            out.append((sfc, toks, s0, s1, i == 0 and j == n - 1))
    return out


def _ok(key: str, toks: tuple) -> bool:
    if len(key) < 2 or _MARKER.fullmatch(key):
        return False
    if len(toks) == 1 and toks[0] in STOP_SOLO:
        return False
    # 나열 연쇄의 부산물("압축기송풍기" 같은 경계 없는 이어붙임)은 표면이
    # 원문에서 잘려 왔으므로 여기 오지 않는다 — 남는 검사는 글자 존재뿐.
    return bool(re.search(r"[가-힣A-Za-z]", key))


def _pairs(out: HarvestResult, maximal: list, sent_text: str, sent_start: int,
           doc_id: str, block: int, sent: int) -> None:
    """같은 문장의 최대 후보끼리 공기 쌍을 만든다 (§5.8b)."""
    for i in range(len(maximal)):
        for j in range(i + 1, len(maximal)):
            (a0, a1, ak), (b0, b1, bk) = maximal[i], maximal[j]
            if ak == bk:
                continue
            between = sent_text[a1:b0]
            if len(between) > _COOC_MAX_DIST * 3:      # 대략 토큰 거리 초과
                continue
            kind = "enum" if _ENUM_SEP.fullmatch(between) else "cooccur"
            a, b = sorted((ak, bk))
            pattern = re.sub(r"\s+", " ", between).strip()[:30]
            out.cooccurs.append(Cooccur(a=a, b=b, pattern=pattern, kind=kind,
                                        doc_id=doc_id, block=block, sent=sent))
