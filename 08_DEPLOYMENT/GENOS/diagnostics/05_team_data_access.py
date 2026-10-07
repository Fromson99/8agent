#!/usr/bin/env python3
"""Show request team scope, source reads, and a matching shared generation catalogue."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3

from trace_common import DEFAULT_ROOT, latest, load, output, paths, records


SHARED_ROOT = Path('/nfs-root/diamo/8-agent')
TEAM = re.compile(r'[A-Za-z0-9_-]+_team\Z')


def _request_body(report: dict) -> dict:
    request = report.get('request') or {}
    if not isinstance(request, dict):
        return {}
    nested = request.get('json')
    return nested if isinstance(nested, dict) else request


def _result_body(report: dict) -> dict:
    result = report.get('result') or {}
    body = result.get('body') if isinstance(result, dict) else None
    return body if isinstance(body, dict) else {}


def _memberships(raw: str) -> set[str]:
    metadata = json.loads(raw or '{}').get('document_metadata') or {}
    if not isinstance(metadata, dict):
        return set()
    locations = [metadata, *(metadata.get('aliases') or [])]
    return {item['team'] for item in locations
            if isinstance(item, dict) and isinstance(item.get('team'), str)
            and TEAM.fullmatch(item['team'])}


def _generation(path: Path, *, expected_id: str | None, expected_sha: str | None,
                team_id: str | None, scope: set[str], read_ids: list[str], limit: int) -> dict:
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f'세대 디렉터리가 없거나 심볼릭 링크입니다: {path}')
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 'term-source-generation-v1':
        raise ValueError('지원하지 않는 generation manifest')
    store = path / 'store.sqlite'
    if not store.is_file() or store.is_symlink():
        raise ValueError(f'세대 store.sqlite를 읽을 수 없습니다: {store}')
    with sqlite3.connect(store.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        rows = db.execute('SELECT document_id,name,json FROM document ORDER BY name,document_id').fetchall()
    docs = [(did, name, _memberships(raw)) for did, name, raw in rows]
    known = {did for did, _, _ in docs}
    names = {did: name for did, name, _ in docs}
    matching = [(did, name, teams) for did, name, teams in docs
                if team_id is None or team_id in teams]
    id_match = expected_id is None or manifest.get('generation_id') == expected_id
    sha_match = expected_sha is None or manifest.get('store_sha256') == expected_sha
    return {
        'path': str(path), 'manifest_read': True, 'store_sqlite_read': True,
        'generation_id': manifest.get('generation_id'),
        'matches_request_generation_id': id_match,
        'matches_request_store_sha256': sha_match,
        'same_generation_as_request': id_match and sha_match and expected_id is not None and expected_sha is not None,
        'document_count': len(docs),
        'team_document_counts': dict(sorted(Counter(team for _, _, teams in docs for team in teams).items())),
        'unassigned_document_count': sum(not teams for _, _, teams in docs),
        'selected_team_document_count': len(matching),
        'selected_team_documents_shown': [{'document_id': did, 'name': name}
                                          for did, name, _ in matching[:limit]],
        'selected_team_documents_truncated': len(matching) > limit,
        'source_text_read_documents': [{'document_id': did, 'name': names.get(did)} for did in read_ids],
        'request_scope_ids_missing_from_generation': sorted(scope - known),
        'request_scope_ids_outside_team': sorted(
            scope - {did for did, _, _ in matching}) if team_id is not None else [],
        'note': '코드스페이스의 NFS 읽기 검사입니다. 실제 코드서빙 경로는 GENOS_GENERATION 설정과 대조하세요.',
    }


def _candidates(shared_root: Path, generation_id: str | None, store_sha: str | None) -> list[Path]:
    if not generation_id or not store_sha or not shared_root.is_dir():
        return []
    found = []
    for pattern in ('term-releases/*/*/generation/manifest.json', 'generations/*/manifest.json'):
        for path in shared_root.glob(pattern):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                manifest = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if (manifest.get('generation_id') == generation_id
                    and manifest.get('store_sha256') == store_sha):
                found.append(path.parent)
    return sorted(set(found))


def summarize(report: dict, *, generation: Path | None, shared_root: Path, limit: int) -> dict:
    request = _request_body(report)
    body = _result_body(report)
    query = body.get('query') or {}
    answer = body.get('answer') or {}
    retrieval = body.get('retrieval') or {}
    selection = body.get('selection') or {}
    scope = set((query.get('scope') or {}).get('document_version_ids') or [])
    team_id = request.get('team_id')
    evidence = list(records(report, 'evidence_unit'))
    observed = list(records(report, 'observation'))
    read_ids = sorted({row['document_id'] for row in evidence if isinstance(row.get('document_id'), str)})
    selected = selection.get('selected') or []
    selected_ids = sorted({row['document_id'] for row in selected
                           if isinstance(row, dict) and isinstance(row.get('document_id'), str)})
    generation_id = query.get('generation_id') or answer.get('generation_id')
    store_sha = answer.get('source_store_sha256')
    bundle = ((body.get('assembly') or {}).get('term_agent') or {}).get('source_bundle') or {}
    candidates = _candidates(shared_root, generation_id, store_sha) if generation is None else []
    chosen = generation or (candidates[0] if len(candidates) == 1 else None)
    catalogue = _generation(chosen, expected_id=generation_id, expected_sha=store_sha,
                            team_id=team_id, scope=scope, read_ids=read_ids, limit=limit) if chosen else None
    if team_id is None:
        team_status = 'NO_TEAM_FILTER'
    elif catalogue is None or not catalogue['same_generation_as_request']:
        team_status = 'REQUESTED_BUT_GENERATION_UNVERIFIED'
    elif catalogue['request_scope_ids_outside_team'] or catalogue['request_scope_ids_missing_from_generation']:
        team_status = 'SCOPE_MISMATCH'
    else:
        team_status = 'FILTER_CONFIRMED_FOR_REQUEST_SCOPE'
    return {
        'request_id': report.get('request_id'), 'run_id': report.get('run_id'),
        'api_type': report.get('api_type'), 'request_team_id': team_id,
        'team_filter_status': team_status,
        'request_generation_id': generation_id,
        'rag_implementation': (retrieval.get('term_agent') or {}).get('implementation'),
        'request_scope_document_count': len(scope),
        'request_scope_document_ids_shown': sorted(scope)[:limit],
        'request_scope_document_ids_truncated': len(scope) > limit,
        'retrieval_candidate_count': len(retrieval.get('candidates') or []),
        'selected_document_ids': selected_ids,
        'source_bundle_status': bundle.get('status'),
        'source_bundle_documents': [{'document_id': row.get('document_id'),
                                     'name': row.get('document_name')}
                                    for row in (bundle.get('sources') or [])[:limit]
                                    if isinstance(row, dict)],
        'source_text_evidence_count': len(evidence),
        'source_text_read_document_ids': read_ids,
        'source_text_access_status': 'SOURCE_TEXT_RECORDED' if evidence else 'NO_SOURCE_TEXT_RECORDED',
        'tool_observation_counts': dict(sorted(Counter(
            f"{row.get('tool')}:{row.get('status')}" for row in observed).items())),
        'matching_nfs_generation_candidates': [str(path) for path in candidates],
        'generation_catalogue': catalogue or {'status': 'NOT_CHECKED',
            'reason': '정확히 일치하는 NFS 세대를 찾지 못했습니다. --generation에 코드서빙 GENOS_GENERATION 경로를 지정하세요.'},
        'note': '팀은 검색 범위 선택이며 접근권한 부여가 아닙니다. 파일 읽기와 실제 원문 사용을 구분해 표시합니다.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='요청별 공유 로그 디렉터리')
    parser.add_argument('--run-id', help='특정 요청의 32자리 run_id; 생략하면 최신 요청')
    parser.add_argument('--generation', type=Path, help='코드서빙 GENOS_GENERATION의 정확한 경로')
    parser.add_argument('--shared-root', type=Path, default=SHARED_ROOT,
                        help='세대 자동 탐색용 NFS 루트')
    parser.add_argument('--limit', type=int, default=30, help='표시할 문서 최대 수')
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error('--limit는 1부터 500까지입니다')
    try:
        if args.run_id:
            path, report = latest(args.root, args.run_id)
        else:
            selected = None
            for path in paths(args.root):
                report = load(path)
                if (report.get('api_type') in ('LEGAL_AGENT', 'ELS_QUERY', 'RAG_ASK')
                        and (_result_body(report).get('query') or {}).get('generation_id')):
                    selected = path, report
                    break
            if selected is None:
                raise ValueError('세대가 기록된 LEGAL_AGENT 요청이 없습니다; --run-id를 지정하세요')
            path, report = selected
        output({'report_file': str(path), **summarize(report, generation=args.generation,
                                                    shared_root=args.shared_root, limit=args.limit)})
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
