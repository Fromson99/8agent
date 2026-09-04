"""법령명 인용 판정 — 문서 무관 신호만 쓴다.

두 가지 판정이 있고 쓰는 자리가 다르다:

- exact_brackets: 「명칭」 낫표 완전일치. 법제처 문서(해석례)의 인용 관례 —
  닫는 낫표까지 맞춰 '상법'≠'상법 시행령'을 가른다 (lawrag/sources/expc.cited_laws
  가 이걸 쓴다).
- plain_mentions: 낫표 없는 본문(금융위 회신·판례 참조조문)용. 명칭 앞이
  한글이면 다른 낱말의 꼬리다 — '국가배상법' 속의 '상법', '기상법' 속의
  '상법'을 거른다. 공백은 양쪽 다 무시한다(붙여쓰기 표기 실재).
"""
from __future__ import annotations

import re


def _pack(s: str) -> str:
    return re.sub(r"\s+", "", s)


def plain_mentions(text: str, names: list[str]) -> list[str]:
    """앞 경계(비한글)를 요구하는 평문 인용 — 걸린 명칭들을 돌려준다.

    경계 판정은 **공백 제거 전 원문 좌표**로 한다 — "구 자본시장과…법률"
    (옛 법 인용, 판례 관례)은 공백을 지우면 '구'가 붙어 꼬리 일치처럼
    보이지만, 원문에서는 공백이 앞에 있으니 진짜 인용이다.
    """
    chars, orig_idx = [], []
    for i, ch in enumerate(text):
        if not ch.isspace():
            chars.append(ch)
            orig_idx.append(i)
    packed = "".join(chars)
    out = []
    for name in names:
        needle = _pack(name)
        if not needle:
            continue
        for m in re.finditer(re.escape(needle), packed):
            oi = orig_idx[m.start()]
            prev = text[oi - 1] if oi > 0 else ""
            if not ("가" <= prev <= "힣"):
                out.append(name)
                break
    return sorted(set(out))
