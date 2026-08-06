"""S3 전역 선택 — DP (SPEC §4 S3).

후보를 읽기순으로 놓고 왼→오 **1회 훑기**(최단경로/Viterbi). 완전탐색이 아니라 exact 다.

    상태 = 위치 + ScopeStack(레벨별 마지막 서수)
    전이 = 각 후보 `reject | activate`
             activate 허용: check_nesting == ok  and  check_ordinal == ok
             activate 시 해당 레벨 서수↑, 하위 레벨 스코프 닫음
             reject 시 후보는 mention 으로 버려지고 스택 불변
    목적 = Σ 활성 s(cand) − Σ 벌점  최대 경로

## 상태가 작은 이유

깊이가 ~5 라 ScopeStack 의 모양이 몇 가지 안 된다. 같은 위치에서 ScopeStack 이 같은
두 경로는 이후가 완전히 같으므로 점수 높은 쪽만 남긴다(Viterbi 병합). 그래서 지수가
아니라 선형이다.

## 미배정 후보

S2 에서 딱지를 단 후보는 **여러 레벨 배정을 시도해** 문맥상 최고점 위치에 앉힌다.
자기 family 가 등재되지 않은 레벨에 앉으면 novelty 벌점(−0.2)을 받는다. 골든 §8.4 의
c9 가 이 경우다: L0 배정은 서수역행 −1.5 로 +0.3, L2 배정은 novelty −0.2 로 +1.6 이라
L2 가 이긴다.

## 가지치기 — 조용히 자르지 않는다

`activate` 의 이득은 `s + 벌점`(벌점 ≤ 0)이고 `reject` 는 0 이므로, `s ≤ 0` 인 후보는
활성해서 점수를 얻을 수 없다. 다만 활성이 스코프를 열어 뒤의 후보를 살리는 경우가
이론상 있으므로 이 가지치기는 **완전 exact 가 아니다.** 그래서 자른 개수를 감사 로그에
남긴다(§4 S3 산출: "후보별 활성/기각 경로 로그"). 200쪽 법령에서 후보가 수만 개가
되는 것을 막는 실용적 장치다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.structure import scoring
from core.structure.global_inner import nesting, ordinal as ordinal_gate
from core.structure.model import Candidate, Ladder, Node, ScopeStack

# s 가 이 값 이하인 후보는 활성 후보에서 뺀다(위 주석 참조)
ACTIVATE_FLOOR = 0.0


@dataclass
class _Path:
    score: float
    stack: ScopeStack
    # (후보 index, 배정 레벨, 전이 점수, 사유). reject 는 level=None
    steps: list[tuple[int, Optional[int], float, str]] = field(default_factory=list)


@dataclass
class DPResult:
    total: float = 0.0
    audit: list[str] = field(default_factory=list)
    pruned: int = 0
    beam_hits: int = 0


def _levels_for(cand: Candidate, ladder: Ladder) -> list[int]:
    """이 후보가 앉을 수 있는 레벨들."""
    if not cand.unassigned and cand.level is not None:
        return [cand.level]
    return list(range(max(1, ladder.depth)))       # 미배정 — 문맥이 정한다


def run(candidates: list[Candidate], ladder: Ladder) -> DPResult:
    """읽기순 1회 훑기. 후보의 `activated` / `decision_note` 를 채운다."""
    result = DPResult()
    depth = max(1, ladder.depth)

    ordered = sorted(candidates, key=lambda c: (c.doc, c.block_idx, c.offset))
    # 계열 정합(S2)에서 떨어진 후보는 DP 에 들어오지 않는다 — 자기 계열 수열·위치가
    # 이미 "구조가 아니다" 라고 말했다. 그래도 감사 로그에는 남는다(§8.7).
    live = [c for c in ordered if c.survives and c.s > ACTIVATE_FLOOR]
    result.pruned = len(ordered) - len(live)

    paths: dict[ScopeStack, _Path] = {
        ScopeStack.empty(depth): _Path(0.0, ScopeStack.empty(depth))}

    for i, cand in enumerate(live):
        nxt: dict[ScopeStack, _Path] = {}

        def _offer(stack: ScopeStack, path: _Path) -> None:
            cur = nxt.get(stack)
            if cur is None or path.score > cur.score:
                nxt[stack] = path

        best_activate = float("-inf")
        for stack, path in paths.items():
            # reject — 스택 불변, 점수 불변
            _offer(stack, _Path(path.score, stack,
                                path.steps + [(i, None, 0.0, "reject")]))

            for level in _levels_for(cand, ladder):
                if level >= depth:
                    continue
                if nesting.check(level, stack) == nesting.FORBID:
                    continue
                penalty, why = ordinal_gate.check(level, cand.ordinal, stack)
                novelty = 0.0
                if ladder.level_of(cand.family_key) != level:
                    novelty = scoring.LEVEL_NOVELTY
                gain = cand.s + penalty + novelty
                best_activate = max(best_activate, gain)
                note = f"L{level} s={cand.s:+.2f}"
                if penalty:
                    note += f" {why}({penalty:+.2f})"
                if novelty:
                    note += f" novelty({novelty:+.2f})"
                _offer(stack.activate(level, cand.ordinal),
                       _Path(path.score + gain, stack.activate(level, cand.ordinal),
                             path.steps + [(i, level, gain, note)]))

        # 최선(활성)과 차선(기각=0)의 차 — 이것이 §4 S5 가 말하는 "근소차" 다.
        cand.decision_margin = (abs(best_activate)
                                if best_activate > float("-inf") else float("inf"))

        if len(nxt) > scoring.BEAM_WIDTH:
            result.beam_hits += 1
            keep = sorted(nxt.items(), key=lambda kv: -kv[1].score)[:scoring.BEAM_WIDTH]
            nxt = dict(keep)
        paths = nxt

    if not paths:
        result.audit.append("DP 가 어떤 경로도 찾지 못했습니다")
        return result

    best = max(paths.values(), key=lambda p: p.score)
    result.total = best.score

    for idx, level, gain, note in best.steps:
        cand = live[idx]
        if level is None:
            cand.activated = False
            cand.activated_level = None
            cand.decision_note = f"reject(mention) | s={cand.s:+.2f}"
        else:
            cand.activated = True
            cand.activated_level = level
            cand.transition_gain = gain
            cand.decision_note = f"activate {note} | 전이 {gain:+.2f}"
        result.audit.append(f"{cand.id}:{cand.surface} → {cand.decision_note}")

    # 가지친 후보도 **로그에 남는다** (§8.7). 가지치기는 구현상의 최적화일 뿐
    # 판정으로는 reject 이며, 왜 버렸는지가 감사에 없으면 고칠 수가 없다.
    live_ids = {id(c) for c in live}
    for c in ordered:
        if id(c) in live_ids:
            continue
        c.activated = False
        c.decision_note = f"reject(mention) | 근거: {_why(c)}, s={c.s:+.2f}"
        result.audit.append(f"{c.id}:{c.surface} → {c.decision_note}")
    result.audit.sort(key=lambda line: _seq(line, ordered))

    if result.pruned:
        result.audit.append(
            f"가지치기: s ≤ {ACTIVATE_FLOOR} 후보 {result.pruned}건을 활성 후보에서 뺐습니다")
    if result.beam_hits:
        result.audit.append(
            f"빔 상한({scoring.BEAM_WIDTH}) 에 {result.beam_hits}회 걸렸습니다 "
            f"— 상태를 잘랐으므로 최적 경로가 아닐 수 있습니다")
    return result


_GUARD_LABEL = {"block_pos": "블록위치", "particle_ko": "조사",
                "particle_ko:referent": "참조서술어", "construction": "construction"}


def _why(cand: Candidate) -> str:
    """기각 근거 — 사람이 읽는 한 줄 (§8.7)."""
    if not cand.survives:
        return f"계열 정합: {cand.family_note}"
    bad = sorted((k for k, v in cand.guards.items() if v < 0),
                 key=lambda k: cand.guards[k])
    if not bad:
        return "이득 없음"
    return "+".join(f"{_GUARD_LABEL.get(k, k)}({cand.guards[k]:+.1f})" for k in bad)


def _seq(line: str, ordered: list[Candidate]) -> int:
    cid = line.split(":", 1)[0]
    for i, c in enumerate(ordered):
        if c.id == cid:
            return i
    return len(ordered)                    # 후보가 아닌 요약 줄은 뒤로


def build_tree(candidates: list[Candidate], n_blocks: int) -> list[Node]:
    """활성 후보를 트리로. 부모 = 자기보다 얕으면서 바로 앞선 활성 후보."""
    active = sorted((c for c in candidates if c.activated),
                    key=lambda c: (c.block_idx, c.offset))
    roots: list[Node] = []
    stack: list[Node] = []
    nodes: list[tuple[Node, Candidate]] = []

    for c in active:
        node = Node(level=c.activated_level or 0, ordinal=c.ordinal,
                    family=c.family_key, surface=c.surface, block_idx=c.block_idx,
                    page=c.page, element_index=c.element_index, candidate_id=c.id,
                    title=c.title, title_reason=c.title_reason,
                    activation_reason=c.decision_note)
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
        nodes.append((node, c))

    # span — 다음 같은/얕은 마디 직전까지
    for i, (node, c) in enumerate(nodes):
        end = n_blocks
        for later, lc in nodes[i + 1:]:
            if later.level <= node.level:
                end = later.block_idx
                break
        node.span = (c.block_idx, end)
    return roots
