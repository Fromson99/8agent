"""Synthetic batching/stop/required-context contracts; no model benchmark."""
import copy
import pytest
from test_unit_fulltext_adaptive_read import session, tree, hit
from semantic_runtime.legal_agent import unit_reading as ur, unit_selection as us
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.errors import ProposalError
from test_batch_reference_navigation import connected, initial
from semantic_runtime.legal_agent import unit_relations as rel


def candidates(s,monkeypatch):
    monkeypatch.setitem(ur.POLICY,'batch_groups',1)
    monkeypatch.setitem(ur.POLICY,'group_units',1)
    first=hit(s,'3');hits=[first,hit(s,'5'),hit(s,'4')]
    r=SourceRecall(s.sources)
    r.discover=lambda:([first['source_id']],{'discovery_mode':'fulltext','routes':{},'unit_hits':hits})
    return r.prepare()


def choice(row,scope):
    return {'id':row['id'],'scope':scope,'reason':'질문의 해당 원문과 상위 조건 확인'}


def test_initial_acquisition_defers_other_candidates_and_explicit_sufficiency_stops(session,monkeypatch):
    s,_=session;record=candidates(s,monkeypatch);before=copy.deepcopy(record);calls=[]
    assert len(record['unit_reads'])==1 and len(record['pending_unit_hits'])==2
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if phase=='source-unit-triage':return {'issues':['긴급 예외'],'choices':[choice(data['units'][0],'exact:3')],'needs_search':False}
        assert 'evidence_sufficient' in schema['required']
        assert '긴급' in data['sources'][0]['text']
        return {'issues':[],'choices':[],'needs_search':False,'evidence_sufficient':True,'sufficiency_reason':'긴급 승인 규칙과 상위 조건을 확보했고 미확인 필수 연결이 없음'}
    out=us.select('긴급 승인 예외',record,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert out['candidate_acquisition']['stop_reason']=='EVIDENCE_SUFFICIENT'
    assert len(out['candidate_acquisition']['unread_candidate_keys'])==2
    assert calls==['source-unit-triage','source-unit-review'] and record==before
    assert {p['block_id'] for e in out['selected_evidence'] for p in e['spans']}=={'0','1','2','3'}
    assert not any(p['block_id'] in ('4','5') for e in s.work.evidence() for p in e['spans'])


def test_insufficient_batch_reads_next_batch_and_uses_unique_receipts(session,monkeypatch):
    s,_=session;record=candidates(s,monkeypatch);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if phase.startswith('source-unit-triage'):
            choices=[] if not phase.endswith('-2') else [choice(next(r for r in data['units'] if r['unit']=='5'),'exact:5')]
            return {'issues':['보고'],'choices':choices,'needs_search':False}
        enough=phase.endswith('-2')
        return {'issues':[],'choices':[],'needs_search':False,'evidence_sufficient':enough,
                'sufficiency_reason':'보고 규칙 확보' if enough else '보고 규칙 미확보'}
    out=us.select('승인 후 보고',record,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert len(out['candidate_acquisition']['batches'])==2
    assert len(out['candidate_acquisition']['unread_candidate_keys'])==1
    assert calls==['source-unit-triage','source-unit-review','source-unit-triage-2','source-unit-review-2']
    assert {p['block_id'] for e in out['selected_evidence'] for p in e['spans']}=={'0','5'}


def test_same_article_matches_group_with_ancestors_but_without_other_sibling(session):
    s,_=session;queue=ur.group_hits(s.sources,[hit(s,'3'),hit(s,'4')])
    assert len(queue)==1
    r=ur.acquire_batch(s.sources,queue,{'count':0,'chars':0})[0]
    assert r['offer']['reader_target']=='blocks' and r['offer']['block_ids']==['0','1','2','3','4']
    assert {p['block_id'] for e in r['evidence'] for p in e['spans']}=={'0','1','2','3','4'}
    assert all(a['action']['args']['target'].startswith('P') for a in r['actions'])
    assert '②' not in r['text'] and not r['offer']['article_complete']
    assert {'exact:3','exact:4','subtree:1'} <= {o['id'] for o in r['offers']}


def test_next_batch_preserves_adopted_scope_and_action_identity(session,monkeypatch):
    s,_=session;record=candidates(s,monkeypatch)
    def invoke(system,data,schema,phase,timeout):
        if phase.startswith('source-unit-triage'):
            row=next(r for r in data['units'] if r['unit']=='5') if phase.endswith('-2') else data['units'][0]
            return {'issues':['예외와 보고'],'choices':[choice(row,'exact:5' if phase.endswith('-2') else 'exact:3')],'needs_search':False}
        return {'issues':[],'choices':[],'needs_search':False,'evidence_sufficient':phase.endswith('-2'),
                'sufficiency_reason':'예외와 보고를 확보함' if phase.endswith('-2') else '보고 규칙을 추가 확인해야 함'}
    out=us.select('긴급 승인 예외와 보고',record,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert {p['block_id'] for e in out['selected_evidence'] for p in e['spans']}=={'0','1','2','3','5'}
    ids=[r[0] for r in s.work.db.execute('SELECT action_id FROM action_context')]
    assert len(ids)==len(set(ids))
    assert any(d['phase']=='source-unit-triage-2' for d in out['decisions'])


def test_sufficient_flag_does_not_skip_unresolved_required_connection(session,monkeypatch):
    s,_=session;record=candidates(s,monkeypatch)
    def navigation(*args,**kwargs):
        return {'batches':[],'actions':[],'seen_target_ids':[],'limits':[],'unresolved':[],
                'pending':True,'scanned_anchors':[record['unit_reads'][0]['source_id']]}
    monkeypatch.setattr(rel,'navigate',navigation)
    def invoke(system,data,schema,phase,timeout):
        return {'issues':[],'choices':[choice(data['units'][0],'exact:3')] if phase.endswith('triage') else [],
            'needs_search':False,'evidence_sufficient':True,'sufficiency_reason':'원문 충분'}
    out=us.select('긴급 승인',record,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert out['candidate_acquisition']['stop_reason']=='REFERENCE_NAVIGATION_INCOMPLETE'
    assert out['status']=='pending' and not out['evidence_sufficient']
    assert len(out['candidate_acquisition']['unread_candidate_keys'])==2


def test_two_batches_bind_actual_model_views_and_persist_selected_evidence(session,monkeypatch):
    import json
    from test_unified_legal_agent import ScriptedTransport
    from test_legal_agent_double_harness import wire
    s,_=session;record=candidates(s,monkeypatch)
    class Transport(ScriptedTransport):
        def send_once(self,*,body,ticket):
            data=json.loads(body['messages'][1]['content'])['view'];phase=data['source_stage']
            if phase.startswith('source-unit-triage'):
                value={'issues':['보고'],'choices':[] if phase.endswith('triage') else [choice(next(r for r in data['units'] if r['unit']=='5'),'exact:5')],'needs_search':False}
            else:
                value={'issues':[],'choices':[],'needs_search':False,'evidence_sufficient':phase.endswith('-2'),
                    'sufficiency_reason':'보고 규칙 확보' if phase.endswith('-2') else '추가 후보 필요'}
            return wire(value)
    from types import SimpleNamespace
    s.gateway=SimpleNamespace(domain={},transport=Transport())
    out=us.select('승인 후 보고',record,s.structured,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert 'source-unit-triage-2' in s.selection_views
    s.persist_bounded_selection(out,record)
    rows=s.work.heads('source_selection',current=True)
    assert rows and all(r['payload']['status']=='SELECTED' for r in rows)


def test_conditional_schema_requires_reason_and_repeated_bad_model_is_not_internal_error(connected):
    s,_=connected;record,sid=initial(s);selected={'U1':record['unit_reads'][0]}
    def invoke(system,data,schema,phase,timeout):
        assert {'applicability','applicability_reason'} <= set(schema['properties']['decisions']['items']['required'])
        return {'needs_more':False,'decisions':[{'id':g['id'],'action':'SKIP','scopes':[],'reason':'정방향이 아님'} for g in data['groups']]}
    # This fixture has ordinary links. Force only their obligation to exercise
    # the photographed invalid conditional skip on the actual closed menu.
    original=rel.catalog
    def catalog(*args):
        groups,statuses,limits,unresolved=original(*args)
        for g in groups:
            for c in g['connections']:c['reading_policy']['obligation']='CHECK_APPLICABILITY'
        return groups,statuses,limits,unresolved
    from unittest.mock import patch
    with patch.object(rel,'catalog',catalog):
        with pytest.raises(ProposalError,match='연결'):
            rel.navigate('승인',s,selected,invoke,read_state={'count':len(record['actions']),'chars':record['source_chars']},seconds_left=lambda:120,max_context_chars=80000)
