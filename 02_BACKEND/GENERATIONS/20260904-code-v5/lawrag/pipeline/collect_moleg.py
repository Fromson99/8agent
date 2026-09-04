"""법제처 입안·심사 기준 수집기 — 해석 위키의 교과서 원천.

    python -m lawrag.pipeline.collect_moleg              # 두 권 수집 + 위키 raw(md) 이관
    python -m lawrag.pipeline.collect_moleg --force

대상은 둘뿐이고 주소가 게시판 첨부라 어댑터 계약(base.py)까지 갈 것이 없다
— 선언·다운로드·manifest·텍스트 이관을 이 파일이 다 한다. 실측(2026-08-14):

    법령 입안·심사 기준     2026년판 880쪽 5.8MB  (moleg.go.kr 정부입법 페이지)
    행정규칙 입안·심사 기준  2026년판 152쪽 3.9MB  (moleg.go.kr 간행물 게시판)

저장:
    data/corpus/moleg/<이름>.pdf            원문 (수집 정본)
    data/corpus/moleg/manifest.json        대장 (phase_model — 원장 밖)
    data/wiki/raw/moleg/<이름>.md      쪽 단위 텍스트 이관 (PyMuPDF) —
                                      위키 컴파일·grep 이 읽는 증거층

880쪽을 통째로 아티클로 만들지 않는다 — raw 에 두고, 위키가 개념을 다룰 때
필요한 장을 근거로 인용한다 (컴파일 대기는 wiki log 에 적는다).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from lawrag.sources.common import (
    HttpClient,
    build_logger,
    detect_format,
    load_manifest,
    make_session,
    manifest_item,
    save_manifest,
    sha256_file,
    upsert_item,
)
from lawrag.platform.paths import data_path, repository_root, runtime_path

REPO_ROOT = repository_root()
MOLEG_DIR = data_path("corpus", "moleg")
RAW_DIR = data_path("wiki", "raw", "moleg")
LOG_DIR = runtime_path("logs")

# 게시판 첨부 주소 실측 (2026-08-14). 개정판이 나오면 list_no 가 바뀐다 —
# moleg.go.kr 법제업무정보에서 새 주소를 확인해 여기만 고친다.
TARGETS = [
    {"name": "법령 입안·심사 기준", "edition": "2026",
     "url": "https://www.moleg.go.kr/boardDownload.es?bid=ATT&list_no=147288&seq=1",
     "page": "https://www.moleg.go.kr/menu.es?mid=a10105030000"},
    {"name": "행정규칙 입안·심사 기준", "edition": "2026",
     "url": "https://www.moleg.go.kr/boardDownload.es?bid=0007&list_no=145393&seq=1",
     "page": "https://www.moleg.go.kr/board.es?mid=a10404000000&bid=0007"
             "&act=view&list_no=145393"},
]


def to_raw_md(pdf_path: Path, name: str, edition: str, url: str) -> Path:
    """PDF → 쪽 단위 텍스트 md (llm-wiki raw-template). 재실행 멱등."""
    import fitz

    doc = fitz.open(pdf_path)
    parts = [f"# {name} ({edition}년판)\n",
             f"> Source: {url}",
             f"> Collected: {time.strftime('%Y-%m-%d')}",
             f"> Published: {edition}",
             f"\n총 {doc.page_count}쪽 — 법제처 발간. 쪽 표제는 원문 쪽 번호다.\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if text:
            parts.append(f"\n## p.{i}\n\n{text}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{edition}-{name.replace('·', '')}.md"
    out.write_text("\n".join(parts) + "\n", "utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="법제처 입안·심사 기준 수집기")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    logger = build_logger(LOG_DIR, "moleg")
    client = HttpClient(make_session(), logger)
    manifest_path = MOLEG_DIR / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest["source"] = "moleg.go.kr 간행물"
    manifest["phase_model"] = "수집→위키 raw (lawrag/pipeline/collect_moleg.py · data/wiki/raw/moleg)"

    MOLEG_DIR.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    for t in TARGETS:
        existing = manifest_item(manifest, t["name"])
        pdf_path = MOLEG_DIR / f"{t['edition']}-{t['name']}.pdf"
        if not args.force and existing and pdf_path.exists() \
                and sha256_file(pdf_path) == existing.get("sha256"):
            print(f"[{t['name']}] skipped (기존 파일 무결)")
            raw = to_raw_md(pdf_path, t["name"], t["edition"], t["page"])
            print(f"  위키 raw 갱신 → {raw.relative_to(REPO_ROOT)}")
            ok += 1
            continue
        try:
            resp = client.get(t["url"], headers={"Referer": t["page"]})
        except Exception as e:
            print(f"[{t['name']}] 실패: {e}", file=sys.stderr)
            failed += 1
            continue
        fmt = detect_format(resp.content[:256])
        if fmt != "pdf":
            print(f"[{t['name']}] PDF 가 아님({fmt}) — 게시판 주소가 바뀐 듯. "
                  f"{t['page']} 에서 재확인 필요", file=sys.stderr)
            failed += 1
            continue
        pdf_path.write_bytes(resp.content)
        raw = to_raw_md(pdf_path, t["name"], t["edition"], t["page"])
        upsert_item(manifest, {
            "name": t["name"], "kind": "moleg-standard", "label": t["name"],
            "edition": t["edition"], "url": t["url"],
            "file": str(pdf_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(pdf_path), "size": pdf_path.stat().st_size,
            "actual_format": "pdf",
            "wiki_raw": str(raw.relative_to(REPO_ROOT)), "status": "ok"})
        save_manifest(manifest_path, manifest)
        print(f"[{t['name']}] ok — {pdf_path.stat().st_size:,}B → "
              f"{raw.relative_to(REPO_ROOT)}")
        ok += 1

    print(f"\n완료: ok={ok} failed={failed} 요청수={client.request_count}")
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    sys.exit(main())
