"""Real reference/HTTP journal projections using synthetic documents only."""
import copy
import io
import json
import logging

import pytest
from test_batch_reference_navigation import connected, initial, decision, rel, ur
from test_rag_activity_log import native_journal
from test_genos_chat_flow import journal
from test_unified_legal_agent import unified
from test_structure_first_search import structured_generation
from semantic_runtime.legal_agent.investigation_diagnostics import exception_diagnostics, selection_report
from semantic_runtime.legal_agent.readable_log import render_detail
from semantic_runtime.legal_agent.memory_rag import SourceInvestigationIncomplete
from semantic_runtime import observability as obs
from semantic_runtime.request_report import _LiveLog


def navigate(s, rec, **kwargs):
    return rel.navigate('승인',s,{'U1':rec['unit_reads'][0]},
        kwargs.pop('invoke',lambda *a:decision(a[1])),read_state=dict(rec['read_state']),
        seconds_left=kwargs.pop('seconds_left',lambda:120),
        max_context_chars=kwargs.pop('max_context_chars',80000),**kwargs)


def test_model_defer_is_not_reported_as_a_data_resolution_failure(connected):
    s,_=connected;rec,_=initial(s)
    out=navigate(s,rec,invoke=lambda *a:decision(a[1],'DEFER'))
    diagnostic=out['diagnostics']
    assert out['pending'] and diagnostic['counts']=={'MODEL_DECISION':1}
    item=diagnostic['blockers'][0]
    assert item['code']=='MODEL_REFERENCE_DEFERRED' and item['decision']['action']=='DEFER'
    assert item['references'] and all(r['resolution'].startswith('EXACT_') for r in item['references'])
    assert item['decision']['reason'] and item['target']['document_id']=='detail'
    text=render_detail('AGENT REFERENCE NAVIGATION STATUS',diagnostic)
    assert item['references'][0]['reference_id'] in text and 'MODEL_REFERENCE_DEFERRED' in text


@pytest.mark.parametrize('connected',['① 「모의승인규정」 제1조제1항을 준용한다.'],indirect=True)
def test_stored_unresolved_required_reference_keeps_resolution_and_locator(connected,monkeypatch):
    s,_=connected
    import sqlite3
    db=sqlite3.connect(':memory:');s.tools.db.backup(db)
    monkeypatch.setattr(s.tools,'db',db)
    # Corrupt only the synthetic reference's resolution, retaining its verified witness.
    rows=s.tools.db.execute('SELECT id,json FROM reference').fetchall()
    for ident,raw in rows:
        row=json.loads(raw)
        if row['document_id']=='detail':
            row.update(resolution='UNRESOLVED_COORDINATE',reason='모의 대상 좌표 미확정')
            s.tools.db.execute('UPDATE reference SET json=? WHERE id=?',(json.dumps(row,ensure_ascii=False),ident))
    s.tools.db.commit()
    src=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    h=rel.hit_for(s,src['id'],'1');state={'count':0,'chars':0}
    original=ur.read(s,h,next(o for o in ur.offers(s,h) if o['id']=='subtree:1'),action_state=state)
    out=rel.navigate('준용 기준',s,{'U1':original},lambda *a:decision(a[1]),
        read_state=state,seconds_left=lambda:120,max_context_chars=80000)
    items=[i for i in out['diagnostics']['blockers'] if i['category']=='DATA_REFERENCE']
    assert out['pending'] and items
    item=items[0]
    assert item['resolution']=='UNRESOLVED_COORDINATE' and item['stored_resolution_reason']=='모의 대상 좌표 미확정'
    assert item['locator'] and item['reference_id'] and item['document_id']=='detail'
    assert item['basis']=='stored_reference' and item['blocks_completion']


def test_context_limit_logs_measured_limit_and_unprocessed_references(connected):
    s,_=connected;rec,_=initial(s)
    out=navigate(s,rec,max_context_chars=1)
    items=out['diagnostics']['blockers']
    limit=next(i for i in items if i['code']=='REFERENCE_CONTEXT_LIMIT')
    assert limit['actual_context_chars']>limit['context_chars_limit']==1
    assert any(i['code']=='REFERENCE_GROUP_NOT_PROCESSED' and i['references'] for i in items)
    assert not any(i['category']=='DATA_REFERENCE' for i in items)
    assert not any(i['code']=='REFERENCE_WORK_LIMIT' for i in items)  # no work limit was reached


def test_timeout_preserves_exception_and_navigation_phase(connected):
    s,_=connected;rec,_=initial(s)
    with pytest.raises(TimeoutError,match='time budget') as raised:
        navigate(s,rec,seconds_left=lambda:0)
    diagnostic=exception_diagnostics(raised.value)
    assert diagnostic['stage']=='REFERENCE_NAVIGATION'
    assert diagnostic['location']['function']=='_navigate'
    assert any(i['category']=='EXECUTION_FAILURE' for i in diagnostic['investigation']['blockers'])
    assert s.repo.db.execute("SELECT 1 FROM event WHERE kind='REFERENCE_NAVIGATION_FAILED'").fetchone()


def test_legacy_pending_is_explicitly_unknown_and_never_assigned_to_data():
    out=selection_report({'status':'pending','next_action':'CONTINUE_REFERENCES',
        'reference_navigation':{'pending':True}})
    assert out['counts']=={'DIAGNOSTIC_GAP':1}
    assert out['cause_codes']==['REFERENCE_PENDING_CAUSE_NOT_RECORDED']
    exc=SourceInvestigationIncomplete({'status':'pending','next_action':'CONTINUE_REFERENCES',
        'reference_navigation':{'pending':True}})
    assert exc.code=='SOURCE_INVESTIGATION_INCOMPLETE' and 'MemoryError' not in str(exc)


def test_failure_details_survive_journal_live_text_and_service_log(native_journal,monkeypatch):
    repo,projection,events=native_journal
    monkeypatch.setenv('GENOS_CODESERVING_TOKEN','sensitive-fixture-token')
    diagnostic={'error_code':'SOURCE_INVESTIGATION_INCOMPLETE','error_type':'fixture.Incomplete',
        'error_message':'bad sensitive-fixture-token','stage':'SELECT','location':{'file':'fixture.py','line':7,'function':'select'},
        'investigation':{'stage':'SELECT','generation_id':'fixture-generation','pending':True,
            'counts':{'DATA_REFERENCE':1},'cause_codes':['REFERENCE_TARGET_UNRESOLVED'],
            'observations':[],'blockers':[{'category':'DATA_REFERENCE','code':'REFERENCE_TARGET_UNRESOLVED',
                'reference_id':'ref-distinct','document_id':'allowed','resolution':'UNRESOLVED_COORDINATE','locator':{'article':'제7조'}}]}}
    repo.fail('SOURCE_INVESTIGATION_INCOMPLETE',diagnostics=diagnostic)
    stream=io.StringIO();handler=_LiveLog('fixture',stream,repo.path.parent)
    handler.journal_path=repo.path;handler.run_id=repo.context.run_id
    try:
        handler.poll_journal()
        record=logging.LogRecord('genos.test',logging.ERROR,__file__,1,'ask.failed',(),None)
        record.fields={'request_id':'fixture','failure_diagnostics':diagnostic}
        handler.emit(record)
        saved=stream.getvalue()
        assert all(v in saved for v in ('ref-distinct','UNRESOLVED_COORDINATE','제7조','fixture.py','SELECT'))
        assert 'sensitive-fixture-token' not in saved and '[REDACTED]' in saved
        fields=json.loads(obs.JsonFormatter().format(record))
        assert fields['failure_diagnostics']['investigation']['blockers'][0]['reference_id']=='ref-distinct'
        assert 'sensitive-fixture-token' not in json.dumps(fields)
    finally:handler.close()


def test_progress_filters_foreign_documents_and_marks_omitted_rows(native_journal):
    repo,projection,events=native_journal
    rows=[{'category':'DATA_REFERENCE','code':'REFERENCE_TARGET_UNRESOLVED','reference_id':f'allowed-ref-{n}',
           'document_id':'allowed','resolution':'UNRESOLVED_COORDINATE'} for n in range(15)]
    rows.append({'category':'DATA_REFERENCE','code':'PRIVATE_CAUSE','document_id':'other','reference_id':'PRIVATE_REF'})
    from semantic_runtime.legal_agent.investigation_diagnostics import report
    repo.event('REFERENCE_NAVIGATION_STATUS',report('REFERENCE_NAVIGATION',True,rows,generation_id='fixture'))
    projection.poll_journal()
    rendered=json.dumps(events,ensure_ascii=False)
    assert 'PRIVATE_CAUSE' not in rendered and 'PRIVATE_REF' not in rendered
    assert '전체 상세' in rendered and '데이터 참조 해석: 15' in rendered


def test_unknown_stop_code_is_visible_instead_of_generic_state():
    text=render_detail('AGENT UNIT CANDIDATE ACQUISITION STOPPED',{'stop_reason':'NEW_CAUSE_X'})
    assert 'NEW_CAUSE_X' in text


def test_http_failure_keeps_source_cause_through_native_runtime(unified,monkeypatch,caplog):
    from semantic_runtime.legal_agent import memory_rag
    from semantic_runtime.legal_agent.investigation_diagnostics import report
    _,send,transport,_,runtime=unified
    diagnostic=report('SELECT',True,[{'category':'DATA_REFERENCE','code':'REFERENCE_TARGET_UNRESOLVED',
        'reference_id':'http-reference-7','document_id':'d','resolution':'UNRESOLVED_COORDINATE',
        'locator':{'article':'제7조'}}],generation_id='synthetic-http-generation')
    monkeypatch.setattr(memory_rag,'select_sources',lambda *a,**kw:{'status':'pending','needs_fulltext':False,
        'next_action':'CONTINUE_REFERENCES','final_ids':['s'],'diagnostics':diagnostic})
    response=send()
    assert response.status_code==422 and 'REFERENCE_TARGET_UNRESOLVED' in response.text
    event=next(r for r in caplog.records if r.getMessage()=='ask.failed')
    assert event.fields['error_code']=='SOURCE_INVESTIGATION_INCOMPLETE'
    assert event.fields['failure_diagnostics']['stage']=='SELECT'
    assert event.fields['failure_diagnostics']['investigation']['blockers'][0]['reference_id']=='http-reference-7'
    import sqlite3
    paths=list(runtime.glob('legal-agent/runs/*/*/journal.sqlite'));assert len(paths)==1
    with sqlite3.connect(paths[0]) as db:
        saved=json.loads(db.execute("SELECT payload_json FROM event WHERE kind='RUN_FAILED'").fetchone()[0])
    assert saved['diagnostics']['investigation']['cause_codes']==['REFERENCE_TARGET_UNRESOLVED']
    assert saved['code']=='SOURCE_INVESTIGATION_INCOMPLETE' and 'memory-assess' not in transport.phases
