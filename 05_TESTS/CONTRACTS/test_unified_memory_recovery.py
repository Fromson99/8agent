"""Store migration and guarded restart contracts on synthetic checkpoint data."""
import json
from pathlib import Path
import sqlite3
import pytest
from lawrag.pipeline.unified_memory import migrate
from semantic_runtime.legal_agent.case_repository import CaseRepository
from semantic_runtime.legal_agent.domain_control import DomainCatalogue,compile_catalogue
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from test_memory_runtime_v2 import memory,command
from test_unified_legal_agent import unified,ok
from test_structure_first_search import structured_generation


def test_case_store_delete_journal_retains_commits_and_rolls_back(tmp_path,monkeypatch):
    monkeypatch.setenv('GENOS_MEMORY_JOURNAL_MODE','DELETE')
    path=tmp_path/'cases-v3.sqlite'
    repo=CaseRepository(path,None,None)
    assert repo.db.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
    assert repo.db.execute('PRAGMA synchronous').fetchone()[0]==2
    with repo.transaction():repo.db.execute("INSERT INTO session VALUES('s','u','t')")
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.db.execute("INSERT INTO session VALUES('failed','u','t')")
            raise RuntimeError('synthetic interruption')
    repo.close()
    repo=CaseRepository(path,None,None)
    assert [r[0] for r in repo.db.execute('SELECT id FROM session')]==['s']
    repo.close()


def test_case_store_rejects_wal_for_nfs_before_creating_db(monkeypatch):
    monkeypatch.setenv('GENOS_MEMORY_JOURNAL_MODE','WAL')
    from semantic_runtime.legal_agent.corrected_memory import Memory
    with pytest.raises(MemoryError,match='DELETE on /nfs-root'):
        Memory('/nfs-root/synthetic-not-created/cases.sqlite',None,None)


def test_explicit_migration_preserves_original_and_does_not_auto_approve(memory,tmp_path):
    legacy,f,w,send,p=memory
    gid=send(command('CASE_START',task='모의 승인',facts=[]))['goal_id']
    origin=legacy.events(gid)[0]['id']
    send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}]))
    send(command('STATE_RESTORE',target=gid,restore_event=origin,restore_fields=['facts']))
    kid=send(command('EXPERIENCE_CONFIRM',target=gid))['knowledge_id']
    before=[tuple(r) for r in legacy.db.execute('SELECT * FROM knowledge')]
    target=tmp_path/'new'/'cases-v3.sqlite'
    receipt=migrate(legacy.path,target)
    assert migrate(legacy.path,target)==receipt
    assert [tuple(r) for r in legacy.db.execute('SELECT * FROM knowledge')]==before
    with sqlite3.connect(target) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
        assert db.execute('SELECT status FROM knowledge').fetchone()[0]=='LEGACY_UNBOUND'
        assert db.execute("SELECT count(*) FROM knowledge WHERE status='ACTIVE'").fetchone()[0]==0
        restore=json.loads(db.execute("SELECT command FROM event WHERE command LIKE '%STATE_RESTORE%'").fetchone()[0])
        assert restore['restore_event']==receipt['mapping']['events'][str(origin)]
    assert Path(receipt['source_snapshot']).is_file()
    assert receipt['mapping']['experiences'][kid]


def test_migration_cannot_overwrite_legacy_store(memory):
    legacy,*_=memory
    with pytest.raises(ValueError,match='separate'):migrate(legacy.path,legacy.path)


def test_catalogue_rejects_unknown_relation_endpoints_and_unreviewed_concepts(tmp_path):
    base={'schema_version':'legal-agent-domain-catalogue-v1','concepts':[{'id':'s','status':'SYSTEM','definition':'원문'}],
          'relations':[{'id':'r','source':'s','target':'missing','status':'SYSTEM'}]}
    with pytest.raises(MemoryError,match='type unknown'):DomainCatalogue(base)
    base.update(relations=[]);base['concepts'][0]['status']='REVIEWED'
    with pytest.raises(MemoryError,match='receipt'):DomainCatalogue(base)
    base['concepts'][0]['review_receipt']={'reviewer':'synthetic','decision':'ACCEPTED',
        'source_generation':'synthetic-v1','source_hash':'a'*64,'evidence_refs':['synthetic-source:1']}
    source=tmp_path/'reviewed.json';source.write_text(json.dumps(base))
    receipt=compile_catalogue(source,tmp_path/'compiled.json')
    assert len(receipt['sha256'])==64
    with pytest.raises(FileExistsError):compile_catalogue(source,tmp_path/'compiled.json')


def test_ownerless_running_request_recovers_to_same_request_checkpoint(unified):
    client,send,t,p,runtime=unified;gid=ok(send())['question_id']
    t.fail='memory-assess'
    assert send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}]),request_id='recover').status_code==502
    path=runtime/'case-memory'/'cases-v3.sqlite'
    with sqlite3.connect(path) as db:db.execute("UPDATE request SET status='RUNNING' WHERE status='FAILED'")
    cases=CaseRepository(path,None,None)
    try:assert len(cases.recover_requests())==1
    finally:cases.close()
    t.fail=None;result=ok(send(request_id='recover'))
    assert result['executed']==['ASSESS','COMPOSE']


def test_accepted_publication_recovery_requires_current_case_guard(unified,monkeypatch):
    from semantic_runtime.legal_agent import publication
    from semantic_runtime.legal_agent.source_bundle import validate_current
    client,send,t,p,runtime=unified
    original=publication.export
    def interrupted(repo,runs):raise OSError('injected publication disk failure')
    monkeypatch.setattr(publication,'export',interrupted)
    with pytest.raises(OSError):send(request_id='disk')
    monkeypatch.setattr(publication,'export',original)
    pipeline=client.app.state.pipeline
    recovered=publication.recover(runtime/'legal-agent'/'runs',runtime/'runs',
        publication_guard=lambda repo,value:validate_current(repo,value,pipeline.store),contracts=pipeline.contracts)
    assert recovered[0]['status']=='COMPLETED'
    result=ok(send(request_id='disk'));assert result['response_schema']=='legal-agent-unified-response-v1'
    assert len(list((runtime/'legal-agent'/'runs').glob('*/*/journal.sqlite')))==1


def test_dependents_are_pending_when_source_experience_is_corrected(unified):
    client,send,t,p,runtime=unified;first=ok(send());gid=first['question_id']
    kid=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    reused=ok(send(command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,
        task='모의승인규정 제1조의 승인 대상은?',facts=[],queries=['승인']),session_id='other'))
    ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}])))
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        assert db.execute('SELECT status,pending FROM goal WHERE id=?',(reused['question_id'],)).fetchone()==('PENDING','ASSESS')


def test_interrupted_experience_rebind_resumes_after_saved_checkpoint(unified):
    client,send,t,p,runtime=unified
    first=ok(send());kid=ok(send(command('EXPERIENCE_CONFIRM',target=first['question_id'])))['experience_id']
    t.fail='domain-choice-PLAN'
    assert send(command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,
        task='모의승인규정 제1조의 승인 대상은?',facts=[],queries=['승인']),session_id='other',request_id='rebind').status_code==502
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        assert db.execute("SELECT status,pending FROM goal WHERE session='other'").fetchone()==('PENDING','PLAN')
        assert db.execute("SELECT count(*) FROM head h JOIN goal g ON g.id=h.goal WHERE g.session='other'").fetchone()[0]==1
    t.fail=None;result=ok(send(session_id='other',request_id='rebind'))
    assert result['executed']==['PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE']


def test_external_context_excludes_private_other_conversation_experience(unified):
    from semantic_runtime.legal_agent.unified_runtime import open_cases
    client,send,t,p,runtime=unified
    gid=ok(send())['question_id'];kid=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    cases=open_cases(client.app.state.pipeline,runtime,{},p)
    try:
        assert kid in {k['id'] for k in cases.candidates(p,'승인')}
        t.binding={**t.binding,'trust_zone':'external'}
        context=cases.context('new-public-session',p,'공개 승인 질문')
        assert context['knowledge']==context['user_wiki']==context['legal_wiki']==[]
        assert context['personal_history']['questions']==[] and context['wiki_links']=={}
    finally:cases.close()
