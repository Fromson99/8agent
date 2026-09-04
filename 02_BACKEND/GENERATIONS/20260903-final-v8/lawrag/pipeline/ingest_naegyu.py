"""내규 docx → 구조 검수 스토어 등록 — core.internal_rules 의 CLI 낯.

    python -m lawrag.pipeline.ingest_naegyu docs/examples/task5-risk-agent/internal-rules/*.docx
    python -m lawrag.pipeline.ingest_naegyu 세칙_v1_2024.docx --status 구판
    python -m lawrag.pipeline.ingest_naegyu 지침.docx --name 투자및인수위험관리지침 --store data/structure

실제 이관은 lawrag/core/internal_rules.py(ingest_internal_rule)가 한다 — 업로드 API 와
같은 문이어야 한다(코드단 일원화, docs/LINEAGE.md). 여기 남은 것은 CLI 인자뿐이다.

구조는 유도(DP) 경로로 잡는다 — 내규 docx 는 Word 스타일이 없거나 반쯤이라
docxstyle 을 믿을 수 없고, 유도는 스타일 없이도 장·조·항·호·목을 잡는다
(실측 core/internal_rules.py 머리말). 같은 파일은 같은 doc_id(sha256 앞 16자리)라
재실행이 멱등이다. 원본은 문서 디렉토리에 source.docx 로 남는다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from lawrag.platform.paths import data_path, repository_root

REPO_ROOT = repository_root()
sys.path.insert(0, str(REPO_ROOT))

from lawrag.core.internal_rules import FOLDER, ingest_internal_rule  # noqa: E402


def _store(arg: str | None) -> Path:
    return Path(arg or os.environ.get("STRUCTURE_STORE") or data_path("structure"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="내규 docx → 구조 스토어 (유도 경로)")
    ap.add_argument("paths", nargs="+", help="내규 docx")
    ap.add_argument("--name", help="문서 이름 (paths 가 1건일 때만; 기본 파일명)")
    ap.add_argument("--store", help="스토어 경로 (기본: $STRUCTURE_STORE 또는 data/structure)")
    ap.add_argument("--folder", default=FOLDER, help=f"묶어 둘 폴더 라벨 (기본 {FOLDER})")
    ap.add_argument("--status", default="현행", choices=["현행", "구판"],
                    help="판 표식 — 신구 대비의 구판은 '구판' 으로")
    ap.add_argument("--series", help="문서군 키 (기본: 이름에서 _vN_YYYY 꼬리를 뗀 것)")
    ap.add_argument("--version", help="판 표식 (기본: 이름의 vN)")
    args = ap.parse_args(argv)

    store = _store(args.store)
    if args.name and len(args.paths) != 1:
        ap.error("--name 은 paths 가 1건일 때만")
    failed = 0
    for p in args.paths:
        path = Path(p)
        try:
            r = ingest_internal_rule(path.read_bytes(), path.name, store=store,
                                     name=args.name or "", folder=args.folder,
                                     status=args.status, series=args.series or "",
                                     version=args.version or "")
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            failed += 1
            print(f"✗ {path.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        m = r["meta"]
        print(f"✓ {m['name']}  doc_id={m['doc_id']}  score={m['score']} {m['tier']}  "
              f"fp={m.get('fingerprint')}  series={m.get('series')} {m.get('version')} "
              f"{m.get('status')}  제정={m.get('enacted')} 개정={m.get('revised')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
