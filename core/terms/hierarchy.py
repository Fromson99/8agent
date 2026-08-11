"""엣지 ⑥ — 용어 계층(is-a) 후보 (ontology_kg §3.5 ⑥).

공짜 신호 두 개에서 후보를 만든다. LLM 은 검증만 한다(제안하지 않는다):

    어휘 포함    "압력 안전밸브" ⊂ "안전밸브" ⊂ "밸브" — 한국어 복합명사의
                수식 구조가 곧 계층. C-value 가 이미 계산한 토큰 중첩에서
                후보가 그냥 나온다 (접미 일치 = 머리 명사 공유)
    나열 문장    "펌프, 압축기 및 송풍기 등의 회전기기" — 나열 뒤에 머리
                명사가 오면 나열 항목들은 그 하위어 후보다 (Hearst 의 한국어
                꼴). 머리 명사가 없으면 형제 증거로만 남는다.

산출은 전부 **후보**(status=후보)다. LLM 검증을 통과하면 잠정, 사람이
확정하면 활성 — 용어와 같은 생애주기를 탄다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.terms.candidates import HarvestResult
from core.terms.stats import Scored, _contiguous_in

# "…, B 등(의) X" — 나열의 머리 명사. 나열 항목 뒤 등/등의 다음의 명사구.
_HEARST_HEAD = re.compile(r"등[의\s]*([가-힣A-Za-z][가-힣A-Za-z0-9·\s]{1,20}?)(?:[을를이가은는에]|$)")


def lexical(rows: list[Scored], toks_of: dict[str, tuple]) -> list[dict]:
    """접미 토큰 일치 — B 가 A 의 접미면 A is-a B. 머리 명사(마지막 토큰)가
    같아야 계층이다: "압력밸브"→"밸브" 는 계층, "압력계"→"압력" 은 아니다."""
    out = []
    keys = [r.key for r in rows]
    for a in keys:
        ta = toks_of.get(a) or ()
        for b in keys:
            tb = toks_of.get(b) or ()
            if not tb or a == b or len(tb) >= len(ta):
                continue
            if ta[-len(tb):] == tb:                      # 접미 일치
                out.append({"child": a, "parent": b, "evidence": "어휘포함",
                            "status": "후보"})
    return out


def enums(h: HarvestResult, keep_keys: set) -> tuple[list[dict], list[dict]]:
    """나열 증거 → (하위어 후보, 형제 증거). 머리 명사가 잡히면 하위어,
    아니면 형제로만 남긴다 — 억지로 부모를 지어내지 않는다."""
    groups: dict[tuple, set] = {}
    for c in h.cooccurs:
        if c.kind == "enum" and c.a in keep_keys and c.b in keep_keys:
            groups.setdefault((c.doc_id, c.block, c.sent), set()).update((c.a, c.b))

    hypo, sibling = [], []
    seen_h: set[tuple] = set()
    seen_s: set[tuple] = set()
    for (doc_id, block, sent), members in groups.items():
        if len(members) < 2:
            continue
        # 그 문장의 원문에서 머리 명사를 찾는다 — 후보 언급의 문장 텍스트 재사용
        head = None
        for key in members:
            for m in h.mentions.get(key, []):
                if (m.doc_id, m.block, m.sent) == (doc_id, block, sent) and m.text:
                    g = _HEARST_HEAD.search(m.text)
                    if g:
                        head_key = re.sub(r"\s+", "", g.group(1))
                        if head_key in keep_keys and head_key not in members:
                            head = head_key
                    break
            if head:
                break
        if head:
            for child in sorted(members):
                k = (child, head)
                if k not in seen_h:
                    seen_h.add(k)
                    hypo.append({"child": child, "parent": head,
                                 "evidence": "나열", "status": "후보",
                                 "anchor": {"doc_id": doc_id, "block": block}})
        else:
            sib = tuple(sorted(members))
            if sib not in seen_s and len(sib) <= 8:
                seen_s.add(sib)
                sibling.append({"siblings": list(sib),
                                "anchor": {"doc_id": doc_id, "block": block}})
    return hypo, sibling


def build(h: HarvestResult, rows: list[Scored]) -> dict:
    toks_of = {r.key: max((m.tokens for m in h.mentions[r.key]), key=len)
               for r in rows}
    keep = {r.key for r in rows}
    lex = lexical(rows, toks_of)
    hypo, sibling = enums(h, keep)
    # 같은 (child, parent) 이 두 경로에서 나오면 증거를 합친다 — 더 강한 후보다
    merged: dict[tuple, dict] = {}
    for e in lex + hypo:
        k = (e["child"], e["parent"])
        if k in merged:
            merged[k]["evidence"] += "+" + e["evidence"]
        else:
            merged[k] = dict(e)
    return {"edges": sorted(merged.values(),
                            key=lambda e: (e["parent"], e["child"])),
            "siblings": sibling}


def save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _assert_reuse():                                    # pragma: no cover
    """(문서화) _contiguous_in 은 stats 의 것을 재사용한다 — 같은 판정이 두
    구현으로 갈리면 C-value 와 계층이 서로 다른 중첩을 보게 된다."""
    return _contiguous_in
