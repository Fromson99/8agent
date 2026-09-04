"""공통 파이프라인: HTTP 클라이언트, 파일명 복원, 매직바이트, manifest IO.

불변 규칙 (docs/access_profile.md·site_survey.md 실측 근거):
- 동시 요청 1개, 요청 간 최소 1초
- 타임아웃 필수 — KOFIA 에 응답 없이 행업하는 엔드포인트가 실재한다
- 429/503 은 2s→8s→32s 백오프 3회, 연속 403 3회·캡차는 전체 중단
- 200 이어도 본문 검증 — 에러페이지가 200 으로 오는 사이트들이다
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import requests

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
COMMON_HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "ko-KR,ko;q=0.9"}

BACKOFF_SECONDS = (2.0, 8.0, 32.0)
FORBIDDEN_STREAK_LIMIT = 3
CAPTCHA_MARKERS = (b"captcha", b"CAPTCHA", b"\xec\x9e\x90\xeb\x8f\x99\xec\x9e\x85\xeb\xa0\xa5\xeb\xb0\xa9\xec\xa7\x80")  # "자동입력방지"


class CrawlAborted(RuntimeError):
    """차단 징후 — 전체 수집을 즉시 중단해야 한다 (계속 두드리면 IP 차단으로 번진다)."""


class FetchError(RuntimeError):
    """단일 문서 실패 — 전체는 계속 진행한다."""


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(COMMON_HEADERS)
    return s


def build_logger(log_dir: Path, source_id: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger(f"collect.{source_id}.{stamp}")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_dir / f"{source_id}_{stamp}.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(fh)
    return logger


class HttpClient:
    """직렬·간격 강제·백오프·차단감지가 붙은 요청 실행기. 모든 요청이 이걸 통과한다."""

    def __init__(
        self,
        session: requests.Session,
        logger: logging.Logger,
        min_interval: float = 1.0,
        timeout: float = 30.0,
        sleep=time.sleep,
    ) -> None:
        self.session = session
        self.logger = logger
        self.min_interval = min_interval
        self.timeout = timeout
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._forbidden_streak = 0
        self.request_count = 0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_error: Exception | None = None
        for attempt in range(len(BACKOFF_SECONDS) + 1):
            self._pace()
            started = time.monotonic()
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as e:
                self.request_count += 1
                self.logger.info("%s %s -> EXC %s", method, url, e)
                last_error = e
                if attempt < len(BACKOFF_SECONDS):
                    self._sleep(BACKOFF_SECONDS[attempt])
                    continue
                raise FetchError(f"요청 실패({e})") from e
            self.request_count += 1
            elapsed = (time.monotonic() - started) * 1000
            self.logger.info(
                "%s %s -> %d %dB %.0fms", method, url, resp.status_code, len(resp.content), elapsed
            )

            if resp.status_code == 403:
                self._forbidden_streak += 1
                if self._forbidden_streak >= FORBIDDEN_STREAK_LIMIT:
                    raise CrawlAborted(f"연속 403 {self._forbidden_streak}회: {url}")
                raise FetchError(f"403 Forbidden: {url}")
            self._forbidden_streak = 0

            if any(m in resp.content[:4096] for m in CAPTCHA_MARKERS):
                raise CrawlAborted(f"캡차 페이지 감지: {url}")

            if resp.status_code in (429, 503):
                if attempt < len(BACKOFF_SECONDS):
                    wait = BACKOFF_SECONDS[attempt]
                    self.logger.info("%d 응답, %.0fs 백오프 후 재시도", resp.status_code, wait)
                    self._sleep(wait)
                    continue
                raise FetchError(f"{resp.status_code} 지속: {url}")

            return resp
        raise FetchError(f"재시도 소진: {url} ({last_error})")

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self.request("POST", url, **kw)

    def _pace(self) -> None:
        if self._last_request_at is not None:
            wait = self.min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = time.monotonic()


# ---------------------------------------------------------------- 파일 판정/이름

def detect_format(head: bytes) -> str:
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "hwp5(ole)"
    if head.startswith(b"PK"):
        return "hwpx(zip)"
    if head.startswith(b"%PDF"):
        return "pdf"
    stripped = head.lstrip()[:64].lower()
    if stripped.startswith(b"<?xml"):
        return "xml"
    if stripped.startswith((b"<!doctype", b"<html", b"<script")):
        return "html"
    return "unknown"


_FILENAME_RE = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.I)


def decode_disposition_filename(cd_raw: str | None) -> str | None:
    """Content-Disposition 에서 파일명 복원.

    국내 기관 서버는 (a) EUC-KR 바이트를 그대로, (b) 퍼센트인코딩 UTF-8 로 보낸다.
    requests 는 헤더를 latin-1 로 디코딩해 주므로 되돌려서 판정한다.
    """
    if not cd_raw:
        return None
    m = _FILENAME_RE.search(cd_raw)
    if not m:
        return None
    token = m.group(1).strip()
    raw = token.encode("latin-1", errors="replace")
    if b"%" in raw:
        try:
            return unquote(token, encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def safe_filename(name: str, fallback: str = "unnamed") -> str:
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    # ext4 파일명 한계는 255"바이트" — 한글은 UTF-8 3바이트라 문자수 제한으로는 못 막는다
    # (실측: law.go.kr 별표 제목이 조문 인용까지 담아 400바이트를 넘는다)
    stem, dot, ext = name.rpartition(".")
    if not dot or len(ext) > 8:
        stem, ext = name, ""
    limit = 200 - (len(ext.encode("utf-8")) + 1 if ext else 0)
    trimmed = stem.encode("utf-8")[:limit].decode("utf-8", errors="ignore").strip(" .")
    name = f"{trimmed}.{ext}" if ext else trimmed
    return name or fallback


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- manifest

def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"collected_at": "", "source": "", "items": []}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["collected_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def manifest_item(manifest: dict, key: str) -> dict | None:
    for item in manifest["items"]:
        if item.get("name") == key:
            return item
    return None


def upsert_item(manifest: dict, item: dict) -> None:
    for i, existing in enumerate(manifest["items"]):
        if existing.get("name") == item.get("name"):
            manifest["items"][i] = item
            return
    manifest["items"].append(item)


def item_files_intact(item: dict, repo_root: Path) -> bool:
    """manifest 항목의 모든 파일이 존재하고 sha256 이 일치하는가 (네트워크 없음)."""
    if item.get("status") != "ok":
        return False
    entries: list[dict] = []
    if item.get("body_file"):
        entries.append({"file": item["body_file"], "sha256": item.get("body_sha256")})
    if item.get("body_html_file"):
        entries.append({"file": item["body_html_file"], "sha256": item.get("body_html_sha256")})
    entries.extend(item.get("attachments", []))
    if not entries:
        return False
    for e in entries:
        f = repo_root / e["file"]
        if not f.exists():
            return False
        expected = e.get("sha256")
        if expected and sha256_file(f) != expected:
            return False
    return True
