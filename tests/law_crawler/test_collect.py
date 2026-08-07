"""collect 파이프라인 — 멱등 판정과 200 위장 에러페이지 방어. 네트워크 없음."""
from __future__ import annotations

import logging

import collect
from sources.base import DocumentRef
from sources.common import HttpClient, sha256_file
from tests.law_crawler.test_common import FakeResponse, FakeSession


def _client(responses):
    return HttpClient(FakeSession(responses), logging.getLogger("test.collect"),
                      min_interval=0, sleep=lambda s: None)


def _ref(ext=".hwp", role="attachment"):
    return DocumentRef(title="테스트 별표", url="https://example.test/download",
                       role=role, version_hint="1", file_ext=ext)


def test_fetch_ref_saves_file_with_decoded_name(tmp_path):
    cd = b'attachment; fileName="0000_[\xc2\xfc\xb0\xed 1].hwp";'.decode("latin-1")
    client = _client([FakeResponse(200, b"\xd0\xcf\x11\xe0rest", {"Content-Disposition": cd})])
    result = collect.fetch_ref(client, _ref(), tmp_path)
    assert result.status == "ok"
    assert result.file.name == "0000_[참고 1].hwp"
    assert result.actual_format == "hwp5(ole)"
    assert result.sha256 == sha256_file(result.file)


def test_fetch_ref_rejects_html_masquerading_as_file(tmp_path):
    # KOFIA: 없는 경로가 307 → 에러페이지(200) 로 온다. 저장하면 코퍼스가 오염된다.
    client = _client([FakeResponse(200, b"<!DOCTYPE html><html>error</html>")])
    result = collect.fetch_ref(client, _ref(ext=".hwp"), tmp_path)
    assert result.status == "error"
    assert "HTML" in result.error
    assert not any(tmp_path.iterdir())


def test_fetch_ref_falls_back_to_title_when_no_disposition(tmp_path):
    client = _client([FakeResponse(200, b"%PDF-1.7 data")])
    result = collect.fetch_ref(client, _ref(ext=".pdf"), tmp_path)
    assert result.status == "ok"
    assert result.file.name == "테스트 별표.pdf"


def test_item_files_intact_detects_missing_and_modified(tmp_path):
    from sources.common import item_files_intact
    f = tmp_path / "corpus" / "kofia" / "규정" / "본문.hwp"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"\xd0\xcf\x11\xe0data")
    item = {
        "status": "ok",
        "body_file": "corpus/kofia/규정/본문.hwp",
        "body_sha256": sha256_file(f),
        "attachments": [],
    }
    assert item_files_intact(item, tmp_path)            # 무결 → skip 가능
    f.write_bytes(b"changed")
    assert not item_files_intact(item, tmp_path)        # 해시 불일치 → 재수집
    f.unlink()
    assert not item_files_intact(item, tmp_path)        # 파일 없음 → 재수집
    assert not item_files_intact({"status": "error", "attachments": []}, tmp_path)
