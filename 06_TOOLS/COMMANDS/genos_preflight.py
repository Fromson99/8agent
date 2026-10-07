#!/usr/bin/env python3
"""GenOS 코드 서빙 배포 전·후 점검.

소스 판에서는 진입점·의존성·Git·반입 데이터를, GenOS 런타임 판에서는 환경변수·
의존성 import·영속 경로·service.py의 ping/health를 확인한다. 비밀값은 출력하지 않는다.

    python 06_TOOLS/run_tool.py genos_preflight.py source
    python 06_TOOLS/run_tool.py genos_preflight.py source --strict
    python 06_TOOLS/run_tool.py genos_preflight.py runtime --strict --probe-upstreams
    python 06_TOOLS/run_tool.py genos_preflight.py all --json
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import importlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
BACKEND_ROOT = ROOT / "02_BACKEND"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class Result:
    level: str
    name: str
    detail: str


class Checks:
    def __init__(self) -> None:
        self.rows: list[Result] = []

    def ok(self, name: str, detail: str) -> None:
        self.rows.append(Result("pass", name, detail))

    def warn(self, name: str, detail: str) -> None:
        self.rows.append(Result("warn", name, detail))

    def fail(self, name: str, detail: str) -> None:
        self.rows.append(Result("fail", name, detail))

    def capture(self, name: str, fn: Callable[[], str]) -> None:
        try:
            detail = fn()
        except Exception as exc:
            self.fail(name, f"{type(exc).__name__}: {exc}")
        else:
            self.ok(name, detail)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _safe_remote(url: str) -> str:
    # https://user:token@host 와 https://token@host 모두 가린다.
    return re.sub(r"(https?://)[^/@]+@", r"\1***@", url)


def _requirements() -> set[str]:
    found: set[str] = set()
    path = ROOT / "requirements.txt"
    for raw in path.read_text("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip().lower()
        if name:
            found.add(name.replace("_", "-"))
    return found


def _service_contract() -> str:
    tree = ast.parse((ROOT / "service.py").read_text("utf-8"))
    functions = [n for n in tree.body
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "service"]
    if len(functions) != 1:
        raise RuntimeError(f"최상위 async service 함수가 {len(functions)}개입니다")
    args = [a.arg for a in functions[0].args.args]
    if args[:2] != ["config", "data"]:
        raise RuntimeError(f"service 인자는 config, data 순서여야 합니다: {args}")
    return "service.py: async service(config, data)"


def _tree_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    if not path.exists():
        return 0
    for parent, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(parent) / name).stat().st_size
            except OSError:
                pass
    return total


def _mb(size: int) -> str:
    return f"{size / 1024 / 1024:.1f}MB"


def source_checks(c: Checks) -> None:
    required_files = (
        "service.py", "requirements-serving.txt", ".env.example",
        ".env.genos.example", ".env.onsite.example",
        "06_TOOLS/COMMANDS/code_ship.py",
        "06_TOOLS/COMMANDS/genos_call.sh",
        "06_TOOLS/EXPERIMENTS/OPERATIONS/genos_patch_apply.py",
        "06_TOOLS/COMMANDS/genos_smoke.sh",
        "07_DOCS/REFERENCE/OPERATIONS/GENOS_QUICKSTART.md",
        "07_DOCS/REFERENCE/OPERATIONS/GENOS_DEPLOY.md",
        "07_DOCS/REFERENCE/OPERATIONS/GENOS_SITE_RUNBOOK.md",
        "07_DOCS/REFERENCE/OPERATIONS/ONSITE_RUNBOOK.md",
        "07_DOCS/REFERENCE/OPERATIONS/GENOS_PATCH_UPDATE.md",
    )
    missing = [name for name in required_files if not (ROOT / name).exists()]
    if missing:
        c.fail("배포 자산", "없음: " + ", ".join(missing))
    else:
        c.ok("배포 자산", f"필수 파일 {len(required_files)}개")

    c.capture("GenOS 진입점", _service_contract)

    expected = {
        "jsonschema", "referencing", "requests", "python-dotenv",
        "fastapi", "httpx",
    }
    try:
        declared = _requirements()
    except Exception as exc:
        c.fail("서빙 의존성", f"{type(exc).__name__}: {exc}")
    else:
        missing_deps = sorted(expected - declared)
        if missing_deps:
            c.fail("서빙 의존성", "직접 선언 누락: " + ", ".join(missing_deps))
        else:
            heavy = sorted(
                name for name in ("torch", "sentence-transformers", "uvicorn")
                if name in declared
            )
            if heavy:
                c.warn("서빙 의존성", "기본 서빙에 선택 패키지 포함: " + ", ".join(heavy))
            else:
                c.ok("서빙 의존성", f"Python 3.11 최소 직접 의존성 {len(expected)}개 선언")

    try:
        tracked_env = _git("ls-files", ".env", ".env.local")
    except Exception as exc:
        c.fail("비밀값 추적", f"Git 확인 실패: {exc}")
    else:
        if tracked_env:
            c.fail("비밀값 추적", f"Git에서 제거 필요: {tracked_env.replace(chr(10), ', ')}")
        else:
            c.ok("비밀값 추적", ".env·.env.local 미추적")

    try:
        status = _git("status", "--porcelain=v1")
        rows = status.splitlines() if status else []
        untracked = sum(row.startswith("??") for row in rows)
        changed = len(rows) - untracked
        staged = sum(not row.startswith("??") and row[0] != " " for row in rows)
    except Exception as exc:
        c.fail("Git 작업판", f"Git 확인 실패: {exc}")
    else:
        branch = _git("branch", "--show-current") or "detached"
        try:
            rev = _git("rev-parse", "--short", "HEAD")
        except subprocess.CalledProcessError:
            # GenOS 내부 Gitea의 빈 저장소를 clone한 직후에는 아직 HEAD가 없다.
            # 현장 가이드는 ZIP 검증 후 첫 commit 전에 preflight를 실행한다.
            rev = "unborn"
        if rows:
            c.warn("Git 작업판", (f"{branch}@{rev} · 변경 {changed}, 미추적 {untracked}, "
                                  f"staged {staged} — 배포 커밋에 포함할 판을 확정해야 합니다"))
        else:
            c.ok("Git 작업판", f"clean · {branch}@{rev}")

    try:
        names = _git("remote").splitlines()
        remotes = []
        remote_urls = {}
        for name in names:
            remote_urls[name] = _git("remote", "get-url", name)
            remotes.append(f"{name}={_safe_remote(remote_urls[name])}")
    except Exception as exc:
        c.warn("Git 원격", f"조회 실패: {exc}")
    else:
        expected_url = os.environ.get("GENOS_GIT_URL", "").strip().rstrip("/")
        expected_match = expected_url and any(
            url.rstrip("/") == expected_url for url in remote_urls.values())
        if "genos" in names or expected_match:
            c.ok("Git 원격", " · ".join(remotes))
        elif remotes:
            c.warn("Git 원격", " · ".join(remotes) + " · 이름이 genos인 코드 서빙 원격을 추가하세요")
        else:
            c.warn("Git 원격", "원격 없음 — GenOS 내부 Gitea를 추가해야 합니다")

    try:
        from lawrag.platform import active_runtime_paths

        paths = tuple(active_runtime_paths(ROOT, target="genos").values())
    except Exception as exc:
        c.warn(
            "반입 데이터",
            f"활성 runtime binding 조회 불가: {type(exc).__name__}: {exc}",
        )
        paths = ()
    sizes = [(p, _tree_bytes(p)) for p in paths if p.exists()]
    if not sizes:
        c.warn("반입 데이터", "로컬 런타임 데이터 없음")
    else:
        total = sum(size for _path, size in sizes)
        detail = " · ".join(
            f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p} {_mb(size)}"
            for p, size in sizes
        )
        c.ok("반입 데이터", f"합계 {_mb(total)} · {detail}")


def _distribution_version(name: str) -> str:
    return f"{name} {importlib.metadata.version(name)}"


def _writable_parent(path: Path) -> bool:
    probe = path if path.is_dir() else path.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe.exists() and os.access(probe, os.W_OK | os.X_OK)


def _probe_models(url: str, key: str) -> str:
    import requests

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    response = requests.get(url.rstrip("/") + "/v1/models", headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json().get("data") or []
    model = data[0].get("id") if data and isinstance(data[0], dict) else "응답은 왔지만 모델 없음"
    return f"HTTP {response.status_code} · {model}"


def runtime_checks(c: Checks, probe_upstreams: bool) -> None:
    from lawrag.platform import active_runtime_paths

    selected_generation_id = None
    if os.environ.get("GENOS_GENERATION", "").strip() or os.environ.get("GENOS_DATA_ROOT", "").strip():
        try:
            from genos_generation_e2e import audit, selected_generation
            generation = selected_generation()
            binding_report = audit(ROOT, generation)
            selected_generation_id = binding_report["generation_id"]
            for row in binding_report["checks"]:
                detail = f"{row['check']}: {row['detail']}"
                if row["status"] == "FAIL":
                    c.fail("세대/fulltext 결속", detail)
            if binding_report["status"] == "PASS":
                c.ok("세대/fulltext 결속", f"generation={selected_generation_id} · index open verified")
        except Exception as exc:
            c.fail("세대/fulltext 결속", f"{type(exc).__name__}: {exc}")
    else:
        c.warn("세대/fulltext 결속", "GENOS_GENERATION 또는 GENOS_DATA_ROOT 미설정; 실제 서빙 세대를 확인하지 못함")

    imports = {
        "FastAPI": "fastapi", "Pydantic": "pydantic", "PyYAML": "yaml",
        "Requests": "requests", "NumPy": "numpy", "PyMuPDF": "fitz",
        "Docling core": "docling_core",
    }
    for label, module in imports.items():
        c.capture(f"import {label}", lambda module=module: (
            f"{module} {getattr(importlib.import_module(module), '__version__', 'ok')}"
        ))
    c.capture("import multipart", lambda: _distribution_version("python-multipart"))

    release_target = os.environ.get("LAWRAG_RELEASE_TARGET", "genos").strip() or "genos"
    persistent = active_runtime_paths(ROOT, target=release_target)
    persistent["OPS_DIR"] = ROOT / "90_RUNTIME" / "ops"
    for key, default in persistent.items():
        raw = os.environ.get(key, "").strip()
        path = Path(raw) if raw else default
        if not raw:
            c.warn(key, f"미설정 · 기본 {path} 사용 — GenOS에서는 영속 볼륨 경로를 권장합니다")
        elif _writable_parent(path):
            c.ok(key, f"{path} · 쓰기 가능한 부모 확인")
        else:
            c.fail(key, f"{path} · 쓰기 가능한 경로가 아닙니다")

    model_env = (
        ("GenOS LLM", "GENOS_LLM_URL", "GENOS_LLM_KEY"),
        ("GenOS Embedding", "GENOS_EMBED_URL", "GENOS_EMBED_KEY"),
    )
    for label, url_key, key_key in model_env:
        url = os.environ.get(url_key, "").strip()
        key = os.environ.get(key_key, "").strip()
        if not url:
            base = os.environ.get("GENOS_BASE_URL", "").strip().rstrip("/")
            if label == "GenOS LLM":
                serving_id = os.environ.get("GENOS_LLM_SERVING_ID", "").strip()
            else:
                serving_id = os.environ.get("GENOS_EMBED_SERVING_ID", "").strip()
            if base and serving_id.isdigit():
                url = f"{base}/api/gateway/rep/serving/{serving_id}"
        if not url:
            c.warn(label, f"{url_key} 또는 GENOS_BASE_URL·서빙 ID 미설정")
            continue
        if not key and label == "GenOS Embedding":
            key = os.environ.get("GENOS_LLM_KEY", "").strip()
        if not key:
            c.warn(label, f"{url_key} 설정 · 인증키 미설정")
        else:
            c.ok(label, f"{url_key}·인증키 설정")
        if probe_upstreams:
            c.capture(f"{label} /v1/models", lambda url=url, key=key: _probe_models(url, key))

    async def service_probe() -> tuple[dict[str, Any], dict[str, Any]]:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        service = importlib.import_module("service")
        ping = await service.service({}, {"op": "ping"})
        health = await service.service({}, {"op": "call", "method": "GET", "path": "/health"})
        return ping, health

    try:
        ping, health = asyncio.run(service_probe())
    except Exception as exc:
        c.fail("service 스모크", f"{type(exc).__name__}: {exc}")
    else:
        if ping.get("service") != "8-AGENT":
            c.fail("service ping", f"예상하지 못한 응답: {ping}")
        else:
            c.ok("service ping", f"rev={ping.get('rev')} store={ping.get('store')}")
        body = health.get("body") or health.get("json") or {}
        if health.get("status") != 200 or body.get("status") != "ok":
            c.fail("service health", json.dumps(health, ensure_ascii=False)[:1000])
        else:
            c.ok("service health", f"HTTP 200 · generation={body.get('generation_id')}")
            if selected_generation_id is not None:
                if body.get("generation_id") == selected_generation_id:
                    c.ok("health 세대 일치", selected_generation_id)
                else:
                    c.fail("health 세대 일치", f"selected={selected_generation_id} health={body.get('generation_id')}")


def render(rows: list[Result], as_json: bool) -> None:
    counts = {level: sum(row.level == level for row in rows)
              for level in ("pass", "warn", "fail")}
    if as_json:
        print(json.dumps({"summary": counts, "checks": [asdict(row) for row in rows]},
                         ensure_ascii=False, indent=2))
        return
    marks = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for row in rows:
        print(f"[{marks[row.level]}] {row.name}: {row.detail}")
    print(f"결과: PASS {counts['pass']} · WARN {counts['warn']} · FAIL {counts['fail']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("phase", choices=("source", "runtime", "all"), nargs="?",
                        default="source")
    parser.add_argument("--strict", action="store_true",
                        help="경고도 배포 차단으로 취급")
    parser.add_argument("--probe-upstreams", action="store_true",
                        help="runtime에서 LLM·Embedding /v1/models까지 실제 호출")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    checks = Checks()
    if args.phase in ("source", "all"):
        source_checks(checks)
    if args.phase in ("runtime", "all"):
        runtime_checks(checks, args.probe_upstreams)
    render(checks.rows, args.json)
    failed = any(row.level == "fail" for row in checks.rows)
    warned = any(row.level == "warn" for row in checks.rows)
    return 1 if failed or (args.strict and warned) else 0


if __name__ == "__main__":
    raise SystemExit(main())
