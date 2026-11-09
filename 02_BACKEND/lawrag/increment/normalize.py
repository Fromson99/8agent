"""조문 비교용 정규화·해시·인용 번호 처리 (결정적, 모델 없음).

- text_hash: NFKC·공백 정규화 후 sha256. 줄바꿈·공백 차이는 같은 내용으로 본다.
- compare_text: 자기 조문 번호를 떼고 인용 번호(제N조·제N항·제N호)를 #으로 가린 값.
  번호가 밀려서 인용만 바뀐 조문과 내용 개정을 구분하는 데 쓴다.
- citations: 본문 인용 목록. 「다른 법」·법·영·시행령 앞의 인용은 외부로 표시한다.
  외부 인용 번호가 바뀌면 이 문서의 조문 이동으로 설명할 수 없으므로 개정으로 본다.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
_SPACE = re.compile(r"\s+")

# 제165조의3, 제1-1조, 제 2 조 — 조 번호 토큰
ARTICLE_REF = re.compile(r"제\s*(\d+(?:-\d+)?)\s*조(?:\s*의\s*(\d+))?")
# 자기 조문 머리 (본문 맨 앞)
OWN_HEADING = re.compile(r"^\s*제\s*\d+(?:-\d+)?\s*조(?:\s*의\s*\d+)?")
# 인용 꼬리의 항·호 번호 (제2조제1항제3호) — 비교값에서 함께 가린다
_SUB_REF = re.compile(r"제\s*\d+\s*(항|호)")
_EXTERNAL_TAIL = re.compile(
    r"(」\s*|(?<![이그])\s*(?:같은\s*법|동\s*법|같은\s*영|동\s*령|시행령|시행규칙|"
    r"(?<!이\s)(?<!이)법|(?<!이\s)(?<!이)영|(?<!이\s)(?<!이)규칙|부칙|세칙))\s*$")
_CONNECTOR_TAIL = re.compile(r"(?:및|또는|·|ㆍ|,|부터|까지|와|과|이나|나)\s*$")


def normalize_text(text: str | None) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = _ZERO_WIDTH.sub("", value)
    return _SPACE.sub(" ", value).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compact(text: str | None) -> str:
    """공백을 모두 뺀 비교값. `제2조 부터`와 `제2조부터` 같은 띄어쓰기 차이는 같은 내용이다."""
    return _SPACE.sub("", normalize_text(text))


def text_hash(text: str | None) -> str:
    return sha256_text(compact(text))


def strip_own_heading(text: str) -> str:
    """조문 머리의 자기 번호만 뗀다. 제목 괄호는 남겨 제목 개정도 잡는다."""
    return OWN_HEADING.sub("", text, count=1).strip()


def article_key(number: str, branch: str | None = None) -> str:
    """제165조의3 → '165의3', 제1-1조 → '1-1'. 가지번호는 '의'로 붙여 하이픈 번호와 구분한다."""
    number = str(number).strip().lstrip("0") or "0"
    branch = str(branch or "").strip().lstrip("0")
    return f"{number}의{branch}" if branch else number


@dataclass(frozen=True)
class Citation:
    key: str          # 인용된 조문 키 (article_key 형식)
    external: bool    # 다른 법령·부칙을 가리키면 True
    text: str         # 원문 토큰


def citations(text: str, *, skip_own_heading: bool = True) -> list[Citation]:
    body = normalize_text(text)
    if skip_own_heading:
        body = normalize_text(strip_own_heading(body))
    out: list[Citation] = []
    previous_end = 0
    previous_external = False
    for match in ARTICLE_REF.finditer(body):
        window = body[max(previous_end, match.start() - 24):match.start()]
        if out and _CONNECTOR_TAIL.search(window) and match.start() - previous_end <= 12:
            external = previous_external
        else:
            external = bool(_EXTERNAL_TAIL.search(window))
        key = article_key(match.group(1), match.group(2))
        out.append(Citation(key, external, match.group(0)))
        previous_end = match.end()
        previous_external = external
    return out


def compare_text(text: str) -> str:
    body = normalize_text(strip_own_heading(normalize_text(text)))
    body = ARTICLE_REF.sub("제#조", body)
    body = _SUB_REF.sub(lambda m: "제#" + m.group(1), body)
    return _SPACE.sub("", body)


def compare_hash(text: str) -> str:
    return sha256_text(compare_text(text))


def bigrams(text: str) -> frozenset[str]:
    compact = text.replace(" ", "")
    if len(compact) < 2:
        return frozenset({compact}) if compact else frozenset()
    return frozenset(compact[i:i + 2] for i in range(len(compact) - 1))


def stable_id(*parts: str, length: int = 32) -> str:
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]
