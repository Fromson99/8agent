"""규정 문서 수집기 — 공통 파이프라인 CLI.

    python collect.py --source kofia --dry-run     # 받을 파일 목록만 출력
    python collect.py --source kofia               # 수집 (재실행 시 멱등 skip)
    python collect.py --source kofia --force       # 멱등성 무시하고 재수집
    python collect.py --source kofia --extra-target "이름:seq값"   # 오류 주입 등 임시 대상

동작 계약 (claude_task/Task_law_crawler.md §8):
- 멱등: manifest 의 파일이 모두 존재하고 해시가 맞으면 네트워크 요청 없이 skip
- 부분 실패 허용: 한 문서 실패는 status=error 기록 후 계속
- 차단 감지(CrawlAborted)만 전체 중단
- 원문 보존: 변환 없음, 매직바이트로 actual_format 판정, sha256 기록
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sources import ADAPTERS
from sources.base import DocumentRef, FetchResult, Target
from sources.common import (
    CrawlAborted,
    FetchError,
    build_logger,
    decode_disposition_filename,
    detect_format,
    item_files_intact,
    load_manifest,
    manifest_item,
    safe_filename,
    save_manifest,
    sha256_file,
    upsert_item,
)

REPO_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = REPO_ROOT / "corpus"
LOG_DIR = REPO_ROOT / "logs"

# 수집 대상 선언 (docs/adapter_design.md 결정사항 반영)
TARGETS: dict[str, list[Target]] = {
    "kofia": [
        Target("kofia", "표준투자권유준칙", "표준투자권유준칙"),
        Target("kofia", "증권 인수업무 등에 관한 규정", "증권 인수업무 등에 관한 규정"),
        Target("kofia", "대표주관업무 등 모범기준", "대표주관업무 등 모범기준"),
        # "금투협 모범규준" = 모범규준 분류(seq=3) 전체 — 구성원으로 전개된다
        Target("kofia", "모범규준(분류)", "모범규준", hints={"folder_seq": "3"}),
    ],
}

SOURCE_LABELS = {"kofia": "law.kofia.or.kr"}


def fetch_ref(client, ref: DocumentRef, dest_dir: Path) -> FetchResult:
    """단일 문서 다운로드 + 검증 + 저장. 실패는 FetchResult(status=error)로 돌려준다."""
    try:
        resp = client.request(ref.method, ref.url, data=ref.data, headers=ref.headers)
    except FetchError as e:
        return FetchResult(status="error", error=str(e))

    if resp.status_code != 200:
        return FetchResult(status="error", error=f"HTTP {resp.status_code}")

    body = resp.content
    fmt = detect_format(body[:256])
    if not body:
        return FetchResult(status="error", error="빈 응답")
    # 기대가 파일인데 HTML 이 오면 에러페이지다 (200 위장 — 실측)
    if ref.file_ext != ".html" and fmt == "html":
        return FetchResult(status="error", error=f"파일 대신 HTML 응답 (에러페이지 추정): {ref.url}")

    cd_raw = resp.headers.get("Content-Disposition")
    name = decode_disposition_filename(cd_raw)
    if not name or not safe_filename(name, ""):
        name = ref.title + ref.file_ext
    filename = safe_filename(name)

    out_dir = dest_dir / ref.subdir if ref.subdir else dest_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(body)

    return FetchResult(
        status="ok", file=path, sha256=sha256_file(path), actual_format=fmt,
        size=len(body), content_disposition_raw=cd_raw,
    )


def collect_target(adapter, client, target: Target, source_dir: Path,
                   dry_run: bool) -> dict:
    """대상 하나 처리 → manifest 항목 반환. CrawlAborted 는 위로 전파."""
    item: dict = {
        "doc_no": target.hints.get("seq", ""),
        "label": target.label,
        "kind": f"{target.source_id}-rule",
        "name": target.key,
        "enforce": "",          # 시행일 필드가 없는 소스는 빈 값으로 둔다 (조작 금지)
        "attachments": [],
        "status": "error",
    }
    try:
        refs = adapter.discover(target)
    except FetchError as e:
        item["error"] = f"discover 실패: {e}"
        return item
    except RuntimeError as e:
        item["error"] = str(e)
        return item

    meta = adapter.metadata(target)
    item["doc_no"] = meta.get("seq", item["doc_no"])
    item.update({k: meta[k] for k in ("history_seq", "revised", "rev_kind", "dept") if k in meta})

    if dry_run:
        item["status"] = "dry-run"
        print(f"\n[{target.key}] 받을 파일 {len(refs)}건:")
        for ref in refs:
            sub = f"{ref.subdir}/" if ref.subdir else ""
            print(f"  {ref.role:17s} {sub}{ref.title}  <- {ref.url}")
        return item

    dest_dir = source_dir / safe_filename(target.key)
    errors: list[str] = []
    for ref in refs:
        result = fetch_ref(client, ref, dest_dir)
        rel = str(result.file.relative_to(REPO_ROOT)) if result.file else None
        entry = {
            "title": ref.title, "role": ref.role, "url": ref.url,
            "version_hint": ref.version_hint, "file": rel,
            "sha256": result.sha256, "actual_format": result.actual_format,
            "size": result.size, "content_disposition_raw": result.content_disposition_raw,
        }
        if result.status != "ok":
            entry["error"] = result.error
            errors.append(f"{ref.title}: {result.error}")
            item["attachments"].append(entry)
            continue
        if ref.role == "body" and ref.file_ext == ".hwp":
            item["body_file"], item["body_sha256"] = rel, result.sha256
            item["body_format"] = result.actual_format
        elif ref.role == "body" and ref.file_ext == ".html":
            item["body_html_file"], item["body_html_sha256"] = rel, result.sha256
        else:
            item["attachments"].append(entry)

    if errors and not item.get("body_file"):
        # 전문 HWP 가 없어도(일부 규정은 서버가 행업으로 응답) 조문 HTML 을 확보했다면
        # 본문은 있는 것이다 — 실패 사유는 그대로 남긴다
        item["status"] = "partial" if item.get("body_html_file") else "error"
        item["error"] = "; ".join(errors)
    elif errors:
        item["status"] = "partial"
        item["error"] = "; ".join(errors)
    else:
        item["status"] = "ok"
    return item


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="규정 문서 수집기")
    ap.add_argument("--source", required=True, choices=sorted(ADAPTERS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--targets", help="쉼표 구분 대상 key 필터")
    ap.add_argument("--extra-target", action="append", default=[],
                    metavar="이름:seq", help="임시 대상 추가 (오류 주입 테스트용)")
    args = ap.parse_args(argv)

    logger = build_logger(LOG_DIR, args.source)
    adapter = ADAPTERS[args.source](logger)
    client = adapter.client

    targets = list(TARGETS[args.source])
    for spec in args.extra_target:
        name, _, seq = spec.partition(":")
        targets.append(Target(args.source, name, name, hints={"seq": seq} if seq else {}))
    if args.targets:
        wanted = {t.strip() for t in args.targets.split(",")}
        targets = [t for t in targets if t.key in wanted]

    source_dir = CORPUS_DIR / args.source
    manifest_path = source_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest["source"] = SOURCE_LABELS.get(args.source, args.source)

    # 폴더형 대상 전개 + key 기준 중복 제거 (모범규준 분류에 이미 포함된 개별 대상)
    expanded: list[Target] = []
    seen_keys: set[str] = set()
    aborted = False
    for target in targets:
        try:
            members = adapter.expand_targets(target)
        except CrawlAborted:
            raise
        except (FetchError, RuntimeError) as e:
            print(f"[{target.key}] 대상 전개 실패: {e}", file=sys.stderr)
            continue
        for member in members:
            if member.key not in seen_keys:
                seen_keys.add(member.key)
                expanded.append(member)

    ok = skipped = failed = 0
    try:
        for target in expanded:
            existing = manifest_item(manifest, target.key)
            if not args.force and existing and item_files_intact(existing, REPO_ROOT):
                print(f"[{target.key}] skipped (기존 파일 무결)")
                skipped += 1
                continue
            item = collect_target(adapter, client, target, source_dir, args.dry_run)
            if not args.dry_run:
                upsert_item(manifest, item)
                save_manifest(manifest_path, manifest)   # 대상 단위로 저장 — 중단돼도 진행분 보존
            if item["status"] in ("ok", "dry-run"):
                ok += 1
            elif item["status"] == "partial":
                ok += 1
                print(f"[{target.key}] 부분 실패: {item.get('error')}", file=sys.stderr)
            else:
                failed += 1
                print(f"[{target.key}] 실패: {item.get('error')}", file=sys.stderr)
    except CrawlAborted as e:
        aborted = True
        print(f"\n!! 차단 감지 — 전체 중단: {e}", file=sys.stderr)
        print("!! 재시도 전략을 임의로 바꾸지 말 것. 시간을 두고 원인 확인 후 재실행.", file=sys.stderr)

    print(f"\n완료: ok={ok} skipped={skipped} failed={failed}"
          f" 요청수={client.request_count}{' (중단됨)' if aborted else ''}")
    return 2 if aborted else (1 if failed and not ok else 0)


if __name__ == "__main__":
    sys.exit(main())
