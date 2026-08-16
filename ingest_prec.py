"""수집된 판례 → 위키 raw 층(md) — 기계적 정리 단계.

    python ingest_prec.py

corpus/prec(수집 정본, XML — 전문 포함)는 읽기만 한다. 코퍼스 법령 인용이
있는 판례만 data/wiki/raw/prec/<선고일>-<사건번호>.md 로 이관한다.
md 에는 대법원이 만든 공식 요지(판시사항·판결요지·참조조문)만 싣는다 —
전문은 corpus XML 이 정본이고 md 머리가 그 경로를 가리킨다.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from sources.cite import plain_mentions  # noqa: E402
from sources.common import safe_filename  # noqa: E402
from sources.prec import case_text, parse_case  # noqa: E402

PREC_DIR = REPO_ROOT / "corpus" / "prec"
CORPUS_DIR = REPO_ROOT / "corpus"
RAW_DIR = REPO_ROOT / "data" / "wiki" / "raw" / "prec"


def corpus_names() -> list[str]:
    m = json.loads((CORPUS_DIR / "law" / "manifest.json").read_text("utf-8"))
    return sorted({(i.get("name") or "").strip() for i in m["items"]} - {""})


def fmt_date(d: str) -> str:
    d = d.strip().replace(".", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d


def main() -> int:
    manifest = json.loads((PREC_DIR / "manifest.json").read_text("utf-8"))
    names = corpus_names()
    today = time.strftime("%Y-%m-%d")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    n = dropped = 0
    taken: set[str] = set()      # 같은 사건번호 중복 등재 실재 — 덮어쓰기 금지
    for item in manifest["items"]:
        if item.get("status") != "ok" or not item.get("file"):
            continue
        case = parse_case((REPO_ROOT / item["file"]).read_text("utf-8"))
        # 저장값을 믿지 않는다 — 지금 규칙·지금 코퍼스로 재판정 (ingest_expc 규율)
        item["laws"] = plain_mentions(case_text(case), names)
        if not item["laws"]:
            dropped += 1
            continue
        decided = fmt_date(case["decided"])
        sect = "\n\n".join(
            f"## {t}\n\n{case[k]}" for t, k in
            (("판시사항", "issues"), ("판결요지", "summary"),
             ("참조조문", "ref_articles"), ("참조판례", "ref_cases"))
            if case.get(k))
        text = (f"# {case['label']}\n\n"
                f"> Source: https://www.law.go.kr/DRF/lawService.do?target=prec"
                f"&ID={case['serial']}&type=HTML\n"
                f"> Collected: {today}\n"
                f"> Published: {decided or 'Unknown'}\n\n"
                f"{case['court']} {case['case_no']} {case['judgment']}"
                f" ({case['kind']}) · 관련: {' · '.join(item['laws'])}\n"
                f"전문: {item['file']}\n\n{sect}\n")
        name = safe_filename(f"{decided}-{case['case_no']}") or case["serial"]
        if name in taken:
            name = f"{name}-{case['serial']}"
        taken.add(name)
        (RAW_DIR / f"{name}.md").write_text(text, "utf-8")
        n += 1
    print(f"위키 raw {n}건 → {RAW_DIR.relative_to(REPO_ROOT)}/"
          f" (인용 없음 제외 {dropped}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
