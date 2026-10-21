from contextlib import closing
import sqlite3
import pytest
from test_authority import WHO,BODY,review_body,generation
from semantic_runtime.storage import Store
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.repository import DDL
from semantic_runtime.basis_links.oracle import OracleRepository,TABLES,ddl
from semantic_runtime.basis_links.service import Service
from lawrag.sources.lawgo_old_new import parse,bind


class FakeOracle:
    """DB-API protocol exercise, NOT a real Oracle database test."""
    def __init__(self,path):
        self.raw=sqlite3.connect(path,isolation_level=None);self.raw.executescript(DDL);self.opened=0;self.commits=0;self.rollbacks=0
    def cursor(self):return FakeCursor(self)
    def commit(self):self.commits+=1;self.raw.commit()
    def rollback(self):self.rollbacks+=1;self.raw.rollback()
    def close(self):self.raw.close()


class FakeCursor:
    def __init__(self,owner):self.owner=owner;self.raw=owner.raw.cursor();owner.opened+=1;self.closed=False
    def execute(self,sql,values):
        if sql=='SET TRANSACTION ISOLATION LEVEL SERIALIZABLE':sql='BEGIN IMMEDIATE'
        self.raw.execute(sql,values)
    @property
    def description(self):return self.raw.description
    @property
    def rowcount(self):return self.raw.rowcount
    def fetchone(self):return self.raw.fetchone()
    def __iter__(self):return iter(self.raw)
    def close(self):
        if not self.closed:self.closed=True;self.owner.opened-=1;self.raw.close()


def test_oracle_dbapi_contract_atomic_review(tmp_path,generation):
    raw=FakeOracle(tmp_path/'fake.sqlite');repo=OracleRepository(raw,{k:k for k in TABLES})
    with closing(Store(generation)) as store:
        service=Service(repo,SourcePort(store));p=service.propose(WHO,BODY)
        v=service.view(WHO);assert len(v['view_id'])==64
        result=service.review_view(WHO,{'view_id':v['view_id'],'rows':[1],'action':'approve','request_id':'approve'})
        assert result['status']=='completed';assert service.list(WHO)['items'][0]['link']['status']=='APPROVED'
        assert raw.opened==0
        with pytest.raises(RuntimeError):
            with repo.transaction():raise RuntimeError('transaction rollback')
        assert raw.rollbacks==1
    repo.close()
    assert 'receipt_id VARCHAR2(128)' in ddl({k:k.upper() for k in TABLES})


def test_old_new_absent_and_wrong_version():
    assert bind(parse('<r><신구법존재여부>N</신구법존재여부></r>'.encode()),{}, {})['status']=='UNAVAILABLE'

    raw='<r><신구법존재여부>Y</신구법존재여부><구조문_기본정보><법령ID>1</법령ID></구조문_기본정보></r>'.encode()
    with pytest.raises(ValueError):bind(parse(raw),{'법령ID':'2'},{})
