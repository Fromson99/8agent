from contextlib import contextmanager
from copy import deepcopy
import time
from types import SimpleNamespace
import pytest
from lawrag.api.routers.legal_knowledge import CURRENT
from lawrag.legal_knowledge.contracts import KnowledgeError
from semantic_runtime.legal_agent.knowledge_bridge import prepare, augment
from semantic_runtime.research_state import KnowledgeReferences
from .conftest import WHO, BINDING, publish


def test_off_does_not_open_storage_or_journal():
    token=CURRENT.set((None,None,{'consumer_mode':'off'}))
    try:assert prepare(None,None,None,None,None) is None
    finally:CURRENT.reset(token)


@pytest.fixture
def journal(tmp_path):
    import sqlite3
    from semantic_runtime.contracts import digest
    class Journal:
        def __init__(self):
            self.db=sqlite3.connect(':memory:')
            self.db.executescript('CREATE TABLE event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash);')
            self.events=[];self.context=SimpleNamespace(deadline=time.monotonic()+30)
        @contextmanager
        def transaction(self):
            with self.db:yield
        def event(self,kind,value,**kwargs):
            import json
            self.events.append((kind,value))
            self.db.execute('INSERT INTO event VALUES(?,?,?,?)',(len(self.events),kind,json.dumps(value),digest(value)))
            return len(self.events)
        def put(self,kind,key,value,seq):
            import json
            self.db.execute('INSERT INTO entity_version VALUES(?,?,?,?,?)',(kind,key,1,json.dumps(value),digest(value)))
            self.db.execute('INSERT INTO entity_head VALUES(?,?)',(kind,key))
    j=Journal();yield j;j.db.close()


@pytest.mark.parametrize('code,status', [('KNOWLEDGE_UNAVAILABLE',503),('KNOWLEDGE_SOURCE_HASH',409)])
def test_lookup_failure_keeps_source_research_and_never_retries(journal, code,status):
    calls=[]
    @contextmanager
    def failed():
        calls.append(1)
        raise KnowledgeError(code,'synthetic',status)
        yield
    host=SimpleNamespace(binding=BINDING)
    token=CURRENT.set((failed,WHO,{'consumer_mode':'consume'}))
    try:
        value=prepare(host,journal,'승인',WHO,['d'])
        again=prepare(host,journal,'승인',WHO,['d'])
        assert value==again and calls==[1]
        assert value['plan']['unresolved']==[code] and not value['plan']['items']
        assert augment({'question':'승인'},value)==({'question':'승인'},'')
    finally:CURRENT.reset(token)


def test_budget_and_journal_tamper(journal):
    host=SimpleNamespace(binding=BINDING)
    journal.context.deadline=time.monotonic()-1
    token=CURRENT.set((lambda:None,WHO,{'consumer_mode':'consume'}))
    try:
        result=prepare(host,journal,'승인',WHO,['d'])
        assert result['plan']['unresolved']==['KNOWLEDGE_BUDGET']
        journal.db.execute('UPDATE event SET payload_json=?',('{}',))
        with pytest.raises(Exception,match='binding changed'):prepare(host,journal,'승인',WHO,['d'])
    finally:CURRENT.reset(token)


def test_observe_never_changes_model_payload(journal,service,definition):
    publish(service,definition)
    @contextmanager
    def factory():yield service
    token=CURRENT.set((factory,WHO,{'consumer_mode':'observe'}))
    try:
        value=prepare(SimpleNamespace(binding=BINDING),journal,'승인',WHO,['d'])
        assert value['plan']['items']
        assert augment({'question':'승인'},value)==({'question':'승인'},'')
    finally:CURRENT.reset(token)
