"""Oracle DB-API transactions. No connection discovery, DDL execution or retry."""
from contextlib import contextmanager
import re
import time
from ..contracts import KnowledgeError, require
from .repository import Repository, TABLES


def validate_tables(tables):
    require(set(tables) == set(TABLES) and len(set(tables.values())) == len(TABLES)
            and all(isinstance(v, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,29}(?:\.[A-Za-z][A-Za-z0-9_]{0,29})?', v)
                    for v in tables.values()), 'KNOWLEDGE_TABLES', '승인된 Oracle 테이블 매핑이 필요합니다.')


def database_error(exc):
    code = getattr(exc.args[0], 'code', None) if exc.args else None
    if code in (1, 8177, 60):
        return KnowledgeError('KNOWLEDGE_REVISION', '동시 변경입니다. 같은 작업 ID로 상태를 확인해 주세요.', 409)
    if code in (28, 1013, 3113, 3114, 3135, 12170, 12514, 12541, 12545) or isinstance(exc, (OSError, TimeoutError)):
        return KnowledgeError('KNOWLEDGE_UNAVAILABLE', '저장소 응답을 확인하지 못했습니다. 같은 작업 ID로 상태를 확인해 주세요.', 503)
    return None


class Cursor:
    def __init__(self, raw): self.raw, self.rowcount = raw, raw.rowcount
    def row(self, value):
        return None if value is None else {c[0].lower(): (v.read() if hasattr(v, 'read') else v)
                                          for c, v in zip(self.raw.description, value)}
    def fetchone(self):
        try: return self.row(self.raw.fetchone())
        finally: self.raw.close()
    def __iter__(self):
        try:
            for row in self.raw: yield self.row(row)
        finally: self.raw.close()


class Connection:
    def __init__(self, raw, tables):
        validate_tables(tables)
        self.raw, self.tables = raw, tables
        raw.autocommit = False
        self.deadline = time.monotonic() + 15
    def limit_deadline(self, deadline):
        self.deadline = min(self.deadline, deadline)
    def check_budget(self):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'KNOWLEDGE_UNAVAILABLE', '지식 조회·저장 시간이 초과되었습니다. 작업 상태를 확인해 주세요.', 503)
        self.raw.call_timeout = max(1, min(1500, int(remaining*1000)))
    def execute(self, statement, args=()):
        self.check_budget()
        for logical, actual in self.tables.items(): statement = re.sub(r'\b'+logical+r'\b', actual, statement)
        indices = iter(range(len(args)))
        statement = re.sub(r'\?', lambda _: ':k'+str(next(indices)), statement)
        cursor = self.raw.cursor()
        try:
            # CLOB payload binds are explicit; large definitions never rely on VARCHAR inference.
            large = {f'k{i}': None for i, value in enumerate(args) if isinstance(value, str) and len(value.encode()) > 4000}
            if 'INSERT INTO' in statement and self.tables['lk_record'] in statement:
                large['k5'] = None
            if large:
                import oracledb
                cursor.setinputsizes(**{key: oracledb.DB_TYPE_CLOB for key in large})
            cursor.execute(statement, {f'k{i}': v for i, v in enumerate(args)})
            result = Cursor(cursor)
            if cursor.description is None: cursor.close()
            return result
        except Exception as exc:
            cursor.close()
            converted = database_error(exc)
            if converted: raise converted from exc
            raise
    @contextmanager
    def transaction(self):
        # Oracle begins a transaction even for reads; finish earlier read-only work.
        self.raw.rollback()
        self.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        try:
            yield
            self.check_budget()
            self.raw.commit()
        except BaseException as exc:
            try: self.raw.rollback()
            except Exception: pass  # Preserve the original failure, including ambiguous commit.
            converted = database_error(exc)
            if converted: raise converted from exc
            raise


def factory(connection_factory, table_map, reference_factory):
    """Inject through create_app(knowledge_factory=..., knowledge_identity=...)."""
    validate_tables(table_map)
    @contextmanager
    def opened():
        from ..application import Service
        raw = None
        try:
            raw = connection_factory()
            with reference_factory() as references:
                yield Service(Repository(Connection(raw, table_map)), references)
        except Exception as exc:
            converted = database_error(exc)
            if converted: raise converted from exc
            raise
        finally:
            if raw is not None: raw.close()
    return opened


def ddl(table_map):
    validate_tables(table_map)
    columns = {
        'lk_record': 'namespace VARCHAR2(32), object_id VARCHAR2(128), revision NUMBER(19), tenant_id VARCHAR2(128) NOT NULL, team_id VARCHAR2(128) NOT NULL, payload CLOB NOT NULL, content_hash VARCHAR2(64) NOT NULL, PRIMARY KEY(namespace,object_id,revision)',
        'lk_head': 'namespace VARCHAR2(32), object_id VARCHAR2(128), revision NUMBER(19) NOT NULL, tenant_id VARCHAR2(128) NOT NULL, team_id VARCHAR2(128) NOT NULL, PRIMARY KEY(namespace,object_id)',
        'lk_lookup': 'release_id VARCHAR2(128), term VARCHAR2(320), object_id VARCHAR2(128), revision NUMBER(19), PRIMARY KEY(release_id,term,object_id,revision)',
    }
    return '\n'.join('CREATE TABLE '+table_map[t]+' ('+columns[t]+');' for t in TABLES)
