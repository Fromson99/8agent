"""레벨 사다리 유도 (SPEC §3.3, S3) — `induce_ladder(survivors) -> Ladder`.

**계열 정합(S2)을 통과한 후보만 본다.** 인용이 섞인 채로 중첩을 관측하면 위치가
오염되어 증거가 무너진다.

## 증거 네 가지 — 센 것부터

**1. 자기계열 depth (관측 없이 확정).**
점번호 `1. / 1.1 / 1.1.1` 은 표면이 스스로 깊이를 말한다. `dot_number:1` 은
`dot_number:2` 보다 반드시 얕다.

**2. 들여쓰기 (기하 증거).**
문서가 계층을 눈에 보이게 그린 그대로를 읽는다. 계열이 몇 건이든, 번호가 리셋되든
말든 잰다 — 아래 두 증거가 각각 못 미치는 자리를 메운다. 자세한 실측은 `indent.py`.

**3. 리셋 정렬 (가장 강한 수열 증거).**
B 의 번호가 되감기는 자리마다 A 의 마커가 놓여 있으면 B 는 A 안에 산다.

    장:  1 ─────────── 2 ─────────── 3
    조:   1,2,3,4,5 │ 1,2,3,4 │ 1,2
                    ↑         ↑
                장 경계에서 정확히 리셋  →  조는 장 아래

이건 밀도가 아니라 **구조**를 재므로 1표 차가 나지 않는다. 그리고 계열 정합을
통과한 후보 위에서만 계산할 수 있다 — 인용이 섞이면 리셋 위치가 오염된다.

**4. 덮음.**
A 가 연 구간 중 몇 할이 B 를 품고 있는가. 담는 쪽은 자기 구간 대부분을 채워야 한다.
마지막 열린 구간은 세지 않는다 — 그러면 뒤에 오는 모든 것을 삼켜 방향이 뒤집힌다.

**5. 사이-끼임 (최후).**
A 의 두 출현 사이에 B 가 들어앉은 횟수. §4 S2-2 의 원래 정의다. 밀도만 재므로 촘촘히
섞인 두 계열에서는 거의 무승부가 된다(실측: 52:51, 29:28, 6:6). 그래서 위 셋이
아무 말도 못 할 때만 쓴다.

## 갈래 A vs B (§4 S2-4)

관측으로 순서가 읽히면 그대로 확정한다(갈래 A — 대부분). 순서가 미정인 쌍은 같은 칸에
나란히 두고 사실만 `notes` 에 남긴다. 갈래 B(배열 열거)는 실제로 그런 문서가 나타났을
때 만든다(§9 over-engineering 방지).
"""

from __future__ import annotations

from collections import defaultdict

from lawrag.core.structure import scoring
from lawrag.core.structure.global_outer import indent as indent_mod
from lawrag.core.structure.global_outer import reg_score as reg
from lawrag.core.structure.model import Candidate, Ladder, Rung

ID = "ladder"
ROLE = "global_outer"
LANG = "any"
SURFACE = "레벨 사다리 유도"

MIN_COVERAGE = 0.5          # 담는 쪽이 자기 구간의 이만큼을 채워야 한다


def _pos(cands: list[Candidate]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for c in cands:
        out[c.doc].append(c.block_idx)
    for v in out.values():
        v.sort()
    return out


# --- 증거 2: 리셋 정렬 ------------------------------------------------------

def reset_alignment(outer: list[Candidate], inner: list[Candidate]) -> tuple[int, int]:
    """(정렬된 리셋 수, 전체 리셋 수). inner 의 되감김이 outer 경계에 맞는가."""
    aligned = total = 0
    po = _pos(outer)
    runs = reg.runs(inner)
    for i in range(1, len(runs)):
        prev_end, start = runs[i - 1][-1], runs[i][0]
        if prev_end.doc != start.doc:
            continue                       # 문서가 바뀌는 자리는 리셋이 당연하다
        total += 1
        if any(prev_end.block_idx < b <= start.block_idx for b in po.get(start.doc, [])):
            aligned += 1
    return aligned, total


# --- 증거 3: 덮음 -----------------------------------------------------------

def coverage(outer: list[Candidate], inner: list[Candidate]) -> float:
    po, pi = _pos(outer), _pos(inner)
    filled = total = 0
    for doc in sorted(set(po) & set(pi)):
        o, i = po[doc], pi[doc]
        for a, b in zip(o, o[1:]):         # 마지막 열린 구간은 세지 않는다
            total += 1
            if any(a < x < b for x in i):
                filled += 1
    return filled / total if total else 0.0


# --- 증거 4: 사이-끼임 ------------------------------------------------------

def nesting_evidence(outer: list[Candidate], inner: list[Candidate]) -> int:
    po, pi = _pos(outer), _pos(inner)
    count = 0
    for doc in sorted(set(po) & set(pi)):
        o, i = po[doc], pi[doc]
        for a, b in zip(o, o[1:]):
            if any(a < x < b for x in i):
                count += 1
    return count


def chain_nesting(outer: list[Candidate], inner: list[Candidate]) -> int:
    """**연속단위 안**의 이웃 사이에 inner 가 들어앉은 횟수 (사이-끼임의 정밀판).

    사이-끼임은 A 의 인접 출현 아무 쌍이나 세기 때문에 촘촘히 섞인 두 계열에서
    무승부가 된다(실측 28:27, 6:6). 그런데 계층의 진짜 증거는 밀도가 아니라
    **번호가 이어지는가**다:

        5) 투자설명서의 변경 …
            가. 나. 다. 라.          ← 5) 와 6) 사이에 통째로 들어앉았다
        6) 집합투자업자의 합병 …     ← 5)→6), 같은 연속단위가 이어진다

    5 다음이 6 이므로 그 사이의 것은 **5) 안에** 있다 — 두 출현이 서로 다른
    수열에 속하면(리셋으로 끊긴 이웃) 그 사이는 중첩의 증거가 아니다. 같은
    연속단위(`chain`)의 이웃만 세어 그 차이를 살린다.

    실측(같은 문서, 계열을 들여쓰기로 쪼갠 뒤): 최상위 `가.` 는 18:1 로 `1)` 을
    품고, 목으로 쓰인 `가.` 는 3:4 로 `1)` 에 담긴다 — 사이-끼임은 둘 다
    무승부(25:24, 6:6)라 아무 말도 못 하던 자리다.
    """
    runs: dict[tuple, list[Candidate]] = defaultdict(list)
    for c in outer:
        if c.chain is not None:
            runs[(c.doc, c.chain)].append(c)
    ipos: dict[str, list[int]] = defaultdict(list)
    for c in inner:
        ipos[c.doc].append(c.block_idx)
    for v in ipos.values():
        v.sort()
    count = 0
    for (doc, _), cs in runs.items():
        i = ipos.get(doc)
        if not i:
            continue
        cs.sort(key=lambda c: c.block_idx)
        for a, b in zip(cs, cs[1:]):
            if any(a.block_idx < x < b.block_idx for x in i):
                count += 1
    return count


# --- 조립 -------------------------------------------------------------------

def _self_depth_edges(keys: list[str]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    by_base: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for key in keys:
        base, sep, d = key.rpartition(":")
        if sep and d.isdigit():
            by_base[base].append((int(d), key))
    for items in by_base.values():
        items.sort()
        for (_, a), (_, b) in zip(items, items[1:]):
            edges.add((a, b))
    return edges


def _toposort(nodes: list[str], edges: set[tuple[str, str]]
              ) -> tuple[list[list[str]], list[str]]:
    """위상정렬. 반환: (층 목록, **순환 때문에 임의로 끊은 계열**).

    순환이 생기면 어느 계열의 층은 증거가 아니라 절단 규칙(이름 순)이 정한다.
    그 사실을 조용히 넘기면 사다리가 틀렸다는 것을 아무도 모른다 — 실측에서
    금소법에 순환이 7개 있었고 절(節)의 레벨이 이름 첫 글자로 정해졌는데
    적합도는 99% 였다. 그래서 끊은 자리를 반드시 돌려준다.
    """
    incoming = {n: set() for n in nodes}
    for a, b in edges:
        if a in incoming and b in incoming:
            incoming[b].add(a)
    layers: list[list[str]] = []
    broken: list[str] = []
    remaining = set(nodes)
    while remaining:
        ready = sorted(n for n in remaining if not (incoming[n] & remaining))
        if not ready:
            ready = [sorted(remaining)[0]]          # 순환 — 결정론적으로 끊는다
            broken.append(ready[0])
        layers.append(ready)
        remaining -= set(ready)
    return layers, broken


def _find_cycles(nodes: list[str], edges: set[tuple[str, str]],
                 limit: int = 6) -> list[list[str]]:
    """순환을 찾아 사람이 읽는 경로로. 보고용이므로 개수를 제한한다."""
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
    found: list[list[str]] = []
    seen_key: set[frozenset] = set()

    def walk(start: str, node: str, path: list[str]) -> None:
        if len(found) >= limit:
            return
        for nxt in sorted(adj[node]):
            if nxt == start and len(path) >= 2:
                key = frozenset(path)
                if key not in seen_key:
                    seen_key.add(key)
                    found.append(path + [start])
            elif nxt not in path and len(path) < 5:
                walk(start, nxt, path + [nxt])

    for n in sorted(nodes):
        walk(n, n, [n])
    return found


def induce_ladder(survivors: list[Candidate], root: str | None = None,
                  hint: list[list[str]] | None = None,
                  partial_order: list[tuple[str, str]] | None = None,
                  page_width: dict[int, float] | None = None,
                  chain_evidence: bool = False) -> Ladder:
    """레벨 사다리를 유도한다.

    hint          층을 통째로 지정한다(`[["dot_number:1"], ["circled"]]`). 주면 유도를
                  건너뛰지만 **관측과 대조해 어긋남을 알린다** — 힌트와 다른 양식의
                  문서가 들어왔을 수 있기 때문이다.
    partial_order 특정 쌍의 순서만 못박는다(`[("kr_장","kr_article")]`). 증거가 얇아
                  못 정하는 쌍(절 6건/리셋 1회 같은)에 한 줄 찍어 주는 용도다.
                  **지정에 이름이 오른 계열은 등재 점수와 무관하게 등재한다** — 등재
                  점수는 "번호가 이어지는가"(런의 결)라서 한 번 나오는 계열(짧은
                  내규의 `부칙` 하나, `[별표 1]` 하나)은 영영 0 이다. 사람이 "이 문서군
                  에서 그것은 구조다"라고 쌍을 찍어 준 것이 곧 등재 근거다. 실측
                  (2026-08 내규 변형 3종): 부칙·별표가 미등재 → 문맥판정으로 자리는
                  맞게 잡았지만 사다리 결함 감점으로 warm 에 머물렀다.
    """
    fams: dict[str, list[Candidate]] = defaultdict(list)
    for c in survivors:
        fams[c.family_key].append(c)

    declared = {k for pair in (partial_order or []) for k in pair}
    ladder = Ladder()
    fired: dict[str, list[Candidate]] = {}
    for key in sorted(fams):
        s = reg.score(key, fams[key])
        if reg.registered(key, fams[key]):
            fired[key] = fams[key]
        elif key in declared:
            fired[key] = fams[key]
            ladder.notes.append(
                f"{key}: 생존 {len(fams[key])}건, 등재점수 {s:.2f} — 지정 순서에 이름이 "
                f"올라 등재")
        elif len(fams[key]) < 2:
            # 하나짜리 — 런의 결을 잴 수 없다. 결함이 아니라 표본 부족이므로 감점
            # 목록(unregistered)이 아니라 따로 둔다. 자리는 문맥판정(S4)이 잡는다.
            # 실측(2026-08 내규 3종): `부칙` 하나·`[별표 1]` 하나가 미등재로 잡혀
            # 사다리 결함 감점을 받았지만 트리는 전부 맞았다 — 감점할 결함이 없었다.
            ladder.singletons.append(key)
            ladder.notes.append(
                f"{key}: 생존 1건 — 계열이 아니라 하나짜리, 문맥판정으로 (감점 없음)")
        else:
            ladder.unregistered.append(key)
            ladder.notes.append(
                f"{key}: 생존 {len(fams[key])}건, 등재점수 {s:.2f} — 레벨 제외, 문맥판정으로")
    if not fired:
        ladder.notes.append("등재된 계열이 없습니다 — 사다리가 비었습니다")
        return ladder

    keys = sorted(fired)
    edges = _self_depth_edges(keys)
    why: list[str] = []
    for a, b in sorted(edges):
        why.append(f"{a}→{b} (자기계열 depth)")

    # 사람이 못박은 순서를 먼저 심는다 — 아래 증거 계산은 이 쌍을 건너뛴다.
    for a, b in (partial_order or []):
        if a in fired and b in fired:
            edges.add((a, b))
            why.append(f"{a}→{b} (지정)")
        else:
            missing = [x for x in (a, b) if x not in fired]
            ladder.notes.append(f"지정 순서 {a}→{b} 를 적용하지 못했습니다 — "
                                f"{missing} 가 등재되지 않았습니다")

    n_pairs = 0
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            n_pairs += 1
            if (a, b) in edges or (b, a) in edges:
                continue
            # 2. 들여쓰기 — 계열이 몇 건이든, 번호가 리셋되든 말든 잰다.
            #    리셋 정렬은 통번호 계열(조)에, 덮음·사이-끼임은 희소 계열(절 6건)에
            #    안 통한다. 그 두 구멍을 이것이 메운다(indent.py 주석의 실측 참조).
            if page_width:
                ab = indent_mod.order(fired[a], fired[b], page_width)
                ba_ = indent_mod.order(fired[b], fired[a], page_width)
                if ab and not ba_:
                    edges.add((a, b))
                    why.append(f"{a}→{b} (들여쓰기 {ab[0]:.3f}<{ab[1]:.3f})")
                    continue
                if ba_ and not ab:
                    edges.add((b, a))
                    why.append(f"{b}→{a} (들여쓰기 {ba_[0]:.3f}<{ba_[1]:.3f})")
                    continue

            ra, ta = reset_alignment(fired[a], fired[b])
            rb, tb = reset_alignment(fired[b], fired[a])
            # 2. 리셋 정렬 — 표본이 충분할 때만. 리셋이 1회뿐이면 그 한 구간 안의
            #    모든 계열이 부모 후보가 되어 판별력이 사라진다(절 실측).
            if ra > rb and ta >= scoring.MIN_RESET_TOTAL and ra / ta >= 0.5:
                edges.add((a, b)); why.append(f"{a}→{b} (리셋 정렬 {ra}/{ta})")
                continue
            if rb > ra and tb >= scoring.MIN_RESET_TOTAL and rb / tb >= 0.5:
                edges.add((b, a)); why.append(f"{b}→{a} (리셋 정렬 {rb}/{tb})")
                continue
            # 3. 덮음
            ca, cb = coverage(fired[a], fired[b]), coverage(fired[b], fired[a])
            big_a = len(fired[b]) >= len(fired[a])
            big_b = len(fired[a]) >= len(fired[b])
            if ca >= MIN_COVERAGE and big_a and (cb < MIN_COVERAGE or not big_b):
                edges.add((a, b)); why.append(f"{a}→{b} (덮음 {ca:.0%})")
                continue
            if cb >= MIN_COVERAGE and big_b and (ca < MIN_COVERAGE or not big_a):
                edges.add((b, a)); why.append(f"{b}→{a} (덮음 {cb:.0%})")
                continue
            # 4. 사이-끼임 — 한 방향이 압도할 때만. 마진 1 은 3:2, 2:1 같은 노이즈를
            #    통과시켜 순환을 만든다(실측: 목→절 2:1 이 순환 7개의 시작점).
            #    **연속단위 안의 이웃만 센다**(chain_nesting) — 밀도가 아니라
            #    "번호가 이어지는 사이에 들어앉았는가"가 중첩의 증거다.
            if chain_evidence:
                na = chain_nesting(fired[a], fired[b])
                nb = chain_nesting(fired[b], fired[a])
            else:
                na = nb = 0
            if na == nb == 0:            # 연속단위 셈이 침묵하면 밀도 셈으로
                na = nesting_evidence(fired[a], fired[b])
                nb = nesting_evidence(fired[b], fired[a])
            total = na + nb
            if total and na > nb and na / total >= scoring.MIN_NESTING_RATIO:
                edges.add((a, b)); why.append(f"{a}→{b} (사이-끼임 {na}:{nb})")
            elif total and nb > na and nb / total >= scoring.MIN_NESTING_RATIO:
                edges.add((b, a)); why.append(f"{b}→{a} (사이-끼임 {nb}:{na})")

    ladder.n_pairs = n_pairs
    ladder.unordered_pairs = [f"{a}/{b}" for i, a in enumerate(keys) for b in keys[i + 1:]
                              if (a, b) not in edges and (b, a) not in edges]

    if hint:
        _apply_hint(ladder, hint, fired, edges, why)
        _apply_root(ladder, root)
        return ladder

    layers, broken = _toposort(keys, edges)
    ladder.cycle_broken = broken
    for level, group in enumerate(layers):
        ladder.rungs.append(Rung(
            level=level, families=list(group),
            reg_score=sum(reg.score(k, fired[k]) for k in group) / len(group),
            evidence="; ".join(e for e in why if e.startswith(tuple(group)))))

    if why:
        ladder.notes.append("근거: " + "; ".join(why))
    if broken:
        cycles = _find_cycles(keys, edges)
        ladder.notes.append(
            f"!! 사다리에 순환이 있습니다. {broken} 의 층은 증거가 아니라 "
            f"절단 규칙(이름 순)이 정했습니다 — 이 계열들의 레벨을 믿지 마세요. "
            + ("순환: " + "; ".join(" → ".join(c) for c in cycles) if cycles else ""))
    if ladder.unordered_pairs:
        ladder.notes.append(
            f"순서 미정 쌍: {', '.join(ladder.unordered_pairs)} — 네 증거가 모두 "
            f"침묵했습니다. 갈래 B(배열 열거) 미구현이라 관측된 층에 그대로 두었습니다")

    _apply_root(ladder, root)
    return ladder


def _apply_hint(ladder: Ladder, hint: list[list[str]], fired: dict[str, list[Candidate]],
                edges: set[tuple[str, str]], why: list[str]) -> None:
    """힌트로 사다리를 세우고 **관측과 대조한다**.

    힌트를 준다고 관측을 버리지 않는다. 힌트가 `장 > 조` 인데 관측이 반대로 말하면
    그 문서는 힌트와 다른 양식일 수 있다 — 조용히 힌트를 따르면 그 사실이 묻힌다.
    """
    placed: set[str] = set()
    for level, group in enumerate(hint):
        got = [k for k in group if k in fired]
        if got:
            ladder.rungs.append(Rung(
                level=len(ladder.rungs), families=got,
                reg_score=sum(reg.score(k, fired[k]) for k in got) / len(got),
                evidence="힌트"))
            placed.update(got)
    ladder.notes.append(f"사다리를 힌트로 세웠습니다 — 유도를 건너뜁니다 "
                        f"({len(ladder.rungs)}층, {sorted(placed)})")

    ghost = [k for group in hint for k in group if k not in fired]
    if ghost:
        ladder.notes.append(f"힌트에 있으나 이 문서에서 발화하지 않은 계열: {sorted(set(ghost))}")
    extra = sorted(set(fired) - placed)
    if extra:
        # 힌트에 없는데 발화한 계열 — 층을 안 주면 문맥판정으로 넘어간다.
        ladder.unregistered.extend(extra)
        ladder.notes.append(f"!! 힌트에 없는데 발화한 계열: {extra} — 층을 주지 않았습니다. "
                            f"힌트가 이 문서를 다 설명하지 못합니다")

    # 관측 대조
    level_of = {k: r.level for r in ladder.rungs for k in r.families}
    conflicts = [f"{a}→{b}" for a, b in sorted(edges)
                 if a in level_of and b in level_of and level_of[a] >= level_of[b]]
    if conflicts:
        ladder.notes.append(
            f"!! 힌트와 관측이 어긋납니다: 관측은 {conflicts} 라고 말합니다 "
            f"— 힌트를 따랐습니다. 이 문서가 다른 양식인지 확인하세요")
    if why:
        ladder.notes.append("관측(참고): " + "; ".join(why))


def _apply_root(ladder: Ladder, root: str | None) -> None:
    """좌표 최상위 접기 — `level` 은 미관이 아니라 `section_id` 를 만든다.

    장을 조의 상위로 두면 모든 조 좌표에 `제N장/` 이 붙어, 조를 최상위로 쓰는
    다운스트림 규약(`KSB/제19조/제3항`)이 통째로 깨진다. 관측은 관측대로 내되
    "어디부터가 좌표의 최상위인가" 는 밖에서 명시한다. 무엇을 접었는지는 남는다.
    """
    if not root:
        return
    cut = ladder.level_of(root)
    if cut is None:
        ladder.notes.append(f"root '{root}' 가 등재된 계열에 없습니다 — 접기를 건너뜁니다")
        return
    ladder.root = root
    for rung in ladder.rungs:
        if rung.level < cut:
            ladder.flattened.extend(rung.families)
        rung.level = max(0, rung.level - cut)
    merged: dict[int, Rung] = {}
    for rung in ladder.rungs:
        cur = merged.get(rung.level)
        if cur is None:
            merged[rung.level] = rung
        else:
            cur.families.extend(rung.families)
            cur.evidence = "; ".join(x for x in (cur.evidence, rung.evidence) if x)
    ladder.rungs = [merged[k] for k in sorted(merged)]
    if ladder.flattened:
        ladder.notes.append(
            f"좌표 최상위를 '{root}' 로 잡아 {sorted(set(ladder.flattened))} 를 "
            f"level 0 으로 접었습니다")
