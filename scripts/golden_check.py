#!/usr/bin/env python3
"""골든 구조 채점 — 해석 결과가 사람이 적은 정답 계층과 얼마나 맞나.

    .venv/bin/python scripts/golden_check.py
    .venv/bin/python scripts/golden_check.py --doc 852bf3ae0102e984 --verbose

## 왜 적합도(fitness) 말고 이게 필요한가

적합도는 커버리지·일관성·사다리 품질의 곱이라 **구조가 더 잘게 갈릴수록 낮아진다.**
실측(2026-08-11): `(N)`/`N)` 계열을 옳게 가르고 목을 제자리에 넣었더니 사람이 읽은
계층에는 가까워졌는데 적합도는 0.737 → 0.555 로 떨어졌다. 그 지표만 보면 개선을
후퇴로 읽는다. 그래서 정답을 적어 두고 **맞은 개수**로 잰다.

## 눈금

**(쪽, 본문 앞부분)** 으로 가리킨다(`anchors`). 블록 번호는 파싱이 바뀌면 통째로
밀려서 눈금이 못 된다 — 실측(2026-08-11): 쪼개진 줄 하나를 제자리로 되돌리자 뒤의
번호가 1씩 밀려 골든이 25/33 → 18/33 으로 "떨어진 것처럼" 보였다. 두 가지를 묻는다:

    parent           이 마디의 부모가 저 마디인가
    same_parent_as   이 마디와 저 마디가 형제인가 (부모가 무엇이든)

`group` 별로 나눠 보고한다 — 한 덩어리 점수는 "무엇이 나아지고 무엇이 깨졌나" 를
말하지 못한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "bench" / "golden"


def _store() -> Path:
    import os
    return Path(os.environ.get("STRUCTURE_STORE", ROOT / "data" / "structure"))


def _node_by_block(result: dict) -> dict[int, dict]:
    """블록 → 그 블록에서 시작하는 마디. 마커가 그 블록에 있는 마디만."""
    out: dict[int, dict] = {}
    for n in result.get("nodes", []):
        b = n.get("block")
        if b is None:
            b = (n.get("span") or [None])[0]
        if b is not None and b not in out:
            out[b] = n
    return out


def _resolve(result: dict, anchors: dict) -> dict[str, int]:
    """이름 → 블록 번호. (쪽, 본문 앞부분)으로 찾는다.

    공백은 접어서 비교한다 — 파서가 줄바꿈 자리에 공백을 넣고 빼는 일이 있어
    글자 그대로 맞추면 애먼 데서 어긋난다.
    """
    fold = lambda s: "".join((s or "").split())
    blocks = result.get("blocks", [])
    out: dict[str, int] = {}
    for name, a in (anchors or {}).items():
        want, page = fold(a.get("text")), a.get("page")
        hit = next((b["idx"] for b in blocks
                    if b.get("page") == page and fold(b.get("text")).startswith(want)), None)
        if hit is None:
            raise SystemExit(f"골든 닻을 못 찾았습니다: {name} (p.{page} '{a.get('text')}') "
                             f"— 본문이 바뀌었는지 확인하세요")
        out[name] = hit
    return out


def check(doc_id: str, spec: dict, verbose: bool = False) -> dict:
    p = _store() / doc_id / "result.json"
    if not p.exists():
        return {"doc_id": doc_id, "error": f"해석 산출이 없습니다: {p}"}
    result = json.loads(p.read_text(encoding="utf-8"))
    by_block = _node_by_block(result)
    by_id = {n["id"]: n for n in result.get("nodes", [])}
    anchor = _resolve(result, spec.get("anchors"))

    def parent_block(block: int):
        """그 블록에서 시작한 마디의 **부모 마디가 시작한 블록**."""
        n = by_block.get(block)
        if n is None:
            return None, "마디가 아님"
        par = by_id.get(n.get("parent"))
        if par is None:
            return None, "부모 없음(뿌리)"
        pb = par.get("block")
        if pb is None:
            pb = (par.get("span") or [None])[0]
        return pb, (par.get("surface") or "")

    groups: dict[str, dict] = {}
    rows = []
    for e in spec.get("expect", []):
        g = groups.setdefault(e.get("group", "기타"), {"ok": 0, "n": 0})
        g["n"] += 1
        # 두 가지 형식을 다 받는다:
        #   node   (쪽, 본문)으로 가리키는 닻 이름 — 재파싱에도 견딘다
        #   block  블록 번호 직접 — 파싱이 안 바뀌는 문서(lawxml 등)에선 그대로 쓴다
        def _blk(v):
            return anchor[v] if isinstance(v, str) else v
        name = e.get("node", e.get("block"))
        blk = _blk(name)
        got, note = parent_block(blk)
        if "parent" in e:
            ok = got == _blk(e["parent"])
            want = e["parent"]
        else:
            ref, _ = parent_block(_blk(e["same_parent_as"]))
            ok = got is not None and got == ref
            want = f"{e['same_parent_as']} 와 같은 부모"
        if ok:
            g["ok"] += 1
        rows.append({"node": str(name), "block": blk, "group": e.get("group", "기타"),
                     "ok": ok, "want": want, "got": got, "note": note,
                     "why": e.get("why", "")})

    n_ok = sum(1 for r in rows if r["ok"])
    # 적합도는 싣지 않는다 (2026-08-11 사용자 결정). 실측에서 골든 6→25/33 로
    # 크게 옳아지는 동안 적합도는 0.737→0.572 로 **떨어졌다** — 구조가 잘게
    # 갈릴수록 ladder_quality 가 깎이는 지표라 개선을 후퇴로 읽는다. 판단은
    # 정답 대비 맞은 개수로만 한다.
    out = {"doc_id": doc_id, "name": spec.get("name", ""),
           "total": len(rows), "ok": n_ok,
           "groups": {k: v for k, v in sorted(groups.items())},
           "rows": rows}
    if verbose:
        for r in rows:
            if not r["ok"]:
                print(f"    ✗ {r['node']:<16} [{r['group']}] 기대 부모 {r['want']} "
                      f"→ 실제 {r['note']!r} {r['why']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=None, help="이 doc_id 만")
    ap.add_argument("--verbose", action="store_true", help="틀린 항목을 전부 보여준다")
    ap.add_argument("--save", default=None, help="결과를 이 JSON 에 저장")
    args = ap.parse_args()

    results = []
    for f in sorted(GOLDEN.glob("*.yaml")):
        spec = yaml.safe_load(f.read_text(encoding="utf-8"))
        doc_id = spec.get("doc_id") or f.stem
        if args.doc and doc_id != args.doc:
            continue
        r = check(doc_id, spec, verbose=args.verbose)
        results.append(r)
        if r.get("error"):
            print(f"{doc_id}: {r['error']}")
            continue
        rate = r["ok"] / r["total"] * 100 if r["total"] else 0
        print(f"\n{r['name'][:40]}")
        print(f"  골든 {r['ok']}/{r['total']} ({rate:.0f}%)")
        for g, v in r["groups"].items():
            mark = "✓" if v["ok"] == v["n"] else ("·" if v["ok"] else "✗")
            print(f"    {mark} {g:10} {v['ok']}/{v['n']}")

    if args.save:
        Path(args.save).write_text(
            json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n저장: {args.save}")


if __name__ == "__main__":
    main()
