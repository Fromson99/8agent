"""Sequential GENOS pilot using the existing selected RAG and workflow runtime."""
import argparse
from contextlib import contextmanager
import csv
import fcntl
import getpass
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
import time
import uuid

from semantic_runtime.basis_links.contracts import digest, require, now

SCHEMA = 'basis-batch-v1'


def atomic(path, value):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'BATCH_PATH', '심볼릭 링크 경로를 사용할 수 없습니다.')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def resources(path):
    available = None
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            available = int(line.split()[1]) * 1024
    free = shutil.disk_usage(path).free
    require(available is not None and available >= 2 * 1024**3,
            'BATCH_MEMORY', '가용 RAM 2 GiB 미만입니다. 새 조사를 시작하지 않습니다.')
    require(free >= 1024**3, 'BATCH_DISK', '가용 저장공간 1 GiB 미만입니다.')
    return {'available_ram_bytes': available, 'available_disk_bytes': free}


def emit(event, **fields):
    from semantic_runtime.observability import _safe_fields
    print(json.dumps({'at': now(), 'event': event, **_safe_fields(fields)}, ensure_ascii=False), flush=True)


def save_state(path, value):
    value['state_sha256'] = digest({k:v for k,v in value.items() if k != 'state_sha256'})
    atomic(path, value)


@contextmanager
def lock(folder):
    folder = Path(folder)
    require(not any(p.is_symlink() for p in (folder, *folder.parents)), 'BATCH_PATH', '잘못된 작업 경로입니다.')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'batch.lock'
    require(not path.is_symlink(), 'BATCH_PATH', '잘못된 잠금 경로입니다.')
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('BATCH_BUSY: 같은 작업이 실행 중입니다.') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def heartbeat(fields):
    stopped = threading.Event()
    def beat():
        while not stopped.wait(15):
            emit('basis.batch.running', **fields, pid=os.getpid())
    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)


def catalogue(app, team):
    pipeline = app.state.pipeline
    store = pipeline.store
    require(not getattr(store, 'is_oracle_query', False), 'BATCH_SQLITE_REQUIRED',
            '이 명령은 명시적으로 선택한 SQLite 원문 세대를 사용합니다.')
    store.selection.require_latest()
    services = app.state.workflow_runtime.services
    who = services.principal(getpass.getuser(), team)
    from semantic_runtime.basis_links.sources import SourcePort
    port = SourcePort(store, (pipeline.contracts.root, pipeline.term_agent.config))
    rows = []
    for did in who['document_ids']:
        if port.catalogue[did]['category'] != 'internal':
            continue
        row = store.db.execute(
            'SELECT name,source_artifact_sha256,json FROM document WHERE document_id=?', (did,)).fetchone()
        metadata = json.loads(row['json']).get('document_metadata') or {}
        require(metadata.get('is_latest') is True, 'BATCH_LATEST_REQUIRED',
                'RAG 최신 표시가 없는 내규입니다: ' + did, 409)
        size = store.db.execute('SELECT coalesce(sum(length(text)),0) FROM source_block WHERE document_id=?', (did,)).fetchone()[0]
        if size:
            rows.append({'document_id': did, 'name': row['name'], 'chars': size,
                         'source_artifact_sha256': row['source_artifact_sha256'], 'is_latest': True})
    return sorted(rows, key=lambda r: (r['chars'], r['name'], r['document_id'])), who


def selected_binding(app, who):
    from semantic_runtime.contracts import sha
    services = app.state.workflow_runtime.services
    store = app.state.pipeline.store
    store.check_unchanged()
    return {'generation_id': store.manifest['generation_id'],
            'manifest_sha256': sha(store.path / 'manifest.json'),
            'store_sha256': store.manifest['store_sha256'],
            'selection_sha256': store.selection.fingerprint,
            'generation_path': str(store.path),
            'runtime': str(services.runtime.resolve()),
            'pipeline_sha256': sha(app.state.pipeline.contracts.root / '00_SYSTEM/PIPELINE.json'),
            'profile_sha256': digest(services.profile), 'principal': who,
            'model': services.profile.get('model_binding'), 'release': services.release}


def plan(app, team, *, count=3, ids=None):
    rows, who = catalogue(app, team)
    require(type(count) is int and 1 <= count <= 20, 'BATCH_COUNT', '한 배치는 1~20개 문서입니다.')
    if ids:
        require(len(ids) == len(set(ids)) and set(ids) <= {r['document_id'] for r in rows},
                'BATCH_SELECTION', '선택 ID는 현재 RAG의 최신 내규 목록에 있어야 합니다.', 403)
        selected = [r for r in rows if r['document_id'] in ids]
        require(len(selected) <= 20, 'BATCH_COUNT', '한 배치는 최대 20개 문서입니다.')
    else:
        selected = rows[:count]
    require(selected, 'BATCH_EMPTY', '조사할 최신 내규가 없습니다.')
    from semantic_runtime.basis_links.grouping import inventory
    for row in selected:
        groups = inventory(app.state.pipeline.store, row['document_id'])
        row.update(scope_count=len(groups), inventory_sha256=digest(groups),
                   largest_scope_chars=max((g['chars'] for g in groups), default=0))
    ident = uuid.uuid4().hex
    value = {'schema_version': SCHEMA, 'batch_id': ident, 'created_at': now(),
             'binding': selected_binding(app, who), 'documents': selected,
             'selection_rule': 'explicit-ids' if ids else 'smallest-visible-latest',
             'scope_policy': 'parent-overlap-v1', 'publish_candidates': True,
             'as_of': now()[:10], 'max_documents': len(selected),
             'model_calls_per_document': app.state.workflow_runtime.services.profile.get('max_model_attempts'),
             'quality_certified': False}
    value['plan_sha256'] = digest(value)
    return value, rows


def verify_plan(app, value):
    require(value.get('schema_version') == SCHEMA and
            value.get('plan_sha256') == digest({k: v for k, v in value.items() if k != 'plan_sha256'}),
            'BATCH_PLAN_HASH', '배치 계획 해시가 다릅니다.', 409)
    rows, who = catalogue(app, value['binding']['principal']['team_id'])
    require(selected_binding(app, who) == value['binding'], 'BATCH_BINDING',
            '코드·모델·권한·최신 선택·원문 세대 또는 runtime이 변경되었습니다.', 409)
    by = {r['document_id']: r for r in rows}
    from semantic_runtime.basis_links.grouping import inventory
    for row in value['documents']:
        require(row['document_id'] in by and by[row['document_id']]['source_artifact_sha256'] == row['source_artifact_sha256'],
                'BATCH_SELECTION', '선택 내규가 변경되었습니다.', 409)
        require(digest(inventory(app.state.pipeline.store, row['document_id'])) == row['inventory_sha256'],
                'BATCH_INVENTORY', '조사 범위가 변경되었습니다.', 409)
    return who


def enable(app):
    pipeline = app.state.pipeline
    runtime = app.state.workflow_runtime.services.runtime
    from semantic_runtime.basis_links.api import local_factory, enabled_shared_factory
    local = app.state.workflow_runtime.services.release.get('mode') == 'local-release'
    if local:
        pipeline.basis_factory = pipeline.basis_factory or local_factory(
            runtime, pipeline.store.path, (pipeline.contracts.root, pipeline.term_agent.config))
    else:
        from semantic_runtime.state_sqlite import network_storage
        require(network_storage(runtime), 'BATCH_SHARED_RUNTIME',
                'GENOS batch와 대사는 같은 외부 공유 runtime을 사용해야 합니다.', 409)
        marker = runtime / 'basis-links/SQLITE_ENABLED.json'
        value = {'schema_version': 'basis-shared-sqlite-v1', 'database': 'authority.sqlite'}
        if marker.exists():
            require(json.loads(marker.read_text()) == value, 'BATCH_AUTHORITY', '기존 관계 설정이 다릅니다.', 409)
        else:
            atomic(marker, value)
        pipeline.basis_factory = enabled_shared_factory(pipeline, runtime)
    require(pipeline.basis_factory is not None, 'BATCH_AUTHORITY', 'SQLite 관계 원장을 연결하지 못했습니다.')
    emit('basis.batch.sqlite.enabled', authority_path=str(runtime / 'basis-links/authority.sqlite'),
         indexing='relation-rows-only', approval='PROPOSED')


def export(app, value, folder):
    who = value['binding']['principal']
    path = folder / 'LINKS.csv'
    temporary = folder / 'LINKS.csv.tmp'
    with app.state.pipeline.basis_factory() as service, temporary.open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['내규 문서', '내규 조항', '내규 원문', '외규 문서', '외규 조항', '외규 원문', '관계', '이유', '상태', '연결 ID']
        writer = csv.writer(stream)
        writer.writerow(fields)
        for doc in value['documents']:
            for item in service.list(who, doc['document_id'])['items']:
                link = item['link']
                ends = item['binding'] or link
                def render(side, field):
                    return '\n'.join(e[field] for e in ends[side])
                def text(side):
                    return '\n'.join(p['text'] for e in ends[side] for p in e['spans'])
                cells = [render('internal', 'document_name'), render('internal', 'title'), text('internal'),
                         render('external', 'document_name'), render('external', 'title'), text('external'),
                         link['kind'], link['reason'], link['status'], link['link_id']]
                # Spreadsheet-safe export; exact originals remain in the authority.
                writer.writerow(["'" + c if c.startswith(('=', '+', '-', '@')) else c for c in cells])
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run(app, value, folder, *, resume=False, use_llm=True):
    folder = Path(folder)
    who = verify_plan(app, value)
    binding = app.state.workflow_runtime.services.profile.get('model_binding') or {}
    if use_llm:
        require(binding.get('trust_zone') == 'internal' and binding.get('provider') == 'genos',
                'BATCH_INTERNAL_MODEL', '내규 배치는 GENOS 내부 모델로만 실행합니다.', 403)
    runtime = app.state.workflow_runtime
    state_path = folder / 'STATE.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        'schema_version': SCHEMA, 'plan_sha256': value['plan_sha256'], 'documents': {}, 'status': 'pending'}
    if state_path.exists():
        require(state.get('state_sha256') == digest({k:v for k,v in state.items() if k != 'state_sha256'}),
                'BATCH_STATE_HASH', '배치 상태 해시가 다릅니다.', 409)
    require(state['plan_sha256'] == value['plan_sha256'], 'BATCH_STATE', '다른 배치의 상태입니다.', 409)
    # Bind invocation mode, including source-only diagnostics, before doing any work.
    require(state.get('use_llm', use_llm) == use_llm, 'BATCH_STATE', '모델 실행 모드가 달라졌습니다.', 409)
    state['use_llm'] = use_llm
    enable(app)
    for index, document in enumerate(value['documents']):
        did = document['document_id']
        saved = state['documents'].get(did, {})
        if saved.get('status') in ('completed', 'partial', 'failed'):
            emit('basis.batch.document.reused', document_id=did, status=saved['status'])
            continue
        resources(folder)
        require(resume or not saved, 'BATCH_RESUME_REQUIRED', '중단된 작업은 resume 명령으로 이어가세요.', 409)
        body = {'workflow_id': 'internal_basis_discovery_workflow',
                'session_id': 'basis-batch:' + value['batch_id'],
                'request_id': 'basis-batch:' + digest([value['batch_id'], did]),
                'as_of': value['as_of'], 'use_llm': use_llm,
                'input': {'internal_document_id': did, 'mode': 'discover',
                          'scope_policy': value['scope_policy'], 'publish_candidates': True}}
        state['documents'][did] = {**saved, 'status': 'running', 'request_id': body['request_id']}
        state.update(status='running', updated_at=now())
        save_state(state_path, state)
        emit('basis.batch.document.started', ordinal=index + 1, total=len(value['documents']), **document)
        try:
            with heartbeat({'document_id': did, 'ordinal': index + 1, 'total': len(value['documents'])}):
                result = runtime.execute(body, who, resume=resume and bool(saved))
            summary = {k: result.get(k) for k in ('run_id', 'status', 'coverage', 'usage', 'error_code', 'continuation_available')}
            state['documents'][did] = {**summary, 'request_id': body['request_id']}
            atomic(folder / (digest(did)[:32] + '.summary.json'), {'document_id':did,**summary})
            report = folder / (digest(did)[:32] + '.report.txt')
            report.write_text(result['answer']['text'], encoding='utf-8')
            emit('basis.batch.document.finished', document_id=did, **summary)
            save_state(state_path, state)
            export(app, value, folder)
        except BaseException as exc:
            state.update(status='interrupted', updated_at=now(),
                         failure={'type': type(exc).__name__, 'code': getattr(exc, 'code', None)})
            save_state(state_path, state)
            emit('basis.batch.interrupted', document_id=did, error_type=type(exc).__name__,
                 error_code=getattr(exc, 'code', None), recovery='Inspect original workflow journal; use resume with this plan.')
            raise
    state['status'] = 'completed' if all(r['status'] == 'completed' for r in state['documents'].values()) else 'partial'
    state['updated_at'] = now()
    save_state(state_path, state)
    export(app, value, folder)
    emit('basis.batch.finished', status=state['status'], state_file=str(state_path), csv_file=str(folder / 'LINKS.csv'),
         quality_certified=False)
    return state


def boot(root):
    # This command explicitly targets SQLite, as requested; serving DP config is not edited.
    os.environ.update(DP='sqlite', SEMANTIC_LLM_BACKEND='genos', GENOS_AUTO_WARMUP='0', AD_WORKER_ENABLED='0')
    root = Path(root).resolve()
    require((root / 'service.py').is_file(), 'BATCH_ROOT', '실제 DEV checkout이 필요합니다.')
    sys.path.insert(0, str(root))
    host = importlib.import_module('service')
    require(Path(host.__file__).resolve().parent == root, 'BATCH_ROOT', '다른 checkout의 service가 로드되었습니다.')
    app = host.application()
    require(Path(app.state.pipeline.contracts.root).resolve() == root, 'BATCH_CODE',
            '현재 checkout 코드로 실행해야 합니다. GENOS의 기존 세대 설정을 확인하세요.', 409)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'plan', 'run', 'resume', 'status', 'export'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--team', default='risk_team')
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--ids', nargs='+')
    args = parser.parse_args(argv)
    if args.command == 'status':
        # Atomic JSON snapshots are safe to inspect while the run lock is held.
        for name in ('PLAN.json', 'STATE.json'):
            path = args.job / name
            require(not any(p.is_symlink() for p in (path,*path.parents)), 'BATCH_PATH', '잘못된 상태 경로입니다.')
            if path.exists():
                print(path.read_text(), flush=True)
        return 0
    with lock(args.job):
        emit('basis.batch.preflight', python=sys.executable, python_version=sys.version.split()[0],
             pid=os.getpid(), **resources(args.job))
        with heartbeat({'phase': 'boot'}):
            app = boot(args.root)
        if args.command in ('list', 'plan'):
            value, rows = plan(app, args.team, count=args.count, ids=args.ids)
            with (args.job / 'LATEST_INTERNAL.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['document_id', 'name', 'chars', 'source_artifact_sha256', 'is_latest'], extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            for row in rows:
                emit('basis.batch.latest_internal', **row)
            if args.command == 'plan':
                path = args.job / 'PLAN.json'
                require(not path.exists(), 'BATCH_PLAN_EXISTS', '기존 계획을 보존했습니다. 새 작업에는 다른 --job 경로를 사용하세요.', 409)
                atomic(path, value)
                emit('basis.batch.planned', selected=value['documents'], binding=value['binding'], plan_file=str(path))
            return 0
        value = json.loads((args.job / 'PLAN.json').read_text())
        if args.command == 'export':
            verify_plan(app, value)
            enable(app)
            export(app, value, args.job)
            return 0
        state = run(app, value, args.job, resume=args.command == 'resume')
        return 0 if state['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
