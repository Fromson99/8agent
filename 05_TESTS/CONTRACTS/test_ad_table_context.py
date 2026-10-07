"""Synthetic large tables: actual paging, context isolation and chat display."""
import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from semantic_runtime.ad_store import Store
from semantic_runtime.ad_context import ContextReader
from semantic_runtime.ad_mode import handle,ENTER,Controller,fields_table
from semantic_runtime import ad_language,chat_adapter

ROOT=Path(__file__).resolve().parents[2]


def output(action,**args):
    plan={'action':action,'args':args}
    return {'plan':plan,'receipt':{'provider':'genos','trust_zone':'internal','model':'synthetic'},'raw':{'plan':plan}}


@pytest.fixture
def large(tmp_path):
    path=tmp_path/'ad.sqlite';handle(path,'financial_team','genos','chat',ENTER,'enter')
    store=Store(path)
    with store.transaction():
        session=store.session('financial_team','genos','chat')
        view=store.view(session['id'],'shortcut',[
            {'kind':'shortcut','id':str(i),'title':f'row-{i} '+('한글|<script>악성</script>\n'*5000),'revision':1,'status':'review'}
            for i in range(1000)])
        store.page(session['id'],view)
    sid=session['id'];store.close()
    def ask(q,model,request='turn'):
        return handle(path,'financial_team','genos','chat',q,request,interpret=model)
    return path,sid,view,ask


def test_large_table_read_uses_only_latest_segment_and_keeps_display_position(large):
    path,sid,view,ask=large;inputs=[]
    def model(ctx,*_):
        inputs.append(json.loads(json.dumps(ctx)))
        assert len(json.dumps(ctx,ensure_ascii=False))<40000
        assert '악성</script>\n'*100 not in json.dumps(ctx,ensure_ascii=False)
        if len(inputs)==1:return output('read_table',source='view',id=view,offset=800,notes='801번 구간 확인')
        if len(inputs)==2:
            assert ctx['segment']['rows'][0]['ordinal']==801
            assert ctx['segment']['next_offset']==808
            return output('read_table',source='view',id=view,offset=808,notes='801번 검토 완료')
        assert ctx['segment']['rows'][0]['ordinal']==809
        assert 'row-800' not in json.dumps(ctx['segment'],ensure_ascii=False)
        return output('clarify',message='809번 항목을 확인할까요?')
    result=ask('뒤쪽 자료도 확인해줘',model)
    assert result['model_call_count']==3 and len(result['model_receipts'])==3
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT position FROM ad_view WHERE id=?',(view,)).fetchone()[0]==20
        assert db.execute('SELECT count(*) FROM ad_language_call').fetchone()[0]==3
        assert json.loads(db.execute('SELECT input FROM ad_language_call WHERE sequence=3').fetchone()[0])['segment']['offset']==808
    assert ask('뒤쪽 자료도 확인해줘',lambda *_:pytest.fail('cached request repeated model'))==result


def test_string_chunks_preserve_every_character_and_use_turn_scoped_cursors(large):
    path,sid,_,_=large;store=Store(path);reader=ContextReader(store,sid)
    value='가나다<>&|\n'*4000;preview=reader.pack(value)
    cursor=preview['cursor'];parts=[]
    while cursor:
        chunk=reader.read(cursor);parts.append(chunk['data'])
        assert len(chunk['data'])<=reader.CHUNK_CHARS
        cursor=chunk['next_cursor']
    assert ''.join(parts)==value
    with pytest.raises(ValueError,match='AD_SCOPE'):ContextReader(store,sid).read(preview['cursor'])
    store.close()


def test_large_list_chunks_cover_every_item_without_overlap(large):
    path,sid,_,_=large;store=Store(path);reader=ContextReader(store,sid)
    source=list(range(1000));preview=reader.pack(source);seen=preview['items'];cursor=preview['cursor']
    while cursor:
        chunk=reader.read(cursor);seen+=chunk['data'];cursor=chunk['next_cursor']
    assert seen==source
    store.close()


def test_detail_pages_are_complete_and_do_not_move_user_position(large):
    path,sid,_,_=large;store=Store(path)
    rows=[{'field':f'column{i}','value':'원문'*1000} for i in range(100)]
    with store.transaction():
        store.db.execute('INSERT INTO ad_detail VALUES(?,?,?,?,?,?)',
            ('Dsynthetic',sid,'entity',json.dumps({'display_schema':'ad-detail-table-v1','rows':rows}),17,1))
    reader=ContextReader(store,sid);offset=0;seen=[]
    while offset is not None:
        segment=reader.table('detail','Dsynthetic',offset);seen+=segment['rows'];offset=segment['next_offset']
    assert [r['field'] for r in seen]==[r['field'] for r in rows]
    assert all(r['value']['total_chars']==2000 for r in seen)
    assert store.db.execute('SELECT position FROM ad_detail WHERE id=?',('Dsynthetic',)).fetchone()[0]==17
    store.close()


def test_nested_structured_edit_values_are_paged_without_losing_source(large):
    path,sid,_,_=large;store=Store(path);reader=ContextReader(store,sid)
    value='긴값'*5000
    for _ in range(4):value={f'field{i}':value for i in range(16)}
    packed=reader.pack(value)
    assert len(json.dumps(packed,ensure_ascii=False))<150000
    assert 'cursor' in json.dumps(packed)
    # Data behind a deferred branch remains accessible, including full columns.
    assert any(isinstance(v,list) for v,_ in reader.cursors.values())
    store.close()


def test_read_cursor_rounds_return_full_large_value_to_model(large):
    path,sid,view,ask=large;pieces=[];calls=[]
    def model(ctx,*_):
        calls.append(1)
        if len(calls)==1:return output('read_table',source='view',id=view,offset=0,notes='첫 행 확인')
        if len(calls)==2:
            cursor=ctx['segment']['rows'][0]['title']['cursor']
            return output('read_context',cursor=cursor,notes='제목 확인')
        pieces.append(ctx['segment']['data'])
        assert isinstance(pieces[-1],str) and len(pieces[-1])<=2000
        if len(calls)<5:return output('read_context',cursor=ctx['segment']['next_cursor'],notes='제목 일부 확인, 아직 미완료')
        return output('clarify',message='제목 범위를 좁혀 주세요.')
    result=ask('첫 행 제목 길게 읽어줘',model)
    assert result['model_call_count']==5 and len(pieces)==3
    with sqlite3.connect(path) as db:original=db.execute('SELECT title FROM ad_view_row WHERE view=? AND ordinal=1',(view,)).fetchone()[0]
    assert ''.join(pieces)==original[:6000]


def test_other_chat_table_read_is_rejected(large):
    path,_,_,ask=large;store=Store(path)
    with store.transaction():
        other=store.session('financial_team','genos','other')
        foreign=store.view(other['id'],'shortcut',[])
    store.close()
    result=ask('표 확인',lambda *_:output('read_table',source='view',id=foreign,offset=0,notes=''))
    assert result['answer_status']=='error' and 'AD_SCOPE' in result['text']


def test_state_change_between_chunks_fences_final_mutation(large):
    path,_,view,ask=large;calls=[]
    def model(ctx,*_):
        calls.append(1)
        if len(calls)==1:return output('read_table',source='view',id=view,offset=0,notes='')
        handle(path,'financial_team','genos','chat','[AD모드 종료]','exit')
        return output('mutate',target={'view_id':view,'rows':[1],'selection':False,'all_rows':False},operation='trash')
    result=ask('확인하고 지워줘',model)
    assert result['answer_status']=='error' and 'AD_CONFLICT' in result['text']
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM ad_change').fetchone()[0]==0


def test_read_exhaustion_never_claims_completed_analysis_or_mutates(large,monkeypatch):
    _,_,view,ask=large;monkeypatch.setattr(ad_language,'MAX_MODEL_CALLS',2)
    result=ask('계속 읽기',lambda *_:output('read_table',source='view',id=view,offset=0,notes=''))
    assert result['answer_status']=='error' and 'AD_CONTEXT_INCOMPLETE' in result['text']


def test_long_history_and_selection_edit_payload_are_referenced(large):
    path,_,_,ask=large;huge='큰편집값'*10000
    with sqlite3.connect(path) as db:
        response={'clarification':huge,'resolved_plan':{'action':'edit','args':{'value':huge}}}
        db.execute("UPDATE ad_operation SET action=?,response=? WHERE request='enter'",(huge,json.dumps(response)))
    def model(ctx,*_):
        assert len(json.dumps(ctx,ensure_ascii=False))<40000
        assert ctx['state']['history'][0]['request']['total_chars']==len(huge)
        assert ctx['state']['history'][0]['resolved_plan']['args']['value']['cursor']
        return output('clarify',message='필드 확인')
    assert ask('이어서',model)['answer_status']=='administration'


def workflow():
    spec=importlib.util.spec_from_file_location('ad_scroll_workflow',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_scroll_table_is_safe_and_workflow_keeps_markdown_fallback(large,monkeypatch):
    path,sid,_,_=large;store=Store(path)
    session=dict(store.db.execute('SELECT * FROM ad_session WHERE id=?',(sid,)).fetchone())
    value='<script>alert(1)</script>|<br>\n<img src=x onerror=alert(2)>'
    result=Controller(store,session).respond(fields_table([{'field':'자료','value':value}]))
    html=result['table_html']
    assert 'overflow:auto' in html and 'max-height:480px' in html and 'position:sticky' in html
    assert '<script>' not in html and '<img' not in html and '&lt;script&gt;' in html
    assert '&lt;br&gt;' in html
    module=workflow();display=module._ad_result(result)
    assert display['text']==html and display['text_markdown']==result['text']
    monkeypatch.setenv('GENOS_AD_TABLE_FORMAT','markdown')
    assert module._ad_result(result)['text']==result['text']
    store.close()


def test_workflow_and_chat_probe_return_scroll_html(monkeypatch):
    module=workflow()
    body={'response_schema':'ad-mode-v1','text':'| 자료 | 值 |','table_html':'<div style="overflow:auto"><table></table></div>'}
    monkeypatch.setattr(module,'_post_code_serving',lambda *_: {'code':0,'data':body})
    assert asyncio.run(module.run({'question':'1번 보여줘','chatId':'chat'}))['text']==body['table_html']
    async def service(_):return {'code':0,'data':body}
    monkeypatch.setattr(chat_adapter,'views',lambda:module)
    monkeypatch.setattr(chat_adapter,'call_service',service)
    assert asyncio.run(chat_adapter.chat({'question':'1번 보여줘','chatId':'chat'}))['data']['text']==body['table_html']
