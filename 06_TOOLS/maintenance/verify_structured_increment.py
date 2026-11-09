"""구조화 경로(GENOS 구조화 결과 → 증분 비교)가 법제처 XML 경로와 같은 판정을 내는지 대조한다.

입력: 법제처 원문 XML 경로 목록. 같은 폴더에 구조화 결과 result.json이 있는 판본만 쓴다
(GENOS 구조화 산출물 ARTIFACTS/STRUCTURE/<문서ID>/{source.xml,result.json}).

검사
1. 문서별: 두 경로의 조문 키·종류·삭제 여부·내용 해시가 같은가 (차이는 키별로 기록).
2. 판본 쌍별: verify_law_increment.py와 같은 순서로 이웃 판본을 비교해 변경 목록
   (판정·옛 키·새 키)·게이트 강한 경고·문서 시행일이 같은가.
3. 같은 입력 재실행 결과가 같은가.

사용:
  .venv/bin/python 06_TOOLS/maintenance/verify_structured_increment.py \
      --list <xml 경로 목록 txt> --out <폴더>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.increment.addenda import schedule_for  # noqa: E402
from lawrag.increment.diff import BaseArticle, diff_snapshot  # noqa: E402
from lawrag.increment.gate import assign_effective, evaluate  # noqa: E402
from lawrag.increment.lawgo_parse import ParseError, parse_lawgo_xml, snapshot_fingerprint  # noqa: E402
from lawrag.increment.normalize import text_hash  # noqa: E402
from lawrag.increment.structured import from_result, header_from_xml  # noqa: E402


def as_base(snapshot):
    return [BaseArticle(a.key, a.kind, a.title, a.text, "L:" + a.key, "base:" + a.key,
                        snapshot.effective, a.seq, a.attachment_sha256)
            for a in snapshot.articles if not a.deleted]


def article_view(snapshot):
    return {a.key: (a.kind, a.deleted, text_hash(a.text)) for a in snapshot.articles}


def judge(old, new):
    result = diff_snapshot(as_base(old), new.articles, doc_cd=new.doc_cd, version_id="v")
    schedule = schedule_for(new)
    effective = assign_effective(result, new, schedule)
    gate = evaluate(result, new, schedule, base_effective="", base_count=len(old.articles),
                    today="20261109")
    changes = sorted((c.change_type, c.old and c.old.key or "", c.new and c.new.key or "")
                     for c in result.changes if c.change_type != "SAME")
    return {"changes": changes, "strong": sorted(w.code for w in gate.strong),
            "stop": gate.stop, "effective": effective, "default": schedule.default,
            "per_article": schedule.per_article}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    seen: dict[str, Path] = {}
    for line in Path(args.list).read_text(encoding="utf-8").splitlines():
        path = Path(line.strip())
        if path.is_file() and (path.parent / "result.json").is_file():
            seen.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), path)

    docs = defaultdict(list)
    doc_rows, rejected = [], []
    key_diff_kinds = Counter()
    for sha, path in sorted(seen.items()):
        raw = path.read_bytes()
        head = raw[:4000].decode("utf-8", "ignore")
        if "<법령" not in head and "<AdmRulService" not in head:
            continue
        try:
            xml_snap = parse_lawgo_xml(raw, source_sha256=sha)
        except ParseError as exc:
            if "지원하지 않는 XML 루트" not in str(exc):
                rejected.append({"path": str(path), "side": "xml", "error": str(exc)})
            continue
        result = json.loads((path.parent / "result.json").read_text(encoding="utf-8"))
        try:
            st_snap = from_result(result, header_from_xml(raw, source_sha256=sha))
        except ParseError as exc:
            rejected.append({"path": str(path), "side": "structured", "error": str(exc)})
            continue
        xv, sv = article_view(xml_snap), article_view(st_snap)
        only_x, only_s = sorted(set(xv) - set(sv)), sorted(set(sv) - set(xv))
        differ = sorted(k for k in set(xv) & set(sv) if xv[k] != sv[k])
        for k in differ:
            key_diff_kinds[xv[k][0]] += 1
        doc_rows.append({"name": xml_snap.name, "no": xml_snap.promulgation_no, "sha16": sha[:16],
                         "articles": len(xv), "only_xml": only_x, "only_structured": only_s,
                         "differ": differ})
        docs[xml_snap.doc_cd].append((xml_snap, st_snap))

    pairs = []
    for doc_cd, items in sorted(docs.items()):
        by_fp = {}
        for xml_snap, st_snap in items:
            by_fp.setdefault(snapshot_fingerprint(xml_snap), (xml_snap, st_snap))
        ordered = sorted(by_fp.values(), key=lambda x: (x[0].promulgated, len(x[0].addenda), x[0].effective))
        for (ox, os_), (nx, ns) in zip(ordered, ordered[1:]):
            jx, js = judge(ox, nx), judge(os_, ns)
            again = judge(os_, ns)
            pairs.append({
                "doc_cd": doc_cd, "name": nx.name, "old": ox.promulgation_no, "new": nx.promulgation_no,
                "same_changes": jx["changes"] == js["changes"],
                "same_gate": (jx["strong"], jx["stop"]) == (js["strong"], js["stop"]),
                "same_effective": (jx["effective"], jx["default"], jx["per_article"])
                                  == (js["effective"], js["default"], js["per_article"]),
                "stable_rerun": again == js,
                "xml_counts": Counter(c[0] for c in jx["changes"]),
                "only_xml_changes": sorted(set(map(tuple, jx["changes"])) - set(map(tuple, js["changes"]))),
                "only_structured_changes": sorted(set(map(tuple, js["changes"])) - set(map(tuple, jx["changes"]))),
                "xml_gate": jx["strong"], "structured_gate": js["strong"],
            })

    summary = {
        "documents": len(doc_rows),
        "documents_identical": sum(1 for d in doc_rows if not (d["only_xml"] or d["only_structured"] or d["differ"])),
        "documents_key_set_differs": sum(1 for d in doc_rows if d["only_xml"] or d["only_structured"]),
        "articles_total": sum(d["articles"] for d in doc_rows),
        "articles_content_differs": sum(len(d["differ"]) for d in doc_rows),
        "content_differs_by_kind": dict(key_diff_kinds),
        "pairs": len(pairs),
        "pairs_same_changes": sum(p["same_changes"] for p in pairs),
        "pairs_same_gate": sum(p["same_gate"] for p in pairs),
        "pairs_same_effective": sum(p["same_effective"] for p in pairs),
        "pairs_unstable_rerun": sum(not p["stable_rerun"] for p in pairs),
        "rejected": len(rejected),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "STRUCTURED_VERIFY.json").write_text(json.dumps(
        {"summary": summary, "pairs": pairs, "documents": doc_rows, "rejected": rejected},
        ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    lines = [json.dumps(summary, ensure_ascii=False)]
    for p in pairs:
        mark = "같음" if p["same_changes"] and p["same_gate"] and p["same_effective"] else "다름"
        lines.append(f'[{mark}] {p["name"]} {p["old"]}→{p["new"]} XML판정={dict(p["xml_counts"])}'
                     + (f' XML만={p["only_xml_changes"][:5]}' if p["only_xml_changes"] else "")
                     + (f' 구조화만={p["only_structured_changes"][:5]}' if p["only_structured_changes"] else "")
                     + ("" if p["same_gate"] else f' 경고 XML={p["xml_gate"]} 구조화={p["structured_gate"]}'))
    for d in doc_rows:
        if d["only_xml"] or d["only_structured"] or d["differ"]:
            lines.append(f'[문서차이] {d["name"]} {d["no"]} XML만={d["only_xml"][:8]} '
                         f'구조화만={d["only_structured"][:8]} 내용다름={d["differ"][:8]}')
    for r in rejected:
        lines.append(f'[거절] {r["side"]} {r["path"]} {r["error"]}')
    (out / "STRUCTURED_VERIFY.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    ok = summary["pairs_same_changes"] == summary["pairs"] and summary["pairs_unstable_rerun"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
