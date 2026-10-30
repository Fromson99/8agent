"""Explicit Oracle DB-API adapter; no connection discovery or SQLite fallback.

Deployment supplies an already authorized connection and an approved table map.
DDL is a proposed portable CLOB schema, not a claim about the site's existing KG.
"""
from contextlib import contextmanager
import re
from .repository import Repository
from .contracts import require,BasisError,BasisUnavailable

TABLES=('basis_head','basis_revision','basis_binding','basis_event','basis_receipt','basis_lineage','basis_migration','basis_view_head')


class Cursor:
    def __init__(self,raw):self.raw=raw;self.count=raw.rowcount
    @property
    def rowcount(self):return self.count
    def _row(self,row):
        if row is None:return None
        return {col[0].lower():(v.read() if hasattr(v,'read') else v) for col,v in zip(self.raw.description,row)}
    def fetchone(self):
        try:return self._row(self.raw.fetchone())
        finally:self.raw.close()
    def __iter__(self):
        try:
            for row in self.raw:yield self._row(row)
        finally:self.raw.close()


class Connection:
    def __init__(self,raw,tables):self.raw=raw;self.tables=tables
    def execute(self,sql,args=()):
        for logical,actual in self.tables.items():sql=re.sub(r'\b'+logical+r'\b',actual,sql)
        count=iter(range(len(args)));sql=re.sub(r'\?',lambda _:':p'+str(next(count)),sql)
        cursor=self.raw.cursor()
        try:cursor.execute(sql,{f'p{i}':v for i,v in enumerate(args)})
        except Exception as exc:
            cursor.close()
            code=getattr(exc.args[0],'code',None) if exc.args else None
            if code in (1,8177):raise BasisError('BASIS_WRITE_CONFLICT','동시 변경 충돌입니다. 같은 요청 ID의 결과를 조회한 뒤 재시도해 주세요.',409) from exc
            if code in (28,3113,3114,3135,12170,12514,12541,12545):raise BasisUnavailable() from exc
            raise
        result=Cursor(cursor)
        if cursor.description is None:cursor.close()
        return result
    def commit(self):self.raw.commit()
    def rollback(self):self.raw.rollback()


class OracleRepository(Repository):
    def __init__(self,connection,table_map):
        require(set(table_map)==set(TABLES) and all(isinstance(v,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_$#]*(?:\.[A-Za-z][A-Za-z0-9_$#]*)?',v) for v in table_map.values()),
                'BASIS_ORACLE_TABLES','허용된 Oracle 테이블 매핑이 필요합니다.')
        require(len(set(table_map.values()))==len(TABLES),'BASIS_ORACLE_TABLES','서로 다른 테이블 매핑이 필요합니다.')
        self.raw=connection;self.raw.autocommit=False;self.db=Connection(connection,table_map)

    def close(self):self.raw.close()

    @contextmanager
    def transaction(self):
        # SERIALIZABLE preserves the authority snapshot; ORA-08177 and unique
        # conflicts propagate. Caller retries the same receipt ID after rollback.
        self.db.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        try:
            yield
            self.raw.commit()
        except BaseException:
            self.raw.rollback();raise


def ddl(table_map):
    require(set(table_map)==set(TABLES) and all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',n) for n in table_map.values()),
            'BASIS_ORACLE_TABLES','DDL에는 검토된 단순 테이블 이름이 필요합니다.')
    columns={
        'basis_view_head':'session_key VARCHAR2(64) PRIMARY KEY, payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL',
        'basis_head':'link_id VARCHAR2(64) PRIMARY KEY, team_id VARCHAR2(256) NOT NULL, revision NUMBER(19) NOT NULL',
        'basis_revision':'link_id VARCHAR2(64), revision NUMBER(19), payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL, PRIMARY KEY(link_id,revision)',
        'basis_binding':'binding_id VARCHAR2(64) PRIMARY KEY, link_id VARCHAR2(64), revision NUMBER(19), generation VARCHAR2(512), payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL, UNIQUE(link_id,revision,generation)',
        'basis_event':'event_id VARCHAR2(64) PRIMARY KEY, link_id VARCHAR2(64), payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL',
        'basis_receipt':'receipt_id VARCHAR2(128) PRIMARY KEY, input_hash VARCHAR2(64) NOT NULL, payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL',
        'basis_lineage':'version_id VARCHAR2(512) PRIMARY KEY, family_id VARCHAR2(512), payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL',
        'basis_migration':'migration_id VARCHAR2(64) PRIMARY KEY, payload CLOB NOT NULL, hash VARCHAR2(64) NOT NULL'}
    return '\n'.join('CREATE TABLE '+table_map[k]+' ('+columns[k]+');' for k in TABLES)
