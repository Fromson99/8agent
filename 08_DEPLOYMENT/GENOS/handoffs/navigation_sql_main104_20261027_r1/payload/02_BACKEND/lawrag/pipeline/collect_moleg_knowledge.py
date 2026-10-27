"""법제처 법령지식 API를 재개 가능한 DatasetPackage v2로 수집한다.

준비 확인(네트워크/키 불필요):
    PYTHONPATH=02_BACKEND .venv/bin/python -m lawrag.pipeline.collect_moleg_knowledge --list-endpoints
    PYTHONPATH=02_BACKEND .venv/bin/python -m lawrag.pipeline.collect_moleg_knowledge --dry-run

전체 목록 수집(OC는 파일이나 명령행에 넣지 않는다):
    export LAW_OC='등록한 이메일 ID'
    PYTHONPATH=02_BACKEND .venv/bin/python -m lawrag.pipeline.collect_moleg_knowledge

질의형 API 예시:
    PYTHONPATH=02_BACKEND .venv/bin/python -m lawrag.pipeline.collect_moleg_knowledge \
      --endpoint legal_term_relations --param query=금융투자업자

완성 패키지는 01_DATA/PACKAGES/EXTERNAL 아래에 생성된다. 중단 상태는
90_RUNTIME/moleg_knowledge에 남고 같은 명령을 다시 실행하면 다음 페이지부터 잇는다.
"""
from __future__ import annotations

import argparse
import fcntl
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Mapping

from lawrag.datasets.catalog import load_package
from lawrag.platform.paths import repository_root, runtime_path
from lawrag.sources.common import HttpClient, build_logger, make_session
from lawrag.sources.moleg_knowledge import (
    ENDPOINTS,
    MolegKnowledgeClient,
    parse_xml_page,
    public_request_plan,
    catalog_identity,
)


DEFAULT_ENDPOINTS = ("legal_terms", "knowledge_terms", "everyday_terms")
COMPILER_PROFILE = "moleg-knowledge-collector-v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _code_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=False,
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "unversioned-workspace"


def parse_params(rows: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for row in rows:
        key, separator, value = row.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"--param은 NAME=VALUE 형식이어야 합니다: {row!r}")
        if key.strip().upper() == "OC":
            raise ValueError("OC는 --param이 아니라 환경변수로만 전달하십시오")
        if key.strip() in values:
            raise ValueError(f"중복 파라미터: {key.strip()}")
        values[key.strip()] = value.strip()
    return values


def _resume_key(endpoint: str, values: Mapping[str, str], display: int) -> str:
    return f"{endpoint}-{_digest({'parameters': dict(values), 'display': display, 'collector': 'verified-pages-v2'})[:16]}"


def _load_checkpoint(path: Path, plan: dict[str, object]) -> dict[str, object]:
    if not path.exists():
        now = datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": "moleg-knowledge-checkpoint-v1",
            "plan_sha256": _digest(plan),
            "next_page": 1,
            "total_count": None,
            "page_count": None,
            "record_count": 0,
            "completed": False,
            "raw_hashes": {},
            "started_at": now,
            "updated_at": now,
        }
    checkpoint = json.loads(path.read_text("utf-8"))
    if checkpoint.get("plan_sha256") != _digest(plan):
        raise RuntimeError("재개 상태와 현재 호출 계획이 다릅니다")
    return checkpoint


def _collect_endpoint_unlocked(client: MolegKnowledgeClient, endpoint: str,
                      values: Mapping[str, str], display: int, max_pages: int,
                      root: Path, snapshot: str = 'initial') -> tuple[Path | None, dict[str, object]]:
    spec = ENDPOINTS[endpoint]
    plan = public_request_plan(endpoint, values, display=display)
    scope = _resume_key(endpoint, values, display)
    work = runtime_path("moleg_knowledge", snapshot, scope)
    raw = work / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    checkpoint_path = work / "checkpoint.json"
    checkpoint = _load_checkpoint(checkpoint_path, plan)
    for filename, expected in checkpoint['raw_hashes'].items():
        if Path(filename).name != filename or not (raw / filename).is_file() or _hash_file(raw / filename) != expected:
            raise RuntimeError('수집한 페이지가 누락되거나 변경되었습니다')
    first_page = int(checkpoint["next_page"])
    page = first_page
    fetched_this_run = 0

    if not checkpoint.get("completed"):
        while True:
            raw_path = raw / f"page-{page:06d}.xml"
            existed = raw_path.exists()
            if existed:
                xml_text = raw_path.read_text('utf-8')
                parsed = parse_xml_page(xml_text, spec, requested_page=page, requested_display=display)
            else:
                xml_text, parsed = client.fetch(endpoint, values, page=page, display=display)
            if spec.paged:
                if parsed.page != page:
                    raise RuntimeError('응답 페이지가 요청과 다릅니다')
                if checkpoint['total_count'] is not None and checkpoint['total_count'] != parsed.total_count:
                    raise RuntimeError('수집 중 총건수가 변경되었습니다; 새 snapshot으로 재시작하십시오')
                expected_rows = min(display, max(0, parsed.total_count - (page - 1) * display))
                if len(parsed.records) != expected_rows:
                    raise RuntimeError('페이지 레코드 수가 총건수와 일치하지 않습니다')
            if not existed:
                temporary = raw_path.with_suffix('.xml.tmp')
                temporary.write_text(xml_text, encoding='utf-8')
                os.replace(temporary, raw_path)
            page_count = max(1, (parsed.total_count + display - 1) // display) if spec.paged else 1
            is_complete = not spec.paged or page >= page_count
            checkpoint['raw_hashes'][raw_path.name] = _hash_file(raw_path)
            checkpoint.update(
                next_page=page + 1,
                total_count=parsed.total_count,
                page_count=page_count,
                record_count=int(checkpoint.get("record_count") or 0) + len(parsed.records),
                completed=is_complete,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            _atomic_json(checkpoint_path, checkpoint)
            if page == 1 or page % 25 == 0 or is_complete:
                print(f'{endpoint}: {page}/{page_count} 페이지, {checkpoint["record_count"]}행', flush=True)
            fetched_this_run += 1
            if is_complete:
                break
            if max_pages and fetched_this_run >= max_pages:
                return None, checkpoint
            page += 1

    normalized = work / "records.jsonl"
    record_count, identities = 0, {}
    duplicates = []
    with normalized.open("w", encoding="utf-8") as stream:
        for raw_path in sorted(raw.glob("page-*.xml")):
            requested_page = int(raw_path.stem.rsplit("-", 1)[-1])
            parsed = parse_xml_page(raw_path.read_text("utf-8"), spec,
                                    requested_page=requested_page,
                                    requested_display=display)
            for row_number, record in enumerate(parsed.records, 1):
                record_count += 1
                if endpoint in DEFAULT_ENDPOINTS:
                    identity = catalog_identity(record)
                    if not record['source_id']:
                        raise RuntimeError('목록의 원천 ID가 없습니다')
                    signature = _digest(record)
                    if identity in identities:
                        previous_page, previous_row, previous_hash = identities[identity]
                        if (endpoint != 'legal_terms' or previous_page != raw_path.name
                                or previous_hash != signature):
                            raise RuntimeError('목록의 원천 ID가 중복되거나 내용이 충돌합니다')
                        duplicates.append({'page': raw_path.name, 'row': row_number,
                                           'first_row': previous_row, 'record_sha256': signature})
                        continue
                    identities[identity] = (raw_path.name, row_number, signature)
                stream.write(json.dumps(record, ensure_ascii=False,
                                        sort_keys=True, separators=(",", ":")) + "\n")
    if record_count != checkpoint['record_count'] or (spec.paged and record_count != checkpoint['total_count']):
        raise RuntimeError('전체 목록 검증 실패; 패키지를 발행하지 않습니다')
    plan_path = work / "request-plan.json"
    _atomic_json(plan_path, {
        "schema_version": "moleg-knowledge-request-plan-v1",
        **plan,
        "source_url": spec.url,
        "commercial_reuse": "permission-not-confirmed",
        "export_default": False,
        "checkpoint": checkpoint,
        "normalization": {"identity_policy": "official-id-with-legal-term-variant-v1",
                          "raw_record_count": record_count,
                          "normalized_record_count": record_count - len(duplicates),
                          "exact_same_page_duplicates": duplicates},
    })
    package = _publish(root, endpoint, work, plan_path, normalized)
    return package, checkpoint


def _collect_endpoint(client, endpoint, values, display, max_pages, root, snapshot='initial'):
    if not snapshot or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in snapshot):
        raise ValueError('snapshot은 영문·숫자·밑줄·하이픈만 허용합니다')
    work = runtime_path('moleg_knowledge', snapshot, _resume_key(endpoint, values, display))
    work.mkdir(parents=True, exist_ok=True)
    with (work / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _collect_endpoint_unlocked(client, endpoint, values, display, max_pages, root, snapshot)


def _publish(root: Path, endpoint: str, work: Path, plan_path: Path,
             normalized: Path) -> Path:
    source_files = [plan_path, normalized, *([work / "scope.sqlite"] if (work / "scope.sqlite").is_file() else []), *sorted((work / "raw").glob("*.xml")), *sorted((work / "raw").glob("*.xml.gz"))]
    seed = _digest([{"name": path.relative_to(work).as_posix(),
                     "sha256": _hash_file(path)} for path in source_files])
    endpoint_id = endpoint.replace("_", "-")
    package_id = f"moleg-knowledge-{endpoint_id}-{seed[:16]}"
    generation_id = f"gen-{seed[:24]}"
    final = root / "01_DATA" / "PACKAGES" / "EXTERNAL" / package_id / generation_id
    manifest_path = final / "manifest.json"
    if final.exists():
        load_package(manifest_path, verify_files=True)
        return manifest_path
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{generation_id}.", dir=final.parent))
    try:
        artifacts: list[dict[str, object]] = []
        for position, source in enumerate(source_files):
            relative = Path("ARTIFACTS") / source.relative_to(work)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            role = "raw" if source.suffix in {".xml", ".gz", ".sqlite"} or source == plan_path else "lexical_index"
            artifacts.append({
                "logical_id": f"moleg:{endpoint_id}:{position:06d}",
                "role": role,
                "path": relative.as_posix(),
                "sha256": _hash_file(target),
                "media_type": "application/vnd.sqlite3" if source.suffix == ".sqlite" else "application/gzip" if source.suffix == ".gz" else "application/xml" if source.suffix == ".xml" else
                              ("application/x-ndjson" if source.suffix == ".jsonl" else "application/json"),
            })
        manifest: dict[str, object] = {
            "schema_version": "dataset-package-v2",
            "package_id": package_id,
            "dataset_id": f"moleg-knowledge-{endpoint_id}",
            "version_id": f"v-{seed[:16]}",
            "variant_id": "official-api-normalized",
            "generation_id": generation_id,
            "source_origin": "public_external",
            "security_class": "public",
            "representation": "real",
            "authority": "authoritative",
            # API 이용승인과 원천 데이터 재배포 허가는 별개이므로 보수적으로 잠근다.
            "export_policy": {"allowed": False},
            "build": {
                "build_id": f"build-{seed[:24]}",
                "execution_site": "outside",
                "code_revision": _code_revision(root),
                "compiler_profile": COMPILER_PROFILE,
                "capabilities": ["lexical_index", "raw"],
            },
            "artifacts": artifacts,
        }
        manifest["manifest_sha256"] = _digest(manifest)
        _atomic_json(staging / "manifest.json", manifest)
        load_package(staging / "manifest.json", verify_files=True)
        os.rename(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest_path


def _print_endpoints() -> None:
    print("endpoint                     target       paging  required / one-of / optional")
    for key, spec in ENDPOINTS.items():
        required = ",".join(spec.required) or "-"
        required_any = ",".join(spec.required_any) or "-"
        optional = ",".join(spec.optional) or "-"
        print(f"{key:28s} {spec.target:12s} {str(spec.paged):7s} "
              f"{required} / {required_any} / {optional}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="법제처 법령지식 DatasetPackage 수집기")
    parser.add_argument("--endpoint", action="append", choices=sorted(ENDPOINTS))
    parser.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--display", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=0,
                        help="이번 실행에서 받을 최대 페이지(0=완료까지)")
    parser.add_argument("--oc-env", default="LAW_OC",
                        help="OC가 든 환경변수 이름(기본 LAW_OC)")
    parser.add_argument('--snapshot', default='initial', help='갱신 수집 시 새로운 snapshot 이름 지정')
    parser.add_argument('--receipt-output', type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-endpoints", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.display <= 100 or args.max_pages < 0:
        parser.error('display는 1~100, max-pages는 0 이상이어야 합니다')

    if args.list_endpoints:
        _print_endpoints()
        return 0
    values = parse_params(args.param)
    endpoints = tuple(args.endpoint or DEFAULT_ENDPOINTS)
    for endpoint in endpoints:
        try:
            MolegKnowledgeClient(None, 'validation-only').params(endpoint, values, display=args.display)
        except ValueError as exc:
            parser.error(str(exc))
        spec = ENDPOINTS[endpoint]
        missing = [name for name in spec.required if not values.get(name)]
        if missing:
            parser.error(f"{endpoint}: --param으로 필수값 필요: {', '.join(missing)}")
        if spec.required_any and not any(values.get(name) for name in spec.required_any):
            parser.error(
                f"{endpoint}: --param으로 다음 중 하나 필요: {', '.join(spec.required_any)}"
            )
    plans = [public_request_plan(endpoint, values, display=args.display)
             for endpoint in endpoints]
    if args.dry_run:
        print(json.dumps(plans, ensure_ascii=False, indent=2))
        return 0

    oc = os.environ.get(args.oc_env, "").strip()
    if not oc:
        env_file = repository_root() / '.env'
        if env_file.is_file():
            from dotenv import dotenv_values
            oc = (dotenv_values(env_file).get(args.oc_env) or '').strip()
    if not oc:
        parser.error(f"환경변수 {args.oc_env}에 법제처 OPEN API OC를 설정하십시오")
    root = repository_root()
    logger = build_logger(runtime_path("logs"), "moleg-knowledge")
    client = MolegKnowledgeClient(HttpClient(make_session(), logger), oc)
    incomplete = False
    packages = []
    for endpoint in endpoints:
        package, checkpoint = _collect_endpoint(
            client, endpoint, values, args.display, args.max_pages, root, args.snapshot,
        )
        if package is None:
            incomplete = True
            print(f"{endpoint}: 일시 정지 (다음 페이지 {checkpoint['next_page']}/"
                  f"{checkpoint['page_count']}); 같은 명령으로 재개")
        else:
            packages.append(str(package.resolve()))
            print(f"{endpoint}: 원 API {checkpoint['total_count']}행 수집 및 패키지 발행 "
                  f"-> {package.relative_to(root)}")
    if args.receipt_output:
        _atomic_json(args.receipt_output, {'completed': not incomplete, 'snapshot': args.snapshot,
                                          'packages': packages})
    return 2 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
