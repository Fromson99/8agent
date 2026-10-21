"""Workflow observability contracts: synthetic journals, no network/model calls."""
import asyncio
import json
import logging
from pathlib import Path
import sqlite3

import pytest

from semantic_runtime import observability as obs
from semantic_runtime.chat_adapter import views
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from semantic_runtime.progress import ProgressCapture
from semantic_runtime.request_journals import children, paths
from semantic_runtime.request_report import _journal, live_log, format_readable_report
from workflow.repository import Repository


@pytest.fixture
def journals(tmp_path):
    root = tmp_path/'runtime'
    ident = 'a'*32
    request = {'workflow_id':'risk_team_compare_workflow', 'request_id':'request',
               'document_ids':['inside','outside'], 'principal':{'team_id':'risk_team','user_id':'session'}}
    binding = {'workflow':'fixture', 'request':digest(request), 'document_ids':request['document_ids'],
               'principal':request['principal']}
    context = RequestContext.create({'id':'q','question':'대사','scope':{'document_version_ids':request['document_ids']}},
                                    request,binding,300,ident)
    path = root/'workflows'/ident/'journal.sqlite'
    path.parent.mkdir(parents=True)
    work = WorkRepository(path,context,DEFAULT_PROFILE)
    repository = Repository(work,request,binding)
    opened = [work]
    def add(side, child_id):
        call_id = 'call-'+side
        repository.intent(call_id,'rag',{'operation':'ask_rag','side':side,'args':{}})
        cpath = path.parent/'children'/side/'legal-agent/runs/day'/child_id/'journal.sqlite'
        cpath.parent.mkdir(parents=True)
        did = 'inside' if side == 'internal' else 'outside'
        b = {'scope':{'document_version_ids':[did]}}
        context = RequestContext.create({'id':'child','question':side}, {'request_id':call_id}, b,300,child_id)
        child = WorkRepository(cpath,context,DEFAULT_PROFILE);opened.append(child)
        work.db.execute('CREATE TABLE IF NOT EXISTS workflow_child_run(call_id TEXT,run_id TEXT,journal TEXT,binding_hash TEXT)')
        work.db.execute('INSERT INTO workflow_child_run VALUES(?,?,?,?)',(call_id,child_id,str(cpath),context.binding_hash))
        child.event('LAW_FULLTEXT_DIRECTORY',{'laws':[{'document_id':did,'name':'모의'+side},
                                                    {'document_id':'denied','name':'PRIVATE DOC'}]})
        child.event('UNIT_READ_STARTED',{'document_id':did,'document_name':'모의'+side,'location':'제1조'})
        child.event('WORKFLOW_CHILD_FAILED',{'cause':'fixture child failure '+side})
        return child
    yield root,path,work,repository,add
    for work in reversed(opened):work.close()


def record(name, **fields):
    value=logging.LogRecord('genos.test',logging.INFO,__file__,1,name,(),None)
    value.fields=fields
    return value


def test_parent_and_both_child_sources_reach_same_frontend_with_no_private_data(journals,monkeypatch):
    root,path,work,repo,add=journals
    events=[];c=ProgressCapture('request',root,events.append)
    c.emit(record('workflow.started',request_id='request',workflow_run_id='a'*32,run_id='a'*32))
    for side,ident in [('internal','b'*32),('external','c'*32)]:
        state=repo.state()['checkpoint'];state['stage']='FIND_'+side.upper();repo.save(state)
        c.poll_journal();add(side,ident)
        c.emit(record('source.read.started',request_id='call-'+side,workflow_request_id='request',
                      workflow_run_id='a'*32,run_id=ident))
        c.poll_journal()
    state=repo.state()['checkpoint'];state['stage']='END';repo.save(state,status='partial',result={'status':'partial'})
    c.poll_journal();before=json.dumps(events,ensure_ascii=False);c.poll_journal()
    assert before==json.dumps(events,ensure_ascii=False)
    assert c.run_id=='a'*32 and len(c.child_captures)==2
    assert all(e['run_id']=='a'*32 for e in events)
    assert '모의internal' in before and '모의external' in before
    assert 'PRIVATE DOC' not in before and 'fixture child failure' not in before
    assert events[-1]['basis']['state']=='partial'
    assert not any(e['basis'].get('stage')=='complete' for e in events)
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','final-cards')
    shown=asyncio.run(views().workflow_display_result({'answer':{'text':'부분 결과'}},events,request_id='request'))
    cards=json.dumps(shown['agentFlowExecutedData'],ensure_ascii=False)
    for label in ('내규 원문','외규 원문','모의internal','모의external','미확인 사항'):assert label in cards


@pytest.mark.parametrize('tamper',['parent_hash','child_hash','child_scope','path','unknown_child'])
def test_unbound_child_is_never_displayed_or_reported(journals,tamper):
    root,path,work,repo,add=journals;child=add('internal','b'*32)
    # Simulate on-disk corruption beyond the normal SQL immutability guard.
    for target in (work,child):
        for name, in target.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='run'").fetchall():
            target.db.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
    if tamper=='parent_hash':work.db.execute('UPDATE run SET binding_hash=?',('0'*64,))
    elif tamper=='child_hash':child.db.execute('UPDATE run SET binding_hash=?',('0'*64,))
    elif tamper=='child_scope':
        b={'scope':{'document_version_ids':['hidden']}}
        child.db.execute('UPDATE run SET binding_json=?,binding_hash=?',(json.dumps(b),digest(b)))
        work.db.execute('UPDATE workflow_child_run SET binding_hash=?',(digest(b),))
    elif tamper=='path':work.db.execute('UPDATE workflow_child_run SET journal=?',(str(path),))
    else:work.db.execute('DELETE FROM workflow_call')
    assert children(path,'a'*32)==[]
    events=[];c=ProgressCapture('request',root,events.append);c.run_id='a'*32;c.poll_journal()
    assert '모의internal' not in json.dumps(events,ensure_ascii=False)
    assert _journal(root,'a'*32)['children']==[]


def test_parent_and_children_live_and_final_logs_have_independent_cursors(journals,tmp_path):
    root,path,work,repo,add=journals
    state=repo.state()['checkpoint'];state['stage']='FIND_INTERNAL';repo.save(state)
    add('internal','b'*32);add('external','c'*32)
    with live_log(tmp_path/'shared','request',root) as (logpath,handler):
        handler.emit(record('workflow.started',request_id='request',run_id='a'*32,workflow_run_id='a'*32))
        handler.emit(record('model.attempt.started',request_id='call-internal',workflow_request_id='request',
                            run_id='b'*32,workflow_run_id='a'*32))
        handler.poll_journal()
        text=logpath.read_text()
        handler.poll_journal();assert logpath.read_text()==text
        assert 'WORKFLOW CHECKPOINT' in text and 'fixture child failure internal' in text and 'fixture child failure external' in text
        assert set(handler.journal_cursors)=={'a'*32,'b'*32,'c'*32}
        assert handler.run_id=='a'*32
    report=_journal(root,'a'*32)
    assert report['status']=='FOUND' and {c['side'] for c in report['children']}=={'internal','external'}
    rendered=format_readable_report({'run_id':'a'*32,'journal':report})
    assert rendered.count('WORKFLOW_CHILD_FAILED')==2
    assert paths(root,'../../bad')==[]


@pytest.mark.parametrize('operation',['WORKFLOW_RUN','WORKFLOW_RESUME'])
@pytest.mark.parametrize('failure',[False,True])
def test_explicit_execution_uses_stream_and_keeps_cards_on_failure(monkeypatch,operation,failure):
    w=views();calls=[];monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','final-cards')
    async def stream(question,data,display,*,payload=None):
        calls.append(payload)
        await display.progress({'schema_version':'rag-progress-v1','kind':'phase','label':'내규 원문을 조사 중',
            'basis':{'kind':'WORKFLOW_CHECKPOINT','detail_mode':'activity','stage':'FIND_INTERNAL'}})
        if failure:raise OSError('PRIVATE ERROR')
        return {'response_schema':'workflow-result-v1','status':'partial','run_id':'a'*32,'answer':{'text':'대사 부분 결과'}}
    monkeypatch.setattr(w,'_stream_code_serving',stream)
    monkeypatch.setattr(w,'_post_code_serving',lambda *_:pytest.fail('JSON path bypassed progress'))
    data={'API_TYPE':operation,'request_id':'request','session_id':'session','team_id':'risk_team',
          'run_id':'a'*32,'expected_revision':3}
    if operation=='WORKFLOW_RUN':data['question']='대사: 비교'
    result=asyncio.run(w._run_once(data))
    assert len(calls)==1 and calls[0]['API_TYPE']==operation
    if operation=='WORKFLOW_RESUME':
        assert calls[0]['json']=={k:v for k,v in data.items() if k not in {'API_TYPE','request_id'}}
    assert '내규 원문' in json.dumps(result['agentFlowExecutedData'],ensure_ascii=False)
    assert 'PRIVATE ERROR' not in result['text']
    assert result['answer_status']==('failed' if failure else 'partial')


def test_explicit_workflow_json_fallback_preserves_exact_resume_payload(monkeypatch):
    import urllib.error
    w=views();sent=[]
    monkeypatch.setattr(w,'_settings',lambda:('http://fixture/json','fixture-token',30))
    monkeypatch.setattr(w.urllib.request,'urlopen',lambda *a,**k:(_ for _ in ()).throw(urllib.error.HTTPError('http://fixture/stream',404,'missing',{},None)))
    payload={'API_TYPE':'WORKFLOW_RESUME','request_id':'req','run_id':'a'*32,'expected_revision':3,
             'session_id':'session','team_id':'risk_team'}
    def post(value):
        sent.append(value)
        return {'status':200,'body':{'status':'partial'}}
    monkeypatch.setattr(w,'_post_code_serving',post)
    monkeypatch.setattr(w,'call_code_serving',lambda *a:pytest.fail('resume must not become a new question'))
    result=asyncio.run(w._stream_code_serving('',{'request_id':'req'},w._ChatProgress({}),payload=payload))
    assert sent==[payload] and result['status']=='partial'


def test_live_log_stop_drains_multiple_bounded_batches(journals,tmp_path):
    root,path,work,repo,add=journals
    child=add('internal','b'*32)
    for n in range(600):child.event('WORKFLOW_TRACE_FIXTURE',{'position':n})
    with live_log(tmp_path/'logs','request',root) as (logpath,handler):
        handler.emit(record('workflow.started',request_id='request',workflow_run_id='a'*32))
    text=logpath.read_text()
    assert text.count('AGENT WORKFLOW TRACE FIXTURE')==600
    assert handler.journal_cursors['b'*32][0]==child.db.execute('SELECT max(seq) FROM event').fetchone()[0]
