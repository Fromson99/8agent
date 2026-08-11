"""재현 판정 키와 저장 분기 (SPEC §2, §4 S5, §7).

    Fingerprint = 발화 family 집합 + 유도된 중첩순서

## compile 은 재현빈도가 결정한다

문서 해석 결과는 **항상** 저장한다(다운스트림이 쓴다). 재사용 frame 은 같은
fingerprint 가 2~3개 쌓였을 때만 freeze 한다. N=1 에 frame 을 만들면 그것이 곧
"이 문서 하나를 위한 룰 추가" 이고, 그렇게 쌓인 룰이 시간이 갈수록 취약해지는
바로 그 실패다(§7).

freeze 트리거 개수(2 vs 3)는 §10 미결이다. 여기서는 상수로 두고 한곳에서 바꾼다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.structure.model import Candidate, Fingerprint, Ladder

# §10 미결: 2 vs 3. 지금은 2 — 두 번째 문서가 같은 모양이면 우연이 아니다.
FREEZE_AT = 2

HOT, WARM, COLD = "hot", "warm", "cold"


def of(candidates: list[Candidate], ladder: Ladder) -> Fingerprint:
    fired = sorted({c.family_key for c in candidates if c.activated})
    order = [sorted(r.families) for r in ladder.rungs]
    return Fingerprint(families=fired, order=order)


@dataclass
class Ledger:
    """fingerprint 별 관측 횟수 + 동결된 frame. 관리소가 붙기 전의 최소 장부다.

    frame 은 재현이 확인된 문서군의 사다리(레벨별 family 순서)다. fingerprint
    키에 순서가 이미 들어 있으므로 같은 키의 문서에 다시 주입하는 것은 무의미
    하고, 가치는 **장부에 남는 것** 자체다 — 어떤 문서군이 안정적으로 재현되는지,
    어떤 바인딩이 동결됐는지를 다음 국면(frame 라우팅, 측정기 장부)이 읽는다.
    """
    path: Optional[Path] = None
    counts: dict[str, int] = field(default_factory=dict)
    docs: dict[str, list[str]] = field(default_factory=dict)
    frames: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Ledger":
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(path=p, counts=data.get("counts", {}), docs=data.get("docs", {}),
                   frames=data.get("frames", {}))

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"counts": self.counts, "docs": self.docs,
                        "frames": self.frames},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    def observe(self, fp: Fingerprint, doc: str) -> int:
        key = fp.key()
        seen = self.docs.setdefault(key, [])
        if doc not in seen:
            seen.append(doc)
        self.counts[key] = len(seen)
        return self.counts[key]

    def freeze(self, fp: Fingerprint, doc: str) -> bool:
        """frame 등재 — may_freeze 판정을 통과한 호출부만 부른다.
        이미 동결돼 있으면 건드리지 않는다(첫 동결이 정본)."""
        key = fp.key()
        if key in self.frames:
            return False
        self.frames[key] = {"order": fp.order, "families": sorted(fp.families),
                            "first_doc": doc}
        return True


def tier(count: int, fitness_passed: bool) -> str:
    """§7 티어링. 재현빈도와 적합도가 함께 정한다."""
    if not fitness_passed:
        return COLD                      # 양식 없음 / 미달 → 보편 skeleton + bounded LLM
    if count >= FREEZE_AT:
        return HOT                       # 반복 확인 → frozen frame 라우팅
    return WARM                          # 양식은 잡혔으나 재현 미확인


def may_freeze(count: int, fitness_passed: bool) -> bool:
    """frame 을 등재해도 되는가 — singleton 에는 만들지 않는다."""
    return fitness_passed and count >= FREEZE_AT
