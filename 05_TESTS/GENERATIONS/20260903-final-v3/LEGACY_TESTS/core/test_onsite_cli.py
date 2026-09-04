from pathlib import Path


def test_stage_copies_supported_files_recursively(tmp_path: Path):
    from lawrag.pipeline.onsite import _stage

    source = tmp_path / "A"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "rule.pdf").write_bytes(b"pdf")
    (source / "ignore.txt").write_text("no", encoding="utf-8")
    inbox = tmp_path / "inbox"

    staged = _stage(source, inbox, "new")
    assert staged == [inbox / "new" / "nested" / "rule.pdf"]
    assert staged[0].read_bytes() == b"pdf"
    assert (source / "nested" / "rule.pdf").exists()


def test_private_url_detection(monkeypatch):
    from lawrag.pipeline.onsite import _is_private_url

    assert _is_private_url("http://127.0.0.1:8000/v1")
    monkeypatch.setenv("ONSITE_ALLOWED_HOSTS", "llm.intra")
    assert _is_private_url("http://llm.intra/v1")
    assert not _is_private_url("https://api.anthropic.com")
