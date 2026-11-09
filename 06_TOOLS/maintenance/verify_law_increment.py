"""법제처 실제 판본으로 조문 비교 엔진을 검증한다 (모델·DB 없음).

같은 법령ID·행정규칙ID의 서로 다른 원문 XML을 시행일 순으로 줄 세워 이웃 판본끼리 비교한다.

검사
1. 누락 0: 새 판본에서 법제처 조문변경여부=Y인 조문을 SAME으로 판정하지 않는다.
   Y는 직전 공포 대비 표시라서, 공포일과 시행일이 모두 늦은 쌍에서만 센다 (판본을 건너뛰어도
   새 공포에서 바뀐 조문은 바뀐 것으로 나와야 한다). 같은 공포번호의 다른 조회본
   (공포 전문 / 시행일 기준본)이나 시행일 기준본끼리 공포·시행 순서가 엇갈린 쌍은 뺀다
   (실측: 상법 제20991호 2026-07-23 기준본은 2026-03-06 시행 제21448호 개정을 이미 담고 있다).
   공식 Y는 일부만 표시한다 (실측: 지배구조법 시행령 제34584호 제19조 제2항 삭제가 N) —
   공식 외 추가 변경은 오탐이 아니라 실제 변경일 수 있어 따로 적기만 한다.
5. 게이트: 잘린 원문(조문 수 급감)은 강한 경고로 자동 반영이 막혀야 한다.
2. 연속 판본(부칙이 정확히 1개 늘어난 쌍)은 우리 변경 집합과 공식 Y 집합의 차이를 함께 적는다.
3. 서식만 다른 원문(조문 지문 동일)은 변경 0이어야 한다.
4. 같은 입력 재실행은 같은 결과여야 한다.

사용:
  .venv/bin/python 06_TOOLS/maintenance/verify_law_increment.py --list <xml 경로 목록 txt> --out <폴더>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.increment.addenda import schedule_for  # noqa: E402
from lawrag.increment.diff import SAME, BaseArticle, diff_snapshot  # noqa: E402
from lawrag.increment.gate import assign_effective, evaluate  # noqa: E402
from lawrag.increment.lawgo_parse import (KIND_ADDENDUM, ParseError, parse_lawgo_xml,  # noqa: E402
                                          snapshot_fingerprint)


def as_base(snapshot):
    return [BaseArticle(a.key, a.kind, a.title, a.text, "L:" + a.key, "base:" + a.key,
                        snapshot.effective, a.seq, a.attachment_sha256)
            for a in snapshot.articles if not a.deleted]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    seen: dict[str, Path] = {}
    for line in Path(args.list).read_text(encoding="utf-8").splitlines():
        path = Path(line.strip())
        if not path.is_file():
            continue
        raw = path.read_bytes()
        seen.setdefault(hashlib.sha256(raw).hexdigest(), path)
    docs = defaultdict(list)
    rejected = []
    for sha, path in seen.items():
        head = path.read_bytes()[:4000].decode("utf-8", "ignore")
        if "<법령" not in head and "<AdmRulService" not in head:
            continue
        try:
            snapshot = parse_lawgo_xml(path.read_bytes(), source_sha256=sha)
        except ParseError as exc:
            if "지원하지 않는 XML 루트" in str(exc):
                continue                      # 용어검색·해석례 등 본문이 아닌 응답
            rejected.append({"path": str(path), "error": str(exc)})
            continue
        docs[snapshot.doc_cd].append((snapshot, path))

    pairs, misses_total, format_only = [], 0, []
    started = time.time()
    for doc_cd, items in sorted(docs.items()):
        if len(items) < 2:
            continue
        by_fp = {}
        for snapshot, path in items:
            by_fp.setdefault(snapshot_fingerprint(snapshot), (snapshot, path))
        if len(by_fp) < len(items):
            groups = defaultdict(list)
            for snapshot, path in items:
                groups[snapshot_fingerprint(snapshot)].append(snapshot.source_sha256[:16])
            format_only.extend({"doc_cd": doc_cd, "same_articles_different_xml": g}
                               for g in groups.values() if len(g) > 1)
        ordered = sorted(by_fp.values(), key=lambda x: (x[0].promulgated, len(x[0].addenda),
                                                        x[0].effective))
        for (old, _), (new, _) in zip(ordered, ordered[1:]):
            t0 = time.time()
            result = diff_snapshot(as_base(old), new.articles, doc_cd=doc_cd, version_id="v")
            elapsed = time.time() - t0
            again = diff_snapshot(as_base(old), new.articles, doc_cd=doc_cd, version_id="v")
            stable = [(c.change_type, c.old and c.old.key, c.new and c.new.key) for c in result.changes] == \
                     [(c.change_type, c.old and c.old.key, c.new and c.new.key) for c in again.changes]
            changed = {c.new.key for c in result.changes
                       if c.new is not None and c.change_type != SAME and c.kind != KIND_ADDENDUM}
            same = {c.new.key for c in result.changes if c.new is not None and c.change_type == SAME}
            official_y = {a.key for a in new.articles if a.official_changed == "Y"}
            later = (new.promulgated > old.promulgated and new.promulgation_no != old.promulgation_no
                     and new.effective >= old.effective)
            schedule = schedule_for(new)
            assign_effective(result, new, schedule)
            gate = evaluate(result, new, schedule, base_effective="", base_count=len(old.articles),
                            today="20261106")
            misses = sorted(official_y & same) if later else []
            misses_total += len(misses)
            consecutive = later and len(new.addenda) == len(old.addenda) + 1
            pairs.append({
                "doc_cd": doc_cd, "name": new.name,
                "old": {"sha16": old.source_sha256[:16], "no": old.promulgation_no, "eff": old.effective},
                "new": {"sha16": new.source_sha256[:16], "no": new.promulgation_no, "eff": new.effective},
                "later_promulgation": later,
                "consecutive": consecutive, "seconds": round(elapsed, 3), "stable_rerun": stable,
                "counts": result.counts(),
                "official_y": sorted(official_y), "misses": misses,
                "extra_vs_official": sorted(changed - official_y) if consecutive and official_y else None,
                "official_tag_present": bool(official_y) or any(a.official_changed for a in new.articles),
                "gate_strong": [w.code for w in gate.strong],
                "gate_info": [w.code for w in gate.warnings if not w.strong],
                "addendum_per_article": schedule.per_article,
                "changes": [{"type": c.change_type, "old": c.old and c.old.key, "new": c.new and c.new.key,
                             "similarity": c.similarity, "reason": c.reason}
                            for c in result.changed() if c.kind != KIND_ADDENDUM],
            })
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "documents_with_multiple_versions": sum(1 for v in docs.values() if len(v) > 1),
        "pairs": len(pairs),
        "later_promulgation_pairs": sum(1 for p in pairs if p["later_promulgation"]),
        "consecutive_pairs": sum(1 for p in pairs if p["consecutive"]),
        "official_y_articles_checked": sum(len(p["official_y"]) for p in pairs if p["later_promulgation"]),
        "misses_official_y_judged_same": misses_total,
        "unstable_reruns": sum(1 for p in pairs if not p["stable_rerun"]),
        "format_only_groups": len(format_only),
        "parse_rejected": len(rejected),
        "total_diff_seconds": round(sum(p["seconds"] for p in pairs), 2),
        "max_diff_seconds": max((p["seconds"] for p in pairs), default=0),
        "wall_seconds": round(time.time() - started, 2),
    }
    (out / "VERIFY.json").write_text(json.dumps({"summary": summary, "pairs": pairs,
                                                 "format_only": format_only, "rejected": rejected},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [json.dumps(summary, ensure_ascii=False)]
    for p in pairs:
        c = {k: v for k, v in p["counts"].items() if v and k != "SAME"}
        lines.append(f'{p["name"]} {p["old"]["no"]}({p["old"]["eff"]})→{p["new"]["no"]}({p["new"]["eff"]}) '
                     f'{"연속" if p["consecutive"] else "이후공포" if p["later_promulgation"] else "같은공포·조회본차이"} '
                     f'{c} 공식Y={len(p["official_y"])} '
                     f'누락={p["misses"]} {p["seconds"]}s'
                     + (f' 공식외추가={p["extra_vs_official"]}' if p["extra_vs_official"] else "")
                     + (f' 강한경고={p["gate_strong"]}' if p["gate_strong"] else ""))
    (out / "VERIFY.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if misses_total == 0 and summary["unstable_reruns"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
