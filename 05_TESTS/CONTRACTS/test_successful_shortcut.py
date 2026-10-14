"""Synthetic publication lifecycle, independent of legal semantic quality."""
import json
import pytest
from test_successful_core_routes import routes,publish
from semantic_runtime.legal_agent import core_evidence_route as core,successful_answer as success
from semantic_runtime.legal_agent.corrected_memory import MemoryError,encoded,digest
from semantic_runtime.ad_store import Store
from semantic_runtime.ad_backend import Backend

def simulate_legacy_or_corrupt_ledger(db):
    # Synthetic fault injection only: production immutable triggers are untouched.
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sw_event'").fetchall():
        db.execute('DROP TRIGGER "'+row[0]+'"')

STATES=['success','recovered_success','failed','interrupted','pending_export','empty','clarification','tampered_receipt','stale_revision','retired_route','foreign_team','rejected']

@pytest.mark.parametrize('surface',['ad_shortcut','native_wiki','compiler'])
@pytest.mark.parametrize('state',STATES)
def test_publication_matrix(routes,state,surface):
    r=routes;repo=r.cases.shortcut;db=repo.db
    simulate_legacy_or_corrupt_ledger(db)
    core.finalize(r.cases,r.result,r.p)
    before=db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]
    p=dict(r.p)
    if state in ('failed','interrupted','pending_export','empty','clarification'):
        db.execute("DELETE FROM sw_event WHERE kind='ANSWER_PUBLISHED'")
        if state in ('failed','interrupted'):db.execute('UPDATE sw_intake SET status=?',(state.upper(),))
    if state=='recovered_success':
        success.fail(r.cases,r.p);publish(r.cases,r.result,r.p)
    if state=='tampered_receipt':db.execute("UPDATE sw_event SET hash='broken' WHERE kind='ANSWER_PUBLISHED'")
    if state=='stale_revision':db.execute('UPDATE goal SET revision=revision+1')
    if state=='retired_route':db.execute("UPDATE route SET status='RETIRED'")
    if state=='foreign_team':p['team_id']='other'
    if state=='rejected':
        from semantic_runtime.ad_store import SCHEMA
        db.executescript(SCHEMA)
        db.execute("INSERT INTO ad_object(kind,entity,workspace,review,trashed,revision,changed_at) VALUES('shortcut',?,'t','REJECTED',0,1,0)",(r.cases.active_case,))
    if surface=='ad_shortcut':
        store=Store(repo.path)
        try:admitted=bool(Backend(store,p['team_id']).list('shortcut'))
        finally:store.close()
    elif surface=='native_wiki':admitted=bool(repo.search(p)['pages'])
    else:
        try:repo.compiler_input(r.cases.active_case,p);admitted=True
        except MemoryError:admitted=False
    assert admitted==(state in ('success','recovered_success'))
    assert db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==before


def test_export_must_precede_receipt(routes):
    r=routes;simulate_legacy_or_corrupt_ledger(r.cases.db);r.cases.db.execute("DELETE FROM sw_event WHERE kind='ANSWER_PUBLISHED'")
    with pytest.raises(MemoryError,match='durably exported'):publish(r.cases,r.result,r.p,status='PENDING')
    assert not success.eligible(r.cases.shortcut,r.cases.active_case)


def test_receipt_rolls_back_with_core_failure(routes,monkeypatch):
    from semantic_runtime.legal_agent import unified_runtime
    r=routes;simulate_legacy_or_corrupt_ledger(r.cases.db);r.cases.db.execute("DELETE FROM sw_event WHERE kind='ANSWER_PUBLISHED'")
    original=success.record
    def write(*a):publish(r.cases,r.result,r.p);return True
    def fail(*a):raise MemoryError('core failed')
    monkeypatch.setattr(success,'record',write);monkeypatch.setattr(core,'finalize',fail)
    # Direct transaction boundary proves receipt and finalization share a rollback.
    monkeypatch.setattr(success,'record',original)
    with pytest.raises(MemoryError):
        with r.cases.transaction():publish(r.cases,r.result,r.p);core.finalize(r.cases,r.result,r.p)
    assert not success.eligible(r.cases.shortcut,r.cases.active_case)


def test_compiler_filters_failed_trace_but_keeps_raw(routes):
    r=routes;repo=r.cases.shortcut
    ref=r.cases.route('g1')['payload']['judgment_refs']['SELECT']
    accepted=repo.trace(r.cases.active_case,r.p,kind='JUDGMENT',payload={'native_ref':ref,'payload':{'text':'accepted'}},documents=r.p['document_ids'],session='s')
    repo.trace(r.cases.active_case,r.p,kind='JUDGMENT',payload={'native_ref':{'run_id':'failed'},'payload':{'text':'bad'}},documents=r.p['document_ids'],session='s')
    snapshot=repo.compiler_input(r.cases.active_case,r.p);rows,excluded=success.compiler_records(repo,[snapshot])
    assert len(rows[0]['traces'])==1 and excluded
    assert repo.db.execute('SELECT count(*) FROM sw_trace').fetchone()[0]==2


def test_http_final_publication_and_failed_retry(unified,monkeypatch):
    client,send,t,p,runtime=unified
    p['authenticated']=True
    client.app.state.pipeline.contracts.pipeline['shortcut_v4']['features'].update(capture=True,core_evidence_route=True)
    t.fail='memory-assess'
    assert send(request_id='retry').status_code==502
    from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
    repo=ShortcutRepository(runtime/'case-memory/cases-v4.sqlite')
    try:
        ids=[r[0] for r in repo.db.execute('SELECT id FROM sw_investigation')]
        assert ids and not any(success.eligible(repo,i) for i in ids)
        t.fail=None;response=send(request_id='retry');assert response.status_code==200,response.text
        ident=response.json()['investigation_id'];assert success.eligible(repo,ident)
        assert repo.search(p)['pages']
        count=repo.db.execute("SELECT count(*) FROM sw_event WHERE kind='ANSWER_PUBLISHED'").fetchone()[0]
        assert send(request_id='retry').status_code==200
        assert repo.db.execute("SELECT count(*) FROM sw_event WHERE kind='ANSWER_PUBLISHED'").fetchone()[0]==count
        simulate_legacy_or_corrupt_ledger(repo.db)
        repo.db.execute("DELETE FROM sw_event WHERE kind='ANSWER_PUBLISHED'")
        assert not success.eligible(repo,ident)
        report=success.backfill(repo,runtime);assert report['verified']==1,report
        assert success.eligible(repo,ident)
    finally:repo.close()

from test_unified_legal_agent import unified
from test_structure_first_search import structured_generation


@pytest.mark.parametrize('change',['blank','clarification'])
def test_record_rejects_nonanswers(routes,change):
    from types import SimpleNamespace
    r=routes;simulate_legacy_or_corrupt_ledger(r.cases.db)
    r.cases.db.execute("DELETE FROM sw_event WHERE kind='ANSWER_PUBLISHED'")
    result=dict(r.result);answer={'text':'  ','claims':[]} if change=='blank' else {'text':'조건을 알려주세요','claims':[]}
    if change=='clarification':result['status']='CLARIFY'
    assert success.record(r.cases,result,r.p,{'answer':answer},None) is None
    assert not success.eligible(r.cases.shortcut,r.cases.active_case)


def test_compilation_binds_success_and_rejects_before_model(routes):
    from lawrag.pipeline.legal_wiki_compiler import compile_snapshots
    r=routes;repo=r.cases.shortcut;seen=[]
    snapshot=repo.compiler_input(r.cases.active_case,r.p)
    def model(prompt,data,schema):
        seen.append(data)
        return {'units':[{'id':'u1','topic':'모의','question':'모의 질문','completeness':'OPEN','unresolved':['검토 필요'],'jurisdiction':'KR','applicable_time':'UNKNOWN'}],
                'members':[{'unit':'u1','segment_id':data['records'][0]['segment_id'],'role':'CONTEXT','reason':'원질문'}],
                'claims':[],'procedures':[],'relations':[],'unassigned_spans':[],'conflicts':[],
                'completeness_checks':[{'unit':'u1','required_facts':False,'sources':False,'exceptions':False,'corrections':False}]}
    binding={'model':'synthetic','policy_hash':'p','prompt_hash':'q','trust_zone':'internal'}
    value=compile_snapshots(repo,r.p,[snapshot],model=model,binding=binding)
    assert value['successful_publications'][r.cases.active_case]
    unit=value['units'][0];stored=repo.current(unit['unit_id'],unit['revision'],r.p,allow_draft=True)
    assert stored['successful_publications']==value['successful_publications']
    success.fail(r.cases,r.p)
    with pytest.raises(MemoryError):compile_snapshots(repo,r.p,[snapshot],model=model,binding=binding)
    assert len(seen)==1
