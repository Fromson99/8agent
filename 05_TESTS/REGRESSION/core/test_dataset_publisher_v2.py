from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lawrag.datasets.catalog import load_package
from lawrag.datasets.publisher import hash_tree, inventory_source, publish_source_package


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_inventory_and_publication_preserve_declared_bytes(tmp_path: Path):
    source = tmp_path / "01_DATA/INBOX/AUTHORING/corpus/law"
    source.mkdir(parents=True)
    body = source / "law.xml"
    body.write_text("<law>frozen</law>", encoding="utf-8")
    manifest = {
        "items": [
            {
                "doc_no": "123",
                "file": "01_DATA/INBOX/AUTHORING/corpus/law/law.xml",
                "sha256": _sha(body),
            }
        ]
    }
    (source / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    inventory = inventory_source(tmp_path, "law")
    assert inventory.item_count == 1
    assert len(inventory.files) == 1
    package_path = publish_source_package(
        tmp_path, inventory, code_revision="a" * 64
    )
    package = load_package(package_path, verify_files=True)
    assert package.package_id.startswith("source-law-")
    assert package.export_allowed is True
    assert len(package.artifacts) == 2


def test_internal_source_fails_closed_for_export(tmp_path: Path):
    source = tmp_path / "01_DATA/INBOX/AUTHORING/corpus/internal"
    source.mkdir(parents=True)
    body = source / "policy.txt"
    body.write_text("restricted", encoding="utf-8")
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "doc_id": "internal-1",
                        "body_file": "01_DATA/INBOX/AUTHORING/corpus/internal/policy.txt",
                        "body_sha256": _sha(body),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    inventory = inventory_source(tmp_path, "internal")
    package = load_package(
        publish_source_package(tmp_path, inventory, code_revision="b" * 64)
    )
    assert package.source_origin == "restricted_internal"
    assert package.security_class == "restricted"
    assert package.export_allowed is False


def test_tree_hash_binds_relative_path_and_content(tmp_path: Path):
    root = tmp_path / "structure"
    first = root / "doc-a/result.json"
    first.parent.mkdir(parents=True)
    first.write_text('{"value": 1}', encoding="utf-8")

    original = hash_tree(root)
    first.write_text('{"value": 2}', encoding="utf-8")
    assert hash_tree(root) != original

    changed_content = hash_tree(root)
    renamed = root / "doc-b/result.json"
    renamed.parent.mkdir(parents=True)
    first.rename(renamed)
    assert hash_tree(root) != changed_content
