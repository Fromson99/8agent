"""문서 파일 묶음(hwp·hwpx·docx·pdf) → 구조 검수 스토어 등록 — core.ingest 의 범용 CLI 낯.

    python -m lawrag.pipeline.ingest_files 01_DATA/INBOX/AUTHORING/corpus/forms/*.hwp --folder 상장서식 --kind krx-form \\
        --source "KRX 상장규정 시행세칙 별지서식" --collected 2026-08-19
    python -m lawrag.pipeline.ingest_files 표준정관.hwp --folder 표준정관 --kind klca-model \\
        --order "kr_장>kr_절" "kr_장>kr_article" "kr_절>kr_article"
    python -m lawrag.pipeline.ingest_files 서식.hwp --dry-run          # 구조만 보고 스토어엔 안 쓴다

lawrag/pipeline/ingest_naegyu.py(내규 docx)·ingest_lawxml.py(법령 XML)·ingest_rulehtml.py(조문
HTML)가 문서군마다 한 장씩이라면, 이것은 문서군 지식이 없는 파일들을 위한 문이다 —
docs/LINEAGE.md 가 "남은 것"으로 적어 둔 hwp 배치 러너. 실제 이관은 lawrag/core/ingest.py
(ingest)가 한다(업로드 API 와 같은 문). 여기 남은 것은 CLI 인자와 meta 의 출처 표기뿐.

- hwp 는 core.parse_adapter.parse_hwp 가 core.hwp5_md(레코드 XML 직독)로 md 를 만들어
  구조화한다 — 사이드카 .md 를 넣는 게 아니라 **원본 .hwp 를 넣는다**(md 는 문이 안 받는다).
- 같은 바이트는 같은 doc_id(sha256 앞 16자리) — 재실행이 멱등이고, 사람이 고친 이름·폴더는
  core.ingest 가 지킨다.
- --kind 는 외규/내규를 가르는 축(law·admrul·krx-rule·kofia-rule·internal …)에 새 값을
  보탠다. 스토어엔 검사가 없다 — 고른 값이 그대로 /v1/lineage·뷰어에 보인다.
- 구조 품질은 meta 의 score·tier 로 남는다. 서식(표 중심 문서)은 warm 이 보통이다 —
  형식을 묶고 싶으면 /v1/formats 로 나중에 바인딩한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from lawrag.platform.paths import data_path, repository_root

REPO_ROOT = repository_root()
sys.path.insert(0, str(REPO_ROOT))

from lawrag.core.ingest import family_of, ingest  # noqa: E402

ACCEPTED = (".hwp", ".hwpx", ".docx", ".pdf")


def _store(arg: str | None) -> Path:
    return Path(arg or os.environ.get("STRUCTURE_STORE") or data_path("INBOX", "AUTHORING", "structure"))


def parse_order(pairs: list[str] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in pairs or []:
        if ">" not in p:
            raise SystemExit(f"--order 는 'A>B' 꼴이어야 합니다 — {p!r}")
        a, b = (s.strip() for s in p.split(">", 1))
        out.append((a, b))
    return out


def gather(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(x for x in path.iterdir()
                                if x.is_file() and x.suffix.lower() in ACCEPTED))
        else:
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="문서 파일 → 구조 스토어 (유도 경로)")
    ap.add_argument("paths", nargs="+", help="hwp·hwpx·docx·pdf 파일 또는 디렉터리")
    ap.add_argument("--name", help="문서 이름 (paths 가 1건일 때만; 기본 파일명)")
    ap.add_argument("--store", help="스토어 경로 (기본: $STRUCTURE_STORE 또는 01_DATA/INBOX/AUTHORING/structure)")
    ap.add_argument("--folder", default="", help="묶어 둘 폴더 라벨")
    ap.add_argument("--kind", default="", help="문서 축 (예: krx-form · klca-model)")
    ap.add_argument("--source", default="", help="출처 표기 (meta.source)")
    ap.add_argument("--collected", default=date.today().isoformat(),
                    help="입수일 YYYY-MM-DD (기본 오늘)")
    ap.add_argument("--order", nargs="*", metavar="A>B",
                    help="계열 순서 힌트 (예: 'kr_장>kr_article')")
    ap.add_argument("--extra", nargs="*", metavar="k=v", help="meta 에 덧붙일 키=값")
    ap.add_argument("--dry-run", action="store_true",
                    help="구조만 해석해 요약을 찍고 스토어엔 쓰지 않는다")
    args = ap.parse_args(argv)

    files = gather(args.paths)
    if not files:
        ap.error("넣을 파일이 없습니다")
    if args.name and len(files) != 1:
        ap.error("--name 은 파일이 1건일 때만")

    extra: dict = {}
    if args.kind:
        extra["kind"] = args.kind
    if args.source:
        extra["source"] = args.source
    if args.collected:
        extra["collected"] = args.collected
    for kv in args.extra or []:
        if "=" not in kv:
            ap.error(f"--extra 는 k=v 꼴 — {kv!r}")
        k, v = kv.split("=", 1)
        extra[k.strip()] = v.strip()
    hints: dict = {}
    order = parse_order(args.order)
    if order:
        hints["partial_order"] = order

    store = _store(args.store)
    failed = 0
    for path in files:
        if family_of(path.name) is None:
            failed += 1
            print(f"✗ {path.name}: 받지 않는 형식 ({ACCEPTED} 만)", file=sys.stderr)
            continue
        raw = path.read_bytes()
        if args.dry_run:
            from lawrag.core.structure.cli import main as interpret_main
            print(f"--- {path.name}")
            interpret_main(["interpret", str(path), "--tree-limit", "0",
                            *(["--order", *[f"{a}>{b}" for a, b in order]] if order else [])])
            continue
        try:
            r = ingest(raw, path.name, store=store, name=args.name or "",
                       folder=args.folder, hints=hints or None, extra_meta=extra or None)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            failed += 1
            print(f"✗ {path.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        m = r["meta"]
        print(f"✓ {m['name']}  doc_id={m['doc_id']}  score={m['score']} {m['tier']}  "
              f"{m.get('source_kind')}/{m.get('structured_by')}  pages={m.get('pages')}  "
              f"kind={m.get('kind', '')}  folder={m.get('folder', '')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
