"""규정 문서 수집기 — 공통 파이프라인 CLI.

    python -m lawrag.pipeline.collect --source kofia --dry-run     # 받을 파일 목록만 출력
    python -m lawrag.pipeline.collect --source kofia               # 수집 (재실행 시 멱등 skip)
    python -m lawrag.pipeline.collect --source kofia --force       # 멱등성 무시하고 재수집
    python -m lawrag.pipeline.collect --source kofia --extra-target "이름:seq값"   # 오류 주입 등 임시 대상

동작 계약 (docs/tasks/Task_law_crawler.md §8):
- 멱등: manifest 의 파일이 모두 존재하고 해시가 맞으면 네트워크 요청 없이 skip
- 부분 실패 허용: 한 문서 실패는 status=error 기록 후 계속
- 차단 감지(CrawlAborted)만 전체 중단
- 원문 보존: 변환 없음, 매직바이트로 actual_format 판정, sha256 기록
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lawrag.sources import ADAPTERS
from lawrag.sources.base import DocumentRef, FetchResult, Target
from lawrag.sources.common import (
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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
LOG_DIR = REPO_ROOT / "var" / "logs"

# 수집 대상 선언 (docs/adapter_design.md 결정사항 반영)
TARGETS: dict[str, list[Target]] = {
    "kofia": [
        Target("kofia", "표준투자권유준칙", "표준투자권유준칙"),
        Target("kofia", "증권 인수업무 등에 관한 규정", "증권 인수업무 등에 관한 규정"),
        Target("kofia", "대표주관업무 등 모범기준", "대표주관업무 등 모범기준"),
        Target("kofia", "금융투자회사의 영업 및 업무에 관한 규정",
               "금융투자회사의 영업 및 업무에 관한 규정"),
        Target("kofia", "금융투자회사의 영업 및 업무에 관한 규정 시행세칙",
               "금융투자회사의 영업 및 업무에 관한 규정 시행세칙"),
        # "금투협 모범규준" = 모범규준 분류(seq=3) 전체 — 구성원으로 전개된다
        Target("kofia", "모범규준(분류)", "모범규준", hints={"folder_seq": "3"}),
    ],
    # 법령·행정규칙 — 국가법령정보센터 OPEN API (별표·서식 HWP 는 본문 XML 에서 전개)
    # 명칭은 공식 명칭 완전일치가 필요하다 (자본시장법→자본시장과 금융투자업에 관한 법률 등
    # 약칭 불가 — 2026-08-12 lawSearch 실측으로 전건 검증)
    "law": [
        Target("law", "자본시장과 금융투자업에 관한 법률",
               "자본시장과 금융투자업에 관한 법률", hints={"kind": "law"}),
        Target("law", "자본시장과 금융투자업에 관한 법률 시행령",
               "자본시장과 금융투자업에 관한 법률 시행령", hints={"kind": "law"}),
        Target("law", "자본시장과 금융투자업에 관한 법률 시행규칙",
               "자본시장과 금융투자업에 관한 법률 시행규칙", hints={"kind": "law"}),
        Target("law", "외국환거래법", "외국환거래법", hints={"kind": "law"}),
        Target("law", "외국환거래법 시행령", "외국환거래법 시행령", hints={"kind": "law"}),
        Target("law", "상법", "상법", hints={"kind": "law"}),
        # 위임 체인 중간 공백 보충 (2026-08-13 lsStmd 체계도 실측 — 법률은 보유,
        # 시행령이 없어 법률→규정 위임 간선이 끊기던 4건. 명칭은 체계도 XML 원문)
        Target("law", "상법 시행령", "상법 시행령", hints={"kind": "law"}),
        Target("law", "신용정보의 이용 및 보호에 관한 법률 시행령",
               "신용정보의 이용 및 보호에 관한 법률 시행령", hints={"kind": "law"}),
        Target("law", "공공기관의 운영에 관한 법률 시행령",
               "공공기관의 운영에 관한 법률 시행령", hints={"kind": "law"}),
        # 금융복합기업집단법
        Target("law", "금융복합기업집단의 감독에 관한 법률",
               "금융복합기업집단의 감독에 관한 법률", hints={"kind": "law"}),
        Target("law", "금융복합기업집단의 감독에 관한 법률 시행령",
               "금융복합기업집단의 감독에 관한 법률 시행령", hints={"kind": "law"}),
        # 금소법 — 업로드본(비공식 표기)을 지우고 공식 수집으로 대체 (2026-08-13)
        Target("law", "금융소비자 보호에 관한 법률",
               "금융소비자 보호에 관한 법률", hints={"kind": "law"}),
        Target("law", "금융소비자 보호에 관한 법률 시행령",
               "금융소비자 보호에 관한 법률 시행령", hints={"kind": "law"}),
        Target("law", "금융소비자 보호에 관한 감독규정",
               "금융소비자 보호에 관한 감독규정", hints={"kind": "admrul"}),
        # 금융사지배구조법
        Target("law", "금융회사의 지배구조에 관한 법률",
               "금융회사의 지배구조에 관한 법률", hints={"kind": "law"}),
        Target("law", "금융회사의 지배구조에 관한 법률 시행령",
               "금융회사의 지배구조에 관한 법률 시행령", hints={"kind": "law"}),
        # 신용정보법
        Target("law", "신용정보의 이용 및 보호에 관한 법률",
               "신용정보의 이용 및 보호에 관한 법률", hints={"kind": "law"}),
        Target("law", "개인정보 보호법", "개인정보 보호법", hints={"kind": "law"}),
        Target("law", "개인정보 보호법 시행령", "개인정보 보호법 시행령",
               hints={"kind": "law"}),
        # 공공기관운영법
        Target("law", "공공기관의 운영에 관한 법률",
               "공공기관의 운영에 관한 법률", hints={"kind": "law"}),
        # 쟁점 카드가 조문 후보로 지목하는데 코퍼스에 없던 법 (2026-08-16)
        # — 카드는 법제처 해석례에서 정확히 인용했는데 창고가 비어 좌표 해소가
        # 실패했다(조문 후보 41개 중 4개). 「다른 법률의 특별한 규정」·「두 법의
        # 관문」류 쟁점은 금융 밖 법률을 가리킬 수밖에 없다.
        Target("law", "국세기본법", "국세기본법", hints={"kind": "law"}),
        Target("law", "공공기관의 정보공개에 관한 법률",
               "공공기관의 정보공개에 관한 법률", hints={"kind": "law"}),
        Target("law", "국가를 당사자로 하는 계약에 관한 법률",
               "국가를 당사자로 하는 계약에 관한 법률", hints={"kind": "law"}),
        Target("law", "중소기업기본법", "중소기업기본법", hints={"kind": "law"}),
        # CM본부 골든(from_samsung, 2026-08-19)이 인용하는데 스토어에 없던 8건 —
        # 스톡옵션·주식평가·상장차익 과세 축. 공식 명칭 완전일치 (lawSearch 규약).
        Target("law", "벤처기업육성에 관한 특별법", "벤처기업육성에 관한 특별법",
               hints={"kind": "law"}),
        Target("law", "벤처기업육성에 관한 특별법 시행령",
               "벤처기업육성에 관한 특별법 시행령", hints={"kind": "law"}),
        Target("law", "상속세 및 증여세법", "상속세 및 증여세법", hints={"kind": "law"}),
        Target("law", "상속세 및 증여세법 시행령", "상속세 및 증여세법 시행령",
               hints={"kind": "law"}),
        Target("law", "조세특례제한법", "조세특례제한법", hints={"kind": "law"}),
        Target("law", "소득세법", "소득세법", hints={"kind": "law"}),
        Target("law", "소득세법 시행령", "소득세법 시행령", hints={"kind": "law"}),
        Target("law", "중소기업창업 지원법 시행령", "중소기업창업 지원법 시행령",
               hints={"kind": "law"}),
        # 공정거래법
        Target("law", "독점규제 및 공정거래에 관한 법률",
               "독점규제 및 공정거래에 관한 법률", hints={"kind": "law"}),
        Target("law", "독점규제 및 공정거래에 관한 법률 시행령",
               "독점규제 및 공정거래에 관한 법률 시행령", hints={"kind": "law"}),
        # 공시 갈래 — 위임 미보유 3위(간선 117)가 가리키던 고시 (2026-08-13)
        Target("law", "증권의 발행 및 공시 등에 관한 규정",
               "증권의 발행 및 공시 등에 관한 규정", hints={"kind": "admrul"}),
        Target("law", "증권의 발행 및 공시 등에 관한 규정 시행세칙",
               "증권의 발행 및 공시 등에 관한 규정 시행세칙", hints={"kind": "admrul"}),
        # 외감법군 — 별도 가족 (법률→시행령→외부감사규정→세칙)
        Target("law", "주식회사 등의 외부감사에 관한 법률",
               "주식회사 등의 외부감사에 관한 법률", hints={"kind": "law"}),
        Target("law", "주식회사 등의 외부감사에 관한 법률 시행령",
               "주식회사 등의 외부감사에 관한 법률 시행령", hints={"kind": "law"}),
        Target("law", "외부감사 및 회계 등에 관한 규정",
               "외부감사 및 회계 등에 관한 규정", hints={"kind": "admrul"}),
        Target("law", "외부감사 및 회계 등에 관한 규정 시행세칙",
               "외부감사 및 회계 등에 관한 규정 시행세칙", hints={"kind": "admrul"}),
        Target("law", "금융투자업규정", "금융투자업규정", hints={"kind": "admrul"}),
        Target("law", "금융투자업규정시행세칙", "금융투자업규정시행세칙",
               hints={"kind": "admrul"}),
        Target("law", "외국환거래규정", "외국환거래규정", hints={"kind": "admrul"}),
        Target("law", "금융복합기업집단 감독규정", "금융복합기업집단 감독규정",
               hints={"kind": "admrul"}),
        Target("law", "금융회사 지배구조 감독규정", "금융회사 지배구조 감독규정",
               hints={"kind": "admrul"}),
        Target("law", "금융회사 지배구조 감독규정 시행세칙",
               "금융회사 지배구조 감독규정 시행세칙", hints={"kind": "admrul"}),
        Target("law", "전자금융감독규정", "전자금융감독규정", hints={"kind": "admrul"}),
        Target("law", "전자금융감독규정시행세칙", "전자금융감독규정시행세칙",
               hints={"kind": "admrul"}),
        Target("law", "금융기관의 업무위탁 등에 관한 규정",
               "금융기관의 업무위탁 등에 관한 규정", hints={"kind": "admrul"}),
        Target("law", "은행업감독업무시행세칙", "은행업감독업무시행세칙",
               hints={"kind": "admrul"}),
    ],
    # 상장 규정 — 규정·시행세칙 쌍을 3개 시장 전부 (별표·별지서식은 어댑터가 함께 찾는다)
    "krx": [
        Target("krx", "유가증권시장 상장규정", "유가증권시장 상장규정"),
        Target("krx", "유가증권시장 상장규정 시행세칙", "유가증권시장 상장규정 시행세칙"),
        Target("krx", "코스닥시장 상장규정", "코스닥시장 상장규정"),
        Target("krx", "코스닥시장 상장규정 시행세칙", "코스닥시장 상장규정 시행세칙"),
        Target("krx", "코넥스시장 상장규정", "코넥스시장 상장규정"),
        Target("krx", "코넥스시장 상장규정 시행세칙", "코넥스시장 상장규정 시행세칙"),
    ],
}

SOURCE_LABELS = {"kofia": "law.kofia.or.kr", "krx": "rule.krx.co.kr",
                 "law": "law.go.kr OPEN API"}


def fetch_ref(client, ref: DocumentRef, dest_dir: Path,
              taken: set[Path] | None = None) -> FetchResult:
    """단일 문서 다운로드 + 검증 + 저장. 실패는 FetchResult(status=error)로 돌려준다.

    taken: 이번 대상에서 이미 쓴 경로 — 서버가 다른 파일에 같은 Content-Disposition
    이름을 주는 경우가 실재한다(KRX 별지서식 3건이 전부 '…_별표.hwp'). 충돌 시
    ' (2)', ' (3)' 을 붙여 덮어쓰기를 막는다.
    """
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
    if taken is not None:
        n = 2
        while path in taken:
            stem, dot, ext = filename.rpartition(".")
            path = out_dir / (f"{stem} ({n}).{ext}" if dot else f"{filename} ({n})")
            n += 1
        taken.add(path)
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
    item.update({k: meta[k] for k in ("kind", "history_seq", "revised", "rev_kind",
                                      "enforce", "promul_no", "dept") if k in meta})

    if dry_run:
        item["status"] = "dry-run"
        print(f"\n[{target.key}] 받을 파일 {len(refs)}건:")
        for ref in refs:
            sub = f"{ref.subdir}/" if ref.subdir else ""
            print(f"  {ref.role:17s} {sub}{ref.title}  <- {ref.url}")
        return item

    dest_dir = source_dir / safe_filename(target.key)
    errors: list[str] = []
    taken: set[Path] = set()
    for ref in refs:
        result = fetch_ref(client, ref, dest_dir, taken)
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
        if ref.role == "body" and ref.file_ext in (".hwp", ".xml"):
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
