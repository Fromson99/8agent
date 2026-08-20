"""정의 조 → 용어의 상하관계 표 (하이쿠 추출, 파생층).

정의 조는 "상위어 = {하위어들}"을 열거하는 문장이다 — 국세기본법 §2 17호
'"세무공무원"이란 … 국세청장, 지방국세청장, 세무서장 또는 그 소속 공무원',
개보법 §2 6호 '"공공기관"이란 … 국회, 법원, … 지방자치단체'. 임베딩이 못 잇는
기관↔직위·개별↔집합의 다리를 **법이 스스로 써 놓은 것**이라, 여기서 옮기면
별칭 표가 사람 손 없이, 근거 좌표를 달고 선다(2026-08-18 사용자 결정 —
"정의라고 판별나면 용어 추출·상하관계는 LLM 에게").

    정의 조(tags.definition_jos + definitions 색인이 잡은 조)  → 조 하나에 하이쿠 1콜
    → [{term, hyponyms:[…], hypernyms:[…], node}]  → data/taxonomy/<doc_id>.jsonl

검증: 하위어·상위어가 **용어집(lexicon)에 실재하는 표면형**이면 grounded=True 로
표시한다 — 메뉴 확장은 grounded 만 쓴다(오절단·환각 방지). 근거는 정의 호 좌표.

쓰는 자리: termretrieve.candidates — 질문 낱말의 정확 히트·이웃마다 이 표에서
상위어를 찾아 판별 메뉴에 "(정의상 상위어 — 근거)"로 올린다. 그러면 '국세청' →
이웃 '국세청장' → 상위어 '세무공무원'이 메뉴에 서고, 프레임이 §84 로 조립된다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from lawrag.core.rag import definitions as definitions_mod
from lawrag.core.rag import tags as tags_mod
from lawrag.core.rag.index import DocView, Index, store_path

log = logging.getLogger("lawrag.core.rag.taxonomy")

MODEL = os.environ.get("RAG_TAXONOMY_MODEL", "claude-haiku-4-5-20251001")
WORKERS = int(os.environ.get("RAG_TAXONOMY_WORKERS", "6"))
JO_CHARS = 5000

SYSTEM = (
    "너는 한국 법령 **정의 조**의 용어 관계 추출기다. 정의 조 하나의 본문(마디 id 가 "
    "붙어 있다)을 받아, 정의되는 용어마다 그 정의 본문이 **열거·포함**하는 하위어와, "
    "본문이 '…에 해당하는', '…의 하나인' 처럼 상위 개념으로 부르는 상위어를 뽑는다.\n"
    "규칙: ① 낱말은 **본문의 표면형 그대로** — 바꿔 쓰거나 요약하지 마라. ② 하위어는 "
    "그 정의가 명시적으로 열거한 것만('국세청장, 지방국세청장, 세무서장' → 셋). "
    "'그 소속 공무원'·'그 밖의 …' 같은 지시·포괄 표현은 넣지 마라. ③ 상위어는 본문이 "
    "부른 것만 — 추론하지 마라. ④ 정의되는 용어가 없으면 빈 배열."
)
SCHEMA = {
    "type": "object",
    "properties": {"terms": {"type": "array", "items": {
        "type": "object",
        "properties": {"node": {"type": "integer"}, "term": {"type": "string"},
                       "hyponyms": {"type": "array", "items": {"type": "string"}},
                       "hypernyms": {"type": "array", "items": {"type": "string"}}},
        "required": ["node", "term", "hyponyms", "hypernyms"],
        "additionalProperties": False}}},
    "required": ["terms"], "additionalProperties": False,
}


def taxonomy_dir() -> Path:
    return Path(os.environ.get("RAG_TAXONOMY_DIR", store_path().parent / "taxonomy"))


def _pack(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


# ---------------------------------------------------------------- 대상 조
def definition_articles(v: DocView) -> list[dict]:
    """정의 조 = 관할급 정의 조(tags) ∪ 정의 색인이 정의어를 찾은 조."""
    ids = set(tags_mod.definition_jos(v))
    ids |= {d["jo"] for d in definitions_mod.defs(v)}
    return [v.by_id[i] for i in sorted(ids) if v.by_id.get(i) is not None]


def _units(v: DocView, jo: dict) -> list[dict]:
    """정의가 실린 마디(항·호) — 본문 id 붙여서. 없으면 조 자신."""
    kids = [n for n in v.nodes if n.get("parent") == jo["id"]]
    seen: set = set()
    units = []
    for n in [jo] + kids + [k for c in kids for k in v.nodes if k.get("parent") == c["id"]]:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        t = v.section_text(n, cap=JO_CHARS // 4 + 400)
        if t and len(t.strip()) > 4:
            units.append({"id": n["id"], "text": t})
    return units


def extract_jo(llm, v: DocView, jo: dict) -> tuple[list[dict], dict]:
    units = _units(v, jo)
    body = "\n\n".join(f"[id={u['id']}] {u['text']}" for u in units)[:JO_CHARS]
    out = llm.structured("rag.taxonomy", SYSTEM,
                         f"[정의 조]\n《{v.name}》 {jo.get('surface','')} {jo.get('title','')}\n\n{body}",
                         SCHEMA, max_tokens=8000, effort=None, model=MODEL)
    if out is None:
        err = llm.log[-1].error if llm.log else "?"
        return [], {"jo": jo["id"], "error": str(err)[:160]}
    ids = {u["id"] for u in units}
    rows = []
    for t in out.get("terms", []):
        term = _pack(t.get("term") or "")
        if not term or t.get("node") not in ids:
            continue
        rows.append({"jo": jo["id"], "node": t["node"], "term": (t.get("term") or "").strip(),
                     "hyponyms": [str(x).strip() for x in (t.get("hyponyms") or []) if str(x).strip()][:20],
                     "hypernyms": [str(x).strip() for x in (t.get("hypernyms") or []) if str(x).strip()][:6]})
    return rows, {"jo": jo["id"], "n": len(rows)}


def extract_doc(v: DocView, llm_factory, out_dir: Optional[Path] = None,
                workers: int = WORKERS, only_missing: bool = True) -> dict:
    out_dir = out_dir or taxonomy_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{v.doc_id}.jsonl"
    done: set = set()
    if only_missing and path.is_file():
        for line in path.read_text("utf-8").splitlines():
            try:
                done.add(json.loads(line)["jo"])
            except Exception:
                pass
    jos = [j for j in definition_articles(v) if j["id"] not in done]
    t0 = time.perf_counter()
    stats = {"doc": v.name, "jos": len(jos), "terms": 0, "errors": 0}
    if not jos:
        return stats

    def work(jo):
        return extract_jo(llm_factory(), v, jo)

    with path.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, jo): jo for jo in jos}
        for fut in as_completed(futs):
            rows, meta = fut.result()
            if meta.get("error"):
                stats["errors"] += 1
                continue
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            if not rows:
                f.write(json.dumps({"jo": futs[fut]["id"], "node": None, "term": "",
                                    "hyponyms": [], "hypernyms": [], "empty": True},
                                   ensure_ascii=False) + "\n")
            f.flush()
            stats["terms"] += len(rows)
    stats["sec"] = round(time.perf_counter() - t0, 1)
    return stats


# ---------------------------------------------------------------- 읽기·조회
_cache: dict = {}


def load(doc_id: str) -> list[dict]:
    p = taxonomy_dir() / f"{doc_id}.jsonl"
    if not p.is_file():
        return []
    mt = p.stat().st_mtime_ns
    c = _cache.get(doc_id)
    if c and c[0] == mt:
        return c[1]
    rows = []
    for line in p.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not r.get("empty"):
            rows.append(r)
    _cache[doc_id] = (mt, rows)
    return rows


class Taxonomy:
    """하위어 → [(상위어, doc_id, node)] · 상위어 → [(하위어, …)]. 용어집으로 grounded 표시."""

    def __init__(self, index: Index, lexicon=None, doc_ids: Optional[set] = None):
        self.up: dict[str, list[dict]] = {}
        self.down: dict[str, list[dict]] = {}
        known = set(lexicon.packed) if lexicon is not None else None
        for did, v in index.entry_docs.items():
            if doc_ids and did not in doc_ids:
                continue
            # 잡음 필터 (2026-08-19): 상위어는 **그 문서의 정의어 색인에 실재하는 용어**만.
            # 하이쿠가 정의 조 밖 열거("지방자치단체 → 개인정보 보호수준 평가")까지
            # 관계로 뽑아 '공공기관' 질문의 actor 집합이 부풀던 실측. 정의된 낱말만이
            # 상위 개념일 자격이 있다 — 그게 정의 조의 뜻이다.
            defined = {_pack(d["term"]) for d in definitions_mod.defs(v)}
            for r in load(did):
                term = r["term"]
                if _pack(term) not in defined:
                    continue
                for h in r.get("hyponyms", []):
                    g = (known is None) or (_pack(h) in known)
                    self.up.setdefault(_pack(h), []).append(
                        {"term": term, "hypo": h, "doc_id": did, "node": r["node"],
                         "doc": v.name, "path": v.path(r["node"]), "grounded": g})
                    self.down.setdefault(_pack(term), []).append(
                        {"term": h, "doc_id": did, "node": r["node"], "doc": v.name,
                         "path": v.path(r["node"]), "grounded": g})
                for h in r.get("hypernyms", []):
                    if _pack(h) not in defined:          # 상위어도 정의된 낱말만 ('사람' 같은 일반어 차단)
                        continue
                    g = (known is None) or (_pack(h) in known)
                    self.up.setdefault(_pack(term), []).append(
                        {"term": h, "hypo": term, "doc_id": did, "node": r["node"],
                         "doc": v.name, "path": v.path(r["node"]), "grounded": g})

    def hypernyms(self, word: str, grounded_only: bool = True) -> list[dict]:
        rows = self.up.get(_pack(word), [])
        return [r for r in rows if r["grounded"] or not grounded_only]

    def hyponyms(self, word: str, grounded_only: bool = True) -> list[dict]:
        rows = self.down.get(_pack(word), [])
        return [r for r in rows if r["grounded"] or not grounded_only]


_tx_cache: dict = {}


def current(index: Index, lexicon=None, doc_ids: Optional[set] = None) -> Taxonomy:
    # 스코프 사본마다 id 가 다르다 — docs 객체 + 스코프로 키를 잡아 같은 스코프의
    # 다음 질의가 재사용하게 한다.
    key = (id(index.docs), id(lexicon), tuple(sorted(doc_ids)) if doc_ids else None,
           tuple(sorted(index.scope)) if index.scope else None)
    tx = _tx_cache.get(key)
    if tx is None:
        tx = Taxonomy(index, lexicon, doc_ids)
        _tx_cache.clear()
        _tx_cache[key] = tx
    return tx
