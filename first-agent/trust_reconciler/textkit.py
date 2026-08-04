"""문자열 유틸 — 정규표현식을 쓰지 않는다.

## 왜 regex 를 뺐나

dataset 9종 전수조사 결과, 문서 서식에 의존하는 패턴은 예외 없이 오버피팅했다.
  - 금액 파서: 442건 중 356건(80%) 오탐. "「소득세법」 제14조제3항제6호" 의 '조'를 4조원으로 읽음
  - 기준일 추출: 9종 중 4종(44%)만 성공. 회사마다 표기가 달라 패턴을 늘려도 다음 문서에서 깨짐
  - 6개 기준일 패턴 중 3개는 0회 매칭 — 근거 없이 추가된 것

패턴을 고치면 다음 회사 문서에서 또 깨진다. 그래서 **문서 내용의 해석은 전부 LLM 이 맡고,
코드는 구조화된 값만 다룬다.** 이 모듈에는 그 경계에서 필요한 최소한의 문자열 조작만 둔다.
전부 str 메서드와 unicodedata 로 구현되어 있고, 어떤 문서 서식도 가정하지 않는다.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Iterator

# 문서마다 다른 유니코드 문장부호를 하나로 모은다.
# str.translate 는 문자 단위 치환이라 패턴 매칭이 아니다 — 서식 가정이 없다.
_PUNCT = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-",
    "×": "*", "÷": "/", "∕": "/", "⁄": "/",
    "％": "%", "，": ",", "。": ".", "․": ".",
    "·": "·", "・": "·", "‧": "·",
    "　": " ", "\xa0": " ",
}
_TRANS = str.maketrans(_PUNCT)


def clean(s: str | None) -> str:
    """문장부호를 통일하고 공백을 하나로 접는다.

    NFKC 정규화는 일부러 하지 않는다. 원문자(①②③)나 전각 숫자가 사라지면
    LLM 이 문서 구조를 읽을 단서를 잃기 때문이다.
    """
    if not s:
        return ""
    return " ".join(s.translate(_TRANS).split())


def squash(s: str | None) -> str:
    """공백을 완전히 제거한 비교용 문자열."""
    if not s:
        return ""
    return "".join(s.translate(_TRANS).split())


def fold(s: str | None) -> str:
    """비교 전용 정규형 — 호환 문자·대소문자·구두점을 모두 없앤다.

    용어집 조회처럼 "같은 말인가"만 보면 되는 곳에 쓴다.
    """
    if not s:
        return ""
    out = []
    for ch in unicodedata.normalize("NFKC", s):
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N"):          # 문자·숫자만 남긴다
            out.append(ch)
        elif ch == "%":
            out.append(ch)
    return "".join(out).casefold()


def is_blank(s: str | None) -> bool:
    return not (s or "").strip()


def truncate(s: str | None, limit: int, ellipsis: str = "…") -> str:
    s = clean(s)
    return s if len(s) <= limit else s[:limit] + ellipsis


def token_set(s: str | None) -> set[str]:
    """어절 집합. 구두점만 떼고 공백으로 자른다."""
    out = set()
    for w in clean(s).split():
        t = "".join(ch for ch in w if unicodedata.category(ch)[0] in ("L", "N") or ch == "%")
        if len(t) > 1:
            out.add(t.casefold())
    return out


def jaccard(a: str | None, b: str | None) -> float:
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def set_jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# LLM 응답에서 JSON 꺼내기 — 괄호 세기, regex 아님
# ---------------------------------------------------------------------------

def _scan_json_span(text: str) -> tuple[int, int] | None:
    """첫 번째 균형 잡힌 { … } 구간을 찾는다. 문자열 리터럴 안의 괄호는 세지 않는다."""
    depth = 0
    start = -1
    in_str = False
    escaped = False
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    return start, i + 1
    return None


def extract_json(text: str) -> Any:
    """모델 응답에서 JSON 객체를 꺼낸다. 코드펜스·앞뒤 설명 문장을 견딘다."""
    import json

    s = (text or "").strip()
    if s.startswith("```"):
        # 첫 줄(``` 또는 ```json)과 마지막 펜스를 잘라낸다
        nl = s.find("\n")
        s = s[nl + 1:] if nl >= 0 else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    span = _scan_json_span(s)
    if span is None:
        raise ValueError(f"응답에서 JSON 을 찾지 못했습니다: {truncate(text, 200)}")
    return json.loads(s[span[0]:span[1]])


# ---------------------------------------------------------------------------
# 줄 다루기
# ---------------------------------------------------------------------------

def numbered(lines: list[str], start: int = 1) -> Iterator[str]:
    """LLM 에 넘길 줄 번호 붙은 텍스트. 응답이 줄 번호로 구간을 가리킬 수 있게 한다."""
    for i, ln in enumerate(lines, start=start):
        yield f"[{i}] {clean(ln)}"
