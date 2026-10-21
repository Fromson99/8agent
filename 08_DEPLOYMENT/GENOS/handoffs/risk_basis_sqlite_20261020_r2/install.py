"""Install this small offline batch patch into an existing GENOS checkout."""
import argparse
import ast
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def target(root, name):
    path = root / name
    require(root in path.resolve().parents and not path.is_symlink(),
            "checkout 밖 경로 또는 symlink: " + name)
    return path


def check(root, manifest):
    require(root.is_dir(), "기존 DEV checkout이 없습니다: " + str(root))
    git_root = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--show-toplevel"], text=True).strip()
    require(Path(git_root).resolve() == root, "적용 대상은 기존 Git checkout 루트여야 합니다.")
    for name, pin in manifest["package_files"].items():
        require(sha(PACKAGE / name) == pin, "패키지 파일 해시 불일치: " + name)
    for name, rule in manifest["payload"].items():
        src = PACKAGE / "payload" / name
        require(sha(src) == rule["sha256"], "payload 해시 불일치: " + name)
        ast.parse(src.read_text(encoding="utf-8"), filename=name)
        previous = sha(target(root, name))
        require(previous == rule["sha256"] or previous in rule["allowed_before"],
                "기존 파일이 검증한 버전과 다릅니다. 덮어쓰지 않습니다: " + name)
    for name, hashes in manifest["dependencies"].items():
        require(sha(target(root, name)) in hashes, "기존 의존 코드 버전 확인 필요: " + name)
    result = {"status": "CODE_CHECKED", "python": sys.executable,
              "python_version": sys.version, "code_root": str(root),
              "git_head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
              "manifest_sha256": sha(PACKAGE / "CODE_MANIFEST.json"),
              "serving_revision": "NOT_VERIFIED", "generation_changed": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def replace(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".risk-basis-tmp")
    with temp.open("wb") as out:
        out.write(body)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "install", "rollback-code", "run"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root, state = args.root.resolve(), args.state.resolve()
    state.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PACKAGE / "CODE_MANIFEST.json").read_text())
    with (state / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = state / "code-backup.json"
        if args.action == "rollback-code":
            receipt = json.loads(receipt_path.read_text())
            require(receipt["root"] == str(root) and
                    receipt["manifest_sha256"] == sha(PACKAGE / "CODE_MANIFEST.json"),
                    "다른 checkout/패키지의 백업입니다.")
            # Validate every file before changing any.
            for name, before in receipt["before"].items():
                require(sha(target(root, name)) in (before, manifest["payload"][name]["sha256"]),
                        "설치 후 변경된 코드가 있습니다: " + name)
                if before is not None:
                    require(sha(state / "backup" / name) == before, "백업 해시 불일치: " + name)
            for name, before in receipt["before"].items():
                path = target(root, name)
                if sha(path) == before:
                    continue
                if before is None:
                    path.unlink()
                else:
                    replace(path, (state / "backup" / name).read_bytes())
            print("CODE_ROLLED_BACK; DB 연결 상태는 별도 revoke 명령으로 관리합니다.")
            return
        info = check(root, manifest)
        if args.action == "check":
            return
        if args.action == "install":
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                require(receipt["root"] == str(root) and receipt["manifest_sha256"] == info["manifest_sha256"],
                        "기존 백업의 대상/패키지가 다릅니다.")
            else:
                before = {name: sha(target(root, name)) for name in manifest["payload"]}
                for name, pin in before.items():
                    if pin is not None:
                        replace(state / "backup" / name, target(root, name).read_bytes())
                receipt = {"root": str(root), "manifest_sha256": info["manifest_sha256"], "before": before}
                save(receipt_path, receipt)
            for name, rule in manifest["payload"].items():
                path = target(root, name)
                if sha(path) != rule["sha256"]:
                    replace(path, (PACKAGE / "payload" / name).read_bytes())
            subprocess.run(["git", "-C", str(root), "diff", "--check", "--", *manifest["payload"]], check=True)
        for name, rule in manifest["payload"].items():
            require(sha(target(root, name)) == rule["sha256"], "먼저 install을 실행하십시오: " + name)
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root / "02_BACKEND"))
        module = importlib.import_module("lawrag.pipeline.risk_basis_seed_cli")
        require(Path(module.__file__).resolve() == root / "02_BACKEND/lawrag/pipeline/risk_basis_seed_cli.py",
                "다른 checkout의 모듈이 선택됐습니다.")
        if args.action == "install":
            save(state / "code-installed.json", {**info, "status": "OFFLINE_CODE_INSTALLED"})
            print("OFFLINE_CODE_INSTALLED; Git push/서빙 배포/DB 변경은 수행하지 않았습니다.")
            return
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        require(bool(command), "실행 명령이 없습니다.")
        raise SystemExit(module.main(command))


if __name__ == "__main__":
    main()
