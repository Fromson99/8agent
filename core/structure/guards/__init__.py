"""국소 가드 (SPEC §3.2, §4 S1) — `guard_*(cand) -> float`.

후보 하나를 **주변만 보고** 채점한다. 독립이고 병렬 가능하며 순서가 무관하다.

## 하드컷 금지

boolean 으로 죽이지 않고 **방향 있는 점수**를 돌려준다. 다른 신호가 상쇄·보강할
여지를 남기기 위해서다 — Docling 이 헤더와 본문을 한 블록으로 붙여 뱉으면 블록위치
신호가 약해지는데(§10), 그때 조사·construction 이 대신 버텨 준다. boolean 이면 그
자리에서 후보가 사라져 만회할 방법이 없다.

## 언어별 분리

조사 가드는 한국어 계열만 발화한다(`LANG = "ko"`). 영문 계열의 전치사 대응물
(`of` / `under`)은 별도 파일로 만든다 — 한 가드에 두 언어를 섞지 않는다(§3.2).
관리소가 `LANG` 을 보고 문서 언어에 맞는 가드만 꺼내 준다.

`s(cand) = Σ guards` 는 `scoring.total_local()` 이 계산한다.
"""

from __future__ import annotations

from core.structure.guards import block_pos, construction, particle_ko

__all__ = ["block_pos", "construction", "particle_ko"]
