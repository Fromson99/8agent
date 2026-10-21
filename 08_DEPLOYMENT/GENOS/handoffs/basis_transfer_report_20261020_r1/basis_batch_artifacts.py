"""Read-only batch reports and portable additive SQLite relation bundles."""
import argparse
from contextlib import closing, contextmanager
from copy import deepcopy
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import uuid
import zipfile

from semantic_runtime.basis_links.contracts import digest, encoded, now, require, visible, BasisError
from semantic_runtime.basis_links.repository import Repository, DDL
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.resolver import retrieval_role, snapshot, targets
from semantic_runtime.state_sqlite import readonly, connect, network_storage
from semantic_runtime.storage import Store

SCHEMA = 'basis-batch-transfer-v1'
MARKER = {'schema_version': 'basis-shared-sqlite-v1', 'database': 'authority.sqlite'}
MAX_BYTES = 128 * 1024 * 1024
MAX_LINKS = 10000


def emit(event, **fields):
    print(encoded({'event': event, 'at': now(), **fields}), flush=True)


def plain(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'TRANSFER_PATH', '파일 또는 상위 경로가 심볼릭 링크입니다.')
    return path


def read_json(path):
    path = plain(path)
    require(path.stat().st_size <= MAX_BYTES, 'TRANSFER_SIZE', '파일 크기 한도를 초과했습니다.')
    return json.loads(path.read_text('utf-8'))


def atomic(path, value):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('x', encoding='utf-8') as stream:
            os.chmod(tmp, 0o600)
            stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def signed(value, key):
    require(value.get(key) == digest({k: v for k, v in value.items() if k != key}),
            'TRANSFER_HASH', '계획·상태·묶음 해시가 다릅니다.')
    return value


def source_pin(store):
    return {'generation_id': store.manifest['generation_id'],
            'manifest_sha256': hashlib.sha256((store.path / 'manifest.json').read_bytes()).hexdigest(),
            'store_sha256': store.manifest['store_sha256'], 'selection_sha256': store.selection.fingerprint}


@contextmanager
def source(generation, pin, who, config=None):
    # This is a narrow linked-row audit, not a replacement for serving generation validation.
    with closing(Store(plain(generation), verify=False)) as store:
        store.selection.require_latest()
        require(source_pin(store) == pin, 'TRANSFER_GENERATION', '원문 세대·검색 선택 필터가 다릅니다.')
        # Match the existing metadata team rule on the authorized IDs only.
        # prepared_catalogue() deliberately hashes the entire source database;
        # this linked-row audit does not claim that whole-generation proof.
        from semantic_runtime.team_scope import validate_team_id, bind_projected_teams
        from semantic_runtime.folder_navigation import load_origin_projection
        validate_team_id(who['team_id'])
        projection = load_origin_projection(config[0], config[1], store) if config else None
        bind_projected_teams(store, projection)
        allowed = []
        for did in who['document_ids']:
            row = store.db.execute('SELECT json FROM document WHERE document_id=?', (did,)).fetchone()
            if row is None:
                continue
            meta = json.loads(row[0]).get('document_metadata') or {}
            teams = {v.get('team') for v in [meta, *meta.get('aliases', [])] if isinstance(v, dict)}
            teams = getattr(store, '_projected_teams', {}).get(did, teams)
            if who['team_id'] in teams:
                allowed.append(did)
        scoped = {**who, 'document_ids': sorted(set(who['document_ids']) & set(allowed))}
        yield SourcePort(store, config), scoped
        store.check_unchanged()


@contextmanager
def authority(path, write=False):
    path = plain(path)
    repo = object.__new__(Repository)
    repo.db = connect(path) if write else readonly(path)
    repo.db.row_factory = sqlite3.Row
    repo.sqlite_document_lookup = True
    try:
        if write:
            repo.db.executescript(DDL)
            with repo.transaction():
                # Never silently backfill an older nonempty authority.
                if not repo.db.execute('SELECT 1 FROM basis_lookup_version WHERE version=1').fetchone():
                    require(not repo.db.execute('SELECT 1 FROM basis_head LIMIT 1').fetchone(),
                            'TRANSFER_SCHEMA', '기존 원장의 조항 조회 색인 이행이 먼저 필요합니다.')
                    repo.db.execute('INSERT INTO basis_lookup_version VALUES(1)')
        require(repo.db.execute('SELECT 1 FROM basis_lookup_version WHERE version=1').fetchone(),
                'TRANSFER_SCHEMA', 'R3 관계 조회 스키마가 필요합니다.')
        yield repo
    finally:
        repo.close()


def batch_run_ids(plan):
    who = {k: plan['binding']['principal'][k] for k in ('user_id', 'team_id')}
    return {digest([who, 'basis-batch:' + plan['batch_id'],
                    'basis-batch:' + digest([plan['batch_id'], d['document_id']])])[:32]
            for d in plan['documents']}


def sibling(name):
    spec = importlib.util.spec_from_file_location('_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def captured_repository(path, json_candidates=False):
    if json_candidates:
        with closing(sibling('basis_batch_candidates').JsonRepository(path)) as repo:
            yield repo
    else:
        with authority(path) as repo:
            repo.db.execute('BEGIN')
            try:
                yield repo
            finally:
                repo.db.rollback()


def capture(job, generation, runtime, config=None):
    """No app boot, batch lock, source write, model call, or full source checksum."""
    job = plain(job)
    plan = signed(read_json(job / 'PLAN.json'), 'plan_sha256')
    require(plan.get('schema_version') == 'basis-batch-v1', 'TRANSFER_PLAN', '지원하지 않는 배치입니다.')
    state = signed(read_json(job / 'STATE.json'), 'state_sha256') if (job / 'STATE.json').exists() else {}
    require(not state or state['plan_sha256'] == plan['plan_sha256'], 'TRANSFER_STATE', '다른 배치의 상태입니다.')
    who = plan['binding']['principal']
    pin = {k: plan['binding'][k] for k in ('generation_id', 'manifest_sha256', 'store_sha256', 'selection_sha256')}
    ids = batch_run_ids(plan)
    value = {'schema_version': SCHEMA, 'batch_id': plan['batch_id'], 'plan_sha256': plan['plan_sha256'],
             'state_sha256': state.get('state_sha256'), 'batch_status': state.get('status', 'not_started'),
             'captured_at': now(), 'documents': deepcopy(plan['documents']), 'document_states': state.get('documents', {}),
             'source': pin, 'principal': who, 'items': [], 'lineage': [], 'document_hashes': {},
             'quality_certified': False}
    candidate = plan.get('candidate_storage')
    if candidate:
        require(candidate.get('kind') == 'json-candidates-v1' and
                plain(candidate['path']) == job / 'CANDIDATES.json',
                'TRANSFER_CANDIDATES', 'JSON 후보 저장 경로가 계획과 다릅니다.')
        path = job / 'CANDIDATES.json'
    else:
        path = plain(Path(runtime) / 'basis-links/authority.sqlite')
    value['storage'] = 'json_candidates_not_published' if candidate else 'legacy_sqlite_already_published'
    with source(generation, pin, who, config) as (sources, scoped):
        require(all(d['document_id'] in scoped['document_ids'] for d in plan['documents']),
                'TRANSFER_SCOPE', '배치 내규의 현재 접근 권한이 다릅니다.')
        if path.exists():
            with captured_repository(path, bool(candidate)) as repo:
                seen = set()
                size = 0
                if candidate:
                    # User-fixed links may concern a latest visible document outside
                    # the model pilot's small selection. Extend only this report;
                    # the running batch PLAN/STATE must stay immutable.
                    known = {d['document_id'] for d in value['documents']}
                    for link in repo.links(who['team_id']):
                        origin = repo.history(link['link_id'])['revisions'][0].get('provenance', {})
                        if (origin.get('type') == 'USER_SELECTION'
                                and origin.get('method') == 'USER_FIXED_RISK_V1'
                                and origin.get('plan_sha256') == plan['plan_sha256']):
                            require(visible(link, scoped), 'TRANSFER_SCOPE', '확정 연결의 현재 문서 권한이 다릅니다.')
                            for end in link['internal']:
                                if end['document_id'] not in known:
                                    value['documents'].append({'document_id': end['document_id'],
                                        'name': end['document_name'], 'selection_reason': 'user_fixed_links'})
                                    known.add(end['document_id'])
                for document in value['documents']:
                    for link in repo.links_for_document(who['team_id'], document['document_id']):
                        if link['link_id'] in seen:
                            continue
                        seen.add(link['link_id'])
                        history = repo.history(link['link_id'])
                        first = history['revisions'][0]
                        origin = first.get('provenance', {})
                        fixed_origin = (candidate and origin.get('type') == 'USER_SELECTION'
                                        and origin.get('method') == 'USER_FIXED_RISK_V1'
                                        and origin.get('plan_sha256') == plan['plan_sha256'])
                        batch_origin = origin.get('method') == 'BATCH_DISCOVERY_V1' and origin.get('run_id') in ids
                        if not (fixed_origin or batch_origin):
                            continue
                        require(all(visible(r, scoped) for r in history['revisions']),
                                'TRANSFER_SCOPE', '관계 이력의 문서 권한이 다릅니다.')
                        binding = repo.binding(link['link_id'], link['revision'], sources.generation)
                        from semantic_runtime.basis_links.temporal import applicability
                        temporal = applicability(repo, binding or link)
                        item = {'link': link, 'binding': binding, 'history': history,
                                'applicability': temporal}
                        size += len(encoded(item).encode())
                        require(size < MAX_BYTES and len(value['items']) < MAX_LINKS,
                                'TRANSFER_SIZE', '한 번에 내보낼 관계 수·크기 한도를 초과했습니다.')
                        value['items'].append(item)
                dids = sorted({e['document_id'] for i in value['items'] for group in ('revisions', 'bindings')
                               for r in i['history'][group] for side in ('internal', 'external') for e in r[side]})
                for did in dids:
                    line = repo.lineage(did)
                    if line:
                        value['lineage'].append(line)
            # Release the authority snapshot before reading source clauses on NFS.
            # In DELETE journal mode, this keeps the writer's lock wait short.
            verified = set()
            for index, item in enumerate(value['items'], 1):
                binding = item['binding']
                check = {'status': 'verified'}
                try:
                    require(binding is not None and binding['status'] == 'current',
                            'TRANSFER_BINDING', '현재 세대의 원문 위치가 없습니다.')
                    for end in binding['internal'] + binding['external']:
                        key = digest(end)
                        if key not in verified:
                            sources.verify(end, scoped)
                            verified.add(key)
                except BasisError as exc:
                    if exc.code == 'BASIS_SCOPE':
                        raise
                    check = {'status': 'failed', 'code': exc.code, 'message': str(exc)}
                item['source_check'] = check
                item['retrievable'] = (check['status'] == 'verified' and retrieval_role(item['link']) is not None
                                       and item['applicability']['priority_eligible'])
                if index % 25 == 0:
                    emit('basis.artifacts.source_progress', checked=index, total=len(value['items']))
            for did in dids:
                row = sources.store.db.execute('SELECT * FROM document WHERE document_id=?', (did,)).fetchone()
                require(row is not None, 'TRANSFER_SOURCE', '연결 문서가 없습니다.')
                value['document_hashes'][did] = digest(dict(row))
        sources.store.check_unchanged()
    value['items'].sort(key=lambda x: (x['link']['internal'][0]['document_name'], x['link']['link_id']))
    value['snapshot_sha256'] = digest(value)
    emit('basis.artifacts.snapshot', batch_status=value['batch_status'], links=len(value['items']),
         snapshot_sha256=value['snapshot_sha256'], model_calls=0, full_source_hash=False)
    return value


def report(value, path):
    # Loading the sibling also supports the exact same module in the standalone handoff.
    require(Path(path).suffix.lower() == '.html', 'TRANSFER_OUTPUT', '보고서 출력은 .html 파일이어야 합니다.')
    renderer = sibling('basis_batch_report')
    atomic(path, renderer.render(value))
    emit('basis.artifacts.html', path=str(Path(path).resolve()), links=len(value['items']))


def literal(value):
    if type(value) is int:
        return str(value)
    require(isinstance(value, str) and '\0' not in value, 'TRANSFER_SQL', 'SQL 값이 잘못되었습니다.')
    return "'" + value.replace("'", "''") + "'"


def rows(item):
    link = item['link']
    yield 'basis_head', [link['link_id'], link['team_id'], link['revision']]
    for v in item['history']['revisions']:
        yield 'basis_revision', [v['link_id'], v['revision'], encoded(v), digest(v)]
    for v in item['history']['bindings']:
        yield 'basis_binding', [v['binding_id'], v['link_id'], v['link_revision'],
                                v['generation_id'], encoded(v), digest(v)]
    for v in item['history']['events']:
        yield 'basis_event', [v['event_id'], v['link_id'], encoded(v), digest(v)]
    documents = {e['document_id'] for group in ('revisions', 'bindings')
                 for v in item['history'][group] for side in ('internal', 'external') for e in v[side]}
    for did in sorted(documents):
        yield 'basis_document_lookup', [link['link_id'], did]


def sql(value):
    # The required UDF is installed only after the runner verifies sources and all conflicts.
    result = ['-- Run with APPLY_RELATIONS.txt apply. Direct sqlite3 import is intentionally refused.',
              'SELECT basis_transfer_guard(' + literal(value['snapshot_sha256']) + ');']
    for v in value['lineage']:
        result.append('INSERT INTO basis_lineage SELECT ' +
                      ','.join(map(literal, [v['version_id'], v['family_id'], encoded(v), digest(v)])) +
                      ' WHERE NOT EXISTS(SELECT 1 FROM basis_lineage WHERE version_id=' + literal(v['version_id']) + ');')
    for item in value['items']:
        for table, values in rows(item):
            result.append('INSERT INTO ' + table + ' SELECT ' + ','.join(map(literal, values)) +
                          ' WHERE EXISTS(SELECT 1 FROM temp.transfer_insert WHERE link_id=' +
                          literal(item['link']['link_id']) + ');')
    return '\n'.join(result) + '\n'


def validate(value, sources, who):
    signed(value, 'snapshot_sha256')
    require(value.get('schema_version') == SCHEMA and 0 < len(value['items']) <= MAX_LINKS,
            'TRANSFER_EMPTY', '이관할 연결이 없거나 지원하지 않는 묶음입니다.')
    seen = set()
    for did, expected in value['document_hashes'].items():
        require(did in who['document_ids'], 'TRANSFER_SCOPE', '연결 문서의 현재 팀 범위가 다릅니다.')
        row = sources.store.db.execute('SELECT * FROM document WHERE document_id=?', (did,)).fetchone()
        require(row is not None and digest(dict(row)) == expected,
                'TRANSFER_METADATA', '연결 문서의 원문·판본·분류 메타데이터가 다릅니다.')
    for v in value['lineage']:
        from semantic_runtime.basis_links.temporal import validate_lineage
        validate_lineage(v)
        require(v['version_id'] in value['document_hashes'] and
                sources.document_hash(v['version_id']) == v['source_artifact_hash'],
                'TRANSFER_LINEAGE', '판본 기록과 원문 해시가 다릅니다.')
    for item in value['items']:
        link = item['link']
        history = item['history']
        require(link['link_id'] not in seen and history['revisions'][-1] == link,
                'TRANSFER_HISTORY', '중복 ID 또는 이력 head가 다릅니다.')
        seen.add(link['link_id'])
        require([v['revision'] for v in history['revisions']] == list(range(1, link['revision'] + 1)),
                'TRANSFER_HISTORY', '연속된 관계 이력이 필요합니다.')
        for v in history['revisions']:
            require(v['link_id'] == link['link_id'] and visible(v, who),
                    'TRANSFER_SCOPE', '이력의 관계 ID 또는 권한이 다릅니다.')
            require(v['schema_version'] == 'basis-link-v1' and
                    v['status'] in ('PROPOSED', 'APPROVED', 'REJECTED', 'REVOKED'),
                    'TRANSFER_HISTORY', '지원하지 않는 관계 상태입니다.')
            for side in ('internal', 'external'):
                require(v[side] and all(e['side'] == side for e in v[side]),
                        'TRANSFER_SIDE', '내규·외규 구분이 다릅니다.')
                for end in v[side]:
                    sources.verify(end, who)
                    require(end['document_id'] in value['document_hashes'],
                            'TRANSFER_METADATA', '연결 문서 메타데이터 지문이 없습니다.')
        for v in history['bindings']:
            require(v['link_id'] == link['link_id'] and 1 <= v['link_revision'] <= link['revision'] and
                    v['generation_id'] == sources.generation and
                    v['binding_id'] == digest([v['link_id'], v['link_revision'], v['generation_id']]),
                    'TRANSFER_BINDING', '같은 원문 세대의 관계 결속만 이관할 수 있습니다.')
            for end in v['internal'] + v['external']:
                sources.verify(end, who)
        require(item['binding'] in history['bindings'] and
                item['binding']['link_revision'] == link['revision'] and item['binding']['status'] == 'current',
                'TRANSFER_BINDING', '현재 원문 결속이 다릅니다.')
        require(all(e['link_id'] == link['link_id'] and 1 <= e['revision'] <= link['revision']
                    for e in history['events']), 'TRANSFER_HISTORY', '사건 이력이 다릅니다.')
        require({e['revision'] for e in history['events']} >= set(range(1, link['revision'] + 1)),
                'TRANSFER_HISTORY', '관계 revision의 사건 기록이 없습니다.')
    sources.store.check_unchanged()


def decisions(repo, value):
    inserted, skipped = [], []
    if repo:
        for v in value['lineage']:
            old = repo.lineage(v['version_id'])
            require(old is None or old == v, 'TRANSFER_LINEAGE', '운영의 판본 기록과 충돌합니다.')
    for item in value['items']:
        ident = item['link']['link_id']
        old = repo.head(ident) if repo else None
        if old is None:
            inserted.append(ident)
        else:
            require(old == item['link'] and repo.history(ident) == item['history'],
                    'TRANSFER_CONFLICT', '운영에 같은 ID의 다른 상태·이력이 있습니다: ' + ident)
            expected_docs = {r[1][1] for r in rows(item) if r[0] == 'basis_document_lookup'}
            actual_docs = {r[0] for r in repo.db.execute('SELECT document_id FROM basis_document_lookup WHERE link_id=?', (ident,))}
            require(expected_docs <= actual_docs, 'TRANSFER_INDEX', '기존 관계의 문서 조회 색인이 누락되었습니다.')
            skipped.append(ident)
    return inserted, skipped


def execute_sql(db, script):
    statement = ''
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ''
    require(not statement.strip(), 'TRANSFER_SQL', '미완성 SQL 문입니다.')


def receipt_key(value, action):
    return 'basis-transfer:' + action + ':' + value['snapshot_sha256']


def verify_consumer(repo, sources, who, value):
    service = Service(repo, sources)
    for item in value['items']:
        link = item['link']
        require(repo.head(link['link_id']) == link, 'TRANSFER_CONSUMER', '저장된 관계가 다릅니다.')
        for end in link['internal']:
            found = repo.links_for_document(who['team_id'], end['document_id'])
            require(link in found, 'TRANSFER_INDEX', '대사 문서 조회 색인에 연결이 없습니다.')
        # Actual resolver, no model/service boot. Revoked/rejected links must remain excluded.
        view = snapshot(service, who, sorted({e['document_id'] for e in link['internal']}))
        view['items'] = [r for r in view['items'] if r['link']['link_id'] == link['link_id']]
        view['snapshot_hash'] = digest({k: v for k, v in view.items() if k != 'snapshot_hash'})
        actual = targets(service, who, view)
        eligible = any(r['applicability']['priority_eligible'] for r in view['items'])
        require(bool(actual) == (bool(retrieval_role(link)) and eligible), 'TRANSFER_CONSUMER', '대사 소비자의 조회 결과가 다릅니다.')


def marker(runtime):
    path = plain(Path(runtime) / 'basis-links/SQLITE_ENABLED.json')
    if path.exists():
        require(read_json(path) == MARKER, 'TRANSFER_MARKER', '다른 관계 저장소 설정이 있습니다.')
    else:
        atomic(path, MARKER)


def apply(value, script, generation, runtime, *, check=False, hook=None, config=None):
    require(value.get('import_review', {}).get('decision') == 'APPROVE_IMPORT',
            'TRANSFER_REVIEW_REQUIRED', 'HTML 검토 후 review --all 또는 review --ids로 적용 대상을 선택하세요.')
    require(script == sql(value), 'TRANSFER_SQL', 'SQL과 연결 데이터가 다릅니다.')
    path = plain(Path(runtime) / 'basis-links/authority.sqlite')
    mp = path.parent / 'SQLITE_ENABLED.json'
    if mp.exists():
        require(read_json(mp) == MARKER, 'TRANSFER_MARKER', '기존 관계 저장소 설정이 다릅니다.')
    with source(generation, value['source'], value['principal'], config) as (sources, who):
        validate(value, sources, who)
        if check and not path.exists():
            inserted, skipped = decisions(None, value)
            return {'status': 'ready', 'insert': len(inserted), 'skip': len(skipped), 'source_verified': 'linked_rows'}
        with authority(path, write=not check) as repo:
            if check:
                repo.db.execute('BEGIN')
                inserted, skipped = decisions(repo, value)
                repo.db.rollback()
                return {'status': 'ready', 'insert': len(inserted), 'skip': len(skipped), 'source_verified': 'linked_rows'}
            with repo.transaction():
                require(repo.receipt(receipt_key(value, 'rollback'), value['snapshot_sha256']) is None,
                        'TRANSFER_ROLLED_BACK', '이미 원복한 묶음입니다. 다시 활성화하려면 별도 검토가 필요합니다.')
                saved = repo.receipt(receipt_key(value, 'apply'), value['snapshot_sha256'])
                if saved:
                    # After response loss, same IDs and state must still be present.
                    decisions(repo, value)
                    result = {**saved, 'status': 'already_applied'}
                else:
                    inserted, skipped = decisions(repo, value)
                    repo.db.execute('CREATE TEMP TABLE transfer_insert(link_id TEXT PRIMARY KEY)')
                    repo.db.executemany('INSERT INTO transfer_insert VALUES(?)', [(x,) for x in inserted])
                    repo.db.create_function('basis_transfer_guard', 1,
                                            lambda key: 1 if key == value['snapshot_sha256'] else (_ for _ in ()).throw(ValueError('guard')))
                    execute_sql(repo.db, script)
                    verify_consumer(repo, sources, who, value)
                    result = {'status': 'applied', 'inserted': inserted, 'skipped': skipped,
                              'at': now(), 'actor': getpass.getuser(), 'snapshot_sha256': value['snapshot_sha256']}
                    repo.save_receipt(receipt_key(value, 'apply'), value['snapshot_sha256'], result)
                sources.store.check_unchanged()
                if hook:
                    hook('before_commit')
            if hook:
                hook('after_commit')
        # If this publication fails, the committed receipt permits a safe identical retry.
        marker(runtime)
        return result


def rollback(value, runtime, hook=None):
    signed(value, 'snapshot_sha256')
    with authority(Path(runtime) / 'basis-links/authority.sqlite', write=True) as repo, repo.transaction():
        old = repo.receipt(receipt_key(value, 'rollback'), value['snapshot_sha256'])
        if old:
            return {**old, 'status': 'already_rolled_back'}
        applied = repo.receipt(receipt_key(value, 'apply'), value['snapshot_sha256'])
        require(applied is not None, 'TRANSFER_NOT_APPLIED', '이 묶음의 적용 기록이 없습니다.')
        items = {x['link']['link_id']: x for x in value['items']}
        for ident in applied['inserted']:
            item = items[ident]
            require(repo.head(ident) == item['link'] and repo.history(ident) == item['history'],
                    'TRANSFER_CONFLICT', '적용 후 변경된 관계가 있어 자동 원복하지 않습니다: ' + ident)
        for ident in applied['inserted']:
            item = items[ident]
            old_link = item['link']
            new = deepcopy(old_link)
            revision = old_link['revision'] + 1
            event = {'event_id': digest(['rollback', value['snapshot_sha256'], ident]), 'link_id': ident,
                     'revision': revision, 'previous_revision': old_link['revision'], 'action': 'revoke',
                     'actor': getpass.getuser(), 'team_id': new['team_id'], 'at': now(),
                     'request_id': receipt_key(value, 'rollback'), 'reason': '관계 이관 묶음 원복'}
            new.update(revision=revision, previous_revision=old_link['revision'],
                       status='REVOKED', review_event_id=event['event_id'])
            repo.append(new, event, old_link['revision'])
            for binding in repo.bindings(ident, old_link['revision']):
                repo.put_binding({**binding, 'link_revision': revision,
                                  'binding_id': digest([ident, revision, binding['generation_id']]),
                                  'previous_binding': binding['binding_id']})
        result = {'status': 'rolled_back', 'revoked': applied['inserted'], 'at': now(),
                  'snapshot_sha256': value['snapshot_sha256']}
        repo.save_receipt(receipt_key(value, 'rollback'), value['snapshot_sha256'], result)
        if hook:
            hook('before_commit')
        return result


def status(value, runtime):
    path = plain(Path(runtime) / 'basis-links/authority.sqlite')
    if not path.exists():
        return {'status': 'not_applied'}
    with authority(path) as repo:
        for action in ('rollback', 'apply'):
            saved = repo.receipt(receipt_key(value, action), value['snapshot_sha256'])
            if saved:
                return {**saved, 'live': {i['link']['link_id']: (repo.head(i['link']['link_id']) or {}).get('status') for i in value['items']},
                        'marker_enabled': (path.parent / 'SQLITE_ENABLED.json').exists()}
    return {'status': 'not_applied'}


def review(value, path, *, link_ids=None, accept_all=False):
    signed(value, 'snapshot_sha256')
    require(bool(accept_all) != bool(link_ids), 'TRANSFER_REVIEW_INPUT', '--all 또는 --ids 중 하나를 선택하세요.')
    known = {i['link']['link_id'] for i in value['items']}
    selected = sorted(known if accept_all else set(link_ids))
    require(selected and set(selected) <= known, 'TRANSFER_REVIEW_INPUT', '표에 있는 연결 ID를 선택해야 합니다.')
    if Path(path).exists():
        old = signed(read_json(path), 'review_sha256')
        require(old['source_snapshot_sha256'] == value['snapshot_sha256'] and old['link_ids'] == selected,
                'TRANSFER_REVIEW_CONFLICT', '기존 검토 선택을 보존했습니다. 다른 선택에는 새 이관 묶음을 생성하세요.')
        return old
    result = {'schema_version': 'basis-import-review-v1', 'decision': 'APPROVE_IMPORT',
              'source_snapshot_sha256': value['snapshot_sha256'], 'link_ids': selected,
              'reviewed_by': getpass.getuser(), 'reviewed_at': now(),
              'scope': 'operator-selected import; original legal review status preserved'}
    result['review_sha256'] = digest(result)
    atomic(path, result)
    return result


def reviewed(value, decision):
    signed(value, 'snapshot_sha256')
    signed(decision, 'review_sha256')
    require(decision.get('schema_version') == 'basis-import-review-v1' and
            decision.get('decision') == 'APPROVE_IMPORT' and
            decision.get('source_snapshot_sha256') == value['snapshot_sha256'],
            'TRANSFER_REVIEW_HASH', '다른 스냅샷의 검토 기록입니다.')
    ids = decision['link_ids']
    require(isinstance(ids, list) and ids and len(ids) == len(set(ids)) and
            set(ids) <= {i['link']['link_id'] for i in value['items']},
            'TRANSFER_REVIEW_INPUT', '검토 선택에 없는 연결이 있습니다.')
    result = deepcopy(value)
    result['items'] = [i for i in result['items'] if i['link']['link_id'] in ids]
    dids = {e['document_id'] for i in result['items'] for group in ('revisions', 'bindings')
            for v in i['history'][group] for side in ('internal', 'external') for e in v[side]}
    result['lineage'] = [v for v in result['lineage'] if v['version_id'] in dids]
    result['document_hashes'] = {k: v for k, v in result['document_hashes'].items() if k in dids}
    result['import_review'] = decision
    result['snapshot_sha256'] = digest({k: v for k, v in result.items() if k != 'snapshot_sha256'})
    return result


def load_reviewed(bundle, value):
    path = bundle.with_name('REVIEW.json')
    require(path.is_file(), 'TRANSFER_REVIEW_REQUIRED', 'HTML 검토 후 review --all 또는 review --ids를 먼저 실행하세요.')
    return reviewed(value, read_json(path))


def reviewed_archive(folder):
    """The reviewed data AND runner travel together, with no manual file picking."""
    names = ('RELATIONS.json', 'REVIEW.json', 'REVIEWED.sql', 'APPLY.sql', 'APPLY_RELATIONS.txt',
             'runner.py', 'CODE_REQUIREMENTS.json', 'basis_batch_artifacts.py', 'basis_batch_report.py',
             'basis_batch_candidates.py', 'basis_batch.py', 'LINKS.html', 'README.txt')
    archive = folder.with_name(folder.name + '_REVIEWED.zip')
    temp = archive.with_name('.' + archive.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with zipfile.ZipFile(temp, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for name in names:
                z.write(plain(folder / name), folder.name + '/' + name)
        os.chmod(temp, 0o600)
        os.replace(temp, plain(archive))
    finally:
        if temp.exists():
            temp.unlink()
    return archive


APPLY_TXT = '''#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
mkdir -p ./basis-transfer-logs || exit 1
LOG="./basis-transfer-logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
trap 'RC=$?; printf "%s\\n" "$RC" > "$LOG.exit"; printf "BASIS_TRANSFER_EXIT=%s LOG=%s\\n" "$RC" "$LOG"' EXIT
exec > >(tee -a "$LOG") 2>&1
python3 "$HERE/runner.py" "${1:-check}" --bundle "$HERE/RELATIONS.json" "${@:2}"
'''


def export_bundle(value, output, kit):
    require(value['items'] and all(i['source_check']['status'] == 'verified' for i in value['items']),
            'TRANSFER_EMPTY', '원문 확인을 통과한 연결이 필요합니다.')
    output = plain(output)
    require(not output.exists() and not output.with_suffix('.zip').exists(),
            'TRANSFER_OUTPUT_EXISTS', '기존 이관 묶음을 보존했습니다. 새 출력 이름을 사용하세요.')
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Temporary directory never gets presented as a completed bundle.
    with tempfile.TemporaryDirectory(prefix='.basis-export-', dir=output.parent) as temp:
        stage = Path(temp) / output.name
        stage.mkdir(mode=0o700)
        atomic(stage / 'RELATIONS.json', value)
        atomic(stage / 'APPLY.sql', sql(value))
        atomic(stage / 'APPLY_RELATIONS.txt', APPLY_TXT)
        for name in ('runner.py', 'CODE_REQUIREMENTS.json', 'basis_batch_artifacts.py', 'basis_batch_report.py',
                     'basis_batch_candidates.py', 'basis_batch.py'):
            src = plain(Path(kit) / name)
            atomic(stage / name, src.read_text('utf-8'))
        report(value, stage / 'LINKS.html')
        atomic(stage / 'README.txt',
               '이 묶음은 내규·외규 연결 이력만 포함합니다. 원문 전체 DB·모델·색인은 포함하지 않습니다.\n'
               'LINKS.html 확인 후 bash ./묶음폴더/APPLY_RELATIONS.txt review --all (또는 --ids 연결ID...).\n'
               'REVIEW.json과 REVIEWED.sql이 만들어집니다. 전체 폴더를 함께 옮깁니다.\n'
               '운영의 실제 TRANSFER에서 압축을 풀고 bash ./묶음폴더/APPLY_RELATIONS.txt check 후 apply.\n'
               '기본 checkout은 ~/DEV, 데이터/공유 runtime은 그 checkout의 GENOS_SERVING_PATHS.json입니다.\n'
               'status로 적용 확인, rollback으로 이번 묶음이 새로 삽입한 연결만 철회(이력 보존).\n'
               '기존 같은 ID의 다른 revision/승인 상태는 덮어쓰지 않고 전체 중단합니다.\n'
               'APPLY.sql은 원문 검증을 수행하는 실행 TXT를 통해서만 실행합니다.\n'
               'PROPOSED는 미승인 후보를 유지합니다. 실제 대사 시 적용성과 법적 타당성을 다시 판단합니다.\n'
               '전체 파일 재해시 대신 선택된 원문·조항·해시·권한을 검증합니다. 일반 서빙 검증을 대체하지 않습니다.\n')
        os.rename(stage, output)
    archive = output.with_suffix('.zip')
    temp_zip = archive.with_name('.' + archive.name + '.tmp')
    try:
        with zipfile.ZipFile(temp_zip, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(output.iterdir()):
                z.write(path, output.name + '/' + path.name)
        os.chmod(temp_zip, 0o600)
        os.replace(temp_zip, archive)
    finally:
        if temp_zip.exists():
            temp_zip.unlink()
    emit('basis.artifacts.exported', folder=str(output), zip=str(archive), links=len(value['items']),
         batch_status=value['batch_status'], snapshot_sha256=value['snapshot_sha256'])
    return archive


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['report', 'export', 'review', 'check', 'apply', 'status', 'rollback',
                                      'stage-plan', 'stage-run', 'stage-resume'])
    p.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--job', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--bundle', type=Path)
    p.add_argument('--kit', type=Path, default=Path(__file__).parent)
    p.add_argument('--local-validation', action='store_true', help='합성 로컬 검증 전용; GENOS 현장 인증 아님')
    p.add_argument('--ids', nargs='+')
    p.add_argument('--all', dest='accept_all', action='store_true')
    p.add_argument('--team', default='risk_team')
    p.add_argument('--count', type=int, default=3)
    a = p.parse_args(argv)
    root = a.root.resolve(strict=True)  # ~/DEV entry alias is allowed; inner artifacts are guarded.
    config = read_json(root / '00_SYSTEM/GENOS_SERVING_PATHS.json')
    generation, runtime = plain(config['generation']), plain(config['runtime'])
    pipeline = read_json(root / '00_SYSTEM/PIPELINE.json')
    source_config = (root, pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent'])
    emit('basis.artifacts.start', command=a.command, code_root=str(root), generation=str(generation),
         runtime=str(runtime), python=sys.executable, python_version=sys.version.split()[0])
    if a.command.startswith('stage-'):
        return sibling('basis_batch_candidates').stage(a.command, root,
            a.job or runtime / 'basis-batch/pilot-review-20261020-r1', a.team, a.count, a.ids)
    if a.command in ('report', 'export'):
        # Prefer the explicitly created review batch; legacy R3 remains readable.
        job = a.job or runtime / 'basis-batch/pilot-review-20261020-r1'
        if not a.job and not (job / 'PLAN.json').exists():
            job = runtime / 'basis-batch/pilot-20261020-r1'
        value = capture(job, generation, runtime, source_config)
        if a.command == 'report':
            output = a.output or Path.cwd() / ('LINKS_' + value['snapshot_sha256'][:12] + '.html')
            report(value, output)
        else:
            # Revalidate every exported historical endpoint, too.
            with source(generation, value['source'], value['principal'], source_config) as (sources, who):
                validate(value, sources, who)
            export_bundle(value, a.output or Path.cwd() / ('BASIS_RELATIONS_' + value['snapshot_sha256'][:12]), a.kit)
        return 0
    require(a.bundle is not None, 'TRANSFER_INPUT', '--bundle RELATIONS.json이 필요합니다.')
    value = signed(read_json(a.bundle), 'snapshot_sha256')
    if a.command == 'review':
        decision = review(value, a.bundle.with_name('REVIEW.json'), link_ids=a.ids, accept_all=a.accept_all)
        approved = reviewed(value, decision)
        atomic(a.bundle.with_name('REVIEWED.sql'), sql(approved))
        archive = reviewed_archive(plain(a.bundle).parent)
        emit('basis.artifacts.reviewed', selected=len(decision['link_ids']), total=len(value['items']),
             review_file=str(a.bundle.with_name('REVIEW.json')), reviewed_zip=str(archive), published_to_sqlite=False)
        return 0
    value = load_reviewed(a.bundle, value)
    if a.command == 'status':
        result = status(value, runtime)
    elif a.command == 'rollback':
        require(a.local_validation or network_storage(runtime), 'TRANSFER_RUNTIME', 'GENOS의 외부 공유 runtime이 필요합니다.')
        result = rollback(value, runtime)
    else:
        require(a.local_validation or network_storage(runtime), 'TRANSFER_RUNTIME', 'GENOS의 외부 공유 runtime이 필요합니다.')
        script = plain(a.bundle.with_name('REVIEWED.sql')).read_text('utf-8')
        result = apply(value, script, generation, runtime, check=a.command == 'check', config=source_config)
    emit('basis.artifacts.result', **result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
