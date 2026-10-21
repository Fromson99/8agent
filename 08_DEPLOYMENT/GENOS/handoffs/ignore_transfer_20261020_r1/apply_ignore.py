"""Append the reviewed ignore delta; preserve data, index and Git history."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
CONFIG = "00_SYSTEM/GENOS_SERVING_PATHS.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Symlink refused: " + str(path))
    return path


def write(path, raw):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if path.exists():
        os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)


def json_write(path, value):
    write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def forbidden(name):
    parts = Path(name).parts
    return (
        any(p == ".Trash" or p.startswith(".Trash-") for p in parts)
        or bool(parts and parts[0].startswith("QUERY_TRANSFER_"))
        or bool(re.search(r"\.(?:db|sqlite|sqlite3)\.partial(?:-.*)?$|\.db-journal$", name))
    )


def validate_rules(raw, spec):
    with tempfile.TemporaryDirectory(prefix="genos-ignore-probe-") as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".gitignore").write_bytes(raw)
        names = spec["excluded_examples"] + spec["retained_examples"]
        for name in names:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "-C", str(root), "-c", "core.excludesFile=/dev/null",
             "-c", "core.ignoreCase=false", "check-ignore", "--no-index", "-z", "--stdin"],
            input=("\0".join(names) + "\0").encode(), capture_output=True)
        if result.returncode not in (0, 1):
            raise ValueError("Git ignore probe failed")
        excluded = set(result.stdout.decode().strip("\0").split("\0"))
        if excluded != set(spec["excluded_examples"]):
            raise ValueError("Existing rules conflict with the expected code/data boundary")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "apply", "status", "undo", "gate"])
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((HERE / "PATCH_SPEC.json").read_bytes())
    for name, pin in spec["payload_hashes"].items():
        if sha(plain(HERE / name).read_bytes()) != pin:
            raise ValueError("Package content changed: " + name)
    root = args.root.expanduser().resolve(strict=True)
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise ValueError("--root must be the existing Git checkout root")
    if not plain(root / ".gitignore").is_file() or not (root / "service.py").is_file():
        raise ValueError("Expected existing GENOS code checkout with .gitignore and service.py")
    print("CODE_ROOT=" + str(root))
    print("PYTHON=" + sys.executable + " VERSION=" + sys.version.split()[0])
    state_path = HERE / "STATE.json"
    with plain(HERE / "apply.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(plain(state_path).read_bytes()) if state_path.exists() else None
        if state and (state["root"] != str(root) or state["spec_sha256"] != sha((HERE / "PATCH_SPEC.json").read_bytes())):
            raise ValueError("Saved state belongs to another root or package")
        if not state:
            block = (HERE / "IGNORE_RULES.txt").read_bytes()
            rows = {}
            for name in spec["profiles"]:
                path = plain(root / name)
                if not path.exists():
                    continue
                before = path.read_bytes()
                after = before + (b"" if before.endswith(b"\n") else b"\n") + b"\n" + block
                validate_rules(after, spec)
                rows[name] = {"before": base64.b64encode(before).decode(),
                              "after": base64.b64encode(after).decode(),
                              "before_sha256": sha(before), "after_sha256": sha(after)}
            config = plain(root / CONFIG)
            state = {"root": str(root), "spec_sha256": sha((HERE / "PATCH_SPEC.json").read_bytes()),
                     "phase": "PREPARED", "head_before": git(root, "rev-parse", "HEAD").decode().strip(),
                     "config_sha256": sha(config.read_bytes()) if config.exists() else None, "files": rows}
            if args.action not in ("check", "apply"):
                raise ValueError("No apply receipt; run check and apply first")
        # Validate every target before changing any of them. An interrupted apply
        # may contain before/after bytes, but unrelated edits must be preserved.
        for name, row in state["files"].items():
            if name not in spec["profiles"]:
                raise ValueError("Unexpected path in saved receipt: " + name)
            for side in ("before", "after"):
                if sha(base64.b64decode(row[side], validate=True)) != row[side + "_sha256"]:
                    raise ValueError("Saved ignore backup changed: " + name)
            current = plain(root / name).read_bytes()
            if sha(current) not in (row["before_sha256"], row["after_sha256"]):
                raise ValueError("Ignore file changed after preparation: " + name)
        if args.action == "check":
            print(json.dumps({"check": "PASS", "profiles": list(state["files"]),
                              "code_changes": 0, "data_changes": 0, "git_changes": 0}))
            return
        if args.action in ("apply", "undo"):
            side = "after" if args.action == "apply" else "before"
            state["phase"] = "APPLYING" if args.action == "apply" else "RESTORING"
            json_write(state_path, state)
            for name, row in state["files"].items():
                raw = base64.b64decode(row[side])
                if plain(root / name).read_bytes() != raw:
                    write(root / name, raw)
            state["phase"] = "APPLIED" if args.action == "apply" else "RESTORED"
            json_write(state_path, state)
            print("IGNORE_" + state["phase"] + "; Git index/history and data files unchanged")
            return
        if state["phase"] != "APPLIED":
            raise ValueError("Apply is incomplete or restored")
        for name, row in state["files"].items():
            if sha(plain(root / name).read_bytes()) != row["after_sha256"]:
                raise ValueError("Applied ignore file differs: " + name)
        tracked = {p for p in git(root, "ls-files", "-z").decode().split("\0") if p}
        bad = sorted(p for p in tracked if forbidden(p))
        print(json.dumps({"ignore_status": "PASS", "tracked_transfer_files": bad,
                          "history_and_remote": "NOT_CHECKED"}, ensure_ascii=False))
        if args.action == "status":
            return
        if bad:
            raise ValueError("Transfer/trash files remain tracked; ignore does not remove committed data")
        if git(root, "status", "--porcelain=v1", "--untracked-files=no").strip():
            raise ValueError("Uncommitted tracked changes remain")
        inventory = json.loads((HERE / "MAIN92_BASE_INVENTORY.json").read_bytes())
        expected = {row["path"]: row["sha256"] for row in inventory["files"]}
        expected.update({row["path"]: row["sha256"] for row in inventory["required_files"]})
        expected.update({name: row["after_sha256"] for name, row in state["files"].items()})
        if state["config_sha256"] is not None:
            expected[CONFIG] = state["config_sha256"]
        mismatches = []
        for name, pin in expected.items():
            path = plain(root / name)
            if name not in tracked or not path.is_file() or sha(path.read_bytes()) != pin:
                mismatches.append(name)
        if mismatches:
            raise ValueError("MAIN92/ignore committed code mismatch: " + ", ".join(mismatches[:20]))
        result = {"status": "MAIN92_PLUS_IGNORE_CODE_MATCH", "code_files": len(expected),
                  "commit": git(root, "rev-parse", "HEAD").decode().strip(),
                  "base_code_zip_sha256": inventory["base_code_zip_sha256"],
                  "history_and_remote": "NOT_CHECKED", "field_model_and_revision": "NOT_CHECKED"}
        json_write(HERE / "CODE_GATE.json", result)
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        json_write(HERE / "LAST_FAILURE.json", {"type": type(exc).__name__, "error": str(exc)})
        print("IGNORE_PATCH_FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
