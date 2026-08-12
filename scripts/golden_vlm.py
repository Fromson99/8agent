#!/usr/bin/env python3
"""골든 구조 초안 — 페이지 그림을 **모델에게 읽혀** 정답 계층을 받아 적는다.

    .venv/bin/python scripts/golden_vlm.py --doc ddaecffe629c8f3c
    .venv/bin/python scripts/golden_vlm.py --doc ddaecffe629c8f3c --pages 1-3   # 맛보기

산출: `bench/golden/<doc_id>.yaml` (형식은 손으로 적은 골든과 같다 —
`scripts/golden_check.py` 가 그대로 채점한다) + `bench/golden/_raw/<doc_id>/pNN.json`
(무엇을 묻고 무엇이 왔는지 사람이 볼 수 있어야 이 골든을 믿을 수 있다).

## 왜 VLM 인가 — 글자만으로는 계층이 안 보인다

법령 PDF 에서 계층을 가르는 것은 마커만이 아니다. `가.` 가 앞 호의 목인지 새 조의
목인지는 **들여쓰기와 쪽 넘김**이 말해 준다. 국가법령정보센터 인쇄본은 그 정보를
글자에 남기지 않는다(`법제처 7 국가법령정보센터` 같은 쪽 장식이 읽기 순서에 섞여
들어오기까지 한다). 그림을 줘야 사람이 읽는 것과 같은 근거로 답한다.

## 왜 해석 결과를 프롬프트에 넣지 않는가

넣으면 골든이 아니다. 우리 트리를 보여 주고 "맞나?" 를 물으면 모델은 대체로
동의하고, 그 골든으로 우리를 채점하면 언제나 만점이 나온다. 그래서 모델에게 주는
것은 **파싱 산출 중 판단이 섞이지 않은 두 가지뿐**이다.

    블록 번호(idx)  읽기 순서. 눈금이지 답이 아니다.
    블록 글자        원문 그대로.

`node`·`level`·`opens` 는 우리 해석이므로 지운다. 대조는 **뒤에서** 한다 — 다 받은
뒤 현재 해석과 견주어 어긋난 줄을 `review` 로 뽑아 준다. 그 줄이 사람이 볼 자리다.

## 왜 쪽마다 따로 묻고, 무엇을 이어 주는가

한 쪽씩 묻는다(그림 한 장 = 물음 하나). 그러면 쪽을 넘어가는 부모를 못 짚으므로
직전까지 **열려 있는 마디의 사슬**(뿌리→마지막)을 함께 실어 준다. 7쪽 첫 블록
`나. 재산상황` 의 부모는 6쪽의 `2. 투자성 상품` 이다 — 사슬이 없으면 답할 수 없다.

## 왜 초안(draft)인가

기계가 적은 골든을 사람이 확정하지 않은 채 회귀 기준으로 쓰면, 틀린 정답에 코드를
맞추게 된다. `status: draft` 로 나가고, 현재 해석과 어긋난 줄에는 `# 검토` 표시가
붙는다. 사람이 그 줄만 보고 확정하면 골든이 된다.

## 뿌리는 expect 에 넣지 않는다

`golden_check` 의 `parent_block()` 은 "부모 없음(뿌리)" 과 "그 블록은 마디가 아님"
을 둘 다 `None` 으로 돌려준다. 뿌리를 `parent: null` 로 적으면 **마디를 아예 못 세운
경우까지 통과**한다. 헛통과하느니 안 재는 편이 낫다 — 뿌리는 `roots:` 에 따로 적어
사람이 읽게 두고, 채점에서는 뺀다.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "bench" / "golden"

# 계층을 여는 마디의 종류. 법령 인쇄본에서 실제로 쓰이는 것만 둔다 — 목록이 길수록
# 판정이 흔들린다. 마지막 셋은 **마디가 아님**을 말하는 값이다.
#
# `번호목`(`1)` 계열)은 나중에 넣었다. 실측(금소법 별표·부칙): 값이 없으니 모델이
# `1)` 을 전부 `목` 으로 밀어 넣고 스스로 confidence=low 를 달았다(21줄). 부모는
# 옳았지만 `목_부모` 한 축에 두 계열이 섞여, 무엇이 나아졌는지 읽을 수 없게 된다.
STRUCTURAL = ("편", "장", "절", "관", "조", "항", "호", "목", "번호목", "부칙", "별표")
NON_STRUCTURAL = ("본문", "쪽장식", "기타")

# 그림 배율. 1.6 배면 9pt 본문도 읽힌다(vlm_heading 과 같은 값).
SCALE = 1.6
# 한 블록에서 보여 줄 글자 수. 마커는 앞에 있으므로 이 정도면 가른다. 전문은
# 그림에 있다 — 여기서 길게 실으면 물음만 무거워진다.
SNIPPET = 130
# 열린 마디 사슬의 최대 길이. 편>장>절>관>조>항>호>목 이 여덟이 한계다.
CHAIN = 8
# 사람이 "이 문서 이름은 뭔가" 를 판단할 재료. 모델에게 문서 종류만 알려 준다.
MODEL = "claude-sonnet-5"

SYSTEM = f"""당신은 한국어 법령 문서의 **계층 판별기**다. 답을 지어내지 마라.

법령 인쇄본 한 쪽의 그림과, 그 쪽의 글 덩어리(블록) 목록을 준다. 블록 번호는 읽기
순서일 뿐 계층 정보가 아니다. 각 블록이 **무엇이며 누구의 자식인지** 답하라.

## 종류

    편 장 절 관   구역 표제 (`제1편`, `제2장`, `제3절`, `제1관`)
    조            `제12조(적합성원칙)` 처럼 조문을 여는 것
    항            `①` `②` 같은 원문자 항
    호            `1.` `2.` 같은 번호 호
    목            `가.` `나.` 같은 한글 목
    번호목        `1)` `2)` 같은 괄호 반쪽 번호. 목(`가.`)보다 한 단 아래에 온다.
    부칙 별표     본칙이 끝난 뒤의 부칙·별표·서식
    본문          앞 마디에 딸린 이어지는 문장. 새 계층을 열지 않는다.
    쪽장식        쪽 머리글·꼬리글·발행처 표시. 본문이 아니다.
                  (예: `법제처 7 국가법령정보센터`, 쪽마다 되풀이되는 법령 이름,
                   `[시행 2026. 1. 2.]` 같은 연혁 표시)
    기타          위 어디에도 안 맞는 것

## 부모를 정하는 법 — 그림을 보라

부모는 **그 블록을 실제로 품는 바로 위 계층의 블록 번호**다. 글자만으로는 갈리지
않는다. 그림에서 다음을 보라.

    들여쓰기   목(`가.`)은 자기 호(`1.`)보다 오른쪽에서 시작한다. 같은 왼쪽 끝에서
               시작하면 형제다.
    바로 위    `1.` 의 부모는 그 위에서 가장 가까운 항(`①`)이고, 항이 없으면 조다.
    쪽 넘김    쪽 첫 블록의 부모는 대개 **앞쪽에 있다.** 프롬프트의 "열려 있는
               마디" 목록에서 골라라. 그 목록의 번호를 그대로 써도 된다.

부모가 없으면(문서의 최상위 구역이면) `parent` 에 -1 을 적어라. 종류가 `본문`·
`쪽장식`·`기타` 인 것도 `parent` 는 -1 로 둔다 — 계층을 열지 않기 때문이다.

## 확신

    high   그림에서 들여쓰기와 번호 흐름이 분명하다
    low    쪽이 잘려 있거나 들여쓰기가 애매해 둘로 읽힌다

억지로 high 를 고르지 마라. low 는 사람이 다시 볼 표시다.

## 지키기

이 쪽의 블록을 **하나도 빠뜨리지 말고** 모두 답하라. `why` 는 부모를 그렇게 정한
근거를 한 줄로 — 그림에서 본 것을 적어라(예: "가. 가 1. 보다 두 칸 들여쓰여 있다").
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block": {"type": "integer"},
                    "kind": {"type": "string",
                             "enum": list(STRUCTURAL) + list(NON_STRUCTURAL)},
                    "parent": {"type": "integer"},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                    "why": {"type": "string"},
                },
                "required": ["block", "kind", "parent", "confidence", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}


# --- 재료 ---------------------------------------------------------------------

def _store() -> Path:
    import os
    return Path(os.environ.get("STRUCTURE_STORE", ROOT / "data" / "structure"))


def load_doc(doc_id: str) -> tuple[dict, list[dict], Path]:
    """해석 산출에서 **판단이 섞이지 않은 것만** 꺼낸다.

    `result.json` 에는 우리 트리(`node`·`level`·`opens`)가 함께 들어 있다. 여기서
    떼어 내는 것은 블록의 읽기 순서와 글자뿐이다 — 프롬프트로 나가는 것은 이 셋
    (idx·page·text)이고, 나머지는 뒤에서 대조할 때만 쓴다.
    """
    d = _store() / doc_id
    result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    blocks = [{"idx": b["idx"], "page": b["page"], "text": (b.get("text") or "").strip()}
              for b in result.get("blocks", [])]
    pdf = d / "source.pdf"
    if not pdf.exists():
        raise SystemExit(f"원본 PDF 가 없습니다: {pdf}")
    return result, blocks, pdf


def parse_pages(spec: Optional[str], available: list[int]) -> list[int]:
    if not spec:
        return available
    want: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            want.update(range(int(a), int(b) + 1))
        elif part:
            want.add(int(part))
    return [p for p in available if p in want]


# --- 물음 ---------------------------------------------------------------------

def chain_for(items: dict[int, dict], last: Optional[int],
              blocks: dict[int, dict]) -> list[dict]:
    """마지막 마디에서 뿌리까지 거슬러 올라간 사슬. 쪽을 넘는 부모를 이어 준다."""
    out: list[dict] = []
    seen: set[int] = set()
    cur = last
    while cur is not None and cur not in seen:
        seen.add(cur)
        it = items.get(cur)
        if it is None:
            break
        out.append(it)
        cur = it["parent"] if it["parent"] >= 0 else None
    return list(reversed(out))[-CHAIN:]


def prompt_for(name: str, page: int, n_pages: int, mine: list[dict],
               chain: list[dict], blocks: dict[int, dict],
               continuous: bool = True) -> str:
    lines = [f"문서: {name}", f"이 그림은 {page}쪽이다 (전체 {n_pages}쪽).", ""]
    if chain and continuous:
        lines.append("## 앞쪽에서 아직 열려 있는 마디 — 이 쪽 첫 블록의 부모는 "
                     "대개 이 중 하나다")
        for it in chain:
            b = blocks.get(it["block"], {})
            lines.append(f"  [blk {it['block']}] {it['kind']:<4} "
                         f"{(b.get('text') or '')[:70]}")
        lines.append("")
    elif not continuous:
        # 앞쪽을 건너뛰었다면 사슬은 **낡았다**. 제1편이 아직 열려 있는지 우리는
        # 모른다 — 모르는 것을 아는 척 실어 주면 없는 부모를 짚게 만든다.
        lines += ["## 앞쪽 사정: 이 쪽 바로 앞은 읽지 않았다. 열려 있는 마디를 "
                  "알 수 없으므로,", "   부모가 이 쪽 밖에 있으면 -1 로 두어라.", ""]
    else:
        lines += ["## 앞쪽에서 열려 있는 마디: (없음 — 문서의 시작이다)", ""]
    lines.append("## 이 쪽의 블록 — 읽기 순서대로. 하나도 빠뜨리지 말고 답하라")
    for b in mine:
        lines.append(f"[blk {b['idx']}] {b['text'][:SNIPPET]}")
    return "\n".join(lines)


def ask_page(llm, name: str, page: int, n_pages: int, mine: list[dict],
             chain: list[dict], blocks: dict[int, dict], pdf: Path,
             model: str, continuous: bool = True) -> list[dict]:
    from core.structure import viewer as viewer_mod

    png = viewer_mod.page_png(pdf, page, scale=SCALE)
    user = prompt_for(name, page, n_pages, mine, chain, blocks, continuous)
    data = llm.structured(f"golden_p{page}", SYSTEM, user, SCHEMA,
                          images=[png], effort="high", model=model,
                          max_tokens=16000)
    if not data:
        return []
    ok = {b["idx"] for b in mine}
    return [v for v in data.get("items", []) if v.get("block") in ok]


# --- 받아 적기 ----------------------------------------------------------------

def _quote(s: str) -> str:
    """YAML 한 줄 문자열. 큰따옴표 안에 들어갈 것만 막는다."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _node_by_block(result: dict) -> dict[int, dict]:
    """블록 → 그 블록에서 시작하는 마디 (golden_check 와 같은 규칙)."""
    out: dict[int, dict] = {}
    for n in result.get("nodes", []):
        b = n.get("block")
        if b is None:
            b = (n.get("span") or [None])[0]
        if b is not None and b not in out:
            out[b] = n
    return out


def compare(result: dict, items: list[dict]) -> dict[int, Optional[int]]:
    """현재 해석이 각 블록의 부모로 무엇을 말하는가. **대조 전용** — 물음에는 안 쓴다."""
    by_block = _node_by_block(result)
    by_id = {n["id"]: n for n in result.get("nodes", [])}
    got: dict[int, Optional[int]] = {}
    for it in items:
        n = by_block.get(it["block"])
        if n is None:
            got[it["block"]] = None
            continue
        par = by_id.get(n.get("parent"))
        if par is None:
            got[it["block"]] = -1
            continue
        pb = par.get("block")
        if pb is None:
            pb = (par.get("span") or [None])[0]
        got[it["block"]] = pb
    return got


def render(doc_id: str, meta: dict, items: list[dict], blocks: dict[int, dict],
           got: dict[int, Optional[int]], model: str, pages: list[int]) -> str:
    struct = [i for i in items if i["kind"] in STRUCTURAL]
    rows = [i for i in struct if i["parent"] >= 0]
    roots = [i for i in struct if i["parent"] < 0]
    furniture = [i for i in items if i["kind"] == "쪽장식"]
    mismatched = [i for i in rows if got.get(i["block"]) != i["parent"]]
    low = [i for i in rows if i["confidence"] == "low"]

    out: list[str] = [
        "# 골든 구조 — **초안**. 페이지 그림을 모델에게 읽혀 받아 적은 계층이다.",
        "#",
        f"#   문서    {meta.get('name', '')}",
        f"#   원본    data/structure/{doc_id}/source.pdf  ({len(pages)}쪽)",
        f"#   읽은이  {model} (페이지 그림 {len(pages)}장, 쪽마다 한 번씩)",
        f"#   만든것  scripts/golden_vlm.py · 물음과 답은 bench/golden/_raw/{doc_id}/ 에",
        "#",
        "# ## 아직 골든이 아니다",
        "#",
        "# 사람이 확정하기 전까지 이건 초안이다. 기계가 적은 정답에 코드를 맞추면 틀린",
        "# 정답을 굳히게 된다. 아래 두 종류의 줄만 보면 된다 — 나머지는 현재 해석과",
        "# 이미 일치한다.",
        "#",
        f"#   `# 검토`  현재 해석과 어긋난 줄 {len(mismatched)}건. 둘 중 하나가 틀렸다.",
        f"#   `# 애매`  모델이 스스로 확신 없다고 한 줄 {len(low)}건.",
        "#",
        "# ## 왜 블록 번호로 적나",
        "#",
        "# 마디 id 는 해석할 때마다 바뀐다. 블록 번호(`idx`)는 파싱 산출의 읽기 순서라",
        "# 재해석해도 그대로다 — 규칙을 고쳐 가며 전후를 재려면 눈금이 변하지 않아야",
        "# 한다.",
        "#",
        "# ## 뿌리는 왜 expect 에 없나",
        "#",
        "# `golden_check` 는 '뿌리다' 와 '마디를 못 세웠다' 를 둘 다 부모 없음으로 읽는다.",
        "# 뿌리를 채점하면 마디를 아예 놓친 경우가 헛통과한다. 그래서 `roots:` 로 빼서",
        "# 사람이 읽게만 두고 점수에는 넣지 않는다.",
        "",
        f"doc_id: {doc_id}",
        f"name: {_quote(meta.get('name', ''))}",
        f"pdf: data/structure/{doc_id}/source.pdf",
        f"pages: [{', '.join(str(p) for p in pages)}]",
        "status: draft",
        f"source: vlm:{model}",
        "",
        "expect:",
    ]

    last_group = None
    for i in sorted(rows, key=lambda x: x["block"]):
        group = f"{i['kind']}_부모"
        if group != last_group:
            out.append(f"  # --- {group} " + "-" * max(0, 60 - len(group)))
            last_group = group
        mark = ""
        if got.get(i["block"]) != i["parent"]:
            mark = f"  # 검토 — 현재 해석은 부모를 {got.get(i['block'])} 로 본다"
        elif i["confidence"] == "low":
            mark = "  # 애매 — 모델이 확신 없다고 했다"
        out.append(f"  - {{block: {i['block']}, parent: {i['parent']}, "
                   f"group: {group}, why: {_quote(i['why'][:90])}}}{mark}")

    out += ["", "# --- 최상위 구역 — 채점하지 않는다 (위 설명 참고) ---", "roots:"]
    for i in sorted(roots, key=lambda x: x["block"]):
        out.append(f"  - {{block: {i['block']}, kind: {i['kind']}, "
                   f"text: {_quote(blocks.get(i['block'], {}).get('text', '')[:60])}}}")

    out += ["", "# --- 쪽 머리글·꼬리글 — 구조가 아니다. 이 블록들이 마디로 서 있거나",
            "#     본문 마디에 딸려 있으면 파싱이나 읽기 순서 쪽의 문제다. ---",
            "furniture:"]
    for i in sorted(furniture, key=lambda x: x["block"])[:40]:
        out.append(f"  - {{block: {i['block']}, "
                   f"text: {_quote(blocks.get(i['block'], {}).get('text', '')[:50])}}}")
    if len(furniture) > 40:
        out.append(f"  # … 그리고 {len(furniture) - 40}건 더")
    return "\n".join(out) + "\n"


# --- 실행 ---------------------------------------------------------------------

def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))

    ap = argparse.ArgumentParser(description="페이지 그림을 읽혀 골든 구조 초안을 만든다")
    ap.add_argument("--doc", required=True, help="doc_id")
    ap.add_argument("--pages", default=None, help="예: 1-3 또는 1,5,7 (기본: 전부)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--out", default=None, help="기본: bench/golden/<doc_id>.yaml")
    args = ap.parse_args()

    from core.llm import LLM

    result, blocks, pdf = load_doc(args.doc)
    meta_path = _store() / args.doc / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    by_idx = {b["idx"]: b for b in blocks}
    all_pages = sorted({b["page"] for b in blocks})
    pages = parse_pages(args.pages, all_pages)
    if not pages:
        raise SystemExit("고른 쪽이 없습니다")

    raw_dir = GOLDEN / "_raw" / args.doc
    raw_dir.mkdir(parents=True, exist_ok=True)

    llm = LLM(model=args.model)
    items: list[dict] = []
    by_block: dict[int, dict] = {}
    last_struct: Optional[int] = None
    prev_page: Optional[int] = None

    print(f"{meta.get('name', args.doc)} — {len(pages)}쪽을 {args.model} 에게 읽힙니다")
    for n, page in enumerate(pages, 1):
        mine = [b for b in blocks if b["page"] == page and b["text"]]
        if not mine:
            continue
        # 앞쪽을 실제로 읽었을 때만 사슬을 잇는다. `--pages 9,17` 처럼 건너뛰면
        # 9쪽에서 열린 마디가 17쪽에도 열려 있다는 보장이 없다.
        continuous = prev_page is not None and page == prev_page + 1
        chain = chain_for(by_block, last_struct, by_idx) if continuous else []
        got = ask_page(llm, meta.get("name", args.doc), page, len(all_pages),
                       mine, chain, by_idx, pdf, args.model, continuous)
        prev_page = page
        for it in got:
            by_block[it["block"]] = it
            if it["kind"] in STRUCTURAL:
                last_struct = it["block"]
        items += got
        (raw_dir / f"p{page:03d}.json").write_text(
            json.dumps(llm.log[-1].dump(), ensure_ascii=False, indent=1),
            encoding="utf-8")
        n_struct = sum(1 for i in got if i["kind"] in STRUCTURAL)
        print(f"  [{n:>3}/{len(pages)}] {page:>3}쪽  블록 {len(mine):>3} → "
              f"마디 {n_struct:>3}, 쪽장식 "
              f"{sum(1 for i in got if i['kind'] == '쪽장식'):>2}"
              f"{'  (답 없음)' if not got else ''}")

    if not items:
        raise SystemExit("받은 답이 없습니다 — bench/golden/_raw/ 의 기록을 보세요")

    got_map = compare(result, items)
    text = render(args.doc, meta, items, by_idx, got_map, args.model, pages)
    out = Path(args.out) if args.out else GOLDEN / f"{args.doc}.yaml"
    out.write_text(text, encoding="utf-8")

    struct = [i for i in items if i["kind"] in STRUCTURAL and i["parent"] >= 0]
    agree = sum(1 for i in struct if got_map.get(i["block"]) == i["parent"])
    print(f"\n저장: {out}")
    print(f"  채점 대상 {len(struct)}줄 · 현재 해석과 일치 {agree} "
          f"({agree / len(struct) * 100:.0f}%) · 검토 필요 {len(struct) - agree}")
    print(f"  물음·답 기록: {raw_dir}")
    print(f"\n  다음: .venv/bin/python scripts/golden_check.py --doc {args.doc} --verbose")


if __name__ == "__main__":
    main()
