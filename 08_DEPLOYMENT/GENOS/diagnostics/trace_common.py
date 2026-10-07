"""Read-only helpers for GENOS per-request JSON reports (stdlib only)."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterator


DEFAULT_ROOT = Path('/nfs-root/diamo/8-agent/rag-request-reports')
RUN_ID = re.compile(r'[a-f0-9]{32}\Z')
SCHEMA = 'genos-request-report-v1'


def paths(root: Path, run_id: str | None = None) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f'요청 기록 디렉터리가 없습니다: {root}')
    if run_id is not None and not RUN_ID.fullmatch(run_id):
        raise ValueError('run_id는 32자리 소문자 16진수여야 합니다')
    found = [path for path in root.glob('*/*.json')
             if path.is_file() and not path.is_symlink()
             and (run_id is None or path.name.startswith(run_id + '-'))]
    return sorted(found, key=lambda path: path.stat().st_mtime_ns, reverse=True)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA:
        raise ValueError(f'지원하지 않는 보고서 형식: {path}')
    return value


def latest(root: Path, run_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    found = paths(root, run_id)
    if not found:
        raise ValueError('조건에 맞는 요청 기록 JSON이 없습니다')
    return found[0], load(found[0])


def records(report: dict[str, Any], table: str) -> Iterator[dict[str, Any]]:
    journal = report.get('journal') or {}
    for entry in journal.get('timeline') or []:
        for item in entry.get('created_records') or []:
            if item.get('table') == table and isinstance(item.get('record'), dict):
                yield item['record']
    for item in (journal.get('state') or {}).get(table) or []:
        if isinstance(item, dict):
            yield item


def output(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
