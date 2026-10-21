"""Transactional JSON candidates behind the existing discovery Service contract."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import uuid

from semantic_runtime.basis_links.contracts import digest, require
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort

SCHEMA = 'json-candidates-v1'


def plain(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'CANDIDATE_PATH', '후보 경로에 심볼릭 링크가 있습니다.')
    return path


class JsonRepository:
    """Small pilot journal; a proposal's head/history/binding/receipt commit together.

    Kept outside the serving authority. Atomic JSON replacement allows report
    readers during a run without a database or batch lock.
    """
    def __init__(self, path, writable=False):
        self.path = plain(path)
        self.writable = writable
        self.in_transaction = False
        self.data = self.load()

    def load(self):
        if not self.path.exists():
            return {'schema_version': SCHEMA, 'links': {}, 'receipts': {}, 'lineage': {}}
        require(self.path.stat().st_size <= 128 * 1024 * 1024, 'CANDIDATE_SIZE', '후보 파일 한도를 초과했습니다.')
        value = json.loads(self.path.read_text('utf-8'))
        checksum = value.pop('sha256', None)
        require(value.get('schema_version') == SCHEMA and checksum == digest(value),
                'CANDIDATE_HASH', '후보 JSON 해시가 다릅니다.')
        return value

    def close(self):
        pass

    @contextmanager
    def transaction(self):
        require(self.writable and not self.in_transaction, 'CANDIDATE_READ_ONLY', '후보 기록은 쓰기 트랜잭션이 필요합니다.')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = plain(self.path.with_suffix('.lock'))
        with lock.open('a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('CANDIDATE_BUSY: 다른 실행이 후보를 기록 중입니다.') from exc
            self.data = self.load()
            before = deepcopy(self.data)
            self.in_transaction = True
            temp = self.path.with_name('.' + self.path.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                yield
                value = {**self.data, 'sha256': digest(self.data)}
                body = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                require(len(body.encode()) <= 128 * 1024 * 1024, 'CANDIDATE_SIZE', '후보 파일 한도를 초과했습니다.')
                with temp.open('x', encoding='utf-8') as target:
                    os.chmod(temp, 0o600)
                    target.write(body)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temp, self.path)
            except BaseException:
                self.data = before
                raise
            finally:
                self.in_transaction = False
                if temp.exists():
                    temp.unlink()
                fcntl.flock(stream, fcntl.LOCK_UN)

    def history(self, ident):
        return deepcopy(self.data['links'].get(ident, {'revisions': [], 'events': [], 'bindings': []}))

    def head(self, ident):
        values = self.data['links'].get(ident, {}).get('revisions', [])
        return deepcopy(values[-1]) if values else None

    def links(self, team):
        return [self.head(k) for k in sorted(self.data['links']) if self.head(k)['team_id'] == team]

    def links_for_document(self, team, document_id):
        return [v for v in self.links(team) if any(e['document_id'] == document_id
                                                for side in ('internal', 'external') for e in v[side])]

    def bindings(self, ident, revision, generation=None):
        return [v for v in self.history(ident)['bindings'] if v['link_revision'] == revision
                and (generation is None or v['generation_id'] == generation)]

    def binding(self, ident, revision, generation):
        rows = self.bindings(ident, revision, generation)
        require(len(rows) <= 1, 'CANDIDATE_BINDING', '같은 세대에 중복 결속이 있습니다.')
        return rows[0] if rows else None

    def receipt(self, key, input_hash):
        row = self.data['receipts'].get(key)
        if row is None:
            return None
        require(row['input_hash'] == input_hash, 'BASIS_REQUEST_CONFLICT', '같은 요청 ID의 후보 내용이 다릅니다.')
        return deepcopy(row['value'])

    def save_receipt(self, key, input_hash, value):
        require(self.in_transaction, 'CANDIDATE_TRANSACTION', '트랜잭션 밖 기록입니다.')
        require(key not in self.data['receipts'], 'BASIS_REQUEST_CONFLICT', '중복 후보 receipt입니다.')
        self.data['receipts'][key] = {'input_hash': input_hash, 'value': deepcopy(value)}

    def append(self, value, event, previous=None):
        require(self.in_transaction, 'CANDIDATE_TRANSACTION', '트랜잭션 밖 기록입니다.')
        old = self.head(value['link_id'])
        require((old is None and previous is None and value['revision'] == 1) or
                (old is not None and old['revision'] == previous and value['revision'] == previous + 1),
                'BASIS_STALE_REVISION', '후보 상태가 변경되었습니다.')
        row = self.data['links'].setdefault(value['link_id'], {'revisions': [], 'events': [], 'bindings': []})
        row['revisions'].append(deepcopy(value))
        row['events'].append(deepcopy(event))
        row['events'].sort(key=lambda e: e['event_id'])

    def put_binding(self, value):
        require(self.in_transaction, 'CANDIDATE_TRANSACTION', '트랜잭션 밖 기록입니다.')
        old = self.binding(value['link_id'], value['link_revision'], value['generation_id'])
        require(old is None or old == value, 'CANDIDATE_BINDING', '기존 후보 결속과 다릅니다.')
        if old is None:
            values = self.data['links'][value['link_id']]['bindings']
            values.append(deepcopy(value))
            values.sort(key=lambda e: e['binding_id'])
        return deepcopy(value)

    def lineage(self, version):
        return deepcopy(self.data['lineage'].get(version))


def factory(app, path):
    @contextmanager
    def opened():
        pipeline = app.state.pipeline
        repo = JsonRepository(path, writable=True)
        try:
            yield Service(repo, SourcePort(pipeline.store, (pipeline.contracts.root, pipeline.term_agent.config)))
        finally:
            repo.close()
    return opened


def load_batch():
    spec = importlib.util.spec_from_file_location('_basis_batch_stage_engine', Path(__file__).with_name('basis_batch.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool_binding():
    import hashlib
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('basis_batch_candidates.py', 'basis_batch.py')}


def stage(command, root, job, team='risk_team', count=3, ids=None):
    """Use the same batch/workflow runner with an explicit JSON repository port."""
    batch = load_batch()
    root = Path(root).resolve()
    job = plain(job)
    # Same fixed R3 bootstrap policy; no external provider fallback.
    pipeline = json.loads((root / '00_SYSTEM/PIPELINE.json').read_text())
    implementation = pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']['implementation']
    require(implementation == 'legal-agent-unified-v6', 'CANDIDATE_CODE', '검증된 R3 legal RAG가 필요합니다.')
    os.environ['GENOS_RAG_IMPLEMENTATION'] = implementation
    with batch.lock(job):
        batch.resources(job)
        with batch.heartbeat({'phase': 'candidate-boot'}):
            app = batch.boot(root)
        if command == 'stage-plan':
            require(not (job / 'PLAN.json').exists(), 'CANDIDATE_PLAN_EXISTS', '기존 배치 계획을 보존했습니다. 새 --job을 사용하세요.')
            value, _ = batch.plan(app, team, count=count, ids=ids)
            value['candidate_storage'] = {'kind': SCHEMA, 'path': str(job / 'CANDIDATES.json'),
                                          'tool': tool_binding(), 'publication': 'manual-review-only'}
            value['plan_sha256'] = digest({k: v for k, v in value.items() if k != 'plan_sha256'})
            batch.atomic(job / 'PLAN.json', value)
            batch.emit('basis.batch.candidate_planned', job=str(job), selected=value['documents'],
                       candidate_file=str(job / 'CANDIDATES.json'), published_to_sqlite=False)
            return 0
        value = json.loads((job / 'PLAN.json').read_text())
        expected = {'kind': SCHEMA, 'path': str(job / 'CANDIDATES.json'),
                    'tool': tool_binding(), 'publication': 'manual-review-only'}
        require(value.get('candidate_storage') == expected, 'CANDIDATE_BINDING',
                'JSON 후보 배치의 코드·저장 위치가 다릅니다. 기존 R3 작업을 이 명령으로 전환하지 않습니다.')
        result = batch.run(app, value, job, resume=command == 'stage-resume',
                           candidate_factory=factory(app, job / 'CANDIDATES.json'))
        return 0 if result['status'] == 'completed' else 2
