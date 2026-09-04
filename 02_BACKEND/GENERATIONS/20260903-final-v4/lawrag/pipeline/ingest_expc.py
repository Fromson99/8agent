"""수집된 법령해석례 → 열람 색인 + 위키 raw 층 — 기계적 정리 단계.

    python -m lawrag.pipeline.ingest_expc                # 색인(data/expc/index.json) + raw(md) 생성
    python -m lawrag.pipeline.ingest_expc --keep-unrelated   # 인용 없는 오탐도 색인에 남긴다

data/corpus/expc 는 수집 정본이라 여기서 절대 고치지 않는다(읽기 전용). 산출은 둘:

1. data/expc/index.json — /expc/ 화면·/v1/expc API 가 읽는 열람 색인.
2. data/wiki/raw/expc/<해석일>-<안건번호>.md — llm-wiki 의 raw 층(소스 1개 =
   파일 1개, 원문 보존). XML 에서 결정적으로 옮기므로 재실행이 멱등이고,
   위키 아티클의 Raw 필드가 이 파일들을 가리킨다.

관련 법령은 저장값을 믿지 않고 **지금 코퍼스 명칭으로 재판정**한다
(lawrag/sources/expc.cited_laws — 수집 이후 코퍼스에 법령이 늘었으면 연결도 늘어야
한다). 안건명 부분일치 수집의 오탐(laws=[])은 색인·raw 모두에서 뺀다.

지식 층(data/wiki/wiki/)은 여기서 만들지 않는다 — LLM 이 raw 를 읽고
컴파일하는 층이라 기계 단계가 아니다 (docs/expc.md §위키).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from lawrag.platform.paths import data_path, persisted_data_path, repository_root

REPO_ROOT = repository_root()
sys.path.insert(0, str(REPO_ROOT))

from lawrag.sources.expc import case_text, cited_laws, parse_case  # noqa: E402

CORPUS_DIR = data_path("corpus")
EXPC_DIR = CORPUS_DIR / "expc"
OUT_DIR = data_path("expc")
RAW_DIR = data_path("wiki", "raw", "expc")


def corpus_names() -> list[str]:
    """인용 판정 명칭 — 코퍼스 세 소스의 문서 명칭 전부."""
    names: set[str] = set()
    for mf in CORPUS_DIR.glob("*/manifest.json"):
        if mf.parent.name == "expc":
            continue
        for item in json.loads(mf.read_text("utf-8")).get("items", []):
            name = (item.get("name") or "").strip()
            if name:
                names.add(name)
    return sorted(names)


def fmt_date(yyyymmdd: str) -> str:
    d = yyyymmdd.strip().replace(".", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else yyyymmdd


def build(keep_unrelated: bool = False) -> dict:
    manifest = json.loads((EXPC_DIR / "manifest.json").read_text("utf-8"))
    names = corpus_names()
    cases, dropped, broken = [], [], []
    for item in manifest["items"]:
        if item.get("status") != "ok" or not item.get("file"):
            broken.append(item.get("case_no") or item.get("name"))
            continue
        xml_path = persisted_data_path(item["file"])
        try:
            case = parse_case(xml_path.read_text("utf-8"))
        except Exception as e:                      # 원본 손상은 건너뛰고 알린다
            broken.append(f"{item.get('case_no')}: {e}")
            continue
        laws = cited_laws(case_text(case), names)
        if not laws and not keep_unrelated:
            dropped.append(f"{case['case_no']} {case['label'][:40]}")
            continue
        cases.append({
            "serial": case["serial"], "case_no": case["case_no"],
            "label": case["label"], "decided": fmt_date(case["decided"]),
            "req_org": case["req_org"], "ans_org": case["ans_org"],
            "laws": laws, "queries": item.get("queries", []),
            "issue": case["issue"], "answer": case["answer"],
            "reason": case["reason"],
        })
    cases.sort(key=lambda c: (c["decided"], c["case_no"]), reverse=True)

    law_counts: dict[str, int] = {}
    for c in cases:
        for law in c["laws"]:
            law_counts[law] = law_counts.get(law, 0) + 1
    return {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": manifest.get("source", ""),
        "collected_at": manifest.get("collected_at", ""),
        "stats": {
            "cases": len(cases), "dropped_unrelated": len(dropped),
            "broken": len(broken),
            "laws": [{"name": k, "count": v}
                     for k, v in sorted(law_counts.items(), key=lambda kv: -kv[1])],
        },
        "cases": cases,
        "_dropped": dropped, "_broken": broken,
    }


def raw_filename(case: dict) -> str:
    """raw 파일명 — 해석일-안건번호. 일자 미상이면 안건번호만 (llm-wiki 규약)."""
    d = case["decided"]
    import re
    return f"{d}-{case['case_no']}.md" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) \
        else f"{case['case_no']}.md"


def write_raw(case: dict, collected: str) -> Path:
    """사례 하나 → raw md (llm-wiki raw-template). 원문 보존 — 재작성 금지."""
    sect = "\n\n".join(f"## {t}\n\n{case[k]}"
                       for t, k in (("질의요지", "issue"), ("회답", "answer"),
                                    ("이유", "reason")) if case.get(k))
    text = (f"# {case['label']}\n\n"
            f"> Source: https://www.law.go.kr/LSW/expcInfoP.do?expcSeq={case['serial']}\n"
            f"> Collected: {collected[:10]}\n"
            f"> Published: {case['decided'] or 'Unknown'}\n\n"
            f"안건번호 {case['case_no']} · 해석기관 {case['ans_org']}"
            f" · 질의기관 {case['req_org'] or '—'}\n\n{sect}\n")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    p = RAW_DIR / raw_filename(case)
    p.write_text(text, "utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="법령해석례 → 열람 색인")
    ap.add_argument("--keep-unrelated", action="store_true",
                    help="코퍼스 인용이 없는 사례도 색인에 남긴다")
    args = ap.parse_args(argv)

    index = build(keep_unrelated=args.keep_unrelated)
    dropped, broken = index.pop("_dropped"), index.pop("_broken")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", "utf-8")

    for case in index["cases"]:
        write_raw(case, index.get("collected_at", ""))

    s = index["stats"]
    print(f"색인 {s['cases']}건 → {out.relative_to(REPO_ROOT)}")
    print(f"위키 raw {s['cases']}건 → {RAW_DIR.relative_to(REPO_ROOT)}/")
    if dropped:
        print(f"제외 {len(dropped)}건 — 코퍼스 인용 없음 (안건명 부분일치 오탐):")
        for line in dropped:
            print(f"  {line}")
    if broken:
        print(f"손상·미수집 {len(broken)}건: {broken}", file=sys.stderr)
    for row in s["laws"][:10]:
        print(f"  {row['count']:3d}  {row['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
