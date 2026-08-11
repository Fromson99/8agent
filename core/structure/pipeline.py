"""구조 해석기 본체 — S0~S6 (SPEC §1.3, §4).

    문서 → Docling 파싱
         → S0 발화 탐지 (후보 수집)
         → S1 국소 채점 (s(cand))
         → S2 계열 정합 (사다리 없이 구조/인용 가르기)      ← 초판에 없던 단계
         → S3 레벨 유도 (정제된 후보로 사다리)
         → S4 전역 선택 (DP → 트리)
         → S5 fitness 게이트 (정상 / cold 라우팅 / 잔여 LLM 배치)
         → S6 저장 분기 (문서결과 항상 / frame 등재는 재현 게이트)

## 초판에서 바뀐 것 — S2 가 사다리 앞으로 왔다

초판은 레벨을 먼저 정하고(S2) 서수로 후보를 걸렀다(S3). 그 순서에서는 등재 심사가
"양수 후보 비율"로 계열을 걸러야 했고, 조(條)처럼 **제목과 같은 글자로 인용되는**
계열은 가드가 인용을 정확히 깎아낼수록 비율이 떨어져 탈락했다. 탈락하면 레벨이 없고,
레벨이 없으면 스코프가 없고, 스코프가 없으면 제55조와 제51조가 만나지 못해 서수
규칙이 영영 발동하지 않았다.

서수 비교는 **같은 계열 안에서만** 일어나므로 레벨이 필요 없다 — 초판이 전제한
의존이 실제로는 없었다. 그래서 계열 정합을 앞으로 옮겼다. 실측: 금소법 조 251 → 77건
(번호 1~69 연속), 준칙 조 206 → 0건(인용만 있는 문서라 정확한 판정).

**core 파이프라인은 고정, 신호는 plug-in 이다**(§3). 이 파일은 관리소를 통해서만
신호를 보므로, 제안자나 가드를 추가해도 여기는 바뀌지 않는다.
"""

from __future__ import annotations

import bisect
from typing import Optional

from core.structure import dp, family as family_mod, title as title_mod
from core.structure import fingerprint as fp_mod, registry as registry_mod
from core.structure import lexicon as lexicon_mod
from core.structure import scoring
from core.structure.global_outer import ladder as ladder_mod
from core.structure.global_outer import reg_score
from core.structure.model import Block, Candidate, StructureResult

def ladder_quality(ladder) -> tuple[float, list[str]]:
    """사다리 자체의 결함을 점수로 (§4 S5).

    후보 하나하나의 정합만 보면 사다리가 틀린 것을 못 본다 — 실측에서 순환 7개를
    이름 순으로 끊은 문서가 99% 를 받았다. 이미 계산해 둔 신호를 점수에 넣는다.
    """
    penalties: list[str] = []
    q = 1.0
    n_fam = sum(len(r.families) for r in ladder.rungs) or 1

    if ladder.cycle_broken:
        share = len(ladder.cycle_broken) / n_fam
        q -= scoring.PENALTY_CYCLE * share
        penalties.append(f"순환 절단 {len(ladder.cycle_broken)}/{n_fam} 계열 "
                         f"({ladder.cycle_broken}) — 층이 증거가 아니라 이름 순으로 정해졌습니다")
    if ladder.unordered_pairs and ladder.n_pairs:
        share = len(ladder.unordered_pairs) / ladder.n_pairs
        q -= scoring.PENALTY_UNORDERED * share
        penalties.append(f"순서 미정 {len(ladder.unordered_pairs)}/{ladder.n_pairs} 쌍")
    if ladder.unregistered:
        share = len(ladder.unregistered) / (n_fam + len(ladder.unregistered))
        q -= scoring.PENALTY_UNREGISTERED * share
        penalties.append(f"미등재 계열 {sorted(ladder.unregistered)}")
    return max(0.0, q), penalties


# ---------------------------------------------------------------------------
# S0 · 발화 탐지 — 판단 0, 순수 수집
# ---------------------------------------------------------------------------

def s0_propose(blocks: list[Block], reg: registry_mod.Registry, lex,
               lang: str = "any", families: Optional[list[str]] = None) -> list[Candidate]:
    """families 를 주면 그 계열의 제안자만 발화시킨다 — 어휘를 문서군에 맞게 좁힌다."""
    allow = set(families or [])
    signals = [s for s in reg.proposers(lang)
               if not allow or s.family in allow or s.id in allow]
    out: list[Candidate] = []
    for block in blocks:
        if not block.proposes:
            continue          # 표 셀 안의 번호, 그림 캡션의 `<그림 3>` 은 구조가 아니다
        for signal in signals:
            out.extend(signal.fn()(block, lex))
    if allow:
        out = [c for c in out if c.family in allow or c.family_key in allow
               or c.family.split(":")[0] in allow]
    out.sort(key=lambda c: (c.block_idx, c.offset, c.family))
    for i, c in enumerate(out, start=1):
        c.id = f"c{i}"
    return out


# ---------------------------------------------------------------------------
# S1 · 국소 채점 — 병렬, 순서 무관
# ---------------------------------------------------------------------------

def s1_score(cands: list[Candidate], blocks: list[Block],
             reg: registry_mod.Registry, lex, lang: str = "any") -> None:
    guards = reg.guards(lang)
    for c in cands:
        acc: dict[str, float] = {}
        for signal in guards:
            acc.update(signal.fn()(c, blocks, lex))
        c.guards = acc
        c.s = scoring.total_local(acc)


# ---------------------------------------------------------------------------
# S2 · 계열 정합 — 사다리 없이 구조와 인용을 가른다
# ---------------------------------------------------------------------------

def s2_family(cands: list[Candidate]) -> dict[str, int]:
    return family_mod.select(cands)


# ---------------------------------------------------------------------------
# S3 · 레벨 유도 (바깥) — 정제된 후보로
# ---------------------------------------------------------------------------

def s3_induce(cands: list[Candidate], root: Optional[str] = None,
              hint: Optional[list[list[str]]] = None,
              partial_order: Optional[list[tuple[str, str]]] = None,
              page_width: Optional[dict[int, float]] = None):
    survivors = [c for c in cands if c.survives]
    ladder = ladder_mod.induce_ladder(survivors, root=root, hint=hint,
                                      partial_order=partial_order,
                                      page_width=page_width)

    by_family: dict[str, list[Candidate]] = {}
    for c in survivors:
        by_family.setdefault(c.family_key, []).append(c)

    for key, group in sorted(by_family.items()):
        level = ladder.level_of(key)
        flagged = {id(c) for c in reg_score.outliers(group)}
        for c in group:
            if level is None:
                c.level, c.unassigned = None, True
                c.assign_note = f"{key} 미등재 — 문맥판정"
            elif id(c) in flagged:
                c.level, c.unassigned = level, True
                c.assign_note = f"{key}=L{level} 이지만 리셋 뒤가 안 이어짐 — 문맥판정"
            else:
                c.level, c.unassigned = level, False
    return ladder


# ---------------------------------------------------------------------------
# S4 · 전역 선택 보정 + 트리 후처리 (층 해제 · 제목 · 잎 · 범위)
# ---------------------------------------------------------------------------

def s4_unlock(cands: list[Candidate], ladder, dpr) -> list[str]:
    """사다리가 **열 수 없는 층**에 앉힌 계열을 미배정으로 풀어 준다. 반환: 푼 계열들.

    ## DP 가 스스로 보고하는 실패

    `dp.run` 은 후보마다 `decision_margin` 을 남긴다. 이 값이 `inf` 라는 것은 근소차로
    졌다는 뜻이 **아니라** 활성 선택지를 하나도 평가하지 못했다는 뜻이다(`dp.py` 의
    `best_activate > -inf` 분기). 그런 일은 한 가지 이유로만 일어난다 —
    `nesting.check` 가 그 레벨을 FORBID 한 것이다. L2 를 열려면 L0·L1 중 하나가 열려
    있어야 하는데 그 자리에서는 둘 다 닫혀 있었다.

    실측(신한은행 신규가입신청서): `bullet_■` 25건 중 문서 앞머리 7건이 전부
    `margin=inf` 로 기각됐다. 그 문서에서 가장 많이 쓰인 구조 마커인데 트리 앞부분에
    한 번도 서지 못했다. 사다리가 `■` 를 L2 에 놓았고, 그 앞에 L0·L1 을 여는 것이
    아무것도 없었기 때문이다.

    ## 왜 사다리를 고치지 않고 후보를 푸는가

    "증거가 얇으면 등재하지 않는다" 를 계열 전체에 적용해 봤더니 더 나빴다(실측):
    구조가 통째로 불릿인 문서(부산은행)는 사다리가 비어 적합도가 0.97 → 0.00 이 됐고,
    다른 문서에서는 활성 개수가 하나도 늘지 않은 채 벌점만 붙었다.

    그래서 **관측된 손해에만** 개입한다. 손해는 DP 가 이미 숫자로 말했다 — 그 계열의
    후보가 열릴 자리를 못 찾았다는 것. 그때만 그 계열의 층을 풀어 문맥이 정하게 한다
    (`dp._levels_for` 는 미배정 후보에 모든 레벨을 후보로 준다).

    푸는 것은 **층뿐이고 판정이 아니다.** 여전히 가드·서수 게이트·계층성이 그대로
    적용되며, 풀린 계열이 아무 데나 앉지 않는다.
    """
    blocked: dict[str, int] = {}
    for c in cands:
        if c.activated or not c.survives:
            continue
        if c.s <= dp.ACTIVATE_FLOOR:
            # 점수로 가지쳐진 후보다(`dp.run` 의 live 필터). DP 에 들어가지 않았으니
            # margin 이 초기값 inf 로 남는데, 그것은 층이 막힌 증거가 아니다 —
            # 여기서 거르지 않으면 저득점 계열의 층이 통째로 풀린다.
            continue
        if c.decision_margin == float("inf") and c.level is not None:
            blocked[c.family_key] = blocked.get(c.family_key, 0) + 1
    if not blocked:
        return []

    freed = sorted(blocked)
    for c in cands:
        if c.family_key in blocked:
            c.level, c.unassigned = None, True
            c.assign_note = (f"{c.family_key} 층 해제 — 사다리가 앉힌 L"
                             f"{ladder.level_of(c.family_key)} 을 열 수 있는 자리가 "
                             f"문서에 없었습니다(막힌 후보 {blocked[c.family_key]}건)")
    # 감사 메시지는 **부르는 쪽이** 두 번째 DP 결과에 붙인다. 여기서 `dpr.audit` 에
    # 넣으면 재실행이 새 DPResult 를 만들면서 통째로 사라진다 — 실제로 사라졌다.
    return freed


def _unlock_note(freed: list[str], cands: list[Candidate]) -> str:
    """무엇을 왜 풀었는지 한 줄로. 기록이 없으면 나중에 고칠 수가 없다(§8.7)."""
    n = {k: sum(1 for c in cands if c.family_key == k) for k in freed}
    return ("[층 해제] " + ", ".join(f"{k}({n[k]}건)" for k in freed)
            + " — 사다리가 앉힌 층을 열 자리가 문서에 없어 미배정으로 돌리고 DP 를 "
              "다시 돌렸습니다")


def _induce_and_select(result: StructureResult, blocks: Optional[list[Block]],
                       n_blocks: int, *, root: Optional[str],
                       hint: Optional[list[list[str]]],
                       partial_order: Optional[list[tuple[str, str]]]) -> None:
    """S3(사다리 유도) → S4(DP · 층 해제 1회 · 트리 · 제목 · 잎 · 범위).

    `interpret` 와 `rebuild` 의 공통 구간 — 같은 열두 줄이 두 곳에 있으면 한쪽만
    고쳐지는 사고가 난다. 감사 로그는 **잇는다**: 첫 해석은 빈 로그라 결과가 같고,
    rebuild 는 앞선 로그를 보존해야 한다(무엇을 풀고 다시 돌렸는지가 거기 있다).
    """
    cands = result.candidates
    result.ladder = s3_induce(cands, root=root, hint=hint,
                              partial_order=partial_order,
                              page_width=Block.page_widths(blocks) if blocks else None)
    dpr = dp.run(cands, result.ladder)
    # 사다리가 열 수 없는 층에 앉힌 계열이 있으면 풀고 **한 번만** 다시 돈다.
    # 되풀이하지 않는다 — 두 번째에도 막히면 그것은 층 문제가 아니다.
    freed = s4_unlock(cands, result.ladder, dpr)
    if freed:
        dpr = dp.run(cands, result.ladder)      # 새 DPResult — 감사도 새로 시작한다
        dpr.audit.insert(0, _unlock_note(freed, cands))
        result.stats["unlocked"] = freed
    result.tree = dp.build_tree(cands, n_blocks)
    # 제목은 **트리가 만들어진 뒤에** 뽑는다 — "이 마디가 내용을 따로 가졌는가"를
    # 알아야 꼬리가 제목인지 본문인지 갈린다.
    if blocks:
        result.stats["titled"] = title_mod.extract(result.tree, cands, blocks)
        result.stats["attached"] = attach_leaves(result, blocks)
    measure_extent(result, blocks)   # 지면에서 덮은 범위 (2단 어긋남의 재료)
    result.audit_log = result.audit_log + dpr.audit
    result.stats["dp_total"] = round(dpr.total, 3)
    result.stats["pruned"] = dpr.pruned


def measure_extent(result: StructureResult, blocks: list[Block]) -> int:
    """마디마다 **지면에서 실제로 덮은 범위**를 잰다. 반환: 잰 마디 수.

    ## 왜 재 두는가 — 읽기 순서는 한 줄이지만 지면은 2차원이다

    2단 편집에서 왼쪽 단의 내용이 오른쪽 단 제목의 span 으로 넘어간다. 실측
    (GMS_D3421 p2): `유사 금융상품과 구별되는 특징`(좌단) 아래의 ELS·DLS 설명이
    `발생 가능한 불이익 사항`(우단) 구역으로 들어갔다. 읽기 순서만 보면 실제로
    그 사이에 있으니 코드로는 틀린 줄을 모른다.

    그림을 보면 사람은 바로 안다 — **좌표가 다르기 때문이다.** 좌단 제목의 x 범위
    안에 있는 내용이 우단 제목에 딸려 있으면 그건 어긋남이다. 그 판단에 필요한
    좌표를 여기서 저장해 둔다.

    ## 지금은 재기만 한다

    어긋남을 고치지 않는다. 2단 판정에는 임계값이 필요하고(어디까지가 같은 단인가),
    그 임계는 이 데이터가 여러 문서에 쌓인 뒤에 정해야 한다. 지금 정하면 문서 하나에
    맞춘 숫자가 된다.

    합집합은 **쪽마다 따로** 둔다. 구역이 쪽을 넘으면 한 상자로 합칠 수 없다.
    표·그림도 포함한다 — 그것도 그 구역이 지면에서 차지한 자리다.
    """
    if not blocks:
        return 0                     # 블록이 없으면 잴 것이 없다(rebuild 경로)
    by_idx = {b.idx: b for b in blocks}
    n = 0
    for node in result.nodes():
        own = by_idx.get(node.block_idx)
        if own is not None and own.bbox:
            node.bbox = list(own.bbox)
            node.bbox_origin = own.bbox_origin
        pages: dict[int, dict] = {}
        for i in range(node.span[0], max(node.span[1], node.span[0] + 1)):
            b = by_idx.get(i)
            if b is None or not b.bbox:
                continue
            cur = pages.get(b.page)
            l, t, r, bo = b.bbox
            if cur is None:
                pages[b.page] = {"box": [l, max(t, bo), r, min(t, bo)],
                                 "origin": b.bbox_origin, "blocks": 1}
            else:
                box = cur["box"]
                box[0] = min(box[0], l)
                box[1] = max(box[1], t, bo)      # BOTTOMLEFT: 위쪽이 큰 y
                box[2] = max(box[2], r)
                box[3] = min(box[3], t, bo)
                cur["blocks"] += 1
        for v in pages.values():
            v["box"] = [round(x, 2) for x in v["box"]]
        node.extent = pages
        n += bool(pages)
    result.stats["measured_extent"] = n
    return n


def s5_thin(result: StructureResult, blocks: list[Block]) -> int:
    """구조가 **얇은 구간**에서 놓친 제목 후보를 잔여로 올린다. 반환: 올린 개수.

    ## 기존 잔여가 못 잡는 자리

    `s5_residual` 은 "후보끼리 신호가 어긋난 것"만 모은다. 그런데 실측에서 가장
    아픈 실패는 **후보가 아예 안 선 것**이다:

        삼성증권 디폴트옵션 안정투자형 포트폴리오 1     번호도 불릿도 없다
        ■ 특정금전신탁상품 서류 목록                   불릿은 있으나 활성화 실패

    후보가 없으면 모순도 없으므로 잔여에 영영 올라오지 않는다. 놓친 것이 "애매한
    것"으로 분류되지조차 않는 것이 지금 구조의 구멍이다.

    ## 무엇을 근거로 의심하는가

    두 가지가 겹칠 때만 올린다 — 하나만으로는 잡음이 너무 많다.

        구간   연속 `THIN_RUN` 블록 이상 **마디가 하나도 열리지 않았다**
        모양   그 안에 **그 쪽 본문보다 큰**(`size_ratio`) 또는 굵은 블록이 있다

    타이포그래피가 없는 문서(스캔본 등)에서는 `size_ratio` 가 `None` 이라 이 단계가
    조용히 0건을 낸다 — 없는 신호로 억지 판정을 하지 않는다.

    ## 여기서 판정하지 않는다

    올리는 것은 **의심**이고 판정이 아니다. 이 목록이 VLM 에 갈 자리다(§0: LLM 은
    결정론이 못 가른 잔여에만). 픽셀은 결정론이 볼 수 없는 축이고, 그 축을 물어야
    하는 자리가 정확히 여기다.
    """
    if not blocks:
        return 0
    opens = {n.block_idx for n in result.nodes()}
    n_before = len(result.residual)

    run_start = 0
    added = 0

    def sweep(lo: int, hi: int) -> int:
        """구간 [lo, hi) 안에서 크거나 굵은 블록을 의심으로 올린다."""
        got = 0
        for b in blocks[lo:hi]:
            if not b.proposes:
                continue
            big = b.size_ratio is not None and b.size_ratio >= scoring.THIN_SIZE
            if not (big or b.bold):
                continue
            why = []
            if big:
                why.append(f"본문 {b.size_ratio:.2f}배")
            if b.bold:
                why.append("굵음")
            if b.gap_before:
                why.append(f"위 간격 {b.gap_before:.0f}pt")
            result.residual.append(
                f"[놓친 제목?] blk{b.idx} typography '{b.text[:40]}' @블록{b.idx} "
                f"p{b.page} — {', '.join(why)}; 마디 없는 구간 {hi - lo}블록")
            got += 1
        return got

    for i in range(len(blocks) + 1):
        if i < len(blocks) and i not in opens:
            continue
        if i - run_start >= scoring.THIN_RUN:
            added += sweep(run_start, i)
        run_start = i + 1

    result.stats["thin_suspects"] = added
    if added:
        result.audit_log.append(
            f"[얇은 구간] 마디 없는 구간에서 크거나 굵은 블록 {added}건을 잔여로 "
            f"올렸습니다 — 후보가 서지 못한 제목일 수 있습니다")
    return len(result.residual) - n_before


def attach_leaves(result: StructureResult, blocks: list[Block]) -> int:
    """표·그림을 **바로 위 마디**에 잎으로 매단다 (S4 뒤). 반환: 매단 개수.

    ## 왜 span 포함으로 정하면 안 되는가 — 실측이 두 가지로 무너진다

    검수 화면은 지금까지 "이 블록을 덮는 마디 중 **가장 깊은 것**" 으로 소유자를
    정했다. 마커가 촘촘한 법령에서는 맞지만 양식 문서에서 두 가지로 깨진다
    (실측 신한은행 신규가입신청서, 표 12개):

        · 문서 앞머리의 표 3개는 **소유자가 없다.** 그 앞의 `■ …` 이 활성화되지
          못해 덮는 마디가 하나도 없었다.
        · 나머지는 **503블록짜리 구간**(`• 생년월일(사업자번호)` p2~p6)에 딸려갔다.
          p3 의 표가 p2 의 불릿 소유가 된다. 사이에 활성 마커가 없으면 span 이
          그만큼 길어지는데, 포함 관계는 거리를 보지 않는다.

    구역을 여는 것은 마커지만 **표가 어느 구역의 것인지는 자리가 정한다.** 사람이
    문서를 볼 때도 표 바로 위의 제목을 그 표의 이름으로 읽는다. 그래서 포함이 아니라
    **직전(가장 가까운 앞)** 마디를 소유자로 삼는다.

    읽기 순서는 파싱 단계에서 이미 좌표로 바로잡혀 있다(`core.reading_order`).
    그래서 "직전" 은 읽기 순서이면서 곧 지면 위의 자리다.

    앞에 마디가 하나도 없으면 **매달지 않는다.** 문서 머리말의 표를 아무 구역에나
    밀어 넣지 않는다 — 소유자가 없다는 사실 자체가 구조가 덜 잡혔다는 신호다.
    """
    nodes = result.nodes()
    for n in nodes:
        n.attachments = []
    if not nodes:
        return 0
    ordered = sorted(nodes, key=lambda n: (n.block_idx, n.level))
    starts = [n.block_idx for n in ordered]
    attached = 0
    for b in blocks:
        if b.proposes:
            continue
        i = bisect.bisect_right(starts, b.idx) - 1
        if i < 0:
            continue                       # 앞에 마디가 없다 — 매달지 않는다
        owner = ordered[i]
        owner.attachments.append({
            "kind": b.kind, "block": b.idx, "page": b.page,
            "element_index": b.element_index,
            "distance": b.idx - owner.block_idx,
            "same_page": b.page == owner.page,
        })
        attached += 1
    return attached


def s5_fitness(result: StructureResult, blocks: list[Block]) -> None:
    """총점(커버리지 × 정합) ≥ threshold → 정상 (§4 S5)."""
    active = result.activated()
    if not active or not blocks:
        result.fitness_score, result.fitness_passed = 0.0, False
        result.warnings.append("활성 후보가 없습니다 — 구조를 찾지 못했습니다")
        return

    # 커버리지 — 블록이 얼마나 구조 아래 들어왔는가
    covered = len({b for n in result.nodes() for b in range(n.span[0], n.span[1])})
    coverage = min(1.0, covered / len(blocks))

    # 정합 — 활성 후보가 벌점 없이 앉았는가
    clean = sum(1 for c in active if "novelty" not in c.decision_note
                and "역행" not in c.decision_note and "건너뜀" not in c.decision_note)
    consistency = clean / len(active)

    quality, penalties = ladder_quality(result.ladder)

    result.fitness_score = coverage * consistency * quality
    result.fitness_passed = result.fitness_score >= scoring.FITNESS_T
    result.stats.update({"coverage": round(coverage, 3),
                         "consistency": round(consistency, 3),
                         "ladder_quality": round(quality, 3),
                         "blocks": len(blocks), "covered_blocks": covered,
                         "table_blocks": sum(1 for b in blocks if b.kind == "table"),
                         "figure_blocks": sum(1 for b in blocks if b.kind == "figure"),
                         "candidates": len(result.candidates),
                         "activated": len(active)})
    # 점수와 별개로 **시끄럽게** 남긴다 — 사다리 결함은 임계값을 넘겨도 알려야 한다.
    for p in penalties:
        result.warnings.append(f"사다리 결함: {p}")
    if not result.fitness_passed:
        result.warnings.append(
            f"적합도 {result.fitness_score:.0%} < T {scoring.FITNESS_T:.0%} "
            f"— cold 라우팅(보편 skeleton + bounded LLM). 룰을 축적하지 않습니다")


def _run_distance(result: StructureResult) -> dict[str, int]:
    """탈락 후보마다 **읽기 순서로 가장 가까운 연속 단위**와의 번호 차.

    "가드는 헤더라는데 수열이 아니라고 한다"가 늘 애매한 것은 아니다. 그 번호가
    가까운 묶음의 범위 근처면 빠진 번호일 수 있지만(→ 애매), 한참 떨어져 있으면
    인용이 확실하다(→ 확정). 실측 KSB-D 에서 0 과 13~48 로 갈린다.
    """
    by_family: dict[str, dict[int, list]] = {}
    for c in result.candidates:
        if c.survives and c.ordinal and c.chain is not None:
            by_family.setdefault(c.family_key, {}).setdefault(c.chain, []).append(c)

    out: dict[str, int] = {}
    for c in result.candidates:
        if c.survives or not c.ordinal:
            continue
        chains = by_family.get(c.family_key)
        if not chains:
            continue
        best = min(chains.values(),
                   key=lambda ch: min(abs(x.block_idx - c.block_idx) for x in ch))
        lo = min(x.ordinal[0] for x in best)
        hi = max(x.ordinal[0] for x in best)
        n = c.ordinal[0]
        out[c.id] = 0 if lo <= n <= hi else min(abs(n - lo), abs(n - hi))
    return out


def s5_residual(result: StructureResult) -> None:
    """**신호가 서로 모순되는 후보**를 모은다 — 문서당 1콜 배치로 갈 것들 (§4 S5).

    "DP 가 근소차로 못 가른 것"만 재던 이전 판은 세 문서에서 0건을 냈다. 실제로
    틀린 자리는 마진이 아니라 **신호 충돌**에 드러난다. 세 종류를 모은다.

        모순 A  가드는 확실한 헤더(s ≥ 1.5)라는데 계열 정합이 인용이라고 했다
        모순 B  DP 가 손해(전이 < 0)를 보면서 활성시켰다 — 다른 선택지가 더 나빴다는 뜻
        모순 C  최선과 차선의 차가 근소하다 (기존 정의)

    이것들만 한 덩어리로 LLM 에 던진다. per-후보 루프가 아니라 **문서당 1콜**이고,
    결정론이 확신한 것은 여기 오지 않는다.
    """
    seen: set[str] = set()

    def add(c, kind: str, detail: str) -> None:
        if c.id in seen:
            return
        seen.add(c.id)
        result.residual.append(
            f"[{kind}] {c.id} {c.family_key} '{c.surface}' @블록{c.block_idx} "
            f"p{c.page} — {detail}")

    near = _run_distance(result)
    for c in result.candidates:
        if c.llm_verdict:
            continue                     # 배치가 이미 판정했다 — 다시 묻지 않는다
        if not c.survives:
            d = near.get(c.id)
            if c.s >= scoring.CONFLICT_S and d is not None and d <= scoring.DOUBT_DISTANCE:
                add(c, "가드↔수열",
                    f"가드 s={c.s:+.2f}(확실한 헤더)이고 가까운 연속 단위와 번호 차가 "
                    f"{d} 뿐입니다 — 빠진 번호일 수 있습니다. {c.family_note}")
            continue
        if c.activated and c.transition_gain < 0:
            add(c, "손해활성", f"전이 {c.transition_gain:+.2f} — {c.decision_note}")
        elif c.decision_margin <= scoring.RESIDUAL_MARGIN:
            add(c, "근소차", f"마진 {c.decision_margin:.2f} — {c.decision_note}")


def residual_prompt(result: StructureResult) -> str:
    """잔여를 LLM 배치 1콜에 던질 형태로 (§4 S5). 후보마다 원문 한 줄을 붙인다.

    후보가 아닌 잔여(`[놓친 제목?] blkN …`, s5_thin)는 싣지 않는다 — 배치의 답은
    후보 id 로만 돌아오므로 물어도 버려지고, 그 의심은 S5c(VLM)가 픽셀로 본다.
    """
    if not result.residual:
        return ""
    by_id = {c.id: c for c in result.candidates}
    lines = [f"문서: {result.doc}",
             "아래 후보들은 결정론 판별이 서로 다른 답을 냈습니다.",
             "각각이 **구조 경계**인지 **본문 속 인용**인지만 판정하세요.", ""]
    for r in result.residual:
        c = by_id.get(r.split()[1])
        if c is None:
            continue
        lines.append(r)
        lines.append(f'    원문: "{c.text[:160]}"')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def interpret(blocks: list[Block], doc: str, *,
              registry: Optional[registry_mod.Registry] = None,
              lexicon=None, lang: str = "ko",
              root: Optional[str] = None,
              families: Optional[list[str]] = None,
              ladder_hint: Optional[list[list[str]]] = None,
              partial_order: Optional[list[tuple[str, str]]] = None,
              llm=None,
              pdf_path=None,
              ledger: Optional[fp_mod.Ledger] = None) -> StructureResult:
    """블록 리스트를 해석해 구조 트리와 frame 재료를 낸다.

    ## 사람이 아는 것을 넣는 통로 (§7 frame 의 수동 주입)

    문서군의 생김새를 이미 안다면 유도를 기다릴 것 없이 넣는다. 강도가 넷이고, 무엇을
    주든 **관측은 계속 돌면서 어긋남을 알린다** — 힌트와 다른 양식이 들어올 수 있다.

    families      어휘 제한. 이 계열의 제안자만 발화시킨다. 후보가 애초에 안 생긴다.
                  예: `["dot_number", "roman"]`
    partial_order 특정 쌍의 순서만 못박는다. 증거가 얇아 못 정하는 쌍에 한 줄.
                  예: `[("kr_장", "kr_article")]`
    ladder_hint   층을 통째로 지정. 유도를 건너뛰므로 순환·순서미정이 사라진다.
                  예: `[["dot_number:1"], ["dot_number:2"], ["dot_number:3"], ["roman_lower"]]`
    root          좌표 최상위. `level` 은 `section_id` 를 만들므로, 조를 최상위로 쓰는
                  다운스트림 규약(`KSB/제19조/제3항`)이 있으면 여기서 명시한다.

    어휘(`proposers/`)에는 여전히 레벨이 없다(SPEC §6). 여기 들어오는 것은 어휘가
    아니라 **이 문서군에 대한 입력**이다.
    """
    reg = registry or registry_mod.default()
    lex = lexicon or lexicon_mod.default()
    result = StructureResult(doc=doc)
    # 이 문서에 무엇을 주입했는지 결과에 남긴다 — 힌트는 시스템 규칙이 아니라
    # **이 문서에 대한 입력**이라 결과와 함께 봐야 뜻이 통한다.
    result.applied = {"root": root, "families": families,
                      "ladder_hint": ladder_hint,
                      "partial_order": [f"{a}>{b}" for a, b in (partial_order or [])],
                      "llm": llm is not None, "lang": lang}

    cands = s0_propose(blocks, reg, lex, lang, families=families)
    result.candidates = cands
    if not cands:
        result.warnings.append(
            "어떤 제안자도 발화하지 않았습니다 — 어휘에 없는 표면 패턴이거나 파싱이 무너졌습니다")
        return result

    s1_score(cands, blocks, reg, lex, lang)

    dropped = s2_family(cands)
    result.stats["family_dropped"] = dropped
    result.stats["survivors"] = sum(1 for c in cands if c.survives)

    result.stats["page_width"] = len(Block.page_widths(blocks))
    _induce_and_select(result, blocks, len(blocks), root=root, hint=ladder_hint,
                       partial_order=partial_order)

    s5_fitness(result, blocks)
    s5_residual(result)
    s5_thin(result, blocks)      # 후보가 서지 못한 제목 (§타이포그래피)

    # S5c · 큰 글씨 제목 — 마커가 없어 후보조차 못 선 상위 제목을 그림째 묻는다.
    # 트리가 다 선 **뒤에** 돈다: 조·항·호는 결정론이 이미 세웠고 VLM 은 그 위에
    # 지붕만 얹는다. pdf_path 나 llm 이 없으면 아무 일도 하지 않는다.
    if llm is not None and pdf_path:
        import time as _t

        from core.structure import vlm_heading as vlm_mod
        t0 = _t.monotonic()
        try:
            vlm_mod.run(result, blocks, pdf_path, llm)
        except Exception as exc:                     # 판정 실패가 해석을 세우면 안 된다
            result.warnings.append(f"VLM 제목 판정 실패 — {type(exc).__name__}: {exc}")
        result.stats["vlm_sec"] = round(_t.monotonic() - t0, 1)

    # S5b · 잔여 해소 — 문서당 배치 1콜. llm 이 없으면 통째로 건너뛴다(결정론 경로).
    if llm is not None:
        from core.structure import resolve as resolve_mod
        r = resolve_mod.resolve(result, llm, rebuild=True, root=root,
                                ladder_hint=ladder_hint, partial_order=partial_order,
                                blocks=blocks)
        result.stats["llm"] = r.dump()
        for n in r.notes:
            result.warnings.append(f"잔여 해소: {n}")

    result.fingerprint = fp_mod.of(cands, result.ladder)
    count = ledger.observe(result.fingerprint, doc) if ledger else 1
    result.tier = fp_mod.tier(count, result.fitness_passed)
    result.stats["fingerprint_count"] = count
    result.stats["may_freeze"] = fp_mod.may_freeze(count, result.fitness_passed)
    if not result.stats["may_freeze"] and result.fitness_passed:
        result.warnings.append(
            f"fingerprint 관측 {count}회 — frame 등재는 {fp_mod.FREEZE_AT}회부터입니다 "
            f"(문서 해석 결과는 저장, N=1 룰 추가 방지)")
    return result


def rebuild(result: StructureResult, *, root: Optional[str] = None,
            ladder_hint: Optional[list[list[str]]] = None,
            partial_order: Optional[list[tuple[str, str]]] = None,
            blocks: Optional[list[Block]] = None) -> None:
    """S3~S5 를 다시 돌린다 — 잔여 해소로 후보의 생존 여부가 바뀐 뒤에 쓴다.

    마커 하나가 살아나면 그 계열의 수열과 사다리가 통째로 달라질 수 있어서,
    트리만 손보면 앞뒤가 안 맞는다.
    """
    n_blocks = result.stats.get("blocks") or (len(blocks) if blocks else 0)
    for c in result.candidates:
        c.activated, c.activated_level = False, None
        c.decision_note, c.transition_gain = "", 0.0
        c.decision_margin = float("inf")
        c.title, c.title_reason = "", ""

    _induce_and_select(result, blocks, n_blocks, root=root, hint=ladder_hint,
                       partial_order=partial_order)
    result.stats["survivors"] = sum(1 for c in result.candidates if c.survives)

    result.warnings = [w for w in result.warnings if not w.startswith("사다리 결함")]
    result.residual = []
    if blocks is not None:
        s5_fitness(result, blocks)
    s5_residual(result)
    s5_thin(result, blocks)      # 후보가 서지 못한 제목 (§타이포그래피)
