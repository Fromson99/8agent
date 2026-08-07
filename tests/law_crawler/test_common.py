"""공통 파이프라인 — 파일명 복원·매직바이트·백오프·차단 감지. 네트워크 없음."""
from __future__ import annotations

import logging

import pytest

from sources.common import (
    BACKOFF_SECONDS,
    CrawlAborted,
    FetchError,
    HttpClient,
    decode_disposition_filename,
    detect_format,
    safe_filename,
)


# ---------------------------------------------------------------- 파일명 복원

def test_filename_euc_kr_raw_bytes():
    # KOFIA 실측 원문: EUC-KR 바이트가 헤더에 그대로 실려 온다
    cd = b'attachment; fileName="0000_[\xc2\xfc\xb0\xed 1].hwp";'.decode("latin-1")
    assert decode_disposition_filename(cd) == "0000_[참고 1].hwp"


def test_filename_percent_encoded_utf8():
    # FSS·KRX 실측 원문: 퍼센트인코딩된 UTF-8
    cd = 'attachment; filename="(%EB%B6%99%EC%9E%841) %EA%B8%B0%EC%97%85.pdf"'
    assert decode_disposition_filename(cd) == "(붙임1) 기업.pdf"


def test_filename_plain_ascii():
    assert decode_disposition_filename('attachment; filename="report.pdf"') == "report.pdf"


def test_filename_missing():
    assert decode_disposition_filename(None) is None
    assert decode_disposition_filename("inline") is None


def test_safe_filename_strips_separators():
    assert "/" not in safe_filename("a/b\\c:d.hwp")
    assert safe_filename("   ") == "unnamed"


# ---------------------------------------------------------------- 매직바이트

@pytest.mark.parametrize(
    "head,expected",
    [
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "hwp5(ole)"),
        (b"PK\x03\x04rest", "hwpx(zip)"),
        (b"%PDF-1.7", "pdf"),
        (b"\n\n<!DOCTYPE html><html>", "html"),
        (b"\x00\x01\x02\x03", "unknown"),
    ],
)
def test_detect_format(head, expected):
    assert detect_format(head) == expected


# ---------------------------------------------------------------- HttpClient

class FakeResponse:
    def __init__(self, status_code=200, content=b"ok", headers=None, url=""):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.url = url


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def request(self, method, url, **kw):
        self.calls += 1
        return self._responses.pop(0)


def _client(responses, sleeps):
    session = FakeSession(responses)
    logger = logging.getLogger("test.http")
    return HttpClient(session, logger, min_interval=0, sleep=sleeps.append), session


def test_backoff_recovers_after_429():
    sleeps: list[float] = []
    client, session = _client(
        [FakeResponse(429), FakeResponse(429), FakeResponse(200, b"data")], sleeps
    )
    resp = client.get("https://example.test/x")
    assert resp.status_code == 200
    assert session.calls == 3
    assert sleeps == [BACKOFF_SECONDS[0], BACKOFF_SECONDS[1]]   # 2s -> 8s


def test_backoff_exhausted_fails_single_document():
    sleeps: list[float] = []
    client, _ = _client([FakeResponse(503)] * 4, sleeps)
    with pytest.raises(FetchError):
        client.get("https://example.test/x")
    assert sleeps == list(BACKOFF_SECONDS)                      # 2s -> 8s -> 32s 후 포기


def test_forbidden_streak_aborts_whole_crawl():
    sleeps: list[float] = []
    client, _ = _client([FakeResponse(403)] * 3, sleeps)
    for _ in range(2):
        with pytest.raises(FetchError):
            client.get("https://example.test/x")
    with pytest.raises(CrawlAborted):
        client.get("https://example.test/x")


def test_forbidden_streak_resets_on_success():
    client, _ = _client(
        [FakeResponse(403), FakeResponse(403), FakeResponse(200), FakeResponse(403)], []
    )
    for _ in range(2):
        with pytest.raises(FetchError):
            client.get("https://example.test/x")
    assert client.get("https://example.test/x").status_code == 200
    with pytest.raises(FetchError):                              # 스트릭이 리셋됐으므로 중단 아님
        client.get("https://example.test/x")


def test_captcha_page_aborts():
    client, _ = _client([FakeResponse(200, "자동입력방지 문자를 입력하세요".encode())], [])
    with pytest.raises(CrawlAborted):
        client.get("https://example.test/x")
