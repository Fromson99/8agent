"""국소 가드 — 블록 위치 (SPEC §3.2, §5.1).

    블록 여는 자리(offset 0)   +0.8
    블록 중간(텍스트가 흐른 뒤) −0.7
    괄호/인라인 내부           −0.9

진짜 헤더는 블록을 여는 자리에 온다. mention 은 흐르는 텍스트 안에 박혀 있다.
그 차이가 offset 하나로 결정되므로 LLM 이 필요 없다.

괄호 안을 블록 중간보다 더 세게 깎는 이유: 괄호는 그 자체로 삽입구 표지라서
"여기부터 새 구역" 이라는 뜻이 될 수 없다. 골든 §8 의 c8 이 이 경우다.

**약점을 알고 쓴다.** Docling 이 헤더와 본문을 한 블록으로 합쳐 뱉으면 진짜 헤더가
offset 0 을 얻지 못한다(§10 미해결). 하드컷이 아니라 점수라서, 그때는 조사·
construction 가드가 버텨 준다.
"""

from __future__ import annotations

from lawrag.core.structure import scoring
from lawrag.core.structure.model import Candidate

ID = "block_pos"
ROLE = "local_guard"
LANG = "any"
SURFACE = "블록 여는 자리 / 중간 / 괄호 내부"


def score(cand: Candidate, blocks, lex) -> dict[str, float]:
    if cand.in_paren:
        return {ID: scoring.BLOCK_INLINE}
    if cand.text[:cand.offset].strip():
        return {ID: scoring.BLOCK_MID}
    return {ID: scoring.BLOCK_OPEN}
