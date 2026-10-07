"""Tier 2+3 빌드 — 통계 깔때기 전체를 한 번에 (ontology_kg §3.2 [C][D], §4.9).

    후보(PeCab) → 지표 4종+Borda → [임베딩 군집] → [LLM 판정] → 게이트 → 등재
    부산물: 공기 증거(§5.8b)·PROTO_REL 집계·계층 후보(⑥)·커버리지 공백 지도

무거운 단은 전부 끌 수 있다: --no-embed(정규형만으로 군집), --no-llm(무판정
잠정 등재). 결정론 구간은 언제나 돈다 — recover 사다리와 같은 규율이다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from lawrag.core.terms import cluster as cluster_mod
from lawrag.core.terms import gate as gate_mod
from lawrag.core.terms import hierarchy as hier_mod
from lawrag.core.terms import judge as judge_mod
from lawrag.core.terms import relations as rel_mod
from lawrag.core.terms.candidates import harvest
from lawrag.core.terms.stats import score
from lawrag.core.terms.transcribe import OUT_DIR, _load_docs, _load_terms

DEFAULT_TOP = 400


def _user_words(terms_file) -> list[str]:
    """수기·tier1 용어를 PeCab 사용자 사전에 — 분석기가 도메인 용어를 쪼개는
    것을 막는다 (§4.8). tombstone 은 거부된 것이라 주입하지 않는다."""
    words = []
    for t in _load_terms(terms_file).values():
        if t.get("status") == "tombstone":
            continue
        words.extend(t.get("surfaces", []))
    return words


def run(store: Optional[Path] = None, glossary: Optional[Path] = None,
        out_dir: Optional[Path] = None, top: int = DEFAULT_TOP,
        min_tf: int = 2, use_embed: bool = True, llm=None,
        dry_run: bool = False) -> dict:
    from lawrag.core.rag.index import terms_path

    out_dir = out_dir or OUT_DIR
    glossary = glossary or (store.parent / "glossary.json" if store
                            else terms_path())
    report: dict = {}
    t0 = time.monotonic()

    views = _load_docs(store)
    print(f"문서 {len(views)}건")

    # ── 후보 + 공기 (한 번의 스캔)
    h = harvest(views, _user_words(glossary))
    print(f"후보 {len(h.mentions)}종 · 문장 {h.n_sents} · 공기 쌍 {len(h.cooccurs)}"
          f" ({time.monotonic() - t0:.0f}s)")

    # ── 점수화 + 컷오프
    rows = score(h, min_tf=min_tf)[:top]
    keep = {r.key for r in rows}
    _write_tsv(rows, out_dir / "candidates.tsv")
    print(f"점수화 → 상위 {len(rows)} (candidates.tsv)")

    # ── 관계 증거(§5.8b) — 컷 통과 후보끼리만 집계
    n_ev = rel_mod.write_evidence(h.cooccurs, out_dir / "rel_evidence.jsonl")
    proto = rel_mod.aggregate(h, keep)
    rel_mod.save(proto, out_dir / "proto_rel.json")
    n_cand = sum(1 for p in proto if p["status"] == "candidate")
    print(f"관계 증거 {n_ev}건 → PROTO_REL {len(proto)}쌍 (candidate {n_cand})")

    # ── 계층 후보(⑥)
    hier = hier_mod.build(h, rows)
    hier_mod.save(hier, out_dir / "hierarchy.json")
    print(f"계층 후보 {len(hier['edges'])}개 · 형제 묶음 {len(hier['siblings'])}개")

    # ── 군집 (임베딩 또는 정규형 단독)
    if use_embed:
        from lawrag.core.terms import embed as embed_mod
        surfaces = [r.surface for r in rows]
        te = time.monotonic()
        vecs, n_fresh = embed_mod.encode(surfaces, out_dir / "embeddings")
        order = list(range(len(rows)))            # rows 는 이미 Borda 순
        groups_idx = cluster_mod.cluster(vecs, order)
        print(f"임베딩 {len(surfaces)}건 (신규 {n_fresh}) → 군집 "
              f"{len(groups_idx)}개 ({time.monotonic() - te:.0f}s)")
    else:
        groups_idx = [[i] for i in range(len(rows))]
        print("임베딩 생략 — 정규형 단독 군집")
    groups = [[rows[i].key for i in g] for g in groups_idx]
    # 군집 감사 파일 — 무엇이 무엇과 묶였는지. 과병합(§2.3 괴물)은 여기서 보인다.
    with (out_dir / "clusters.jsonl").open("w", encoding="utf-8") as f:
        for gi, g in enumerate(groups):
            if len(g) > 1:
                f.write(json.dumps({"id": gi, "members": g},
                                   ensure_ascii=False) + "\n")

    # ── LLM 배치 판정 (있으면)
    clusters_payload = []
    for gi, g in enumerate(groups_idx):
        members = [rows[i] for i in g]
        snippets = []
        for r in members:
            for m in h.mentions.get(r.key, []):
                if m.text and m.text not in snippets:
                    snippets.append(m.text)
                if len(snippets) >= 3:
                    break
            if len(snippets) >= 3:
                break
        clusters_payload.append({
            "id": gi, "surfaces": [r.surface for r in members],
            "tf": sum(r.tf for r in members),
            "df": max(r.df for r in members), "snippets": snippets})
    verdicts = judge_mod.judge(llm, clusters_payload)
    if llm is not None:
        n_yes = sum(1 for v in verdicts.values() if v.is_term)
        print(f"판정 {len(verdicts)}/{len(groups)} (용어 {n_yes}) · "
              f"{llm.totals()}")
    else:
        print("LLM 없음 — 무판정 잠정 등재로 내려간다")

    # ── 게이트 + 등재
    if dry_run:
        print("dry-run — 등재하지 않음")
        report["dry_run"] = True
    else:
        rep = gate_mod.register(h, rows, groups, verdicts, glossary)
        swept = gate_mod.sweep(h, glossary)
        if swept["demoted"]:
            print(f"소급 강등 {len(swept['demoted'])}: "
                  + " · ".join(swept["demoted"][:10]))
        print(f"등재 신규 {len(rep['added'])} · 갱신 {len(rep['updated'])} · "
              f"기각 {len(rep['rejected'])} → {rep['store']}")
        for r in rep["rejected"][:8]:
            print(f"  기각: {r['군집']} — {r['이유']}")
        report["register"] = {k: rep[k] for k in ("added", "updated", "total")}
        report["rejected"] = rep["rejected"]

        cov = gate_mod.coverage(h, views, glossary)
        (out_dir / "coverage.json").write_text(
            json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"커버리지: 구역 {cov['total']['nodes']} 중 공백 "
              f"{cov['total']['gaps']} ({cov['total']['gap_ratio']:.0%})")
        report["coverage"] = cov["total"]

    report["took_sec"] = round(time.monotonic() - t0, 1)
    return report


def _write_tsv(rows, path: Path) -> None:
    """점수 근거 전부를 감사 가능하게 — 왜 이 후보가 이 순위인지."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("rank\tkey\tsurface\ttokens\ttf\tdf\theading\tcvalue\tg2\tdc\tborda\n")
        for r in rows:
            f.write(f"{r.rank}\t{r.key}\t{r.surface}\t{r.n_tokens}\t{r.tf}\t"
                    f"{r.df}\t{r.heading}\t{r.cvalue:.2f}\t{r.g2:.2f}\t"
                    f"{r.dc:.3f}\t{r.borda}\n")


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m lawrag.core.terms build",
        description="Tier 2+3 — 통계 깔때기 + 임베딩 군집 + LLM 판정 + 게이트 등재")
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--glossary", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--min-tf", type=int, default=2)
    ap.add_argument("--no-embed", action="store_true",
                    help="임베딩 군집 생략 (모델 다운로드 없이 결정론만)")
    ap.add_argument("--no-llm", action="store_true",
                    help="판정 생략 — 전 군집이 무판정 잠정 등재")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    llm = None
    if not args.no_llm:
        import os

        from lawrag.core import llm as llm_mod
        if llm_mod.available():
            llm = llm_mod.LLM()
        else:
            print(f"LLM 없음({llm_mod.MISSING_HINT}) — LLM 판정을 건너뛴다")

    run(store=args.store, glossary=args.glossary, out_dir=args.out,
        top=args.top, min_tf=args.min_tf, use_embed=not args.no_embed,
        llm=llm, dry_run=args.dry_run)
    return 0
