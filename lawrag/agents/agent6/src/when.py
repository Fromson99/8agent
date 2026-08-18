"""조건부 활성화 DSL — 항목 스펙의 `when` 을 평가한다 (AGENT6 §3·§5-1).

§3 표의 when 은 자연어("항상", "age≥65", "ELS류")로 적혀 있어 그대로는 평가할 수 없다.
그래서 아주 작은 문법을 정의하고 파서를 손으로 짠다. **eval() 은 쓰지 않는다** —
항목 스펙은 데이터지 코드가 아니고, 데이터가 임의 코드로 실행되는 순간 결정론(§0 원칙 1)이
깨진다. 문법이 좁아야 스펙 작성자가 무엇을 쓸 수 있는지도 명확해진다.

문법:
    expr    := or_expr
    or_expr := and_expr ("or" and_expr)*
    and_expr:= primary ("and" primary)*
    primary := "(" expr ")" | "always" | comparison
    comparison := IDENT (("=="|"!="|">="|"<="|">"|"<") literal
                        | ["not"] "in" "[" literal ("," literal)* "]")
    literal := 수 | true | false | 맨낱말(한글 포함) | "따옴표 문자열"

예:
    always
    is_high_difficulty == true
    customer_age >= 65
    product_type in [ELS, ELB, DLS, DLB]
    is_high_difficulty == true or customer_age >= 65
    risk_profile != 적합

세 값 논리를 쓰는 이유 (이 파일의 핵심 설계 결정)
--------------------------------------------------
메타(product_type·customer_age…)는 **선택 입력**이다. 전사만 올라오고 상품·고객 메타가
비어 있는 호출이 실제로 있다. 이때 `customer_age >= 65` 를 조용히 거짓으로 접으면
C-18(숙려기간)·E-27(고령자 보호)이 통째로 사라진다 — 리포트에는 아무 흔적도 남지 않고,
점검하지 않은 항목이 점검한 것처럼 보인다. 이것이 §0 원칙 4(비대칭 임계)가 금지하는
정확히 그 실패다: 거짓 FAIL 비용(PB 재설명 몇 분) ≪ 거짓 PASS 비용(불완전판매 통과).

그래서 평가 결과는 ACTIVE / INACTIVE / **UNKNOWN** 세 값이고, UNKNOWN 은
    (a) 보수적으로 **활성**시키고(`.active` 가 참),
    (b) 이유("메타 부족: customer_age")를 남겨 리포트에 싣고,
    (c) 판정 confidence 를 한 단계 낮춘다(`.confidence_penalty`).
"모르는 것을 아는 것처럼" 처리하지 않는다는 규율(§0 조용한 실패 금지)의 구체형이다.

and/or 는 Kleene 3치 논리를 따른다 — UNKNOWN 이 결과를 바꾸지 못하는 곳에서는 사라진다.
    `is_high_difficulty == true or customer_age >= 65` 에서 나이가 67로 확정이면
    is_high_difficulty 가 없어도 결과는 ACTIVE 이고 감점도 없다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Optional, Union

ACTIVE = "ACTIVE"
INACTIVE = "INACTIVE"
UNKNOWN = "UNKNOWN"

State = Literal["ACTIVE", "INACTIVE", "UNKNOWN"]

COMPARISONS = ("==", "!=", ">=", "<=", ">", "<")
KEYWORDS = frozenset({"always", "and", "or", "in", "not", "true", "false"})

# 필드명은 ASCII 식별자로 제한한다. 메타 키는 코드·JSON 이 함께 쓰는 이름이므로
# 한글 필드명을 허용하면 STT 파이프라인 쪽 키와 조용히 어긋난다.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WhenSyntaxError(ValueError):
    """when 문법 오류. **로드 시점에** 던진다 — 런타임까지 미루면 판정 도중에 터진다."""


# --- 토큰 ------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""(?P<space>\s+)
      | (?P<op>==|!=|>=|<=|>|<)
      | (?P<punct>[\[\],()])
      | (?P<string>"[^"]*"|'[^']*')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<word>[^\s\[\],()=!<>"']+)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Tok:
    kind: str          # op | punct | string | number | word | end
    text: str
    pos: int


def _tokenize(src: str) -> list[_Tok]:
    toks: list[_Tok] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:      # 문법에 없는 글자 — 조용히 건너뛰지 않는다
            raise WhenSyntaxError(f"when 식의 {pos}번째 글자 '{src[pos]}' 를 읽을 수 없습니다: {src!r}")
        kind = m.lastgroup or ""
        if kind != "space":
            toks.append(_Tok(kind, m.group(), pos))
        pos = m.end()
    toks.append(_Tok("end", "", len(src)))
    return toks


# --- 구문 트리 (불변 — 같은 식은 언제 평가해도 같다) -------------------------

@dataclass(frozen=True)
class Always:
    def __str__(self) -> str:
        return "always"


@dataclass(frozen=True)
class Compare:
    field: str
    op: str
    value: Any

    def __str__(self) -> str:
        return f"{self.field} {self.op} {_lit_str(self.value)}"


@dataclass(frozen=True)
class In:
    field: str
    values: tuple
    negated: bool = False

    def __str__(self) -> str:
        kw = "not in" if self.negated else "in"
        return f"{self.field} {kw} [{', '.join(_lit_str(v) for v in self.values)}]"


@dataclass(frozen=True)
class BoolOp:
    op: str            # and | or
    left: "Expr"
    right: "Expr"

    def __str__(self) -> str:
        return f"({self.left} {self.op} {self.right})"


Expr = Union[Always, Compare, In, BoolOp]


def _lit_str(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


# --- 파서 (재귀 하강) -------------------------------------------------------

class _Parser:
    def __init__(self, src: str) -> None:
        self.src = src
        self.toks = _tokenize(src)
        self.i = 0

    # -- 도구
    def peek(self) -> _Tok:
        return self.toks[self.i]

    def next(self) -> _Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def at_keyword(self, kw: str) -> bool:
        t = self.peek()
        return t.kind == "word" and t.text.lower() == kw

    def fail(self, msg: str, tok: Optional[_Tok] = None) -> None:
        t = tok or self.peek()
        where = f"위치 {t.pos}" + (f" ('{t.text}')" if t.text else " (식의 끝)")
        raise WhenSyntaxError(f"when 식 {where}: {msg} — {self.src!r}")

    # -- 규칙
    def parse(self) -> Expr:
        if not self.toks or self.toks[0].kind == "end":
            raise WhenSyntaxError("when 식이 비어 있습니다 (조건이 없으면 'always' 라고 적는다)")
        node = self.or_expr()
        if self.peek().kind != "end":
            self.fail("여기서 식이 끝나야 합니다")
        return node

    def or_expr(self) -> Expr:
        node = self.and_expr()
        while self.at_keyword("or"):
            self.next()
            node = BoolOp("or", node, self.and_expr())
        return node

    def and_expr(self) -> Expr:
        node = self.primary()
        while self.at_keyword("and"):
            self.next()
            node = BoolOp("and", node, self.primary())
        return node

    def primary(self) -> Expr:
        t = self.peek()
        if t.kind == "punct" and t.text == "(":
            self.next()
            node = self.or_expr()
            close = self.next()
            if close.kind != "punct" or close.text != ")":
                self.fail("닫는 괄호가 없습니다", close)
            return node
        if self.at_keyword("always"):
            self.next()
            return Always()
        return self.comparison()

    def comparison(self) -> Expr:
        t = self.next()
        if t.kind != "word" or t.text.lower() in KEYWORDS:
            self.fail("필드명이 와야 합니다", t)
        if not _IDENT_RE.match(t.text):
            self.fail(f"필드명 '{t.text}' 은 영문 식별자여야 합니다 (예: customer_age)", t)
        field = t.text

        nxt = self.peek()
        if nxt.kind == "word" and nxt.text.lower() in ("in", "not"):
            negated = nxt.text.lower() == "not"
            self.next()
            if negated:
                if not self.at_keyword("in"):
                    self.fail("'not' 다음에는 'in' 이 와야 합니다")
                self.next()
            return In(field, tuple(self.value_list()), negated)

        if nxt.kind != "op":
            self.fail(f"'{field}' 다음에 비교연산자({', '.join(COMPARISONS)}) 나 in 이 와야 합니다")
        op = self.next().text
        return Compare(field, op, self.literal())

    def value_list(self) -> list[Any]:
        t = self.next()
        if t.kind != "punct" or t.text != "[":
            self.fail("in 다음에는 [ 로 시작하는 목록이 와야 합니다", t)
        values: list[Any] = []
        if self.peek().kind == "punct" and self.peek().text == "]":
            self.fail("in 목록이 비어 있습니다 — 아무것도 활성화하지 못합니다")
        while True:
            values.append(self.literal())
            t = self.next()
            if t.kind == "punct" and t.text == "]":
                return values
            if t.kind != "punct" or t.text != ",":
                self.fail("목록의 값 사이에는 , 가 와야 합니다", t)

    def literal(self) -> Any:
        t = self.next()
        if t.kind == "number":
            return float(t.text) if "." in t.text else int(t.text)
        if t.kind == "string":
            return t.text[1:-1]
        if t.kind == "word":
            low = t.text.lower()
            if low in ("true", "false"):
                return low == "true"
            if low in KEYWORDS:
                self.fail(f"'{t.text}' 는 예약어라 값으로 쓸 수 없습니다", t)
            return t.text
        self.fail("값이 와야 합니다", t)
        raise AssertionError                      # 도달 불가 (fail 이 예외를 던진다)


def parse(source: str) -> Expr:
    """when 문자열 → 구문 트리. 문법 오류는 여기서 예외로 터진다."""
    return _Parser((source or "").strip()).parse()


def fields(expr: Union[str, Expr]) -> set[str]:
    """식이 참조하는 메타 필드 이름들 — 어떤 메타를 받아야 하는지 스펙에서 뽑을 때 쓴다."""
    node = parse(expr) if isinstance(expr, str) else expr
    if isinstance(node, (Compare, In)):
        return {node.field}
    if isinstance(node, BoolOp):
        return fields(node.left) | fields(node.right)
    return set()


# --- 평가 ------------------------------------------------------------------

@dataclass(frozen=True)
class WhenResult:
    """세 값 판정 결과.

    `active` 는 **INACTIVE 가 아닌 모든 것**이다 — UNKNOWN 은 활성 쪽에 붙는다(§0 원칙 4).
    """
    state: State
    reasons: tuple[str, ...] = ()
    source: str = ""

    @property
    def active(self) -> bool:
        return self.state != INACTIVE

    @property
    def unknown(self) -> bool:
        return self.state == UNKNOWN

    @property
    def confidence_penalty(self) -> int:
        """confidence 를 몇 단계 낮출 것인가. 메타가 모자라 활성된 항목은 한 단계."""
        return 1 if self.state == UNKNOWN else 0

    def reason_text(self) -> str:
        """리포트의 inactive_reason·비고에 그대로 넣는 한 줄."""
        if self.state == INACTIVE:
            return f"조건 미충족: {self.source}"
        if self.state == UNKNOWN:
            return "보수적 활성 — " + "; ".join(self.reasons)
        return f"조건 충족: {self.source}"


def _norm_text(v: Any) -> str:
    return unicodedata.normalize("NFKC", str(v)).strip().casefold()


_TRUE_WORDS = {"true", "y", "yes", "예", "참", "1"}
_FALSE_WORDS = {"false", "n", "no", "아니오", "아니요", "거짓", "0"}


def _as_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    t = _norm_text(v)
    if t in _TRUE_WORDS:
        return True
    if t in _FALSE_WORDS:
        return False
    return None


def _as_num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None                     # 참/거짓을 1/0 으로 몰래 바꾸지 않는다
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(_norm_text(v))
    except (TypeError, ValueError):
        return None


def _eq(raw: Any, lit: Any) -> Union[bool, str]:
    """같은가? 판정 불가면 이유 문자열을 돌려준다(UNKNOWN 으로 올라간다)."""
    if isinstance(lit, bool):
        b = _as_bool(raw)
        if b is None:
            return f"메타 타입 불일치: {raw!r} 을 참/거짓으로 읽을 수 없습니다"
        return b is lit
    if isinstance(lit, (int, float)):
        n = _as_num(raw)
        if n is None:
            return f"메타 타입 불일치: {raw!r} 을 수로 읽을 수 없습니다"
        return n == float(lit)
    return _norm_text(raw) == _norm_text(lit)


def _tri(cond: bool) -> State:
    return ACTIVE if cond else INACTIVE


def _eval(node: Expr, meta: Mapping[str, Any]) -> tuple[State, list[str]]:
    if isinstance(node, Always):
        return ACTIVE, []

    if isinstance(node, BoolOp):
        ls, lr = _eval(node.left, meta)
        rs, rr = _eval(node.right, meta)
        if node.op == "or":
            state = (ACTIVE if ACTIVE in (ls, rs)
                     else INACTIVE if (ls, rs) == (INACTIVE, INACTIVE) else UNKNOWN)
        else:
            state = (INACTIVE if INACTIVE in (ls, rs)
                     else ACTIVE if (ls, rs) == (ACTIVE, ACTIVE) else UNKNOWN)
        # 결과가 확정된 가지의 "메타 부족"은 결과를 바꾸지 못했으므로 감점 사유가 아니다
        return state, (lr + rr if state == UNKNOWN else [])

    field = node.field
    raw = meta.get(field)
    if field not in meta or raw is None:
        return UNKNOWN, [f"메타 부족: {field}"]

    if isinstance(node, In):
        results = [_eq(raw, v) for v in node.values]
        bad = next((r for r in results if isinstance(r, str)), None)
        if bad is not None:
            return UNKNOWN, [f"{field}: {bad}"]
        hit = any(results)
        return _tri(hit != node.negated), []

    # Compare
    if node.op in ("==", "!="):
        r = _eq(raw, node.value)
        if isinstance(r, str):
            return UNKNOWN, [f"{field}: {r}"]
        return _tri(r if node.op == "==" else not r), []

    a, b = _as_num(raw), _as_num(node.value)
    if a is None or b is None:
        return UNKNOWN, [f"{field}: 메타 타입 불일치 — "
                         f"{raw!r} {node.op} {node.value!r} 를 수로 비교할 수 없습니다"]
    cmp_ = {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[node.op]
    return _tri(cmp_), []


def _as_mapping(meta: Any) -> Mapping[str, Any]:
    if meta is None:
        return {}
    if isinstance(meta, Mapping):
        return meta
    if hasattr(meta, "model_dump"):                 # pydantic (TranscriptMeta)
        return meta.model_dump()
    if hasattr(meta, "__dict__"):
        return vars(meta)
    raise TypeError(f"메타를 사전으로 읽을 수 없습니다: {type(meta).__name__}")


def evaluate(expr: Union[str, Expr], meta: Any = None) -> WhenResult:
    """식과 메타로 활성 여부를 판정한다. 같은 입력이면 언제나 같은 결과다."""
    node = parse(expr) if isinstance(expr, str) else expr
    state, reasons = _eval(node, _as_mapping(meta))
    # 이유는 중복 없이, 나온 순서대로 (리포트 문구가 매번 같아야 한다)
    seen: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.append(r)
    return WhenResult(state=state, reasons=tuple(seen), source=str(node))


def describe(expr: Union[str, Expr]) -> str:
    """정규화된 한 줄 표기 — 리포트·문서에 식을 실을 때."""
    return str(parse(expr) if isinstance(expr, str) else expr)
