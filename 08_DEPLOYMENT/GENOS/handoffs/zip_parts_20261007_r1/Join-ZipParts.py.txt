#!/usr/bin/env python3
"""Restore Windows split-archive-v1 pieces on GENOS/Linux (standard library only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def leaf_name(value: object) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."} or any(
        char in value for char in ("/", "\\", "\0", ":")
    ):
        raise ValueError("Invalid file name in manifest")
    return value


def restore(parts_directory: Path, output: Path | None) -> Path:
    directory = parts_directory.resolve(strict=True)
    manifest = json.loads((directory / "parts-manifest.json").read_text(encoding="utf-8-sig"))
    if manifest["schema_version"] != "split-archive-v1":
        raise ValueError("Unsupported manifest schema")
    name = leaf_name(manifest["archive"])
    total, limit = manifest["archive_bytes"], manifest["part_max_bytes"]
    if type(total) is not int or total < 0 or type(limit) is not int or not 1 <= limit <= 50_000_000:
        raise ValueError("Invalid manifest sizes")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", manifest["archive_sha256"]):
        raise ValueError("Invalid original SHA-256")
    seen: set[str] = set()
    expected_sum = 0
    for part in manifest["parts"]:
        part_name = leaf_name(part["name"])
        if part_name.casefold() in seen:
            raise ValueError(f"Duplicate part: {part_name}")
        seen.add(part_name.casefold())
        size = part["bytes"]
        if type(size) is not int or not 1 <= size <= limit or not re.fullmatch(r"[0-9a-fA-F]{64}", part["sha256"]):
            raise ValueError(f"Invalid part metadata: {part_name}")
        path = directory / part_name
        if not path.is_file() or path.is_symlink() or path.stat().st_size != size:
            raise ValueError(f"Missing/invalid part: {part_name}")
        expected_sum += size
    if expected_sum != total:
        raise ValueError("Part sizes do not equal original size")
    output = Path(os.path.abspath(output or directory.parent / name))
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial-" + uuid.uuid4().hex)
    whole = hashlib.sha256()
    copied = 0
    try:
        with temporary.open("xb") as writer:
            for part in manifest["parts"]:
                digest = hashlib.sha256()
                count = 0
                with (directory / part["name"]).open("rb") as reader:
                    for block in iter(lambda: reader.read(1024 * 1024), b""):
                        count += len(block)
                        if count > part["bytes"]:
                            raise ValueError(f"Part grew while reading: {part['name']}")
                        writer.write(block)
                        digest.update(block)
                        whole.update(block)
                if count != part["bytes"] or digest.hexdigest() != part["sha256"].lower():
                    raise ValueError(f"Part hash/size mismatch: {part['name']}")
                copied += count
                print(f"Verified {part['name']}", flush=True)
            writer.flush()
            os.fsync(writer.fileno())
        expected = manifest["archive_sha256"].lower()
        if copied != total or whole.hexdigest() != expected or sha256_file(temporary) != expected:
            raise ValueError("Restored file does not match original SHA-256/size")
        # link publishes a complete file without overwriting a concurrently created output.
        os.link(temporary, output)
        temporary.unlink()
    except Exception:
        if temporary.exists():
            print(f"Incomplete output retained at: {temporary}", file=sys.stderr)
        raise
    print(f"OK: {output}\nVerified original SHA-256: {expected}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parts_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        restore(args.parts_directory, args.output)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
