"""Only tests provide SQLite. Production uses the injected Oracle connection."""
from contextlib import contextmanager
import re
import sqlite3
from copy import deepcopy
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lawrag.legal_knowledge.adapters.repository import Repository
from lawrag.legal_knowledge.application import Service
from lawrag.legal_knowledge.contracts import require

WHO = {'authenticated': True, 'tenant_id': 'demo', 'team_id': 'risk_team', 'user_id': 'synthetic',
       'document_ids': ['d'], 'knowledge_roles': ['read', 'edit', 'publish']}
BINDING = {'generation': 'demo-generation', 'store_sha256': 'a'*64, 'unit_index_sha256': None}


class DB:
    def __init__(self, path):
        self.raw = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
    def execute(self, statement, args=()):
        statement = re.sub(r'FETCH FIRST (\d+) ROWS ONLY', r'LIMIT \1', statement)
        return self.raw.execute(statement, args)
    @contextmanager
    def transaction(self):
        self.raw.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.raw.commit()
        except BaseException:
            self.raw.rollback(); raise


class References:
    denied = False
    def resolve(self, ref, who):
        require(not self.denied, 'KNOWLEDGE_NOT_FOUND', '사용 중지된 근거', 404)
        return {'ref': ref, 'document_ids': ['d']}
    def verify_source(self, ref, who, binding):
        require(not self.denied, 'KNOWLEDGE_SOURCE_HASH', '변경된 근거', 409)
        require(ref['document_id'] in who['document_ids'], 'KNOWLEDGE_NOT_FOUND', '권한 없음', 404)


@pytest.fixture
def service(tmp_path):
    from lawrag.legal_knowledge.adapters.oracle import ddl
    db = DB(tmp_path/'test-only.sqlite')
    db.raw.executescript(ddl({n:n for n in ('lk_record', 'lk_head', 'lk_lookup')}))
    value = Service(Repository(db), References())
    yield value
    db.raw.close()


@pytest.fixture
def definition():
    return {'schema_version': 'legal-knowledge-v1', 'kind': 'METHOD', 'title': '모의 승인 검토',
        'description': '승인 주체와 예외를 원문에서 확인한다.',
        'scope': {k: {'mode': 'ANY_REVIEWED', 'values': []} for k in ('business','product','role','action','jurisdiction')},
        'source_refs': [{'document_id': 'd', 'version': 'd', 'locator': '1', 'content_hash': 'f'*64}],
        'dependencies': [], 'lookup_terms': ['승인'], 'effective_from': '2020-01-01', 'effective_to': None,
        'content': {'purpose': '승인 검토', 'requested_outputs': ['승인 주체'], 'inputs': [], 'evidence_needs': ['본문·예외'],
            'steps': [{'id': 'read', 'label': '승인 주체 확인', 'capability': 'READ_SOURCE', 'after': []}], 'policies': []}}


def command(service, operation, arguments, key=None, who=None):
    import uuid
    return service.command(who or deepcopy(WHO), {'schema_version': 'legal-knowledge-v1',
        'operation': operation, 'operation_id': key or uuid.uuid4().hex, 'arguments': arguments})


def publish(service, definition, binding=None):
    from lawrag.legal_knowledge.application import ref
    draft = command(service, 'save_draft', {'object_id': None, 'expected_revision': 0, 'definition': definition})
    build = command(service, 'prepare_publication', {'refs': [ref(draft)], 'source_binding': binding or BINDING, 'review_note': '모의 계약 검증'})
    current = service.active(WHO)
    channel = command(service, 'publish', {'build_id': build['id'], 'build_hash': build['content_hash'], 'expected_revision': current['revision'] if current else 0})
    return draft, build, channel
