"""S5c · 큰 글씨 제목 — 마커가 없어 후보조차 서지 못한 상위 제목을 VLM 으로 세운다.

    candidates(blocks)              비정상적으로 큰 글씨 뭉치를 고른다 (결정론)
    ask(llm, page_png, cands, ctx)  페이지 그림째 물어 heading 여부와 범위를 받는다
    promote(result, verdicts, ...)  확정된 것을 **한 계층 위** 마디로 세우고 구간을 자른다

## 왜 크기 임계로는 안 되는가 — 실측이 정확히 뒤집혀 있다

크기 임계로 후보를 내는 제안자를 만들려다 접었다. 신한은행 신규가입신청서에서:

    heading  1.263배  설명의무 이행 확인
    heading  3.748배  특정금전신탁 계약서(全文)
    body     3.932배  은행에 등록된            ← 가장 큰데 제목이 아니다
    body     3.932배  고객님의 정보입니다
    body     1.249배  (2-1)

**가장 큰 두 개가 제목이 아니고 1.26배가 제목이다.** 임계를 어디에 두든 `은행에
등록된`(미완결 조각)이 먼저 걸린다. 미완결 조각·종결어미·반복 라벨·사본 구분표시는
크기로 갈리지 않고 **뜻으로만** 갈린다. 그래서 이 단계는 결정론이 아니라 판정이다.

## 왜 페이지 **전체** 그림인가

잘라 보내면 그 줄이 아래 무엇을 거느리는지 볼 수 없다. 제목인지 아닌지는 그 줄 자체가
아니라 **아래에 거느릴 내용이 있는가**로 갈린다(실측 근거: "미완결 조각으로 양식 내
문구의 일부"). 페이지를 통째로 줘야 그 판단이 가능하다.

## 왜 트리를 **다 세운 뒤에** 도는가

VLM 에게 조를 찾게 하지 않는다. 조·항·호는 결정론이 이미 정확히 세워 두었고, VLM 은
"이 큰 글씨가 그중 어디부터 어디까지를 거느리는가"만 답하면 된다. 물음이 좁을수록
답이 안정된다(§0).

## 구간은 **서수 열**이 정한다 — 다음 제목까지 무조건 자르지 않는다

처음에는 "다음 제목 직전까지"로 잘랐는데 틀렸다. 그러면 마지막 제목이 문서 끝까지
전부 삼킨다(실측: `span=(51, 981)` — 930블록). 제목이 실제로 거느리는 것은 다음
제목이 어디 있느냐가 아니라 **자기 아래 서수 열이 어디서 끝나느냐**다.

    제목 A  아래에 제1조 … 제10조 → A 는 **자기 열의 끝(제10조)까지**를 주장한다

그 열 **중간에** 새 제목 B 가 나오면 두 가지 중 하나다. 이건 규칙으로 못 정하고
서수가 말해 준다:

    이어짐   B 아래가 제7조다 — 앞 열이 끊기지 않고 계속된다.
             → B 가 A 의 **꼬리를 잘라 간다.** A 는 제6조까지로 줄고 B 가 제7조부터.
             다만 한 서수 열을 둘로 가르는 것이므로 **B 가 진짜 구역인지 의심스럽다**
             (쪽 배너·이어지는 쪽의 반복 표제일 수 있다). 그 사실을 남긴다.
    리셋됨   B 아래가 다시 제1조다 — 새 열이 시작된다.
             → B 는 **새 꼬리**를 연다. A 는 자기 열 끝까지 그대로 유지한다.

그래서 VLM 에게 `relation` 을 함께 묻는다. 서수 연속성은 우리가 계산해 프롬프트에
실어 주고, 판정만 받는다 — 재료는 결정론이 대고 판단만 맡기는 §0 의 형태다.

제목 **아래**의 평문(표제에 딸린 안내문)은 시작점이 제목 블록이므로 자연히 들어온다.
"""

from __future__ import annotations

import statistics
from typing import Any, Optional

from core.structure.model import Block, Node, StructureResult

# 이 배율 미만은 아예 묻지 않는다. 실측 제목 최소가 1.26 배였고, 1.15 아래는
# 본문 강조가 대부분이라 물음만 늘린다.
MIN_RATIO = 1.20
# 한 페이지에서 이보다 많이 걸리면 그 쪽은 표지·양식이라 크기가 의미를 잃은 것이다.
MAX_PER_PAGE = 12
# 물어볼 쪽 수 상한. 호출 하나가 수십 초라 쪽이 많으면 재해석이 통째로 느려진다.
MAX_PAGES = 6
# 같은 글이 이만큼 되풀이되면 **쪽 머리글·문서 표제**다 — 묻지 않고 뺀다.
# 실측(GMS_D3421 5쪽): `KB able ELS 제3421호 핵심(요약)상품설명서` 가 2.87배로
# 5쪽 전부에 나온다. 문서 중간의 구역 제목이 아니라 문서 이름이므로 구조를 열지
# 않는다. 이걸 묻느라 호출이 5배로 늘고 재해석이 300초 가까이 걸렸다.
REPEAT_FURNITURE = 3
# 판정은 가르는 일이지 짓는 일이 아니다 — 싼 모델로 충분하다. 비싸게 갈 이유가
# 있으면 부르는 쪽이 model 을 준다.
CHEAP_MODEL = "claude-haiku-4-5-20251001"
# 같은 크기로 묶는 자릿수 — 3.932 와 3.930 은 같은 뭉치다.
ROUND = 2

SYSTEM = """당신은 한국어 문서의 **상위 제목 판별기**다. 답을 지어내지 마라.

문서의 조·항·호는 이미 정확히 잡혀 있다. 당신이 답할 것은 그것이 아니라, 마커가 없어
잡히지 않은 **큰 글씨**가 무엇인지다. 페이지 그림과 함께 후보 줄을 준다.

각 후보에 대해 판정하라.

    heading  이 줄은 아래 내용을 거느리는 제목이다. 그림에서 아래에 무엇이 오는지 보라.
    body     본문·안내문·라벨·양식 문구다. 크지만 제목이 아니다.
    unsure   둘 다로 읽힌다. 억지로 고르지 마라.

## 판단 기준 — 크기로 정하지 마라

크기는 이미 우리가 쟀고, 그것만으로는 갈리지 않는다(실측: 3.9배 조각이 본문이고
1.3배 명사구가 제목이었다). 그림에서 **아래에 거느릴 내용이 실제로 있는지** 보라.

    제목이다   아래에 조문·항목·설명이 이어지고, 그것들이 이 줄의 이름 아래 묶인다
    아니다     미완결 조각("은행에 등록된"), 종결어미로 끝나는 안내문("~입니다"),
               쪽마다 반복되는 라벨("원금 비보장 상품"), 사본 구분("고객용/은행용"),
               일련번호("(2-1)"), 기호만 있는 줄

## heading 이면 무엇을 거느리는지도 답하라

`covers` 에 그 제목이 거느리는 **첫 마디의 표면형**을 적어라(예: "제1조"). 그림에서
이 제목 바로 아래에 오는 마디다. 제목 아래에 마디가 없고 평문뿐이면 빈 문자열로 둔다.

`relation` 은 앞 제목과의 관계다. 프롬프트에 **앞 구간의 서수 열**을 함께 준다.

    new_run   아래 서수가 다시 1 부터 시작한다 — 새 열을 여는 독립된 부분이다.
    cut_tail  앞 구간의 서수 열이 끊기지 않고 이어진다 — 앞 제목의 꼬리를 가져간다.
              한 열을 둘로 가르는 것이므로, 이럴 때는 정말 구역을 여는지 더 엄하게 보라.
              이어지는 쪽의 반복 표제나 쪽 배너면 heading 이 아니라 body 다.
    none      거느리는 마디가 없다(평문뿐이거나 body).

끝나는 자리는 답하지 마라 — 서수 열로 우리가 계산한다."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["heading", "body", "unsure"]},
                    "covers": {"type": "string"},
                    "relation": {"type": "string",
                                 "enum": ["new_run", "cut_tail", "none"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "verdict", "covers", "relation", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


def candidates(blocks: list[Block], result: StructureResult) -> list[Block]:
    """비정상적으로 큰 글씨. **되풀이되는 것은 빼고** 돌려준다.

    이미 구역을 연 블록은 뺀다 — 마커가 잡은 것을 다시 물을 이유가 없다.

    같은 글이 `REPEAT_FURNITURE` 번 이상 나오면 쪽 머리글이거나 문서 표제다. 문서
    **중간**의 구역 제목은 그렇게 되풀이되지 않는다. 이건 판정이 필요 없는 구별이라
    결정론으로 처리하고 VLM 을 부르지 않는다 — 비용의 대부분이 여기 있었다.
    """
    opens = {n.block_idx for n in result.nodes()}
    big = [b for b in blocks
           if b.proposes and b.text and b.idx not in opens
           and b.size_ratio is not None and b.size_ratio >= MIN_RATIO]
    if not big:
        return []

    seen: dict[str, int] = {}
    for b in big:
        key = b.text.replace(" ", "")[:60]
        seen[key] = seen.get(key, 0) + 1
    furniture = {k for k, n in seen.items() if n >= REPEAT_FURNITURE}
    if furniture:
        result.stats["vlm_furniture"] = sorted(furniture)[:5]
        result.audit_log.append(
            f"[VLM 제목] 되풀이 {REPEAT_FURNITURE}회 이상인 큰 글씨 {len(furniture)}종을 "
            f"쪽 머리글·문서 표제로 보아 묻지 않았습니다")

    per_page: dict[int, int] = {}
    out: list[Block] = []
    for b in sorted(big, key=lambda x: x.idx):
        if b.text.replace(" ", "")[:60] in furniture:
            continue
        n = per_page.get(b.page, 0)
        if n >= MAX_PER_PAGE:
            continue                      # 이 쪽은 크기가 의미를 잃었다
        per_page[b.page] = n + 1
        out.append(b)
    return out


def _context(result: StructureResult, blocks: list[Block],
             page: int) -> list[str]:
    """그 쪽에서 결정론이 이미 세운 마디들 — VLM 이 '무엇을 거느리는가' 를 답할 재료."""
    return [f"{n.surface} {n.title}".strip()
            for n in sorted(result.nodes(), key=lambda n: n.block_idx)
            if n.page == page][:20]


def ordinal_run(result: StructureResult, start: int, end: int) -> dict[str, Any]:
    """[start, end) 구간에서 **가장 얕은 계열**의 서수 열. 제목의 사정거리다.

    "제목이 어디까지 거느리는가" 는 다음 제목이 어디냐가 아니라 **자기 아래 서수가
    어디서 끝나느냐**다. 가장 얕은 계열을 보는 이유: 조 아래 항·호는 조에 딸린 것이라
    조가 끝나면 함께 끝난다.
    """
    ns = [n for n in sorted(result.nodes(), key=lambda n: n.block_idx)
          if start <= n.block_idx < end and n.ordinal]
    if not ns:
        return {"family": "", "first": "", "last": "", "end_block": start + 1, "n": 0}
    top = min(n.level for n in ns)
    run = [n for n in ns if n.level == top]
    return {"family": run[0].family, "first": run[0].surface, "last": run[-1].surface,
            "first_ord": list(run[0].ordinal or ()), "last_ord": list(run[-1].ordinal or ()),
            "end_block": run[-1].span[1] if run[-1].span[1] > run[-1].block_idx
                         else run[-1].block_idx + 1,
            "n": len(run)}


def prompt_for(page: int, cands: list[Block], result: StructureResult,
               blocks: list[Block], n_blocks: int = 0,
               prev_run: Optional[dict] = None) -> str:
    lines = [f"{page}쪽. 이 쪽에서 결정론이 이미 세운 마디:",
             "  " + (", ".join(_context(result, blocks, page)) or "(없음)"), ""]
    if prev_run and prev_run.get("n"):
        lines += [f"앞 구간의 서수 열: {prev_run['family']} "
                  f"{prev_run['first']} … {prev_run['last']} ({prev_run['n']}건)", ""]
    lines.append("판정할 큰 글씨 후보 — 각각 아래에 이어지는 서수 열을 함께 적는다:")
    for b in cands:
        run = ordinal_run(result, b.idx, n_blocks or (b.idx + 400))
        if run["n"]:
            cont = ("앞 열에서 **이어짐**"
                    if prev_run and prev_run.get("last_ord") and run.get("first_ord")
                    and run["first_ord"] > prev_run["last_ord"]
                    else "**리셋**(1부터 다시)" if run.get("first_ord") == [1]
                    else "판단 필요")
            lines.append(f"    └ 아래 서수 열: {run['family']} {run['first']} … "
                         f"{run['last']} ({run['n']}건) — {cont}")
        lines.append(f"[blk{b.idx}] 본문의 {b.size_ratio}배"
                     f"{' 굵음' if b.bold else ''}"
                     f"{f' 위여백 {b.gap_before:.0f}pt' if b.gap_before else ''}")
        lines.append(f'    "{b.text[:110]}"')
    return "\n".join(lines)


def ask(llm, page: int, page_png: str, cands: list[Block],
        result: StructureResult, blocks: list[Block],
        n_blocks: int = 0, prev_run: Optional[dict] = None,
        model: Optional[str] = None) -> list[dict]:
    """페이지 하나를 그림째 묻는다. 실패하면 빈 목록 — 조용히 지어내지 않는다."""
    # 싼 모델은 `effort` 를 지원하지 않는다(haiku: 400). 모델을 지정한 호출은
    # effort 를 빼고 부른다 — 지원 여부를 모델별로 외우지 않기 위해서다.
    kw: dict = {"images": [page_png], "effort": None if model else "high"}
    if model:
        kw["model"] = model
    data = llm.structured(f"vlm_heading_p{page}", SYSTEM,
                          prompt_for(page, cands, result, blocks, n_blocks, prev_run),
                          SCHEMA, **kw)
    if not data:
        return []
    ok = {f"blk{b.idx}" for b in cands}
    return [v for v in data.get("verdicts", []) if v.get("id") in ok]


def promote(result: StructureResult, verdicts: list[dict],
            blocks: list[Block], n_blocks: int) -> int:
    """확정된 제목을 **한 계층 위** 마디로 세우고 형제끼리 구간을 자른다.

    구간은 순차다 — 앞 제목의 끝은 다음 제목이 시작하는 자리다. 그래서 뒤에 새 제목이
    나오면 앞엣것이 저절로 줄어든다(사용자가 말한 "수정"이 이 규칙 하나로 끝난다).

    기존 마디는 새 제목의 자식이 되고 레벨이 하나씩 밀린다. 트리 전체를 다시 세우지
    않는다 — 결정론이 세운 조·항·호의 관계는 그대로 옳고, 그 위에 지붕만 얹는다.
    """
    picked = sorted(
        (v for v in verdicts if v.get("verdict") == "heading"),
        key=lambda v: int(v["id"].replace("blk", "")))
    if not picked:
        return 0
    by_idx = {b.idx: b for b in blocks}
    starts = [int(v["id"].replace("blk", "")) for v in picked]

    roots: list[Node] = []
    for i, (v, start) in enumerate(zip(picked, starts)):
        nxt = starts[i + 1] if i + 1 < len(starts) else n_blocks
        b = by_idx.get(start)
        if b is None:
            continue
        # 끝은 **자기 서수 열이 끝나는 자리**다. 다음 제목이 그보다 앞에 있으면
        # 거기서 잘린다(꼬리를 잘라 간 것). 뒤에 있으면 열 끝에서 멈춘다 — 이게
        # 없으면 마지막 제목이 문서 끝까지 삼킨다(실측 930블록).
        run = ordinal_run(result, start, n_blocks)
        reach = run["end_block"] if run["n"] else nxt
        end = max(start + 1, min(nxt, reach))
        note = ""
        if run["n"] and reach > nxt:
            # 열이 다음 제목 너머로 이어진다 — 다음 제목이 이 열을 둘로 갈랐다.
            note = (f" · 서수 열({run['first']}…{run['last']})이 다음 제목 너머로 "
                    f"이어져 여기서 잘렸습니다")
        elif run["n"] and reach < nxt:
            note = f" · 서수 열이 {run['last']} 에서 끝나 다음 제목 전에 닫혔습니다"
        roots.append(Node(
            level=0, ordinal=None, family="vlm_heading",
            surface=b.text[:40], block_idx=b.idx, page=b.page,
            element_index=b.element_index, candidate_id=f"vlm-{b.idx}",
            title=b.text[:80],
            title_reason=f"VLM: {v.get('reason', '')[:80]}",
            activation_reason=(f"큰 글씨({b.size_ratio}배) — VLM {v.get('relation', '')}"
                               f"{', 거느림 ' + v['covers'] if v.get('covers') else ''}"
                               f"{note}"),
            span=(start, end)))

    # --- 제목끼리의 층위 — **확정된 것들 사이에서만** 크기로 줄 세운다 ---------
    #
    # 크기로 heading/body 를 가르는 것은 앞서 실패했다(3.9배가 본문이었다). 그러나
    # **이미 제목이라고 확정된 것들 사이의 순위**는 다른 문제다. 같은 문서에서
    # `특정금전신탁 계약서(全文)` 3.75배가 `설명의무 이행 확인` 1.26배보다 위인 것은
    # 크기가 곧바로 말해 준다. 판정은 VLM 이 이미 했고 여기서는 정렬만 한다.
    sizes = sorted({round(by_idx[s_].size_ratio, 1) for s_ in starts if s_ in by_idx},
                   reverse=True)
    rank = {v: i for i, v in enumerate(sizes)}
    for r in roots:
        b = by_idx.get(r.block_idx)
        r.level = rank.get(round(b.size_ratio, 1), 0) if b else 0
    depth = len(sizes)

    # 큰 제목 안에 든 작은 제목은 그 자식이 된다. 구간 포함으로 정한다 — 제목끼리는
    # 겹치지 않도록 위에서 이미 잘라 두었다.
    def nest(items: list[Node]) -> list[Node]:
        out: list[Node] = []
        for n in sorted(items, key=lambda x: (x.block_idx, x.level)):
            host = next((h for h in reversed(out)
                         if h.level < n.level and h.span[0] <= n.block_idx < h.span[1]),
                        None)
            if host is None:
                out.append(n)
            else:
                host.children.append(n)
        return out

    tops = nest(roots)

    # --- 기존 마디를 지붕 아래로 -----------------------------------------------
    # 순서 기반으로 찾은 마디(조·항·호)는 큰 제목보다 **아래**다. 레벨을 제목 깊이만큼
    # 밀어 준다 — 그래야 L0 이 문서 표제가 되고 조가 그 아래로 간다.
    def shift(n: Node, by: int) -> None:
        n.level += by
        for c in n.children:
            shift(c, by)

    def place(n: Node) -> bool:
        """가장 깊은(=가장 작은 제목) 지붕 아래에 넣는다.

        미는 폭은 **그 지붕의 레벨 + 1** 이지 제목 층 전체 깊이가 아니다. 깊이로
        밀면 L0 제목 아래 조가 L2 로 가서 L1 이 비어 버린다(실측). 레벨은
        `section_id` 를 만들므로 빈 층이 생기면 좌표가 흔들린다.
        """
        home = None
        for r in roots:
            if r.span[0] <= n.block_idx < r.span[1]:
                if home is None or r.level > home.level:
                    home = r
        if home is None:
            return False
        shift(n, home.level + 1)
        home.children.append(n)
        return True

    leftover = [old for old in result.tree if not place(old)]
    result.tree = sorted(tops + leftover, key=lambda n: n.block_idx)
    result.stats["vlm_headings"] = len(roots)
    result.stats["vlm_heading_depth"] = depth
    result.audit_log.append(
        f"[VLM 제목] 큰 글씨 {len(verdicts)}건을 물어 {len(roots)}건을 제목으로 세웠습니다 "
        f"— 크기로 {depth}층, 구간은 서수 열이 끝나는 자리까지")
    return len(roots)


def run(result: StructureResult, blocks: list[Block], pdf_path,
        llm, *, max_pages: int = MAX_PAGES, scale: float = 1.6,
        model: Optional[str] = CHEAP_MODEL) -> int:
    """S5c 전체 — 후보 고르기 → 쪽마다 그림째 묻기 → 세우기. 반환: 세운 제목 수.

    ## 같은 글은 한 번만 묻는다

    쪽마다 부르면 **반복 표제를 쪽 수만큼 되묻는다.** 실측(GMS_D3421 5쪽):
    `KB able ELS 제3421호 핵심(요약)상품설명서` 가 5쪽 전부에 2.87배로 반복돼
    5번 물었고, 호출 하나가 수십 초라 재해석이 300초 가까이 걸렸다.

    같은 글은 판정도 같다. 글자로 묶어 **처음 나온 쪽에서 한 번만 묻고** 나머지
    occurrence 에 그 판정을 그대로 편다. 반복 표제는 대개 쪽 머리글이므로 VLM 이
    body 로 내리는데, 그 판정 하나면 5개가 모두 정리된다.

    `llm` 이나 `pdf_path` 가 없으면 **아무것도 하지 않는다.**
    """
    from core.structure import viewer as viewer_mod

    if llm is None or not pdf_path:
        return 0
    cands = candidates(blocks, result)
    if not cands:
        return 0

    # 글자로 묶는다 — 공백을 지운 정규형이 같으면 같은 글로 본다.
    groups: dict[str, list[Block]] = {}
    for b in cands:
        groups.setdefault(b.text.replace(" ", "")[:60], []).append(b)
    firsts = [g[0] for g in groups.values()]
    result.stats["vlm_asked"] = len(firsts)
    result.stats["vlm_deduped"] = len(cands) - len(firsts)

    pages = sorted({b.page for b in firsts})
    if max_pages and len(pages) > max_pages:
        result.warnings.append(
            f"큰 글씨가 {len(pages)}쪽에 걸쳐 있어 앞 {max_pages}쪽만 물었습니다 "
            f"— 나머지 쪽의 제목은 세워지지 않습니다")
        pages = pages[:max_pages]
    result.stats["vlm_pages"] = len(pages)

    verdicts: list[dict] = []
    prev_run: Optional[dict] = None
    for page in pages:
        mine = [b for b in firsts if b.page == page]
        try:
            png = viewer_mod.page_png(pdf_path, page, scale=scale)
        except Exception as exc:                     # pragma: no cover
            result.warnings.append(f"{page}쪽 그림을 만들지 못했습니다 — {exc}")
            continue
        got = ask(llm, page, png, mine, result, blocks, len(blocks), prev_run,
                  model=model)
        verdicts += got
        heads = [v for v in got if v.get("verdict") == "heading"]
        if heads:
            last = max(int(v["id"].replace("blk", "")) for v in heads)
            prev_run = ordinal_run(result, last, len(blocks))

    # 물은 것의 판정을 같은 글의 나머지에도 편다.
    by_id = {f"blk{b.idx}": b for b in firsts}
    spread: list[dict] = []
    for v in verdicts:
        b = by_id.get(v.get("id"))
        if b is None:
            continue
        key = b.text.replace(" ", "")[:60]
        for twin in groups.get(key, []):
            spread.append({**v, "id": f"blk{twin.idx}"})
    return promote(result, spread, blocks, len(blocks))
