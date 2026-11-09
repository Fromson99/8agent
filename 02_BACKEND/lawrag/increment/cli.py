"""증분 처리 명령줄.

  python -m lawrag.increment.cli --db <sqlite 파일 | oracle:<연결 JSON>> [--owner OWNER] <명령>

명령
  schema                       테이블 생성 (SQLite) / --print-ddl 로 Oracle DDL 출력
  ingest <xml>...              원문 XML 적재 → 비교 → PREVIEW / NO_CHANGE / BLOCKED (같은 파일 재실행은 그대로)
  ingest-manifest <manifest.json> [--targets 이름,...]
                               collect.py --source law 결과의 본문 XML과 별표 첨부 sha를 함께 적재
  preview <작업ID> [--html f]  신구조문 대비표 JSON/HTML과 승인용 해시
  relink <작업ID> <xml> OLD=NEW...  승인 전 수동 계보 연결 후 재비교
  approve <작업ID> --hash H --user U [--ack]
  reject <작업ID> --user U --reason R
  unblock <작업ID> --user U --reason R
  index <작업ID> [--external GOLD,VECTOR | --no-external]
  mark <작업ID> <종류> READY|FAILED [--count N] [--ref R]
  activate <작업ID> --user U
  status [작업ID]
  as-of <문서코드> <YYYYMMDD>

oracle 연결 JSON은 {"user","password","dsn"} 이며 0600 권한이어야 한다.
Dataiku에서는 이 CLI 대신 service.IncrementService(DataikuDatabase(SQLExecutor2(...)), owner=...)를 쓴다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from .db import OracleDatabase, SqliteDatabase
from .lawgo_parse import ParseError, attach_files, manifest_attachments, parse_lawgo_xml
from .preview import preview_hash, render_html
from .schema import ddl, new_words, oracle_comments
from .service import IncrementError, IncrementService


def _database(spec: str):
    if spec.startswith("oracle:"):
        path = Path(spec[len("oracle:"):])
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise SystemExit(f"연결 파일 권한이 너무 넓다 ({oct(mode)}) — chmod 600")
        import oracledb
        info = json.loads(path.read_text(encoding="utf-8"))
        return OracleDatabase(oracledb.connect(user=info["user"], password=info["password"], dsn=info["dsn"]))
    return SqliteDatabase(spec)


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lawrag.increment")
    ap.add_argument("--db", default=os.environ.get("LAW_INCREMENT_DB", ""))
    ap.add_argument("--owner", default=os.environ.get("LAW_INCREMENT_OWNER") or None)
    ap.add_argument("--today", help="기준일 KST YYYYMMDD (시험용)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("schema")
    p.add_argument("--print-ddl", choices=["oracle", "sqlite"])
    p = sub.add_parser("ingest")
    p.add_argument("xml", nargs="+")
    p = sub.add_parser("ingest-manifest")
    p.add_argument("manifest")
    p.add_argument("--targets")
    p = sub.add_parser("preview")
    p.add_argument("load_id")
    p.add_argument("--html")
    p = sub.add_parser("relink")
    p.add_argument("load_id")
    p.add_argument("xml")
    p.add_argument("pairs", nargs="+")
    for name in ("approve", "reject", "unblock"):
        p = sub.add_parser(name)
        p.add_argument("load_id")
        p.add_argument("--user", required=True)
        if name == "approve":
            p.add_argument("--hash", required=True)
            p.add_argument("--ack", action="store_true", help="강한 경고 확인")
        else:
            p.add_argument("--reason", required=True)
    p = sub.add_parser("index")
    p.add_argument("load_id")
    p.add_argument("--external", default="GOLD")
    p.add_argument("--no-external", action="store_true", help="Gold 게시 확인 없이 (개발 검증용)")
    p = sub.add_parser("mark")
    p.add_argument("load_id")
    p.add_argument("kind")
    p.add_argument("status", choices=["READY", "FAILED", "PENDING"])
    p.add_argument("--count", type=int)
    p.add_argument("--ref")
    p.add_argument("--error")
    p = sub.add_parser("activate")
    p.add_argument("load_id")
    p.add_argument("--user", required=True)
    p = sub.add_parser("status")
    p.add_argument("load_id", nargs="?")
    p = sub.add_parser("as-of")
    p.add_argument("doc_cd")
    p.add_argument("date")
    args = ap.parse_args(argv)

    if args.cmd == "schema" and args.print_ddl:
        statements = ddl(args.print_ddl, args.owner)
        if args.print_ddl == "oracle":
            statements += oracle_comments(args.owner)
        print(";\n\n".join(statements) + ";")
        print("\n-- 표준단어 확인·신청 후보 약어: " + ", ".join(new_words()))
        return 0
    if not args.db:
        raise SystemExit("--db 또는 LAW_INCREMENT_DB 필요")
    service = IncrementService(_database(args.db), owner=args.owner, today=args.today)
    try:
        if args.cmd == "schema":
            service.create_schema()
            _print({"created": True})
        elif args.cmd in ("ingest", "ingest-manifest"):
            out = []
            jobs = [(Path(x), {}) for x in getattr(args, "xml", [])]
            if args.cmd == "ingest-manifest":
                manifest_path = Path(args.manifest)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                wanted = {t.strip() for t in (args.targets or "").split(",") if t.strip()}
                for item in manifest.get("items") or ():
                    if wanted and item.get("name") not in wanted:
                        continue
                    if not item.get("body_file") or item.get("status") not in ("ok", "partial"):
                        out.append({"file": item.get("name"), "state": "SKIPPED", "error": item.get("error")})
                        continue
                    candidates = [manifest_path.parent / item["body_file"], Path(item["body_file"])]
                    body = next((c for c in candidates if c.is_file()), None)
                    if body is None:
                        out.append({"file": item["body_file"], "state": "FAILED", "step": "READ",
                                    "error": "본문 파일 없음"})
                        continue
                    jobs.append((body, manifest_attachments(item)))
            for path, files in jobs:
                raw = Path(path).read_bytes()
                try:
                    snapshot = parse_lawgo_xml(raw)
                except ParseError as exc:
                    out.append({"file": path, "state": "FAILED", "step": "PARSE", "error": str(exc),
                                "sha256": hashlib.sha256(raw).hexdigest()})
                    continue
                if files:
                    attach_files(snapshot, files)
                result = service.ingest(snapshot, source_name=Path(path).name)
                out.append({"file": path, "load_id": result.load_id, "doc_cd": result.doc_cd,
                            "state": result.state, "reused": result.reused,
                            "counts": result.gate.get("counts"), "stop": result.gate.get("stop_reason"),
                            "warnings": [w["code"] for w in result.gate.get("warnings", [])],
                            "preview_hash": result.preview_hash})
            _print(out)
            return 1 if any(o["state"] == "FAILED" for o in out) else 0
        elif args.cmd == "preview":
            preview = service.preview(args.load_id)
            digest = preview_hash(preview)
            if args.html:
                Path(args.html).write_text(render_html(preview, digest), encoding="utf-8")
            _print({"preview_hash": digest, "counts": preview["gate"]["counts"],
                    "warnings": preview["gate"]["warnings"], "html": args.html})
        elif args.cmd == "relink":
            raw = Path(args.xml).read_bytes()
            job = service.job(args.load_id)
            if job is None or hashlib.sha256(raw).hexdigest() != job["SRC_HASH_VALU"]:
                raise IncrementError("작업의 원문 sha와 파일이 다르다")
            forced = dict(pair.split("=", 1) for pair in args.pairs)
            result = service.ingest(parse_lawgo_xml(raw), source_name=Path(args.xml).name, forced=forced)
            _print({"state": result.state, "counts": result.gate.get("counts"),
                    "preview_hash": result.preview_hash})
        elif args.cmd == "approve":
            _print(service.approve(args.load_id, user=args.user, preview_digest=args.hash,
                                   acknowledge=args.ack)["PRCS_STTS_CD"])
        elif args.cmd == "reject":
            _print(service.reject(args.load_id, user=args.user, reason=args.reason)["PRCS_STTS_CD"])
        elif args.cmd == "unblock":
            _print(service.unblock(args.load_id, user=args.user, reason=args.reason)["PRCS_STTS_CD"])
        elif args.cmd == "index":
            external = () if args.no_external else tuple(x for x in args.external.split(",") if x)
            _print(service.prepare_index(args.load_id, external=external))
        elif args.cmd == "mark":
            service.mark_index(args.load_id, args.kind, status=args.status, count=args.count,
                               ref=args.ref, error=args.error)
            _print({"marked": args.kind, "status": args.status})
        elif args.cmd == "activate":
            _print(service.activate(args.load_id, user=args.user))
        elif args.cmd == "status":
            if args.load_id:
                _print({"job": service.job(args.load_id),
                        "index": service.db.query(f"SELECT IDX_KIND_CD, ARTC_KEY_VALU, IDX_STTS_CD FROM "
                                                  f"{service.t('IDX_WORK')} WHERE LOAD_WORK_ID=:id "
                                                  f"AND ARTC_KEY_VALU='*'", {"id": args.load_id})})
            else:
                _print(service.db.query(f"SELECT LOAD_WORK_ID, RGLT_DOC_CD, PRCS_STTS_CD, CHG_ASTM FROM "
                                        f"{service.t('LOAD_WORK')} ORDER BY CHG_ASTM DESC"))
        elif args.cmd == "as-of":
            rows = service.articles_as_of(args.doc_cd, args.date)
            _print([{k: r[k] for k in ("ARTC_KEY_VALU", "ENFC_STRT_DT", "ENFC_END_DT")} for r in rows])
    except IncrementError as exc:
        print(f"거절: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
