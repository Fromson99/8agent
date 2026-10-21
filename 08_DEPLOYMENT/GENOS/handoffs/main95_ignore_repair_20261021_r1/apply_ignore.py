"""Repair MAIN95 ignore rules and explicitly clean only new forbidden index entries."""
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
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


def validate_rules(raw, spec, local=None):
    with tempfile.TemporaryDirectory(prefix="genos-ignore-probe-") as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".gitignore").write_bytes(raw)
        if local is not None:
            (root / ".git/info/exclude").write_bytes(local)
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


def verify_base(root, state):
    inventory = json.loads((HERE / "MAIN95_BASE_INVENTORY.json").read_bytes())
    for row in inventory["files"]:
        name = row["path"]
        if name in state["files"]:
            continue
        expected = state["config_sha256"] if name == CONFIG and state["config_sha256"] else row["sha256"]
        path = plain(root / name)
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise ValueError("MAIN95 code mismatch (no code changed): " + name)


def clean_stage(root, state, undo=False):
    """Atomic Git index transaction; never touch worktree files or HEAD."""
    index = plain(Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip()))
    head = git(root, "rev-parse", "HEAD").decode().strip()
    saved = HERE / "STAGE_STATE.json"
    before = index.read_bytes()
    if undo:
        receipt = json.loads(plain(saved).read_bytes())
        if receipt["root"] != str(root) or receipt["head"] != head:
            raise ValueError("Index restore root/HEAD changed")
        restored = plain(HERE / "INDEX_BEFORE.bin").read_bytes()
        if sha(restored) != receipt["before_sha256"]:
            raise ValueError("Index backup changed")
        if sha(before) == receipt["before_sha256"]:
            print("INDEX_ALREADY_RESTORED"); return
        if sha(before) != receipt["after_sha256"]:
            raise ValueError("Index has later edits; preserve them and inspect")
    else:
        if git(root, "ls-files", "--unmerged", "-z"):
            raise ValueError("Unmerged index entries; no automatic index changes")
        committed = [n for n in git(root, "ls-tree", "-r", "-z", "--name-only", "HEAD").decode().split("\0") if n and forbidden(n)]
        if committed:
            json_write(HERE / "COMMITTED_DATA.json", {"head": head, "paths": committed, "action": "NONE"})
            raise ValueError("Forbidden data already in HEAD; no index/history changes. Inspect COMMITTED_DATA.json before commit/push")
        bad = [n for n in git(root, "ls-files", "-z").decode().split("\0") if n and forbidden(n)]
        profiles = [n for n in state["files"] if not n.startswith("@")]
        if not bad and not git(root, "diff", "--name-only", "--", *profiles).strip():
            if saved.exists():
                receipt = json.loads(plain(saved).read_bytes())
                if receipt["root"] == str(root) and receipt["head"] == head and sha(before) == receipt["after_sha256"]:
                    receipt["phase"] = "APPLIED"; json_write(saved, receipt)
            print("INDEX_ALREADY_CLEAN; other staged changes preserved"); return
        if saved.exists():
            receipt = json.loads(plain(saved).read_bytes())
            if receipt["root"] != str(root) or receipt["head"] != head or sha(before) != receipt["before_sha256"]:
                raise ValueError("Previous index transaction differs; preserve saved index and inspect")
        if (HERE / "INDEX_BEFORE.bin").exists():
            if plain(HERE / "INDEX_BEFORE.bin").read_bytes() != before:
                raise ValueError("Existing index backup differs")
        else:
            write(HERE / "INDEX_BEFORE.bin", before)
    lockpath = plain(Path(str(index) + ".lock"))
    fd = os.open(lockpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    lock_released = False
    candidate = None
    try:
        if not undo:
            with tempfile.NamedTemporaryFile(dir=index.parent, prefix="ignore-stage-", delete=False) as f:
                candidate = Path(f.name); f.write(before)
            env = {**os.environ, "GIT_INDEX_FILE": str(candidate), "GIT_LITERAL_PATHSPECS": "1"}
            if bad:
                subprocess.run(["git", "-C", str(root), "update-index", "--force-remove", "-z", "--stdin"],
                               input=("\0".join(bad) + "\0").encode(), env=env, check=True)
            subprocess.run(["git", "-C", str(root), "add", "--", *profiles], env=env, check=True)
            restored = candidate.read_bytes()
            receipt = {"root": str(root), "head": head, "before_sha256": sha(before),
                       "after_sha256": sha(restored), "removed_new_paths": bad,
                       "staged_profiles": profiles, "phase": "PREPARED", "disk_files_deleted": 0}
            json_write(saved, receipt)
        if index.read_bytes() != before or git(root, "rev-parse", "HEAD").decode().strip() != head:
            raise ValueError("Index/HEAD changed during preparation")
        with os.fdopen(fd, "wb") as stream:
            fd = None; stream.write(restored); stream.flush(); os.fsync(stream.fileno())
        os.replace(lockpath, index)
        lock_released = True
        receipt["phase"] = "RESTORED" if undo else "APPLIED"
        json_write(saved, receipt)
        print("INDEX_" + receipt["phase"] + "; removed_new_paths=" + str(len(receipt["removed_new_paths"])) + "; disk files/HEAD/remote unchanged")
    finally:
        if fd is not None:
            os.close(fd)
        if not lock_released:
            lockpath.unlink(missing_ok=True)
        if candidate is not None:
            candidate.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "apply", "clean-stage", "undo-stage", "status", "undo", "gate", "gate-sqlite"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--generation", type=Path)
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
    targets = {n: plain(root / n) for n in spec["profiles"]}
    targets["@git-info-exclude"] = plain(Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").decode().strip()))
    state_path = HERE / "STATE.json"
    with plain(HERE / "apply.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(plain(state_path).read_bytes()) if state_path.exists() else None
        if state and (state["root"] != str(root) or state["spec_sha256"] != sha((HERE / "PATCH_SPEC.json").read_bytes())):
            raise ValueError("Saved state belongs to another root or package")
        if not state:
            block = (HERE / "IGNORE_RULES.txt").read_bytes()
            rows = {}
            for name, path in targets.items():
                if name != "@git-info-exclude" and not path.exists():
                    continue
                before = path.read_bytes() if path.exists() else b""
                after = before if block in before else before + (b"" if before.endswith(b"\n") else b"\n") + b"\n" + block
                if name != "@git-info-exclude":
                    validate_rules(after, spec)
                rows[name] = {"existed": path.exists(), "target": str(path), "before": base64.b64encode(before).decode(),
                              "after": base64.b64encode(after).decode(),
                              "before_sha256": sha(before), "after_sha256": sha(after)}
            validate_rules(base64.b64decode(rows[".gitignore"]["after"]), spec, base64.b64decode(rows["@git-info-exclude"]["after"]))
            config = plain(root / CONFIG)
            state = {"root": str(root), "spec_sha256": sha((HERE / "PATCH_SPEC.json").read_bytes()),
                     "phase": "PREPARED", "head_before": git(root, "rev-parse", "HEAD").decode().strip(),
                     "config_sha256": sha(config.read_bytes()) if config.exists() else None, "files": rows}
            if args.action not in ("check", "apply"):
                raise ValueError("No apply receipt; run check and apply first")
        # Validate every target before changing any of them. An interrupted apply
        # may contain before/after bytes, but unrelated edits must be preserved.
        for name, row in state["files"].items():
            if name not in targets or row["target"] != str(targets[name]):
                raise ValueError("Unexpected path in saved receipt: " + name)
            for side in ("before", "after"):
                if sha(base64.b64decode(row[side], validate=True)) != row[side + "_sha256"]:
                    raise ValueError("Saved ignore backup changed: " + name)
            current = targets[name].read_bytes() if targets[name].exists() else b""
            if sha(current) not in (row["before_sha256"], row["after_sha256"]):
                raise ValueError("Ignore file changed after preparation: " + name)
        if args.action in ("check", "apply", "clean-stage", "gate", "gate-sqlite"):
            verify_base(root, state)
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
                path = targets[name]
                if args.action == "undo" and not row["existed"]:
                    path.unlink(missing_ok=True)
                elif not path.exists() or path.read_bytes() != raw:
                    write(path, raw)
            state["phase"] = "APPLIED" if args.action == "apply" else "RESTORED"
            json_write(state_path, state)
            print("IGNORE_" + state["phase"] + "; Git index/history and data files unchanged")
            return
        if state["phase"] != "APPLIED":
            raise ValueError("Apply is incomplete or restored")
        for name, row in state["files"].items():
            if sha(targets[name].read_bytes()) != row["after_sha256"]:
                raise ValueError("Applied ignore file differs: " + name)
        if args.action in ("clean-stage", "undo-stage"):
            clean_stage(root, state, undo=args.action == "undo-stage")
            return
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
        inventory = json.loads((HERE / "MAIN95_BASE_INVENTORY.json").read_bytes())
        expected = {row["path"]: row["sha256"] for row in inventory["files"]}
        expected.update({row["path"]: row["sha256"] for row in inventory["required_files"]})
        expected.update({name: row["after_sha256"] for name, row in state["files"].items() if not name.startswith("@")})
        if state["config_sha256"] is not None:
            expected[CONFIG] = state["config_sha256"]
        mismatches = []
        for name, pin in expected.items():
            path = plain(root / name)
            if name not in tracked or not path.is_file() or sha(path.read_bytes()) != pin:
                mismatches.append(name)
        if mismatches:
            raise ValueError("MAIN95/ignore committed code mismatch: " + ", ".join(mismatches[:20]))
        result = {"status": "MAIN95_PLUS_IGNORE_CODE_MATCH", "code_files": len(expected),
                  "commit": git(root, "rev-parse", "HEAD").decode().strip(),
                  "base_code_zip_sha256": inventory["base_code_zip_sha256"],
                  "history_and_remote": "NOT_CHECKED", "field_model_and_revision": "NOT_CHECKED"}
        if args.action == "gate-sqlite":
            def load(name, path):
                binding = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(binding)
                binding.loader.exec_module(module)
                return module
            gate = load("checked_release_gate", root / "06_TOOLS/COMMANDS/genos_release_gate.py")
            selected = args.generation
            if selected is None:
                select = load("checked_generation_selection", root / "06_TOOLS/COMMANDS/genos_generation_e2e.py")
                selected = select.operator_generation(root)
            gate.check_generation(root, selected)
            result.update(generation=str(selected.resolve()), generation_check="PASS")
        json_write(HERE / "CODE_GATE.json", result)
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        json_write(HERE / "LAST_FAILURE.json", {"type": type(exc).__name__, "error": str(exc)})
        print("IGNORE_PATCH_FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
