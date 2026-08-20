"""마디 성격 태그 — "무엇인가"(정의·단서·벌칙…)와 "어떤 규범인가"(의무·재량…).

문서 구조화(result.json)는 계층과 좌표만 안다. 이 층은 그 위에 **성격**을
얹는다 — 외부 설계 검토(docs/TAGS.md, 2026-08-18)의
content_type/condition_type 분류를 받아들이되, 저장 모델을 바꿨다:
청크가 메타를 들고 다니는 대신 **파생층**이고, enum 하나 대신 **다중 태그**다.

다중 태그인 이유는 실물 하나로 족하다 — 증권발행공시규정 제1-2조 ⑦은 한 항
안에 정의('"지주회사"란')·단서("다만, 외국법인등…")·정량("100분의 50 이상")이
같이 산다. 타입 하나를 고르게 하면 이 항을 넣을 자리가 없다.

패턴은 **문서 무관 신호만** 쓴다 — 법제처 입안·심사 기준이 규격화한 표현이라
코퍼스 전역에서 정형이다(실측 2026-08-18, 42문서·96,580블록: 의무 6,353 ·
단서 3,138 · 정의 2,774 · 정량 1,968 · 벌칙 490 …). 문서별 상수는 여기 두지
않는다(샘플 과적합 금지).

**판정은 하지 않는다** — addendum_kind 와 같은 규율로 이름표만 붙인다.
회수에 개입하는 것은 expand.expand_floor 의 동반 두 종(정의·제재)뿐이고,
그것도 엔진 스위치(floor_definition·floor_sanction)로 사용자가 끈다.
정량의 구조화(기준·값)도 결정론까지만 — "자기자본의 100분의 25"처럼 기준이
문면에 붙은 것만 뽑고, 표기는 **원문 그대로** 남긴다(grounding — "25%"로
바꿔 적지 않는다). LLM 정련은 이 태그가 지목한 자리에서 나중 일이다.
"""
from __future__ import annotations

import re
from typing import Optional

# 조 표면형 — 법률의 `제34조의2`와 규정·세칙류 편-조 체계 `제4-19조`를 함께
# 문다 (docs/LEGAL_DOMAIN §2 함정 ①: 좁게 잡으면 조용히 빠진다).
_JO = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")
_Q_OPEN, _Q_CLOSE = "\"“‘'", "\"”’'"

# ---------------------------------------------------------------- 패턴 등록부
# content_type — 마디의 "무엇인가". 키가 곧 태그 이름이다.
TYPES: dict[str, re.Pattern] = {
    "정의": re.compile(
        rf'[{_Q_OPEN}][^{_Q_OPEN}{_Q_CLOSE}\n]{{1,40}}[{_Q_CLOSE}]\s*'
        r'(?:이?란|이?라\s*함은)|용어의\s*(?:뜻|정의)'),
    "단서": re.compile(r'다만,|(?m:^\s*단,)'),
    "예외": re.compile(r'예외로\s*한다|제외한다|그러하지\s*아니하다|'
                       r'적용(?:하지|되지)\s*아니한다'),
    "특례": re.compile(r'에도\s*불구하고|특례|특별한\s*규정'),
    "벌칙": re.compile(r'(?:징역|벌금|금고|과료)에\s*처한다|과태료를\s*부과'),
}

# condition_type — 마디의 "어떤 규범인가". "할 수 있다"의 허용(사업자)/권한
# (감독기관) 구분은 주어 판별이 필요해 아직 가르지 않는다 — 허용으로 묶는다.
CONDS: dict[str, re.Pattern] = {
    # "하여야 한다"만 잡으면 "알려야·받아야·갖추어야 한다"가 빠진다 —
    # 개보법 제17조 ②(알려야 한다)가 의무 없음으로 읽히는 실측 오탐.
    "의무": re.compile(r'[가-힣]*(?:아야|어야|여야|해야)\s*한다'),
    "금지": re.compile(r'(?:하여서는|해서는)\s*아니\s*된다|하지\s*못한다|'
                       r'할\s*수\s*없다|금지한다'),
    "허용": re.compile(r'할\s*수\s*있다'),
    "절차": re.compile(r'(?:승인|인가|허가)[을를]?\s*받아야|심의를\s*거쳐|'
                       r'의결을\s*거쳐'),
    "신고보고": re.compile(r'(?:신고|보고|통지|공시|제출)하여야\s*한다'),
    "위임": re.compile(r'(?:대통령령|총리령|부령|규칙)으로\s*정(?:한다|하는)|'
                       r'위원회가\s*정하|정하여\s*고시하|원장이\s*정(?:한다|하는)'),
    "간주": re.compile(r'[으]?로\s*본다|효력[을이]?\s*가진다|간주한다'),
}

# 정의 **선언** — "이 법에서 사용하는 용어" / '이 법에서 "X"란'. 스코프를
# 문서가 스스로 밝힌 자리라, 제목에 '정의'가 없는 정의 조(자본시장법
# 제3~8조의2 — 제9조 「그 밖의 용어의 정의」가 앞이 정의였음을 증언한다)를
# 이 신호가 잡는다.
_DECL = re.compile(
    rf'이\s*(?:법|영|규정|규칙|세칙|편|장|절)에서\s*'
    rf'(?:사용하는\s*용어|[{_Q_OPEN}][^{_Q_OPEN}{_Q_CLOSE}\n]{{1,40}}[{_Q_CLOSE}]\s*'
    r'(?:이?란|이?라\s*함은))')
# '정의' 앞이 한글이면 다른 낱말이다 — "업무규**정의** 보고"(자본시장법
# 제290조)가 물리는 오탐 실측으로 경계를 박았다.
_DEF_TITLE = re.compile(r'(?<![가-힣])정의|용어의\s*뜻')
_SANC_TITLE = re.compile(r'벌칙|과태료')

# 정량 — 표기(원문 그대로)와, 문면에 붙어 있을 때만 기준(base). 값을 바꿔
# 적지 않는다: "100분의 25"를 "25%"로 옮기는 순간 grounding 이 끊긴다.
_QUANT: list[tuple[str, re.Pattern]] = [
    ("비율", re.compile(r'(?:([가-힣·]{2,20})의\s*)?'
                        r'((?:100|1천|1만|만|천)분의\s*[\d,]+(?:\.\d+)?)')),
    ("비율", re.compile(r'()([\d,]+(?:\.\d+)?\s*퍼센트)')),
    ("금액", re.compile(r'()([\d,]+\s*(?:조|억|천만|백만|십만|만)?\s*원(?![가-힣]))')),
    ("기간", re.compile(r'()([\d,]+\s*(?:년|개월|월|주|일|시간)\s*'
                        r'(?:이내|이상|이하|안에|전까지))')),
    ("배수", re.compile(r'()([\d,]+(?:\.\d+)?\s*배(?![가-힣]))')),
]
_QUANT_HINT = re.compile(r'분의|퍼센트|원|이내|이상|이하|전까지|\d\s*배')

DEF_COMPANION_MAX = 2      # 착지 하나가 동반하는 정의 조 — 최근접 스코프 + 문서 대표
QUANT_MAX = 8              # 마디 하나에서 뽑는 정량 표기 상한 — 표(별표)의 폭주 방지


# ---------------------------------------------------------------- 계산·캐시
def _chain(v, node_id: Optional[int]) -> list[dict]:
    """자신 → 조상 사슬. 순환 가드 포함 (index._in_subtree 와 같은 규율)."""
    out, seen = [], set()
    cur = v.by_id.get(node_id) if node_id is not None else None
    while cur is not None and cur.get("id") not in seen:
        out.append(cur)
        seen.add(cur.get("id"))
        cur = v.by_id.get(cur.get("parent"))
    return out


def _compute(v) -> dict:
    """DocView 하나의 태그 전량 — 처음 쓰일 때 한 번, 인스턴스에 남는다.

    블록 한 번 훑기(태그) + 조 한 번 훑기(정의 조·벌칙 조 판별)로 끝난다.
    스토어가 바뀌면 Index 가 DocView 를 새로 지으므로 무효화는 공짜다.
    """
    cached = getattr(v, "_tags_cache", None)
    if cached is not None:
        return cached

    blocks: dict[int, set] = {}
    for b in v.blocks:
        t = b.get("text") or ""
        if not t:
            continue
        tags = {name for name, rx in TYPES.items() if rx.search(t)}
        tags |= {name for name, rx in CONDS.items() if rx.search(t)}
        if _QUANT_HINT.search(t) and any(rx.search(t) for _, rx in _QUANT):
            tags.add("정량")
        if _DECL.search(t):
            tags.add("_선언")
        if tags:
            blocks[b.get("idx")] = tags

    def span_tags(n: dict) -> set:
        s = n.get("span") or [0, 0]
        agg: set = set()
        for i in range(s[0], max(s[1], s[0] + 1)):
            agg |= blocks.get(i, set())
        return agg

    # 정의 조(관할급)의 문턱은 **제목 또는 선언**이다 — 인용정의('"X"란')의
    # 반복만으로는 안 세운다. "이 조에서 …이란"의 인라인 정의(금융투자업규정
    # 실측 81개 중 대다수)는 제 조 밖을 관할하지 못하는데, 관할로 세우면
    # 엉뚱한 조의 용어가 이웃 착지에 끌려온다. 블록 태그 '정의'는 그대로
    # 남으니 관측은 잃지 않는다.
    defs: list[int] = []
    sanctions: set[int] = set()
    for n in v.nodes:
        if not _JO.fullmatch((n.get("surface") or "").strip()):
            continue
        anc = _chain(v, n.get("id"))[1:]
        # 부칙 제외 — 「다른 법률의 개정」 조는 남의 법 정의문을 통째로
        # 인용하므로(자본시장법 부칙 실측) 정의 조로 서면 안 된다.
        if any("부칙" in ((a.get("surface") or "") + (a.get("title") or ""))
               for a in anc):
            continue
        agg = span_tags(n)
        title = (n.get("title") or "").strip()
        if _DEF_TITLE.search(title) or "_선언" in agg:
            defs.append(n.get("id"))
        anc_title = " ".join((a.get("title") or "") for a in anc)
        if "벌칙" in agg or _SANC_TITLE.search(title) or _SANC_TITLE.search(anc_title):
            sanctions.add(n.get("id"))

    out = {"blocks": blocks, "defs": defs, "sanctions": sanctions}
    v._tags_cache = out
    return out


# ---------------------------------------------------------------- 조회
def node_marks(v, node_id: Optional[int]) -> list[str]:
    """마디 자신의 블록에 붙은 태그 — 관측용(응답 context 행). 정렬 고정."""
    n = v.by_id.get(node_id) if node_id is not None else None
    if n is None:
        return []
    blocks = _compute(v)["blocks"]
    s = n.get("span") or [0, 0]
    agg: set = set()
    for i in range(s[0], max(s[1], s[0] + 1)):
        agg |= blocks.get(i, set())
    order = list(TYPES) + ["정량"] + list(CONDS)
    return [t for t in order if t in agg]


def has_condition(v, node_id: Optional[int], wanted: tuple) -> bool:
    """착지 마디(자기 범위)에 이 규범 성격이 있는가 — 제재 동반의 조건."""
    n = v.by_id.get(node_id) if node_id is not None else None
    if n is None:
        return False
    blocks = _compute(v)["blocks"]
    s = n.get("span") or [0, 0]
    return any(w in blocks.get(i, ())
               for i in range(s[0], max(s[1], s[0] + 1)) for w in wanted)


def definition_jos(v) -> list[int]:
    """관할급 정의 조 목록 — 문서 순서. 제목(`정의`·`용어의 뜻`) 또는 본문
    선언(`이 법에서 사용하는 용어` / `이 편에서 "X"란`)이 신호다. 부칙과
    인라인 정의("이 조에서")는 제외 — _compute 머리의 이유."""
    return list(_compute(v)["defs"])


def governing_definitions(v, node_id: Optional[int],
                          cap: int = DEF_COMPANION_MAX) -> list[int]:
    """착지 마디의 **관할** 정의 조 — 최근접 스코프 + 문서 대표.

    정의 조는 문서마다 하나가 아니다 — 금융투자업규정은 편마다 제 정의 조를
    두어 11개다(실측). 제3편 착지에는 제3-6조(같은 편)와 제1-2조(문서 전체)가
    관할이고, 제3-6조의 용어를 제8편에 끌고 가면 안 된다. 그래서:

      · 최근접 — 착지와 실제 조상(편·장)을 공유하는 정의 조 중 가장 깊은 것
      · 대표   — 문서 순서 첫 정의 조 (통상 총칙 — 문서 전체 관할)

    착지가 정의 조 자신(또는 그 안)이면 빈손 — 자기 자신을 동반하지 않는다.
    """
    c = _compute(v)
    defs = c["defs"]
    if not defs or node_id is None:
        return []
    chain = _chain(v, node_id)
    if not chain:
        return []
    chain_ids = [n.get("id") for n in chain]
    if set(chain_ids) & set(defs):
        return []
    depth = {nid: len(chain_ids) - 1 - i for i, nid in enumerate(chain_ids)}

    best, best_shared = None, -1
    for d in defs:
        shared = max((depth.get(a.get("id"), -1)
                      for a in _chain(v, d)[1:]), default=-1)
        if shared > best_shared:
            best, best_shared = d, shared
    out: list[int] = []
    if best is not None and best_shared >= 0:      # 실제 조상을 공유할 때만
        out.append(best)
    if defs[0] not in out:
        out.append(defs[0])
    return out[:cap]


def is_sanction(v, node_id: Optional[int]) -> bool:
    """이 마디가 벌칙 조(안)인가 — 제재 동반의 출발점 검사. 조 제목·소속
    장 제목(`벌칙`·`과태료`) 또는 본문 처벌 술어(`…에 처한다`)가 신호다."""
    sanctions = _compute(v)["sanctions"]
    return any(n.get("id") in sanctions for n in _chain(v, node_id))


def quant_rules(v, node_id: Optional[int], cap: int = QUANT_MAX) -> list[dict]:
    """마디 자기 범위의 정량 표기 — [{종류, 표기, 기준?}] 원문 그대로.

    기준(base)은 "자기자본의 100분의 25"처럼 문면에 붙었을 때만 담는다 —
    떨어져 있는 기준을 잇는 것은 판단이라 여기 없다(결정론까지만)."""
    n = v.by_id.get(node_id) if node_id is not None else None
    if n is None:
        return []
    s = n.get("span") or [0, 0]
    out, seen = [], set()
    for i in range(s[0], max(s[1], s[0] + 1)):
        b = v.block_by_idx.get(i)
        t = (b or {}).get("text") or ""
        if not t or not _QUANT_HINT.search(t):
            continue
        for kind, rx in _QUANT:
            for m in rx.finditer(t):
                surface = m.group(2).strip()
                if surface in seen:
                    continue
                seen.add(surface)
                row = {"종류": kind, "표기": surface}
                if m.group(1):
                    row["기준"] = m.group(1)
                out.append(row)
                if len(out) >= cap:
                    return out
    return out
