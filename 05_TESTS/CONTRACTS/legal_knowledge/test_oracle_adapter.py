from types import SimpleNamespace
import time
import pytest
from lawrag.legal_knowledge.adapters.oracle import Connection, ddl, database_error
from lawrag.legal_knowledge.adapters.repository import TABLES
from lawrag.legal_knowledge.contracts import KnowledgeError


class RawCursor:
    description=None;rowcount=1
    def __init__(self,owner):self.owner=owner
    def setinputsizes(self,**kw):self.owner.types.append(kw)
    def execute(self,text,args):self.owner.statements.append((text,args))
    def close(self):self.owner.closed_cursors+=1


class Raw:
    def __init__(self):
        self.statements=[];self.types=[];self.closed_cursors=0;self.commits=0;self.rollbacks=0
    def cursor(self):return RawCursor(self)
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1


def test_oracle_uses_binds_serializable_transaction_clob_and_closes_cursor():
    raw=Raw();db=Connection(raw,{t:'A8_'+t.upper() for t in TABLES})
    with db.transaction():
        db.execute('INSERT INTO lk_record VALUES(?,?,?,?,?,?,?)',('definition','x',1,'tenant','team','가'*6000,'a'*64))
    assert raw.statements[0][0]=='SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
    sql,args=raw.statements[1]
    assert 'A8_LK_RECORD' in sql and ':k5' in sql and '가' not in sql
    assert args['k5']=='가'*6000 and raw.types
    assert raw.commits==1 and raw.closed_cursors==2 and raw.autocommit is False
    assert 1<=raw.call_timeout<=1500


def test_oracle_unknown_transaction_failure_rolls_back_and_does_not_retry():
    raw=Raw();db=Connection(raw,{t:t for t in TABLES})
    with pytest.raises(RuntimeError):
        with db.transaction():raise RuntimeError('synthetic crash')
    assert raw.commits==0 and raw.rollbacks==2 and len(raw.statements)==1
    db.limit_deadline(time.monotonic()-1)
    with pytest.raises(KnowledgeError):db.execute('SELECT 1 FROM lk_head')
    assert len(raw.statements)==1


@pytest.mark.parametrize('code,status',[(1,409),(8177,409),(3113,503),(12541,503)])
def test_oracle_classifies_only_known_errors(code,status):
    assert database_error(Exception(SimpleNamespace(code=code))).status==status
    assert database_error(Exception('unclassified')) is None


def test_ddl_does_not_accept_user_sql():
    with pytest.raises(KnowledgeError):ddl({t:'table; DROP TABLE secret' for t in TABLES})
    text=ddl({t:t for t in TABLES})
    assert text.count('CREATE TABLE')==3 and 'payload CLOB' in text
