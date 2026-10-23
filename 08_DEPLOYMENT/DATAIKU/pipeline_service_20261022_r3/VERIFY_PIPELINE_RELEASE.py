"""Read-only check of the actual pipeline-only deployment checkout against this ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for b in iter(lambda: stream.read(1024**2), b""):
            h.update(b)
    return h.hexdigest()


def verify(code_root, require_committed=False):
    reference = Path(__file__).resolve().parent
    root = Path(code_root).resolve(strict=True)
    pins_path = reference / "CODE_PINS.json"
    pins = json.loads(pins_path.read_text())
    expected = sha(pins_path)
    if (root / "CODE_PINS.json").is_symlink() or sha(root / "CODE_PINS.json") != expected:
        raise ValueError("DEPLOYMENT_PINS_DIFFER")
    for name, digest in pins["files"].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or sha(path) != digest:
            raise ValueError("DEPLOYMENT_CODE_DIFFER: " + name)
    commit = None
    if require_committed:
        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
        commit = git("rev-parse", "HEAD")
        names = [*pins["files"], "CODE_PINS.json"]
        git("ls-files", "--error-unmatch", "--", *names)
        if git("diff", "HEAD", "--name-only", "--", *names):
            raise ValueError("DEPLOYMENT_HAS_UNCOMMITTED_CHANGES")
    return {"status": "CODE_VERIFIED", "root": str(root), "files": len(pins["files"]),
            "code_sha256": expected, "commit": commit, "python": sys.executable,
            "python_version": sys.version.split()[0], "genos_revision": "NOT_VERIFIED",
            "generation": "PER_JOB_TEMPORARY; no NFS generation selected"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--code-root", required=True)
    p.add_argument("--require-committed", action="store_true")
    a = p.parse_args()
    print(json.dumps(verify(a.code_root, a.require_committed), ensure_ascii=False, indent=2))
