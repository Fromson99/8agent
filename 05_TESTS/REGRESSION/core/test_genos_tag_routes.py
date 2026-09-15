"""ADR-0341 ordinary routing contracts; synthetic files/parsers, no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.core import fitness_gate, parse_adapter, router, structurize
from lawrag.pipeline import genos_build as build


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def tagged_file(tmp_path):
    root = tmp_path / "raw"
    folder = root / "team" / "forms"
    folder.mkdir(parents=True)
    document = folder / "금소법 [별표 1].hwp"
    document.write_bytes(b"synthetic routing bytes; not a real HWP document")
    return root, document


@pytest.mark.parametrize(
    "sidecar,doc_binding,folder_binding,expected",
    [
        ("금소법", "금소법시행령", "표준투자권유준칙", "금소법"),
        (None, "금소법시행령", "표준투자권유준칙", "금소법시행령"),
        (None, None, "표준투자권유준칙", "표준투자권유준칙"),
        (None, None, None, None),
    ],
)
def test_explicit_tag_binding_priority(tagged_file, tmp_path, sidecar,
                                       doc_binding, folder_binding, expected):
    root, document = tagged_file
    if sidecar:
        save_json(document.with_name(document.name + ".genos.json"), {"doc_type": sidecar})
    mapping = {"docs": {}, "folders": {}}
    if doc_binding:
        mapping["docs"][build.sha(document)[:16]] = doc_binding
    if folder_binding:
        mapping["folders"]["team/forms"] = folder_binding
    bindings = tmp_path / "bindings.json"
    save_json(bindings, mapping)
    row = build.inventory(root, "external", bindings)["files"][0]
    assert row["doc_type"] == expected


def test_filename_alone_does_not_infer_doc_type(tagged_file):
    root, document = tagged_file
    row = build.inventory(root, "external")["files"][0]
    assert row["name"] == document.stem
    assert row["doc_type"] is None
    assert row["engine"] == ""


def test_folder_binding_is_exact_not_parent_inheritance(tagged_file, tmp_path):
    root, _ = tagged_file
    bindings = tmp_path / "bindings.json"
    save_json(bindings, {"folders": {"team": "금소법"}, "docs": {}})
    assert build.inventory(root, "external", bindings)["files"][0]["doc_type"] is None


def test_sidecar_folder_is_the_binding_lookup_key(tagged_file, tmp_path):
    root, document = tagged_file
    save_json(document.with_name(document.name + ".genos.json"), {"folder": "declared-folder"})
    bindings = tmp_path / "bindings.json"
    save_json(bindings, {"folders": {"declared-folder": "금소법"}, "docs": {}})
    row = build.inventory(root, "external", bindings)["files"][0]
    assert row["doc_type"] == "금소법"
    assert row["folder"] == "declared-folder"
    assert row["relative"] == document.relative_to(root).as_posix()


def test_unregistered_type_is_rejected_before_parsing(tagged_file, monkeypatch):
    root, document = tagged_file
    save_json(document.with_name(document.name + ".genos.json"), {"doc_type": "unregistered-test-type"})
    monkeypatch.setattr(parse_adapter, "parse", lambda *a, **kw: pytest.fail("inventory parsed a document"))
    with pytest.raises(router.UnregisteredDocType, match="unregistered-test-type"):
        build.inventory(root, "external")


def test_registered_type_missing_format_asset_is_rejected(tagged_file, tmp_path, monkeypatch):
    root, document = tagged_file
    save_json(document.with_name(document.name + ".genos.json"), {"doc_type": "금소법"})
    missing = tmp_path / "does-not-exist.format.json"
    monkeypatch.setattr(router.Route, "format_path", lambda self: missing)
    with pytest.raises(router.RouteAssetMissing, match="형식 파일이 없습니다"):
        build.inventory(root, "external")


@pytest.mark.parametrize("extension", [".hwp", ".hwpx", ".pdf"])
def test_docxstyle_rejects_other_suffixes(tmp_path, extension):
    document = tmp_path / ("source" + extension)
    document.write_bytes(b"synthetic bytes")
    save_json(document.with_name(document.name + ".genos.json"), {"engine": "docxstyle"})
    with pytest.raises(ValueError, match="docxstyle requires DOCX"):
        build.inventory(tmp_path, "external")


@pytest.mark.parametrize("extension", [".docx", ".doc"])
def test_docxstyle_allows_native_or_explicitly_converted_word(tmp_path, extension):
    document = tmp_path / ("source" + extension)
    document.write_bytes(b"synthetic bytes")
    save_json(document.with_name(document.name + ".genos.json"), {"engine": "docxstyle"})
    assert build.inventory(tmp_path, "external")["files"][0]["engine"] == "docxstyle"


def test_doc_type_and_engine_are_mutually_exclusive(tagged_file):
    root, document = tagged_file
    save_json(document.with_name(document.name + ".genos.json"),
              {"doc_type": "금소법", "engine": "induce"})
    with pytest.raises(ValueError, match="not both"):
        build.inventory(root, "external")


@pytest.mark.parametrize("extension,parser_name", [
    (".hwp", "parse_hwp"), (".hwpx", "parse_hwp"), (".docx", "parse_docx"),
])
def test_tagged_parser_and_format_low_score_is_advisory(tmp_path, monkeypatch,
                                                      extension, parser_name):
    """Real registry/from_format/export; only bytes-to-elements and score are fake.

    This checks dispatch and mechanical admission, not HWP/DOCX conversion quality.
    """
    root, out = tmp_path / "raw", tmp_path / "out"
    root.mkdir()
    out.mkdir()
    document = root / ("source" + extension)
    document.write_bytes(b"synthetic route fixture")
    save_json(document.with_name(document.name + ".genos.json"), {"doc_type": "금소법"})
    seen = []

    def synthetic_parser(path):
        seen.append(("parser", Path(path).suffix))
        return parse_adapter.ParseResult(
            path=str(path), doc_id=build.sha(Path(path))[:12],
            parser="synthetic-" + parser_name, born_digital=True,
            elements=[
                parse_adapter.Element(index=0, type="text", text="제1조(시험) 합성 본문입니다."),
                parse_adapter.Element(index=1, type="text", text="구조 연결을 확인하는 합성 문장입니다."),
            ],
        )

    original_structurize = structurize.run

    def tracked_structurize(parsed, fmt, glossary):
        seen.append(("format", fmt.doc_type, glossary.doc_type))
        return original_structurize(parsed, fmt, glossary)

    monkeypatch.setattr(parse_adapter, parser_name, synthetic_parser)
    monkeypatch.setattr(structurize, "run", tracked_structurize)
    monkeypatch.setattr(fitness_gate, "apply", lambda *a, **kw: fitness_gate.Fitness(
        score=0.1, passed=False, warnings=["synthetic advisory score"],
    ))
    plan = build.inventory(root, "external")
    messages = []
    with build.isolated(out):
        build.ingest_files(plan, out, messages.append)
        database, receipt = build.source_jobs(out, plan)

    did = plan["files"][0]["document_id"]
    meta = json.loads((out / "structure" / did / "meta.json").read_text())
    result = json.loads((out / "structure" / did / "result.json").read_text())
    assert seen == [("parser", extension), ("format", "금소법", "금소법")]
    assert meta["structured_by"].startswith("format:금소법@v")
    assert meta["passed"] is False and meta["score"] == 0.1
    assert result["fitness"]["passed"] is False
    assert result["parser"] == "synthetic-" + parser_name
    assert result["blocks"] and result["nodes"]
    assert receipt["document_ids"] == [did]
    assert any("점수" in message for message in messages)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM authoring_job").fetchone()[0] > 0

