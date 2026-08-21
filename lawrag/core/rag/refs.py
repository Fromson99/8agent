"""조문 상호참조 — 본문 속 "제4조를 참고한다" 를 구역 간선으로 세운다.

용어 마킹(term_marker)과 같은 철학이다: **찾기는 결정론이 잘한다**. 법령·약관의
참조 표기는 문서와 무관한 관례(제N조 · 제N조의M · 제N조제P항제Q호R목 ·
제N장/절/편/관 · 별표N · 별지N, 조 바로 뒤에 붙은 ①·(2) 같은 표면형)라서
문자열 패턴으로 찾을 수 있고, 어느 구역을 가리키는지도 구역 제목을 같은
문법으로 읽어 결정론으로 잇는다.

조 아래로는 **실존하는 데까지만** 내려간다(사슬 하강): "제1조 (2)" 는 먼저
제1조를 찾고, 그 아래에 둘째 항목이 실제로 있으면 거기까지, 없으면 조에
머문다. 단위 이름(항·호·목)은 표기 계열(①·1.·가.)과 법령 관례로 맞물리고,
그 계열이 아예 없는 문서에서만 서수로 무른다 — 항을 (1) 로 쓰는 약관이 있다.

## 두 개의 결

    resolve()        문서 **안** — 제2조 본문이 제4조를 가리키면 (제2조 → 제4조).
                     전부 결정론. 다른 문서 참조(「신탁법」 제10조 · 동법 제12조)는
                     여기서 잇지 않는다 — 이 문서에 같은 번호가 있어도 그 조가
                     아니다.
    cross_resolve()  문서 **사이** — 「수수료규정」 제2조 를 저장소의 그 문서
                     구역으로. 힌트(문서명)가 한 문서로 떨어질 때만 확정하고,
                     동법·같은 규정 같은 대용어나 후보가 여럿이면 **보류**로
                     돌려준다 — 판정은 judge.py(LLM, 닫힌 후보)나 사람이 한다.
                     새 문서가 들어오면 색인이 다시 서고 이 대조도 다시 돈다 —
                     어제 빈손이던 「수수료규정」 이 그 문서가 올라오는 순간
                     확정 간선이 된다.

## 열거와 범위

    "제19조제1항ㆍ제3항"·"제2조제6호가목ㆍ다목" — 연결사(ㆍ·, 및 또는 부터 와 과)
    뒤에 조 없이 온 항·호·목은 같은 조의 다른 가지로 잇는다. "제129조부터
    제132조까지"는 양 끝을 잡되, 앞 끝의 문서 이름(「형법」)이 뒤 끝도 덮는다.

## 건너뛰는 것

    · 자기 자신·조상/자손 참조 — 계층 간선이 이미 담당한다. 조문 제목 블록이
      제 번호를 다는 자기 출현도 이 규칙이 걸러 준다.
    · "같은 조"·"전항" 류 대용어와 문장 첫머리의 맨 "제N항" — 문맥 해석이
      필요해 결정론 밖이다.
    · "법 제87조"의 '법' 같은 총칭 힌트 — 이름이 아니라 그 문서가 정의한
      대용어다. 이름 대조로 확정하지 않고 보류로 보낸다. 다만 총칭도 **종별**은
      말한다: '법'이라 부른 조가 시행령의 조일 수는 없다(법령 명명 관례 —
      문서 무관). 보류 후보를 그 종별로 걸러, 같은 번호를 가졌을 뿐인 다른
      종의 문서가 후보에 서지 않게 한다. 이름 없이 쓴 남의 조("제279조" —
      이 문서는 제51조까지다)도 문서 사이에서 보류가 된다.

번호가 겹치면(본문 제1조와 부칙 제1조) **출발 구역과 조상을 가장 깊이 공유하는
쪽**을 고른다 — 본문에서 쓴 "제1조"는 본문의 제1조다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:                      # 실행 시 의존을 만들지 않는다 — 타입만
    from lawrag.core.rag.index import DocView

_UNITS = "편장절관"

# 본문 참조 — 자간 벌어짐(제 4 조)을 허용한다. 조는 의N(가지조문)까지 잡고,
# 뒤따르는 항·호·목 사슬은 _tail() 이 이어 읽는다: "제4조의2제3항제2호나목".
_ARTICLE = re.compile(r"제\s*(\d{1,3})\s*조(?:의\s*(\d{1,2}))?")
_MOK_LETTERS = "가나다라마바사아자차카타파하"   # hangul_jamo 제안자와 같은 열

# 조 뒤의 하강 토큰. 항·호는 공식 표기라 제- 를 요구하고, 목은 맨 숫자·글자
# ("2목"·"나목")로도 쓰여 열어 둔다 — (?!적) 은 "다목적" 방지. 표면형 ①·(2) 는
# 조에 붙어 있을 때만 참조다. 제목 괄호("제1조(목적)")는 숫자가 아니라 안 걸린다.
_TAIL = (
    ("항", re.compile(r"\s*제\s*(\d{1,2})\s*항")),
    ("호", re.compile(r"\s*제\s*(\d{1,3})\s*호")),
    ("목", re.compile(rf"\s*([{_MOK_LETTERS}]|\d{{1,2}})\s*목(?!적)")),
    ("항", re.compile(r"\s?([①-⑳])")),
    (None, re.compile(r"\s?\(\s*(\d{1,2})\s*\)")),
)
_DIVISION = re.compile(rf"제\s*(\d{{1,3}})\s*([{_UNITS}])")
_ANNEX = re.compile(r"(별표|별지)\s*(?:제\s*)?(\d{1,3})(?:\s*호)?")

# 다른 문서를 가리키는 앞말 — 「…」 인용부호, 또는 법령·규정 명사가 바로 앞에
# 붙은 경우("신탁법 제10조", "동법 제12조"). 두 단어 이름("근로자퇴직급여보장법
# 시행령")과 맨 "영"(이하 '영'이라 한다 — 시행령의 대용어)도 받는다. 맨 「」
# 닫힘은 제목이 창보다 길어 잘린 경우다 — 외부인 것만 알고 힌트는 없다.
_TITLE_WORD = r"[가-힣A-Za-z0-9·]{0,20}(?:법|법률|령|규칙|세칙|규정|약관|조례|정관|지침|고시)"
_SUFFIX_EXT = r"(?:시행령|시행규칙|시행세칙)"
_EXTERNAL = re.compile(
    rf"(?:「[^」]{{0,40}}」|」|(?:동|같은)\s*{_TITLE_WORD}|"
    rf"{_TITLE_WORD}\s+{_SUFFIX_EXT}|{_TITLE_WORD}|(?<![가-힣])영)\s*$")
_SELF_DOC = re.compile(rf"(?:이|본|위)\s+{_TITLE_WORD}\s*$")
_ANAPHORA = re.compile(r"^(?:동|같은)")   # 동법·같은 규정 — 이름이 아니라 대용어
# 이름 없이 종류만 부른 힌트 — "법 제87조"의 '법'은 어느 법의 이름이 아니라
# 그 문서가 앞서 정의한 대용어다("이하 '법'이라 한다"). 이름 대조로 확정하면
# 이름에 '법'이 든 아무 문서에나 붙는다 — 보류로 보내 판정이 정한다.
_GENERIC_HINT = re.compile(
    r"^(?:법|법률|영|령|규칙|세칙|규정|약관|조례|정관|지침|고시|시행령|시행규칙|시행세칙)+$")
_CONTEXT = 48                          # 앞말 창 — 「…」 최대 42자가 잘리지 않아야 한다
# 열거 연결사 — "제1항ㆍ제3항", "제129조부터 제132조까지"의 이음새.
# 연결사 앞의 단서·본문·전단·후단은 앞 참조의 부속 표현이다("법 제81조제1항
# 단서 및 제234조제4항" — 법령 관례, 문서 무관). 이 낱말이 사이에 끼어도
# 이음새가 끊기지 않아야 앞의 문서 이름('법')이 뒤 끝을 덮는다 — 끊기면
# 뒤 참조가 이 문서 안의 같은 번호 조로 잘못 붙는다(시행령에서 실측된 오연결).
_CONT = re.compile(r"\s*(?:(?:단서|본문|전단|후단)\s*)?(?:[ㆍ·,、]|및|또는|부터|와|과)\s*")

# 관계 술어 — 표면형 **바로 뒤** 문면이 간선의 의미를 말한다. 법령 관용구라
# 문서 무관이다(과적합 아님). 위임("대통령령으로 정하는")은 여기 없다 —
# 문면에 좌표가 없어 refs 가 아니라 위임 데이터(delegation.json)의 몫이다.
#   준용   "제N조를 준용한다" — 다른 규범을 변경 가해 적용 (보완 간선)
#   배제   "제N조에도 불구하고" · "제N조를 적용하지 아니한다" (부정 간선 —
#          놓치면 반대 답이 나가는 유일한 부류)
#   의제   "제N조를 위반한 것으로 본다" (간주)
#   수임   "제N조에서 '금융위원회가 정하여 고시하는 것'이란 …" — **위임 수신**
#          정의구문. 이 문장을 쓴 조문이 곧 그 위임의 구체 내용이다. 하위
#          법령·규정이 상위 조문을 되가리키는 유일한 좌표라(위임 데이터의
#          행정규칙 대상은 문서 수준뿐 — 실측 2026-08-13), 수직 체인 복원의
#          핵심 간선이다. 신호는 "에서" 바로 뒤의 여는 따옴표.
#   근거   "제N조에 따라/따른/의하여" (조건·근거 표시)
#   인용   그 밖 — 술어 없는 언급
# 열거("제1항ㆍ제3항을 준용")는 술어가 마지막 참조 뒤에만 붙으므로 앞 항들은
# 인용으로 남는다 — 보수적 분류(확실한 것만 라벨)를 택한다.
_REL_AFTER = (
    ("준용", re.compile(r"^\s*(?:[을를]\s*)?준용")),
    ("배제", re.compile(r"^\s*에도\s*불구하고")),
    ("배제", re.compile(r"^\s*(?:[은는을를이가]\s*)?적용(?:하지|되지)\s*아니")),
    ("의제", re.compile(r"^\s*(?:[은는을를이가]\s*)?.{0,12}?(?:으로|로)\s*본다")),
    # "제26조제1항제1호 **단서**에서 '세칙으로 정하는 경우'란" — 단서·본문·전단·후단이
    # 조 좌표와 '에서' 사이에 낄 수 있다(KRX 상장규정 시행세칙 실측, 2026-08-19).
    # 이걸 못 물면 규정→세칙 역방향 동반(floor_reception)이 영영 안 선다.
    ("수임", re.compile(r"^\s*(?:단서|본문|전단|후단)?\s*에서\s*[\"'“「『]")),
    ("근거", re.compile(r"^\s*에\s*(?:따라|따른|의하|의한|근거)")),
)


def rel_of(text: str, end: int) -> str:
    """참조 끝 위치의 뒷문면 → 관계 라벨. end 는 표면형(사슬 포함)의 끝."""
    tail = text[end:end + 20]
    for rel, pat in _REL_AFTER:
        if pat.match(tail):
            return rel
    return "인용"


# 구역 제목 읽기 — 본문 패턴과 같은 문법을 앞머리 고정으로 쓴다.
_LABEL_ARTICLE = re.compile(r"^제\s*(\d{1,3})\s*조(?:의\s*(\d{1,2}))?")
_LABEL_DIVISION = re.compile(rf"^제\s*(\d{{1,3}})\s*([{_UNITS}])")
_LABEL_ANNEX = re.compile(r"^(별표|별지)\s*(?:제\s*)?(\d{1,3})")
_LABEL_CLAUSE = re.compile(r"^제\s*(\d{1,2})\s*항")
_LABEL_HO = re.compile(r"^제\s*(\d{1,3})\s*호")
_LABEL_ENUM = re.compile(r"^\(?(\d{1,3})[.)](?!\d)")          # 1. · (1) · 1) — 호의 표기 계열
_LABEL_MOK = re.compile(rf"^([{_MOK_LETTERS}])\s*[.)]")       # 가. · 가) — 목의 표기 계열
_CIRCLED = {chr(0x2460 + i): i + 1 for i in range(20)}        # ① … ⑳


def _ord(token: str) -> int:
    """하강 토큰의 번호 — ①·가·2 를 같은 서수 좌표로 읽는다."""
    if token in _CIRCLED:
        return _CIRCLED[token]
    if token in _MOK_LETTERS:
        return _MOK_LETTERS.index(token) + 1
    return int(token)


def _tail(text: str, pos: int) -> tuple[tuple, int]:
    """조 매치 끝에서 하강 토큰을 잇는 대로 읽는다 — (사슬, 끝 위치)."""
    chain: list[tuple] = []
    while True:
        for unit, pat in _TAIL:
            m = pat.match(text, pos)
            if m:
                chain.append((unit, _ord(m.group(1))))
                pos = m.end()
                break
        else:
            return tuple(chain), pos


@dataclass
class Ref:
    """참조 출현 하나. key() 가 구역 제목의 키와 같은 좌표계다."""
    unit: str                  # "조" | 편장절관 | "별표" | "별지"
    n: int
    sub: Optional[int]         # 조의N — 가지조문
    chain: tuple               # 조 뒤 하강 사슬 — (("항",1),("호",2)) · 단위 불명이면 (None, 2)
    surface: str               # 문서에 실제로 쓰인 표면형
    start: int
    external: bool             # 다른 문서 참조 — 이 문서 안에서 잇지 않는다
    hint: str = ""             # 외부일 때 그 문서의 이름 단서 ("신탁법", "동법")
    quoted: bool = False       # 힌트가 「…」 로 명시된 제목인가 — 총칭('법')과 가른다

    def key(self) -> tuple:
        return (self.unit, self.n, self.sub)


def _doc_ref(text: str, start: int) -> tuple[bool, str, bool]:
    """참조 앞말 판독 — (외부인가, 문서 힌트, 인용된 제목인가). 이/본/위 가
    이끌면 이 문서 자신이다("이 약관 제6조")."""
    ctx = text[max(0, start - _CONTEXT):start]
    if _SELF_DOC.search(ctx):
        return False, "", False
    m = _EXTERNAL.search(ctx)
    if m is None:
        return False, "", False
    hint = m.group(0).strip()
    quoted = hint.startswith("「")
    if quoted:
        hint = hint.strip("「」")
    elif hint == "」":
        hint = ""                      # 잘린 긴 제목 — 외부인 것만 안다
    return True, hint, quoted


def find(text: str) -> list[Ref]:
    """한 문자열에서 참조 출현을 전부. 위치 순으로 돌려준다."""
    out: list[Ref] = []
    text = text or ""
    prev_end: Optional[int] = None
    prev_ext, prev_hint, prev_q = False, "", False
    for m in _ARTICLE.finditer(text):
        chain, end = _tail(text, m.end())
        ext, hint, quoted = _doc_ref(text, m.start())
        if (not ext and prev_ext and prev_end is not None
                and _CONT.fullmatch(text[prev_end:m.start()])):
            # "「형법」 제129조부터 제132조까지" — 앞의 이름이 뒤 끝도 덮는다
            ext, hint, quoted = True, prev_hint, prev_q
        out.append(Ref(unit="조", n=int(m.group(1)),
                       sub=int(m.group(2)) if m.group(2) else None,
                       chain=chain, surface=text[m.start():end], start=m.start(),
                       external=ext, hint=hint, quoted=quoted))
        base = out[-1]
        # 열거 연속 — "제19조제1항ㆍ제3항", "제2조제6호가목ㆍ다목ㆍ마목".
        # 연결사 뒤 조 없는 항·호·목 토큰은 같은 조의 다른 가지다. 같은 단위는
        # 갈아 끼우고 아랫단은 이어 읽는다. "같은 조 …" 는 토큰이 아니라 멈춘다.
        pos = end
        while True:
            cm = _CONT.match(text, pos)
            if not cm or _ARTICLE.match(text, cm.end()):
                break                      # 다음 조 참조는 제 몫 — 저기서 잡힌다
            tok = None
            for unit, pat in _TAIL[:3]:    # 항·호·목 — 표면형(①·(2))은 열거하지 않는다
                tm = pat.match(text, cm.end())
                if tm:
                    tok = (unit, _ord(tm.group(1)), tm.end())
                    break
            if tok is None:
                break
            unit, num, tend = tok
            more, tend = _tail(text, tend)
            cut = next((i for i, (u, _) in enumerate(chain) if u == unit),
                       len(chain))
            out.append(Ref(unit="조", n=base.n, sub=base.sub,
                           chain=chain[:cut] + ((unit, num),) + more,
                           surface=text[cm.end():tend], start=cm.end(),
                           external=ext, hint=hint, quoted=quoted))
            pos = tend
        prev_end, prev_ext, prev_hint, prev_q = pos, ext, hint, quoted
    for m in _DIVISION.finditer(text or ""):
        ext, hint, quoted = _doc_ref(text, m.start())
        out.append(Ref(unit=m.group(2), n=int(m.group(1)), sub=None, chain=(),
                       surface=m.group(0), start=m.start(),
                       external=ext, hint=hint, quoted=quoted))
    for m in _ANNEX.finditer(text or ""):
        ext, hint, quoted = _doc_ref(text, m.start())
        out.append(Ref(unit=m.group(1), n=int(m.group(2)), sub=None, chain=(),
                       surface=m.group(0), start=m.start(),
                       external=ext, hint=hint, quoted=quoted))
    return sorted(out, key=lambda r: r.start)


def label_key(label: str) -> Optional[tuple]:
    """구역 제목 → 참조 키. "제4조(신탁의 설정)" → ("조", 4, None),
    "①" → ("항", 1, None). 읽을 수 없으면 None — 그 구역은 번호로 지목되지 않는다."""
    t = (label or "").strip()
    if not t:
        return None
    if t[0] in _CIRCLED:
        return ("항", _CIRCLED[t[0]], None)
    m = _LABEL_ARTICLE.match(t)
    if m:
        return ("조", int(m.group(1)), int(m.group(2)) if m.group(2) else None)
    m = _LABEL_DIVISION.match(t)
    if m:
        return (m.group(2), int(m.group(1)), None)
    m = _LABEL_ANNEX.match(t)
    if m:
        return (m.group(1), int(m.group(2)), None)
    m = _LABEL_CLAUSE.match(t)
    if m:
        return ("항", int(m.group(1)), None)
    m = _LABEL_HO.match(t) or _LABEL_ENUM.match(t)
    if m:
        return ("호", int(m.group(1)), None)
    m = _LABEL_MOK.match(t)
    if m:
        return ("목", _MOK_LETTERS.index(m.group(1)) + 1, None)
    return None


def _key_map(view: "DocView") -> dict[tuple, list]:
    """참조 키 → 그 번호를 제목에 단 구역들. surface 를 먼저 읽는다."""
    out: dict[tuple, list] = {}
    for n in view.nodes:
        for label in (n.get("surface"), n.get("title")):
            k = label_key(label or "")
            if k:
                out.setdefault(k, []).append(n.get("id"))
                break
    return out


def _fold_name(name: str) -> str:
    """문서명 → 대조용 정규형. 확장자를 떼고 공백을 접는다."""
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", (name or "").strip())
    return re.sub(r"\s+", "", base).casefold()


# 종별 접미 — 이름·힌트 끝의 법형식 낱말을 정규형으로 접는다. 시행령·령·영은
# 한 종이고, 법·법률이 한 종이다. "…법률 시행령" 은 끝이 시행령이라 령으로
# 읽힌다 — 접미만 보면 중간의 '법률'에 속지 않는다.
_KIND_CANON = {"법": "법", "법률": "법", "영": "령", "령": "령", "시행령": "령",
               "규칙": "규칙", "시행규칙": "규칙", "세칙": "세칙", "시행세칙": "세칙",
               "규정": "규정", "약관": "약관", "조례": "조례", "정관": "정관",
               "지침": "지침", "고시": "고시"}
_KIND_SUFFIX = sorted(_KIND_CANON, key=len, reverse=True)


def _kind(name: str) -> str:
    """이름·힌트 → 종별 정규형("법"·"령"·"규칙"…). 못 읽으면 ""."""
    t = _fold_name(name)
    for suf in _KIND_SUFFIX:
        if t.endswith(suf):
            return _KIND_CANON[suf]
    return ""


def _chain(view: "DocView", nid) -> list:
    """뿌리부터 nid 까지의 조상 사슬."""
    out, seen = [], set()
    while nid is not None and nid not in seen:
        seen.add(nid)
        out.append(nid)
        nid = (view.by_id.get(nid) or {}).get("parent")
    return list(reversed(out))


def _nearest(view: "DocView", cands: list, src_chain: list,
             children: Optional[dict] = None, chain: tuple = ()) -> int:
    """후보가 여럿이면 출발 구역과 조상을 가장 깊이 공유하는 쪽 — 본문의
    "제1조"는 본문의 제1조지 부칙의 제1조가 아니다. 조상 공유가 동률이면
    **사슬이 실존하는 쪽** — "제2조제6호가목"이 본문과 개정문 양쪽의 제2조에
    걸리면, 6호가목을 실제로 가진 제2조가 그 제2조다. 그래도 동률이면 번호가
    가까운 쪽."""
    def score(nid: int) -> tuple:
        ch = _chain(view, nid)
        shared = 0
        for a, b in zip(src_chain, ch):
            if a != b:
                break
            shared += 1
        reach = _descend(view, children, nid, chain)[1] if chain else 0
        src = src_chain[-1] if src_chain else nid
        return (-shared, -reach, abs(nid - src))
    return min(cands, key=score)


def _children(view: "DocView") -> dict:
    """부모 → 자식 목록."""
    out: dict = {}
    for n in view.nodes:
        if n.get("parent") is not None:
            out.setdefault(n.get("parent"), []).append(n.get("id"))
    return out


def _sub_key(view: "DocView", nid) -> Optional[tuple]:
    """구역 제목을 하강 좌표로 — ("항"|"호"|"목", 번호). 그 층이 아니면 None."""
    n = view.by_id.get(nid) or {}
    for label in (n.get("surface"), n.get("title")):
        k = label_key(label or "")
        if k and k[0] in ("항", "호", "목"):
            return (k[0], k[1])
    return None


def _step(view: "DocView", children: dict, nid: int, unit: Optional[str],
          n: int, depth_max: int = 3) -> Optional[int]:
    """토큰 하나만큼 내려간다 — BFS 라 가장 얕은 일치가 이긴다.

    단위를 알면 그 표기 계열을 먼저 찾고, 계열 자체가 없는 문서(항을 (1) 로
    쓰는 약관)에서만 서수로 무른다. 계열이 있는데 그 번호가 없으면 None —
    없는 것은 없는 것이다, 조에 머문다.
    """
    frontier, seen_family, loose = [nid], False, None
    for _ in range(depth_max):
        nxt = []
        for cur in frontier:
            for kid in children.get(cur, []):
                k = _sub_key(view, kid)
                if k:
                    if k[1] == n:
                        if unit is None or k[0] == unit:
                            return kid
                        if loose is None:
                            loose = kid
                    if unit is not None and k[0] == unit:
                        seen_family = True
                nxt.append(kid)
        frontier = nxt
    return None if seen_family else loose


def _descend(view: "DocView", children: dict, nid: int,
             chain: tuple) -> tuple[int, int]:
    """사슬을 실존하는 데까지 따라 내려간다 — (멈춘 구역, 내려간 깊이).
    깊이는 후보 동률을 가르는 데도 쓰인다(_nearest)."""
    cur, depth = nid, 0
    for unit, n in chain:
        nxt = _step(view, children, cur, unit, n)
        if nxt is None:
            break
        cur, depth = nxt, depth + 1
    return cur, depth


# 부칙의 개정·폐지 조 — 여기서 부르는 조번호는 **남의 법** 것이다.
#   "금융감독기구설치법 제17조제4호 중 '선물시장'을 '파생상품시장'으로 한다"
# 이 제17조는 개정 **대상** 법률의 제17조이지 이 문서의 제17조가 아니다. 같은
# 문서 좌표로 해소하면 번호만 같은 엉뚱한 조에 붙는다 — 실측(2026-08-16):
# 문서 안 간선 16,334개 중 이 출발지가 2,987개(18.3%)였고, 자본시장법 부칙
# 제42조의 '제17조'는 같은 부칙의 「신탁의 회계감사에 관한 경과조치」에 붙어
# 있었다. §2 함정 ②(본문·부칙 번호 중복)보다 나쁘다: 그쪽은 후보가 여럿인
# 문제지만 이쪽은 **정답이 이 문서에 아예 없다**.
#
# 대상 문서로의 cross 해소는 별건이다 — 대상 법령명이 조가 아니라 그 항의
# 머리("…법률 일부를 다음과 같이 개정한다")에 있어 항 단위 스코프가 필요하다.
# 여기서는 **틀린 간선을 만들지 않는 것**까지만 한다 (조용한 오답 금지).
_AMEND_TITLES = ("다른 법령의 개정", "다른 법률의 개정",
                 "다른 법령의 폐지", "다른 법률의 폐지")


def _is_amendment_clause(view: "DocView", nid) -> bool:
    path = view.path(nid) or ""
    return "부칙" in path and any(t in path for t in _AMEND_TITLES)


def resolve(view: "DocView") -> list[dict]:
    """문서 안의 참조 간선 — [{"src","dst","surface","block"}].

    src 는 참조가 쓰인 블록을 덮는 가장 깊은 구역, dst 는 제목이 그 번호를
    다는 구역이다. 자기 자신·조상/자손으로의 참조는 버린다. 부칙 개정·폐지
    조에서 출발하는 참조는 아예 만들지 않는다(_is_amendment_clause 머리).
    """
    by_key = _key_map(view)
    children = _children(view)

    edges: list[dict] = []
    seen: set[tuple] = set()
    for b in view.blocks:
        src = view.owner(b.get("idx"))
        if src is None:
            continue
        if _is_amendment_clause(view, src.get("id")):
            continue
        src_chain = _chain(view, src.get("id"))
        for ref in find(b.get("text") or ""):
            if ref.external:
                continue
            cands = by_key.get(ref.key())
            if not cands:
                continue
            dst = _nearest(view, cands, src_chain, children, ref.chain)
            if ref.chain:
                dst = _descend(view, children, dst, ref.chain)[0]
            if dst in src_chain or src.get("id") in _chain(view, dst):
                continue
            pair = (src.get("id"), dst)
            if pair in seen:
                continue
            seen.add(pair)
            text = b.get("text") or ""
            edges.append({"src": src.get("id"), "dst": dst,
                          "surface": ref.surface.strip(), "block": b.get("idx"),
                          "rel": rel_of(text, ref.start + len(ref.surface))})
    return edges


# 대용어 자기 선언 — "「자본시장과 금융투자업에 관한 법률」(이하 "법"이라 한다)".
# 저자가 이 문서 스코프에서 그 말의 뜻을 정의한 것이다 — 발명이 아니라 전사라
# 이름 대조와 같은 급의 확정 근거다. 약칭 선언("이하 "지배구조법"이라 한다")도
# 같은 문법이라 함께 잡힌다. 같은 말의 재선언은 첫 것이 이긴다(첫머리 정의가 정본).
_DECL_RE = re.compile(
    r"「([^」]{2,40})」[^「」]{0,30}?이하\s*[\"'“]?\s*([가-힣A-Za-z]{1,8})\s*"
    r"[\"'”]?\s*(?:이|이라|라)\s*한다")


def declared_aliases(view: "DocView") -> dict[str, str]:
    """문서가 선언한 대용어 → 선언된 문서명 (표면 그대로)."""
    out: dict[str, str] = {}
    for b in view.blocks:
        for m in _DECL_RE.finditer(b.get("text") or ""):
            out.setdefault(_fold_name(m.group(2)), m.group(1).strip())
    return out


_ALIAS_CACHE: dict = {"sig": None, "map": {}}
_COMPOUND_SUFFIX = ("시행세칙", "시행규칙", "시행령")


def alias_map() -> dict[str, str]:
    """data/aliases.json — 관용 약칭 → 정식 문서명 (양쪽 다 접힌 형태).

    선언(declared_aliases)이 **문서 안의** 지식이라면 이것은 **실무 공동체의**
    지식이다 — 법제처가 고시하는 공식 약칭 관례("자본시장법"·"금소법")를 사람이
    채워 두면, 선언 없이 약칭으로 인용하는 문서(협회 모범기준·내규류)의 참조가
    결정론으로 이어진다. 코드는 사전을 읽을 뿐 항목을 모른다(지식은 데이터로)."""
    from lawrag.core.rag.index import store_path
    f = store_path().parent / "aliases.json"
    try:
        sig = f.stat().st_mtime_ns
    except OSError:
        return {}
    if _ALIAS_CACHE["sig"] != sig:
        try:
            raw = json.loads(f.read_text("utf-8"))
        except Exception:
            raw = {}
        _ALIAS_CACHE.update(sig=sig, map={_fold_name(k): _fold_name(v)
                                          for k, v in raw.items()
                                          if isinstance(v, str)})
    return _ALIAS_CACHE["map"]


def _alias_official(hint_folded: str) -> str:
    """약칭(접힘) → 정식 이름(접힘). "금소법시행령"처럼 종별 접미가 붙은 합성은
    접미를 떼어 머리를 사전에서 찾고 정식 이름에 접미를 되붙인다 — "…법률 시행령"
    문서명이 접히면 정확히 그 꼴이다. 사전에 없으면 ""."""
    am = alias_map()
    if hint_folded in am:
        return am[hint_folded]
    for suf in _COMPOUND_SUFFIX:
        head = hint_folded[:-len(suf)]
        if hint_folded.endswith(suf) and head in am:
            return am[head] + suf
    return ""


def cross_resolve(docs: dict, declare: bool = True) -> tuple[list, list]:
    """문서 사이의 참조 — (확정 간선, 보류 목록). declare=False 면 선언
    별칭 확정을 끈다(엔진 스위치) — 그 참조들은 보류로 내려간다.

    확정은 결정론이 닿는 데까지만: 힌트가 문서명과 맞고(「수수료규정」 ⊂
    수수료규정.pdf) 대상 구역이 하나로 떨어질 때. 제 이름을 부른 참조
    ("신탁약관 제4조" 가 신탁약관 안에 — resolve 는 외부로 보고 넘긴 것)도
    여기서 제자리를 찾는다.

    보류는 후보가 있는데 하나로 못 정한 것이다 — 대용어(동법·같은 규정),
    이름 없이 잘린 제목, 여러 문서·구역에 걸린 번호. 닫힌 후보 목록과 참조가
    쓰인 원문을 실어 돌려주므로, judge.judge()(LLM)나 사람이 그대로 고를 수
    있다. 후보가 아예 없으면 조용히 버린다 — 그 문서가 아직 저장소에 없다.
    """
    keymaps = {d: _key_map(v) for d, v in docs.items()}
    kidmaps = {d: _children(v) for d, v in docs.items()}
    names = {d: _fold_name(v.name) for d, v in docs.items()}
    decls = {d: declared_aliases(v) for d, v in docs.items()}
    # 문서마다 제 조 번호의 지붕 — 이보다 큰 번호는 이 문서의 조가 아니다
    own_max = {d: max((k[1] for k in km if k[0] == "조"), default=0)
               for d, km in keymaps.items()}
    edges: list[dict] = []
    pending: list[dict] = []
    seen_e: set[tuple] = set()
    seen_p: set[tuple] = set()

    for doc_id, v in docs.items():
        for b in v.blocks:
            src = v.owner(b.get("idx"))
            if src is None:
                continue
            src_id = src.get("id")
            text = b.get("text") or ""
            for ref in find(text):
                if (not ref.external and ref.unit == "조"
                        and own_max[doc_id] and ref.n > own_max[doc_id]):
                    # 이름 없이 쓴 남의 조("제279조" — 이 문서는 제51조까지다).
                    # resolve 가 못 이은 것을 여기서 이름 없는 외부로 받는다.
                    ref.external, ref.hint = True, ""
                if not ref.external:
                    continue
                key = ref.key()
                hint = _fold_name(ref.hint)
                named = (bool(hint) and not _ANAPHORA.match(ref.hint)
                         and (ref.quoted or not _GENERIC_HINT.match(hint)))
                # 선언 별칭 — 이 문서가 "이하 '법'이라 한다"로 그 말을 정의했다.
                # 동법·같은 법(대용어의 대용어 — 선행 인용 문맥)은 선언으로
                # 확정하지 않는다: "「수수료규정」 … 동법"의 동법은 수수료규정이다.
                decl = (decls[doc_id].get(hint)
                        if declare and hint and not _ANAPHORA.match(ref.hint)
                        else None)
                decl_hit = False
                if decl is not None:
                    dn = _fold_name(decl)
                    # 정확 일치가 있으면 그것만 — named 분기의 2026-08-19 수리와
                    # 같은 병이 여기 남아 있었다: 부분 일치까지 넣으면 선언된
                    # 법("자본시장법")의 조가 법·시행령 둘 다의 후보가 되어
                    # "후보 둘 → 보류"가 된다 (실측 2026-08-20: 보류 5,610건 중
                    # 1,663건이 법+그 시행령 짝).
                    exact = [d for d, nm in names.items()
                             if d != doc_id and nm and nm == dn]
                    tgts = exact or [d for d, nm in names.items()
                                     if d != doc_id and nm and (dn in nm or nm in dn)]
                    dc = [(d, nid) for d in tgts for nid in keymaps[d].get(key, [])]
                    if dc:
                        cands, decl_hit = dc, True
                # 사전 별칭 — 선언이 없는 문서의 관용 약칭("금소법"·"외부감사법").
                # 정확 일치만 받는다: 사전 값이 정식 이름 전체이기 때문이다.
                alias_hit = False
                if not decl_hit and named:
                    ali = _alias_official(hint)
                    if ali:
                        ac = [(d, nid) for d, nm in names.items()
                              if d != doc_id and nm == ali
                              for nid in keymaps[d].get(key, [])]
                        if ac:
                            cands, alias_hit = ac, True
                if decl_hit or alias_hit:
                    pass
                elif named and (hint in names[doc_id] or names[doc_id] in hint):
                    # 제 이름을 부른 참조 — 이 문서 자신에서 찾는다
                    cands = [(doc_id, nid) for nid in keymaps[doc_id].get(key, [])]
                elif named:
                    # 정확 일치가 있으면 그것만 — 「소득세법」은 소득세법이지 소득세법
                    # 시행령이 아니다. 부분 일치까지 후보에 넣으면 법·시행령이 둘 다
                    # 그 조를 가져 "후보 둘 → 보류"가 된다 (2026-08-19 실측: 보류
                    # 6,497건 중 1,696건이 이 모양 — 「자본시장과 금융투자업에 관한
                    # 법률」 351 · 「소득세법」 324 …). 정확 일치가 없을 때만 부분
                    # 일치(잘린 제목·약칭)로 넓힌다.
                    exact_docs = [d for d, nm in names.items()
                                  if d != doc_id and nm and nm == hint]
                    pool = exact_docs or [d for d, nm in names.items()
                                          if d != doc_id and nm and (hint in nm or nm in hint)]
                    cands = [(d, nid) for d in pool for nid in keymaps[d].get(key, [])]
                else:
                    # 대용어·잘린 제목 — 이름으로 못 정한다. 번호를 가진 문서 전부가
                    # 후보다. 다만 맨 총칭("법 제238조"의 '법')은 종별을 말한다 —
                    # 법이라 부른 조가 시행령의 조일 수는 없으니 후보를 종별로
                    # 거른다. 동법·같은 규정 대용어는 안 거른다 — 선행 인용이
                    # 무엇이었는지는 문맥이라 판정(judge) 몫이고, 실제 문서는
                    # 「수수료규정」 뒤에 '동법'을 쓰기도 한다.
                    k = _kind(hint) if hint and not _ANAPHORA.match(ref.hint) else ""
                    cands = [(d, nid) for d in docs if d != doc_id
                             and (not k or _kind(names[d]) == k)
                             for nid in keymaps[d].get(key, [])]
                cands = [c for c in cands if c != (doc_id, src_id)]
                if not cands:
                    continue
                if (named or decl_hit or alias_hit) and len(cands) == 1:
                    dst_doc, dst = cands[0]
                    if ref.chain:
                        dst = _descend(docs[dst_doc], kidmaps[dst_doc], dst,
                                       ref.chain)[0]
                    ek = (doc_id, src_id, dst_doc, dst)
                    if ek in seen_e:
                        continue
                    seen_e.add(ek)
                    edges.append({"src_doc": doc_id, "src": src_id,
                                  "dst_doc": dst_doc, "dst": dst,
                                  "surface": ref.surface.strip(), "hint": ref.hint,
                                  "block": b.get("idx"),
                                  "via": ("선언" if decl_hit
                                          else "별칭" if alias_hit else "이름대조"),
                                  "rel": rel_of(text, ref.start + len(ref.surface))})
                else:
                    pk = (doc_id, src_id, key, ref.hint)
                    if pk in seen_p:
                        continue
                    seen_p.add(pk)
                    lo = max(0, ref.start - 60)
                    pending.append({
                        "src_doc": doc_id, "src": src_id,
                        "surface": ref.surface.strip(), "hint": ref.hint,
                        "key": list(key), "block": b.get("idx"),
                        "context": text[lo:ref.start + len(ref.surface) + 40],
                        "rel": rel_of(text, ref.start + len(ref.surface)),
                        "candidates": [{"doc_id": d, "node": n} for d, n in cands]})
    return edges, pending
