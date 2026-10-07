"""Bounded presentation regressions; synthetic sources, no model experiments."""
from copy import deepcopy
import json
import pytest
from test_tool_exploration_v3 import session, read, tool, delivered, decision, PROFILE
from test_legal_agent_double_harness import generation
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ProposalError, BudgetExhausted
from semantic_runtime.legal_agent.repository import encoded
from semantic_runtime.legal_agent import relations_protocol
from semantic_runtime.legal_agent.relations_repository import RelationsRepository


def dense(s,count=153):
    first=s.work.notices()[0]
    for i in range(count):
        n={**deepcopy(first),'relation_id':f'REL-dense-{i:03}',
           'completion_required':False,'guidance':'합성 긴 연결 안내. '*1000}
        n['notice_hash']=digest({k:v for k,v in n.items() if k!='notice_hash'})
        with s.work.transaction(): s.work.record_notice(n)


def expanded(action):
    return tool(action['tool'],**action['args'])


def test_root_read_error_has_executable_repair(tmp_path,generation):
    with session(tmp_path,generation) as s:
        v=s.view('investigate');delivered(s,v)
        with pytest.raises(ProposalError,match='Use locate'):
            s.apply_turn(v,decision(actions=[tool('read',target=v['corpus_root'],extent='article',cursor=None)]))
        assert not s.work.evidence()
        s.apply_turn(v,decision(actions=[tool('locate',locator='모의승인규정 제1조',target=v['corpus_root'],branch='any',cursor=None)]))
        v=s.view('investigate');delivered(s,v)
        target=next(o['items'][0]['target'] for o in v['last_action_results'] if o['tool']=='locate')
        s.apply_turn(v,decision(actions=[tool('read',target=target,extent='subtree',cursor=None)]))
        assert s.work.evidence()


def test_dense_menu_paging_selection_and_receipts(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);dense(s)
        v=s.view('investigate');delivered(s,v)
        assert v['exact_evidence'] and v['relation_selection_required']
        assert len(v['relation_menu'])==PROFILE['relation_page_size']
        assert not v['relation_notices']
        menu=v['relation_menu'][0];rid=menu['relation_id'];n=s.work.notice(rid)
        assert 'witness_spans' not in menu and 'preview_spans' not in encoded(menu)
        with pytest.raises(ProposalError,match='not presented'):
            s.work.item_visible(v['view_id'],'relation',rid,n['notice_hash'])
        seen={n['relation_id'] for n in v['relation_menu']}
        for i in range(3):
            more=next(c for c in v['continuations'] if c['section']=='relation_menu')
            # Tokens survive reopening the journal and remain bound to the original section.
            db=RelationsRepository(s.work.path)
            assert db.db.execute('SELECT 1 FROM navigation_cursor WHERE cursor=?',(more['action']['args']['cursor'],)).fetchone()
            db.close()
            wrong={**more['action']['args'],'section':'coverage'}
            with pytest.raises(ProposalError,match='another operation'):
                s.sources.validate_action(tool('view_page',**wrong))
            s.apply_turn(v,decision(actions=[expanded(more['action'])]))
            v=s.view('investigate');delivered(s,v)
            current={n['relation_id'] for n in v['relation_menu']}
            assert not current & seen
            seen.update(current)
        chosen=v['relation_menu'][0]
        count=len(s.work.evidence())
        s.apply_turn(v,decision(actions=[expanded(chosen['inspect_action'])]))
        v=s.view('investigate');delivered(s,v)
        full=next(n for n in v['relation_notices'] if n['relation_id']==chosen['relation_id'])
        s.work.item_visible(v['view_id'],'relation',full['relation_id'],full['notice_hash'])
        assert len(s.work.evidence())==count  # Expanding a relation does not READ its targets.
        assert len(encoded(v))<=s.profile['max_context_chars']
        assert len(encoded(s.gateway.request('investigate',v,'TurnDecision')).encode())<=s.gateway.transport.binding['max_input_bytes']
        summary=s.metadata(final=True)['exploration_v3']
        relations_protocol.validate('AuditSummary',summary)
        assert summary['totals']['relations']>=153 and summary['truncated']
        assert len(summary['display_lines'])<=64 and summary['display_lines'][-1].startswith('실행 기록:')


def test_large_evidence_is_paged_without_gaps(tmp_path,term_glossary):
    original='승인 범위를 확인한다. '*3200
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',[original])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        result=read(s,'모의규정 제1조')
        target=result['effective_args']['target']; chunks=[]
        while True:
            chunks.extend(s.work.evidence(e)['spans'][0] for e in result['evidence_ids'])
            v=s.view('investigate');delivered(s,v)
            assert len(encoded(v))<=s.profile['max_context_chars']
            if not result['next_cursor']: break
            assert not result['coverage']['complete']
            result=s.sources.execute(tool('read',target=target,extent='subtree',cursor=result['next_cursor']),f'page-{len(chunks)}')
        assert result['coverage']['complete']
        assert ''.join(p['text'] for p in chunks)==original
        assert all(a['end_cp']==b['start_cp'] for a,b in zip(chunks,chunks[1:]))
        assert len(chunks)>1
        assert all(len(p['text'])<=s.profile['max_context_chars']//8 for p in chunks)
        more=next(c for c in v['continuations'] if c['section']=='exact_evidence')
        old={e['evidence'] for e in v['exact_evidence']}
        r=s.sources.execute(expanded(more['action']),'show-stored')
        assert r['budget']['new_read_chars']==0
        v=s.view('investigate');delivered(s,v)
        assert set(r['evidence_ids'])<={e['evidence'] for e in v['exact_evidence']}
        assert set(r['evidence_ids'])-old


def test_search_only_materializes_returned_page(tmp_path,generation,monkeypatch):
    with session(tmp_path,generation,{**PROFILE,'page_size':1}) as s:
        from types import SimpleNamespace
        ids=[sid for sid,source in s.sources.tools.sources.items() if source['document_id'] in s.sources.scope]
        monkeypatch.setattr(s.sources.matcher,'fulltext',SimpleNamespace(
            rank=lambda *args:ids*1000,manifest={'tokenizer':'synthetic','ranking':'synthetic'}))
        s.sources.capabilities['fulltext']=True
        materialized=[];original=s.sources.node_card
        def card(*args,**kwargs):
            materialized.append(args)
            return original(*args,**kwargs)
        monkeypatch.setattr(s.sources,'node_card',card)
        args={'target':s.sources.root,'mode':'fulltext','query':'승인','cursor':None}
        result=s.sources.execute(tool('search',**args),'first')
        assert result['status'] not in ('ERROR','NOT_EXECUTED'),result.get('server_reason')
        assert len(materialized)==1 and result['search_receipt']['total']==len(ids)
        assert result['next_cursor']
        second=s.sources.execute(tool('search',**{**args,'cursor':result['next_cursor']}),'second')
        assert len(materialized)==2 and second['items'][0]['target']!=result['items'][0]['target']


def test_wire_byte_budget_includes_schema_and_korean_text(tmp_path,generation,monkeypatch):
    with session(tmp_path,generation) as s:
        read(s);dense(s,30)
        initial=s.view('investigate')
        # Deliberately lower the simulated deployment limit, without a network call.
        base=len(encoded(s.gateway.request('investigate',{},'TurnDecision')).encode())
        monkeypatch.setattr(s.gateway.transport,'binding',{**s.gateway.transport.binding,'max_input_bytes':base+16000})
        v=s.view('investigate')
        assert v['continuations']
        assert len(encoded(s.gateway.request('investigate',v,'TurnDecision')).encode())<=base+16000
        assert len(encoded(v))<=s.profile['max_context_chars']
        # Mandatory joint review is never silently converted into a partial receipt.
        s.profile['max_context_chars']=100
        with pytest.raises(BudgetExhausted):s.view('compose',required=[e['evidence'] for e in initial['exact_evidence']])


def test_many_relations_skip_automatic_target_read(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조를 준용한다.','승인 절차.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation',{**PROFILE,'relation_page_size':1}) as s:
        read(s,'모의규정 제1조')
        assert len(s.work.evidence())==1
        assert s.work.db.execute("SELECT 1 FROM system_task WHERE status='SKIPPED_SELECTION'").fetchone()
        assert not any(a['tool']=='read' and a['actor']=='SYSTEM_POLICY' for a in s.sources.action_summaries())
