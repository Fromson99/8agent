"""소스별 manifest 를 data/corpus/manifest.json 하나로 병합한다.

    python scripts/merge_manifests.py

각 항목에 source 필드를 넣어 출처를 구분한다. 스키마는 docs/adapter_design.md.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO_ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
CORPUS = REPO_ROOT / "01_DATA" / "corpus"


def main() -> None:
    merged = {"collected_at": time.strftime("%Y-%m-%d %H:%M:%S"), "sources": [], "items": []}
    for path in sorted(CORPUS.glob("*/manifest.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        source = data.get("source") or path.parent.name
        merged["sources"].append({"source": source, "collected_at": data.get("collected_at", "")})
        for item in data.get("items", []):
            merged["items"].append({"source": source, **item})
    out = CORPUS / "manifest.json"
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{out}: 소스 {len(merged['sources'])}개, 항목 {len(merged['items'])}건")


if __name__ == "__main__":
    main()
