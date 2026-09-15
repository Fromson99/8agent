"""S4 전역 선택 — DP (SPEC §4 S4).

후보를 읽기순으로 놓고 왼→오 **1회 훑기**(최단경로/Viterbi). 완전탐색이 아니라 exact 다.

    상태 = 위치 + ScopeStack(레벨별 마지막 서수 · 들여쓰기 · 연 계열)
    전이 = 각 후보 `reject | activate`
             activate 허용: check_nesting != FORBID 이고 자기 계열 안이 아닐 것
                            (nesting.self_nested — 제2조 는 제1조 의 자식이 아니다;
                            서수 게이트는 벌점만 준다)
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

from lawrag.core.structure import scoring
from lawrag.core.structure.global_inner import nesting, ordinal as ordinal_gate
from lawrag.core.structure.model import Candidate, Ladder, Node, ScopeStack

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


def _levels_for(cand: Candidate, ladder: Ladder,
                stack: Optional[ScopeStack] = None,
                depth: Optional[int] = None) -> list[int]:
    """이 후보가 앉을 수 있는 레벨들.

    사다리가 층을 정해 준 후보라도, **지금 열린 구간보다 더 들여쓰여 있으면**
    그 구간 안쪽 자리도 후보로 준다. 전역 사다리는 계열마다 층이 하나라
    "여기서는 `가.` 가 `1)` 안" 을 표현하지 못하는데, 그 문서는 들여쓰기로
    이미 그렇게 그려 놓았다(실측 2026-08-11 상품설명서 p.123). 고르는 것은
    DP 다 — 사다리를 벗어나면 novelty 벌점을 물므로, 기하가 뚜렷할 때만 이긴다.
    """
    top = depth if depth is not None else max(1, ladder.depth)
    if cand.unassigned or cand.level is None:
        return list(range(top))                    # 미배정 — 문맥이 정한다
    levels = [cand.level]
    if stack is not None and cand.x_norm is not None:
        # 나보다 얕게 그려진 채 열려 있는 가장 깊은 구간 — 나는 그 안이다
        inner = [i for i, x in enumerate(stack.xs)
                 if x is not None and i > cand.level
                 and x + scoring.INDENT_EPS < cand.x_norm]
        if inner:
            levels.append(min(max(inner) + 1, top - 1))
    return sorted(set(levels))


def _freed_novelty(family_key: str, level: int, stack: ScopeStack, ladder: Ladder) -> float:
    """층 해제된 계열의 novelty — 절대 층이 아니라 **바로 위 부모의 계열 순위**로 잰다.

    사다리가 앉힌 층은 무효지만(열 자리가 없었다) 사다리의 **상대 순서**는 살아 있다:
    "부칙 > 조 > 항". 실측(2026-08 내규, 장 없이 조만 있고 부칙이 둘): 조가 풀린 뒤

        옛 층(L1)만 면제      → 제2조가 제1조 안으로 (self_nested 가 이제 막는다)
        어디서도 novelty 없음  → 부칙의 제1조(시행일)가 부칙 밖 형제로 — L0 과 L1 이
                                동점이라 얕은 쪽이 이겼다

    그래서 부모를 본다. 부모가 사다리에서 나보다 위인 계열(부칙)이면 0 — 문서가
    그리로 들어가라고 한 자리다. 부모가 없으면(최상위) 미세 감점 — 허용하되 위 계열
    안보다 뒤. 부모가 나보다 아래이거나 순위를 모르면 novelty — 조가 ① 안에 앉는
    뒤집힘이다.
    """
    parent = None
    for i in range(min(level, len(stack.fams)) - 1, -1, -1):
        if stack.last[i] is not None:
            parent = stack.fams[i]
            break
    if parent is None:
        return -scoring.FREED_DEPTH_BIAS
    lp, lf = ladder.level_of(parent), ladder.level_of(family_key)
    if lp is not None and lf is not None and lp < lf:
        return 0.0
    return scoring.LEVEL_NOVELTY


def run(candidates: list[Candidate], ladder: Ladder, *, strict_levels: bool = False, required_candidates=()) -> DPResult:
    """읽기순 1회 훑기. 후보의 `activated` / `decision_note` 를 채운다."""
    result = DPResult()
    # 사다리 칸 수 + 여유. 사다리는 계열마다 층이 하나뿐이라, 같은 표기가 더
    # 깊은 자리에도 쓰인 문서에서는 **맨 아래 계열보다 더 안쪽**에 앉힐 칸이
    # 아예 없다(실측: `1)` 이 마지막 칸이라 그 아래 목을 놓을 자리가 없었다).
    # 들여쓰기를 잴 수 있는 문서에서만 연다 — 기하 없이 열면 근거 없는 깊이가
    # 생긴다. 여는 것과 쓰는 것은 다르다: 쓰려면 novelty 벌점을 물어야 한다.
    ordered = sorted(candidates, key=lambda c: (c.doc, c.block_idx, c.offset))
    # 계열 정합(S2)에서 떨어진 후보는 DP 에 들어오지 않는다 — 자기 계열 수열·위치가
    # 이미 "구조가 아니다" 라고 말했다. 그래도 감사 로그에는 남는다(§8.7).
    required = set(required_candidates)
    if not required <= {c.id for c in ordered}:raise ValueError("Unknown required candidate")
    live = [c for c in ordered if (c.survives and c.s > ACTIVATE_FLOOR) or c.id in required]
    result.pruned = len(ordered) - len(live)

    depth = max(1, ladder.depth)
    if any(c.x_norm is not None for c in live):
        depth += scoring.INDENT_EXTRA_DEPTH

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
            if cand.id not in required:
                _offer(stack, _Path(path.score, stack,
                                    path.steps + [(i, None, 0.0, "reject")]))

            for level in ([ladder.level_of(cand.family_key)] if strict_levels and ladder.level_of(cand.family_key) is not None else ([] if strict_levels else _levels_for(cand, ladder, stack, depth))):
                if level >= depth:
                    continue
                if nesting.check(level, stack) == nesting.FORBID:
                    continue
                if nesting.self_nested(cand.family_key, level, stack, cand.x_norm):
                    continue            # 제2조 는 제1조 의 자식이 아니다 — 경로 배제
                penalty, why = ordinal_gate.check(level, cand.ordinal, stack)
                novelty = 0.0
                if cand.family_key in ladder.freed:
                    novelty = _freed_novelty(cand.family_key, level, stack, ladder)
                elif ladder.level_of(cand.family_key) != level:
                    novelty = scoring.LEVEL_NOVELTY
                # 들여쓰기 모순 — 이 자리에 앉으면 나보다 얕게 그려진 구간을
                # 닫게 되는가. 그렇다면 문서가 그린 안팎을 뒤집는 배치다.
                contra = 0.0
                if cand.x_norm is not None:
                    if any(x is not None and x + scoring.INDENT_EPS < cand.x_norm
                           for x in stack.xs[level:]):
                        contra = scoring.INDENT_CONTRADICTION
                gain = cand.s + penalty + novelty + contra
                best_activate = max(best_activate, gain)
                note = f"L{level} s={cand.s:+.2f}"
                if contra:
                    note += f" 들여쓰기모순({contra:+.2f})"
                if penalty:
                    note += f" {why}({penalty:+.2f})"
                if novelty <= scoring.LEVEL_NOVELTY:
                    note += f" novelty({novelty:+.2f})"
                nxt_stack = stack.activate(level, cand.ordinal, cand.x_norm,
                                           cand.family_key)
                _offer(nxt_stack,
                       _Path(path.score + gain, nxt_stack,
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
        # 사유를 뭉개지 않는다 — 계열 정합 탈락과 점수 가지치기는 다른 판정이다.
        n_family = sum(1 for c in ordered if not c.survives)
        n_floor = result.pruned - n_family
        parts = []
        if n_family:
            parts.append(f"계열 정합 탈락 {n_family}건")
        if n_floor:
            parts.append(f"s ≤ {ACTIVATE_FLOOR} {n_floor}건")
        result.audit.append(f"가지치기: {' · '.join(parts)} 을 활성 후보에서 뺐습니다")
    if result.beam_hits:
        result.audit.append(
            f"빔 상한({scoring.BEAM_WIDTH}) 에 {result.beam_hits}회 걸렸습니다 "
            f"— 상태를 잘랐으므로 최적 경로가 아닐 수 있습니다")
    return result


_GUARD_LABEL = {"block_pos": "블록위치", "particle_ko": "조사",
                "particle_ko:referent": "참조서술어"}


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
