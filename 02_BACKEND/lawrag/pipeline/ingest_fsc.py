"""수집된 금융위 회신사례 → 위키 raw 층(md) — 기계적 정리 단계.

    python -m lawrag.pipeline.ingest_fsc

data/corpus/fsc(수집 정본, HTML)는 읽기만 한다. 관련 법령은 저장값을 믿지 않고
**지금 코퍼스 명칭·현행 판정 규칙으로 재판정**한다 (ingest_expc 와 같은
규율 — 판정 규칙이 고쳐지면 연결도 따라와야 한다). 인용이 있는 사례만
data/wiki/raw/fsc/<회신일>-<키>.md 로 이관한다 (llm-wiki raw-template).
재실행 멱등 — 같은 원문은 같은 md 가 된다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from lawrag.platform.paths import data_path, persisted_data_path, repository_root

REPO_ROOT = repository_root()
sys.path.insert(0, str(REPO_ROOT))

from lawrag.sources.cite import plain_mentions  # noqa: E402
from lawrag.sources.fsc import BASE, case_text, parse_detail  # noqa: E402

FSC_DIR = data_path("corpus", "fsc")
CORPUS_DIR = data_path("corpus")
RAW_DIR = data_path("wiki", "raw", "fsc")


def corpus_names() -> list[str]:
    m = json.loads((CORPUS_DIR / "law" / "manifest.json").read_text("utf-8"))
    return sorted({(i.get("name") or "").strip() for i in m["items"]} - {""})


def main(argv: list[str] | None = None) -> int:
    import argparse
    argparse.ArgumentParser(description="수집된 금융위 회신사례 → 위키 raw 층(md) — 인자 없음, 있으면 전부 다시 쓴다").parse_args(argv)
    manifest = json.loads((FSC_DIR / "manifest.json").read_text("utf-8"))
    names = corpus_names()
    today = time.strftime("%Y-%m-%d")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    n = dropped = 0
    for item in manifest["items"]:
        if item.get("status") != "ok" or not item.get("file"):
            continue
        case = parse_detail(persisted_data_path(item["file"]).read_text("utf-8"))
        item["laws"] = plain_mentions(case_text(case, item.get("label", "")),
                                      names)
        if not item["laws"]:
            dropped += 1
            continue
        replied = (item.get("replied") or case.get("replied") or "").strip()
        sect = "\n\n".join(
            f"## {t}\n\n{case[k]}" for t, k in
            (("질의요지", "issue"), ("회답", "answer"), ("이유", "reason"))
            if case.get(k))
        text = (f"# {item['label']}\n\n"
                f"> Source: {BASE} 회신사례 ({item['kind']} · {item['name']})\n"
                f"> Collected: {today}\n"
                f"> Published: {replied or 'Unknown'}\n\n"
                f"유형 {item['kind']} · 소관부서 {case.get('dept') or '—'}"
                f" · 관련: {' · '.join(item['laws'])}\n\n{sect}\n")
        prefix = f"{replied}-" if replied else ""
        (RAW_DIR / f"{prefix}{item['name']}.md").write_text(text, "utf-8")
        n += 1
    print(f"위키 raw {n}건 → {RAW_DIR.relative_to(REPO_ROOT)}/"
          f" (인용 없음 제외 {dropped}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
