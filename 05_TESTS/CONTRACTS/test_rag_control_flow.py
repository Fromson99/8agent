"""Structural investigation regressions; synthetic originals, no model service."""
import copy
import json
from types import SimpleNamespace

import pytest
from test_unit_fulltext_adaptive_read import session, tree, hit, record, ur, us
from test_batch_reference_navigation import connected, initial, decision, rel
from test_progressive_grouped_reading import candidates


def unit_choice(data, scope):
    return {'issues': [], 'choices': [{'id': data['units'][0]['id'], 'scope': scope,
        'reason': '모의 원문 확인'}], 'needs_search': False}


def test_group_order_keeps_first_hit_of_each_source(connected, monkeypatch):
    s, _ = connected
    monkeypatch.setitem(ur.POLICY, 'group_units', 1)
    docs={v['document_id']:v['id'] for v in s.tools.sources.values()}
    hits=[rel.hit_for(s,docs['d'],'2'),rel.hit_for(s,docs['detail'],'2'),rel.hit_for(s,docs['d'],'3')]
    assert [h['key'] for h in ur.group_hits(s,hits)]==[h['key'] for h in hits]


def test_expansion_reads_only_uncovered_blocks_and_budget(session):
    s,_=session;h=hit(s);state={'count':0,'chars':0}
    offers={o['id']:o for o in ur.offers(s.sources,h)}
    first=ur.read(s.sources,h,offers['exact:3'],action_state=state)
    expanded=ur.read(s.sources,h,offers['subtree:1'],action_state=state)
    assert len(first['actions'])==1 and len(expanded['actions'])==3
    assert {p['block_id'] for a in expanded['actions'] for eid in a['result']['evidence_ids']
        for p in s.work.evidence(eid)['spans']}=={'1','2','4'}
    assert state['chars']==offers['subtree:1']['chars']
    assert expanded['complete'] and '긴급' in expanded['text'] and '일반' in expanded['text']


def test_a_narrower_read_projects_existing_evidence_without_reading(session):
    s,_=session;h=hit(s);state={'count':0,'chars':0};offers={o['id']:o for o in ur.offers(s.sources,h)}
    ur.read(s.sources,h,offers['subtree:1'],action_state=state)
    before=state['chars'];r=ur.read(s.sources,h,offers['exact:3'],action_state=state)
    assert r['complete'] and r['actions']==[] and state['chars']==before
    assert {p['block_id'] for e in r['evidence'] for p in e['spans']}=={'3'}


def test_partial_block_resumes_from_the_missing_character(session):
    s,_=session;h=hit(s);offer=ur.offers(s.sources,h)[0]
    target=s.sources.handle('P',{'document_id':'d','unit_id':None,'source_id':h['source_id'],
        'block_ids':['3'],'read_segments':[{'block_id':'3','start_cp':0,'end_cp':5}]})
    s.sources.execute({'tool':'read','args':{'target':target,'extent':'exact','cursor':None},
        'reason':'중단된 읽기 모의','question_refs':[],'expected_information':'앞부분'},'seed',actor='SYSTEM_POLICY')
    r=ur.read(s.sources,h,offer,action_state={'count':0,'chars':5})
    assert r['complete'] and r['text']=='가. 긴급 승인 예외는 허용한다.'
    fresh=[p for a in r['actions'] for eid in a['result']['evidence_ids'] for p in s.work.evidence(eid)['spans']]
    assert fresh[0]['start_cp']==5 and sum(p['end_cp']-p['start_cp'] for p in fresh)==offer['chars']-5


def test_reentry_preserves_action_identity_and_read_budget(session):
    s,_=session;h=hit(s)
    first=ur.read(s.sources,h,ur.offers(s.sources,h)[0],action_state={'count':0,'chars':0})
    other=hit(s,'5');state={'count':0,'chars':0}
    second=ur.read(s.sources,other,ur.offers(s.sources,other)[0],action_state=state)
    assert first['actions'][0]['result']['action_id']!=second['actions'][0]['result']['action_id']
    assert state['count']==2 and state['chars']==first['offer']['chars']+second['offer']['chars']


def test_unread_candidates_do_not_materialize_ancestor_offers(session,monkeypatch):
    s,_=session;calls=[];original=ur.offer_plan
    def plans(sess,h):calls.append(h['unit_id']);return original(sess,h)
    monkeypatch.setattr(ur,'offer_plan',plans)
    rec=candidates(s,monkeypatch)
    assert len(rec['pending_unit_hits'])==2 and '5' not in calls and '4' not in calls


def test_review_expansion_is_presented_before_sufficiency(session):
    s,_=session;rec=record(s);reviews=[]
    def invoke(system,data,schema,phase,timeout):
        if phase.endswith('triage'):return unit_choice(data,'exact:3')
        reviews.append(data['sources'][0]['text'])
        if len(reviews)==1:
            value=unit_choice(data,'subtree:1')
            return {**value,'evidence_sufficient':False,'sufficiency_reason':'일반 승인도 확인해야 함'}
        return {'issues':[],'choices':[],'needs_search':False,
            'evidence_sufficient':True,'sufficiency_reason':'원칙과 제한을 모두 확보함'}
    out=us.select('승인 비교',rec,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert len(reviews)==2 and '일반 승인' not in reviews[0] and '일반 승인' in reviews[1]
    assert out['status']=='complete' and not out['needs_fulltext']


def test_first_sufficient_visible_group_stops_before_more_model_calls(session):
    from semantic_runtime.legal_agent.source_recall import SourceRecall
    s,_=session;hits=[hit(s,'3'),hit(s,'4')];recall=SourceRecall(s.sources)
    recall.discover=lambda:([hits[0]['source_id']],{'discovery_mode':'fulltext','routes':{},'unit_hits':hits})
    rec=recall.prepare();phases=[]
    def invoke(system,data,schema,phase,timeout):
        phases.append(phase);assert phase=='source-unit-triage'
        return {**unit_choice(data,data['units'][0]['read_options'][0][0]),
            'evidence_sufficient':True,'sufficiency_reason':'필요한 조건과 예외의 실제 원문이 모두 제시됨'}
    out=us.select('긴급과 일반 승인 예외',rec,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert out['status']=='complete' and phases==['source-unit-triage']


def test_resolved_navigation_replaces_historical_pending(session,monkeypatch):
    s,_=session;rec=record(s);pending=[]
    def navigation(question,sess,selected,invoke,**kw):
        value=not pending;pending.append(value)
        return {'batches':[],'actions':[],'seen_target_ids':[],'limits':[],'unresolved':[],
            'scanned_anchors':list({r['source_id'] for r in selected.values()}),'pending':value}
    monkeypatch.setattr(rel,'navigate',navigation);reviews=0
    def invoke(system,data,schema,phase,timeout):
        nonlocal reviews
        if phase.endswith('triage'):return unit_choice(data,'exact:3')
        reviews+=1
        return {**(unit_choice(data,'subtree:1') if reviews==1 else {'issues':[],'choices':[],'needs_search':False}),
                'evidence_sufficient':True,'sufficiency_reason':'원문 및 연결 확인 완료'}
    out=us.select('승인',rec,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000)
    assert pending==[True,False] and out['status']=='complete' and not out['reference_navigation']['pending']


def test_omitted_connection_menus_continue_without_search(connected,monkeypatch):
    s,_=connected;rec,sid=initial(s);selected={'U1':rec['unit_reads'][0]}
    template=rel.catalog(s,[sid],selected,set())[0][0];groups=[]
    for n in range(20):
        g=copy.deepcopy(template);g['key']='group-'+str(n)
        for c in g['connections']:
            c['reference_id']='reference-'+str(n);c['reading_policy']['obligation']='CHECK_APPLICABILITY'
        groups.append(g)
    monkeypatch.setattr(rel,'catalog',lambda *args,**kw:(copy.deepcopy(groups),[],[],[]))
    menus=[]
    def invoke(system,data,schema,phase,timeout):
        menus.append(data);return decision(data)
    out=rel.navigate('승인',s,selected,invoke,read_state=dict(rec['read_state']),seconds_left=lambda:120,max_context_chars=80000)
    refs=[c['reference_id'] for data in menus for g in data['groups'] for c in g['connections']]
    assert len(menus)>1 and len(refs)==20 and len(set(refs))==20 and not out['pending']


@pytest.mark.parametrize('connected',['① 「모의승인규정」 제1조제1항을 준용하며 예외는 다음 각 호와 같다.'],indirect=True)
def test_expanded_already_scanned_source_exposes_and_reads_required_link(connected):
    s,_=connected;rec,sid=initial(s);state=dict(rec['read_state'])
    detail=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    h=rel.hit_for(s,detail['id'],'2');r=ur.read(s,h,ur.offers(s,h)[0],action_state=state)
    selected={'U1':rec['unit_reads'][0],'U2':r};targets=[]
    def invoke(system,data,schema,phase,timeout):
        value=decision(data)
        for g in data['groups']:
            targets.append(g['target']['document_id'])
            d=next(d for d in value['decisions'] if d['id']==g['id'])
            if g['target']['document_id']=='detail' or any(c['reading_policy']['obligation']=='REQUIRED' and not c['already_read'] for c in g['connections']):
                options={o[0] for o in g['read_options']}
                d.update(action='FOLLOW',scopes=['subtree:1' if 'subtree:1' in options else 'subtree:0'],applicability='APPLIES')
        return value
    out=rel.navigate('승인 예외',s,selected,invoke,read_state=state,seconds_left=lambda:120,max_context_chars=80000)
    assert targets==['detail','d'] and not out['pending']
    assert '일반 승인' in ur.original_map(selected.values())[sid]['text']


def test_exact_decisions_survive_the_next_navigation(connected):
    s,_=connected;rec,sid=initial(s);state={};menus=[];selected={'U1':rec['unit_reads'][0]}
    def invoke(system,data,schema,phase,timeout):menus.append(data);return decision(data)
    for _ in range(2):
        out=rel.navigate('승인',s,selected,invoke,read_state=dict(rec['read_state']),seconds_left=lambda:120,
            max_context_chars=80000,state=state)
        assert not out['pending']
    assert len(menus)==1


def test_reference_edge_cursor_reaches_the_next_page(connected,monkeypatch):
    import sqlite3
    s,_=connected;rec,sid=initial(s);state=dict(rec['read_state'])
    db=sqlite3.connect(':memory:');s.tools.db.backup(db)
    raw=db.execute("SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=? AND json_extract(r.json,'$.source_id')!=? LIMIT 1",(sid,sid)).fetchone()[0]
    ref=json.loads(raw);original_id=ref['id'];ref['id']='zz-synthetic-next-page'
    db.execute('INSERT INTO reference VALUES(?,?,?)',(ref['id'],ref['document_id'],json.dumps(ref)))
    db.execute('INSERT INTO reference_end SELECT source_id,? FROM reference_end WHERE reference_id=?',(ref['id'],original_id));db.commit()
    monkeypatch.setattr(s.tools,'db',db)
    h=rel.hit_for(s,sid,'0');r=ur.read(s,h,next(o for o in ur.offers(s,h) if o['id']=='subtree:0'),action_state=state)
    selected={'U1':r};monkeypatch.setitem(rel.LIMITS,'edges_per_anchor',1);menus=[]
    def invoke(system,data,schema,phase,timeout):menus.append(data);return decision(data)
    out=rel.navigate('승인',s,selected,invoke,read_state=state,seconds_left=lambda:120,max_context_chars=80000)
    references=[c['reference_id'] for m in menus for g in m['groups'] for c in g['connections']]
    assert len(menus)>=2 and len(references)==len(set(references)) and not out['pending']
    db.close()


def test_pending_references_do_not_reenter_fulltext(monkeypatch):
    from semantic_runtime.legal_agent import memory_rag,corrected_memory
    source=SimpleNamespace(force_fulltext_recall=False)
    execution=memory_rag.NativeExecution(SimpleNamespace(verify=lambda _:None,question=lambda _:'Q'),
        SimpleNamespace(sources=source,work=SimpleNamespace(event=lambda *_:None)),{}, {})
    monkeypatch.setattr(memory_rag,'select_sources',lambda *a,**kw:{'final_ids':['s'],
        'status':'pending','needs_fulltext':False,'next_action':'CONTINUE_REFERENCES'})
    parts={'PLAN':{'payload':{'law_names':[],'queries':['Q']}},'READ':{'payload':{'record':{'discovery_mode':'fulltext'}}}}
    with pytest.raises(corrected_memory.MemoryError,match='CONTINUE_REFERENCES'):
        execution.stage('SELECT',{'facts':[]},parts,'Q','prose')
    assert not source.force_fulltext_recall


def test_accepted_reference_read_resumes_after_serialized_checkpoint(connected,monkeypatch):
    s,_=connected;rec,sid=initial(s);selected={'U1':rec['unit_reads'][0]};state={};saved=[];calls=[]
    def checkpoint(value):saved.append(json.loads(json.dumps(value)))
    def invoke(system,data,schema,phase,timeout):
        calls.append([(g['anchor']['source_id'],g['target']['source_id'],g['direction'],
            tuple(c['reference_id'] for c in g['connections'])) for g in data['groups']]);value=decision(data)
        for d,g in zip(value['decisions'],data['groups']):
            d.update(action='FOLLOW',scopes=[g['read_options'][0][0]],applicability='APPLIES')
        return value
    original=rel.read
    def interrupted(*args,**kw):raise TimeoutError('모의 원문 읽기 중단')
    monkeypatch.setattr(rel,'read',interrupted)
    with pytest.raises(TimeoutError):
        rel.navigate('승인',s,selected,invoke,read_state=dict(rec['read_state']),seconds_left=lambda:120,
            max_context_chars=80000,state=state,on_checkpoint=checkpoint)
    assert saved[-1]['accepted']
    monkeypatch.setattr(rel,'read',original)
    out=rel.navigate('승인',s,selected,invoke,read_state=dict(rec['read_state']),seconds_left=lambda:120,
        max_context_chars=80000,state=saved[-1],on_checkpoint=checkpoint)
    assert not out['pending'] and calls.count(calls[0])==1 and not out['state']['accepted']


def test_fresh_candidate_is_presented_at_a_context_boundary(session,monkeypatch):
    s,_=session;rec=candidates(s,monkeypatch);views=[]
    def invoke(system,data,schema,phase,timeout):
        if phase.startswith('source-unit-triage'):
            views.append(data['units'])
            row=next((r for r in data['units'] if r['unit']=='5'),None)
            return {'issues':[],'choices':[{'id':row['id'],'scope':'exact:5','reason':'보고 원문'}] if row else [],'needs_search':False}
        enough=bool(data['sources'])
        return {'issues':[],'choices':[],'needs_search':False,'evidence_sufficient':enough,
            'sufficiency_reason':'보고 원문 확보' if enough else '보고가 필요함'}
    out=us.select('보고',rec,invoke,session=s.sources,remaining_seconds=120,max_fulltext_chars=7000)
    assert len(views)==2 and views[0][0]['unit']=='3' and views[1][0]['unit']=='5'
    assert out['status']=='complete'
    assert [d['phase'] for d in out['decisions']]==['source-unit-triage','source-unit-review',
        'source-unit-triage-2','source-unit-review-2']


def test_model_receives_the_phase_time_budget():
    from semantic_runtime.legal_agent.memory_binding import RuntimeModel
    limits=[];model=RuntimeModel.__new__(RuntimeModel)
    model.ensure=lambda:None
    model.session=SimpleNamespace(context=SimpleNamespace(remaining=lambda:200),profile={'max_output_tokens':100},
        structured=lambda system,data,schema,phase,timeout,tokens:limits.append(timeout) or {})
    model.invoke('s',{}, {},'source-unit-review',timeout=7)
    assert limits==[7]


def test_interrupted_review_resumes_accepted_triage_and_evidence(session):
    s,_=session;rec=record(s);saved=[];phases=[]
    def checkpoint(value):saved.append(json.loads(json.dumps(value)))
    def first(system,data,schema,phase,timeout):
        phases.append(phase)
        if phase.endswith('triage'):return unit_choice(data,'exact:3')
        raise TimeoutError('모의 중단')
    with pytest.raises(TimeoutError):
        us.select('승인',rec,first,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000,on_checkpoint=checkpoint)
    previous_actions=s.work.db.execute('SELECT COUNT(*) FROM action_context').fetchone()[0]
    def resumed(system,data,schema,phase,timeout):
        phases.append(phase);assert phase=='source-unit-review' and '긴급' in data['sources'][0]['text']
        return {'issues':[],'choices':[],'needs_search':False,'evidence_sufficient':True,'sufficiency_reason':'원문 확보'}
    out=us.select('승인',rec,resumed,session=s.sources,remaining_seconds=120,max_fulltext_chars=80000,checkpoint=saved[-1])
    assert out['status']=='complete' and phases.count('source-unit-triage')==1
    assert s.work.db.execute('SELECT COUNT(*) FROM action_context').fetchone()[0]==previous_actions


def test_durable_progress_is_loaded_only_for_unchanged_goal(memory):
    from test_memory_runtime_v2 import command
    mem,fake,wire,send,principal=memory
    original=fake.stage;observed=[]
    def interrupted(stage,state,parts,*args):
        if stage=='SELECT':
            observed.append(fake.selection_progress)
            if fake.selection_progress is None:
                fake.save_selection_progress({'cursor':4,'decisions':['accepted']})
                raise TimeoutError('모의 중단')
        return original(stage,state,parts,*args)
    fake.stage=interrupted
    with pytest.raises(TimeoutError):send(command('CASE_START',task='보고',facts=[]))
    gid=mem.db.execute('SELECT id FROM goal').fetchone()[0]
    result=send(command('RESEARCH_REENTER',target=gid,stage='SELECT'))
    assert result['status']=='READY' and observed==[None,{'cursor':4,'decisions':['accepted']}]
    assert mem.db.execute('SELECT COUNT(*) FROM stage_progress').fetchone()[0]==0


from test_memory_runtime_v2 import memory
