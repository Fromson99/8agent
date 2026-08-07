"""수집기 자료형과 어댑터 계약.

소스마다 다른 것은 "목록을 어떻게 얻고 파일 URL을 어떻게 얻는가"뿐이다.
다운로드·재시도·저장·manifest 는 공통 파이프라인(collect.py + common.py) 소유.
설계 근거: docs/adapter_design.md, 실측 근거: docs/site_survey.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping, Protocol, runtime_checkable

import requests

Role = Literal["body", "attachment", "comparison_table"]


@dataclass(frozen=True)
class Target:
    source_id: str
    key: str                      # 출력 디렉터리명 (규정명)
    label: str                    # 소스 사이트에서의 정확한 규정명 (트리·검색 매칭 키)
    hints: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentRef:
    title: str
    url: str
    role: Role
    version_hint: str
    file_ext: str                 # 선언된 확장자 — 실제 형식은 매직바이트로 판정
    subdir: str = ""              # "별표서식" | "신구조문대비표" | ""
    method: str = "GET"
    data: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None


@dataclass
class FetchResult:
    status: Literal["ok", "error", "skipped"]
    file: Path | None = None
    sha256: str | None = None
    actual_format: str | None = None
    size: int = 0
    content_disposition_raw: str | None = None
    error: str | None = None


@runtime_checkable
class SourceAdapter(Protocol):
    source_id: str

    def session(self) -> requests.Session:
        """Phase 0 접속 프로파일이 적용된 세션."""
        ...

    def expand_targets(self, target: Target) -> list[Target]:
        """폴더형 대상을 개별 규정으로 전개. 기본은 [target] 그대로."""
        ...

    def discover(self, target: Target) -> list[DocumentRef]:
        """다운로드 참조 목록 반환. 파일 저장은 하지 않는다."""
        ...

    def metadata(self, target: Target) -> dict[str, str]:
        """discover 과정에서 확보한 버전 메타데이터 (manifest 기록용)."""
        ...
