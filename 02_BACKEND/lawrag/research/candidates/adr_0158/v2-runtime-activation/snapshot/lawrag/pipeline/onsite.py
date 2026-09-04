"""프론트 없는 온사이트 운영 CLI.

    python -m lawrag.pipeline.onsite doctor --strict
    python -m lawrag.pipeline.onsite llm-check
    python -m lawrag.pipeline.onsite vector-check --query "설명의무"
    python -m lawrag.pipeline.onsite vector-sync
    python -m lawrag.pipeline.onsite process /mnt/incoming/A --folder 신규반입

모든 명령은 로컬 파일 또는 명시된 사내 URL만 사용한다. ``process``는 원본을
건드리지 않고 pipeline inbox로 복사한 다음 기존 batch 정본을 실행한다.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
ACCEPTED = (".xml", ".html", ".htm", ".hwp", ".hwpx", ".docx", ".pdf")
DEFAULT_STAGES = "ingest,structure,delegation,terms,embed,scopes"


def _emit(value: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    print("OK" if value.get("ok") else "FAIL", "-", value.get("summary", ""))
    for check in value.get("checks", []):
        print(f" {'✓' if check['ok'] else '✗'} {check['name']}: {check['detail']}")


def _is_private_url(value: str) -> bool:
    if not value:
        return False
    host = (urlparse(value).hostname or "").lower()
    allowed = {x.strip().lower() for x in os.environ.get("ONSITE_ALLOWED_HOSTS", "").split(",") if x.strip()}
    if host in allowed or host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(ipaddress.ip_address(address).is_private for address in addresses)


def doctor(strict: bool = False) -> dict:
    from lawrag.core import embedding, llm
    from lawrag.core.rag import vector

    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    llm_backend = llm.backend()
    llm_url = os.environ.get("LOCAL_LLM_URL") if llm_backend == "local" else os.environ.get("GENOS_LLM_URL", "")
    add("llm-config", llm.available(), f"backend={llm_backend}; url={llm_url or '-'}")
    if strict:
        add("llm-private-network", llm_backend in ("local", "genos") and _is_private_url(llm_url or ""),
            "local/genos + 사설 주소 또는 ONSITE_ALLOWED_HOSTS 필요")
    add("embedding", embedding.available(),
        f"backend={embedding.backend()}; model={os.environ.get('EMBED_MODEL', embedding.MODEL)}")
    vector_backend = vector.backend()
    if vector_backend == "qdrant":
        try:
            from lawrag.core.rag import qdrant_store
            status = qdrant_store.ping()
            add("vector-store", status["ok"] and status.get("ready", False),
                json.dumps(status, ensure_ascii=False))
            if strict:
                add("vector-private-network", _is_private_url(qdrant_store.url()), qdrant_store.url())
        except Exception as exc:  # noqa: BLE001
            add("vector-store", False, f"{type(exc).__name__}: {exc}")
    else:
        path = vector.sections_dir()
        add("vector-store", (path / "vectors.npz").exists() and (path / "meta.jsonl").exists(),
            f"backend=file; path={path}")
    for name, module in (("pdf", "fitz"), ("docx/hwp", "docling")):
        try:
            __import__(module)
            add(f"parser-{name}", True, module)
        except Exception as exc:  # noqa: BLE001
            add(f"parser-{name}", False, f"{type(exc).__name__}: {exc}")
    if strict:
        add("offline-flags",
            os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1",
            "HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1")
    ok = all(row["ok"] for row in checks)
    return {"ok": ok, "summary": f"온사이트 사전점검 {sum(x['ok'] for x in checks)}/{len(checks)}",
            "checks": checks}


def llm_check(log_path: str = "") -> dict:
    from lawrag.core import llm as llm_mod

    if not llm_mod.available():
        return {"ok": False, "summary": f"LLM 미설정: {llm_mod.MISSING_HINT}"}
    client = llm_mod.LLM()
    schema = {"type": "object", "properties": {"status": {"type": "string"}},
              "required": ["status"], "additionalProperties": False}
    result = client.structured("onsite.connection", "연결 확인용 요청이다.",
                               "status 값을 ok로 반환하라.", schema, max_tokens=64,
                               effort=None)
    if log_path:
        client.dump_log(log_path)
    return {"ok": bool(result and str(result.get("status", "")).lower() == "ok"),
            "summary": "로컬 LLM structured-output 연결 확인",
            "backend": client.backend, "model": client.model, "result": result,
            "usage": client.totals(), "log": log_path or None}


def vector_check(query: str = "") -> dict:
    from lawrag.core.rag import vector

    if vector.backend() == "qdrant":
        from lawrag.core.rag import qdrant_store
        status = qdrant_store.ping()
    else:
        index = vector.current()
        status = {"ok": index is not None, "backend": "file",
                  "path": str(vector.sections_dir()), "points": len(index.rows) if index else 0}
    hits = vector.search(query, topk=3, minimum=-1.0) if query and status.get("ok") else []
    ready = status.get("ready", status.get("ok"))
    return {"ok": bool(status.get("ok") and ready), "summary": "Vector DB 연결 확인",
            "status": status, "query": query or None, "hits": hits}


def vector_sync(recreate: bool = False) -> dict:
    from lawrag.core.rag import qdrant_store, vector

    result = qdrant_store.sync_from_files(vector.sections_dir(), recreate=recreate)
    return {"ok": True, "summary": "파일형 벡터 정본을 Qdrant에 동기화", **result}


def _source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in ACCEPTED else []
    return sorted(path for path in source.rglob("*")
                  if path.is_file() and path.suffix.lower() in ACCEPTED)


def _stage(source: Path, inbox: Path, folder: str) -> list[Path]:
    files = _source_files(source)
    if not files:
        raise ValueError(f"지원 파일이 없습니다 ({', '.join(ACCEPTED)}): {source}")
    target_root = inbox / (folder or "onsite")
    target_root.mkdir(parents=True, exist_ok=True)
    staged = []
    for path in files:
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != path.read_bytes():
            target = target.with_name(f"{int(path.stat().st_mtime_ns)}-{target.name}")
        if not target.exists():
            shutil.copy2(path, target)
        staged.append(target)
    return staged


def process(source: str, *, folder: str, stages: str, store: str = "",
            pipeline_dir: str = "", inbox: str = "", workers: int | None = None) -> dict:
    if store:
        os.environ["STRUCTURE_STORE"] = str(Path(store).resolve())
    if pipeline_dir:
        os.environ["PIPELINE_DIR"] = str(Path(pipeline_dir).resolve())
    if inbox:
        os.environ["PIPELINE_INBOX"] = str(Path(inbox).resolve())
    from lawrag.core import batch
    from lawrag.core.llm import DEFAULT_MODEL, LLM, available as llm_available

    selected = [x.strip() for x in stages.split(",") if x.strip()]
    unknown = [x for x in selected if x not in batch.STAGES]
    if unknown:
        raise ValueError(f"모르는 단계: {', '.join(unknown)}")
    if "frames" in selected and llm_available():
        model = LLM().model
        if model != DEFAULT_MODEL:
            raise ValueError(f"제품 context를 만드는 frames는 {DEFAULT_MODEL}만 허용됩니다; 현재 {model}")
    staged = _stage(Path(source).expanduser().resolve(), batch.inbox_path(), folder)
    options = {"workers": workers} if workers else {}
    started = batch.RUNNER.start(selected, options)
    while batch.RUNNER.is_running():
        time.sleep(0.2)
    status = batch.RUNNER.status()
    return {"ok": status.get("status") == "done", "summary": "헤드리스 파일 파이프라인 완료",
            "source": str(Path(source).resolve()), "staged": [str(x) for x in staged],
            "run_id": started["run_id"], "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="온사이트/폐쇄망 운영 CLI")
    parser.add_argument("--json", action="store_true", help="기계 판독 JSON 출력")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor", help="설정·의존성·사설망 사전점검")
    d.add_argument("--strict", action="store_true", help="외부망 차단 플래그와 사설 URL까지 검사")
    lc = sub.add_parser("llm-check", help="structured-output 실제 연결 확인")
    lc.add_argument("--log", default="", help="요청·응답 로그 JSON 경로")
    vc = sub.add_parser("vector-check", help="파일/Qdrant 벡터 저장소 연결 확인")
    vc.add_argument("--query", default="", help="선택: 실제 임베딩+검색 smoke 질의")
    vs = sub.add_parser("vector-sync", help="파일형 벡터 정본을 Qdrant로 upsert")
    vs.add_argument("--recreate", action="store_true", help="대상 collection을 재생성")
    p = sub.add_parser("process", help="파일/디렉터리를 inbox에 복사하고 파이프라인 실행")
    p.add_argument("source", help="새 파일 하나 또는 디렉터리(A 위치)")
    p.add_argument("--folder", default="onsite", help="스토어 폴더 라벨")
    p.add_argument("--stages", default=DEFAULT_STAGES,
                   help=f"쉼표 구분 단계(기본 {DEFAULT_STAGES}; LLM frames는 명시 추가)")
    p.add_argument("--store", default="", help="STRUCTURE_STORE 재정의")
    p.add_argument("--pipeline-dir", default="", help="파이프라인 상태/로그 경로")
    p.add_argument("--inbox", default="", help="staging inbox 경로")
    p.add_argument("--workers", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor(args.strict)
        elif args.command == "llm-check":
            result = llm_check(args.log)
        elif args.command == "vector-check":
            result = vector_check(args.query)
        elif args.command == "vector-sync":
            result = vector_sync(args.recreate)
        else:
            result = process(args.source, folder=args.folder, stages=args.stages,
                             store=args.store, pipeline_dir=args.pipeline_dir,
                             inbox=args.inbox, workers=args.workers)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "summary": f"{type(exc).__name__}: {exc}"}
    _emit(result, args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
