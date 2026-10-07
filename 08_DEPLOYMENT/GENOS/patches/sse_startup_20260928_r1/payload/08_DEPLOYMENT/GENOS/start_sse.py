"""Start the GENOS SSE app on the existing platform port."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent
PORT_NAMES = ("PORT", "UVICORN_PORT", "SERVER_PORT", "GENOS_PORT")


def port_from_environment():
    values = {name: os.environ[name].strip() for name in PORT_NAMES
              if os.environ.get(name, "").strip()}
    if not values:
        raise ValueError("기존 수신 포트 환경변수가 없습니다. 기존 시작 명령의 --port 값을 그대로 지정해 주세요.")
    ports = {int(value) for value in values.values()}
    if len(ports) != 1:
        raise ValueError("포트 환경변수가 서로 다릅니다. 기존 리비전의 수신 포트를 --port로 지정해 주세요.")
    return ports.pop()


def dependencies():
    result = {}
    for name in ("fastapi", "uvicorn"):
        if importlib.util.find_spec(name) is None:
            raise RuntimeError("SSE 시작 의존성 누락: " + name + "; requirements-sse.txt를 빌드에 사용해 주세요.")
        result[name] = importlib.metadata.version(name)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, help="기존 코드서빙 리비전의 수신 포트")
    parser.add_argument("--check", action="store_true", help="의존성만 확인하고 서버는 시작하지 않음")
    args = parser.parse_args(argv)
    versions = dependencies()
    if args.check:
        print(json.dumps({"sse_dependencies": versions}, ensure_ascii=False))
        return
    port = args.port if args.port is not None else port_from_environment()
    if not 1 <= port <= 65535:
        parser.error("수신 포트는 1~65535 사이여야 합니다.")
    # No data generation is selected here. The existing service resolves it.
    os.chdir(ROOT)
    sys.path.insert(0, str(APP_DIR))
    import uvicorn
    print(json.dumps({"event": "sse.server.starting", "port": port,
                      "startup_revision": "sse-startup-20260928-r1", "workers": 1,
                      "resource_initialization": "on_backend_request",
                      "app": "stream_app:app", "dependencies": versions}, ensure_ascii=False), flush=True)
    # Ignore platform WEB_CONCURRENCY: each worker owns a separate generation
    # cache and would repeat full-file NFS validation and matcher preparation.
    # This does not limit concurrent requests within the serving process.
    uvicorn.run("stream_app:app", host="0.0.0.0", port=port, access_log=False, workers=1)


if __name__ == "__main__":
    main()
