"""Prospective contract checks for hierarchical originals; no legal quality claim."""
from copy import deepcopy
from types import SimpleNamespace as NS
import sqlite3

import pytest
from semantic_runtime.navigation_match import SurfaceIndex, norm
from semantic_runtime.legal_agent import structure_query as sq, request_repair as rr
from semantic_runtime.legal_agent import tool_availability as availability, unit_reading as ur
from semantic_runtime.legal_agent import evidence_inventory as evidence, law_candidates as lc
from semantic_runtime.legal_agent.errors import ContractError, BudgetExhausted
from semantic_runtime.legal_agent.repository import text_hash


def nested_session(*, embedded=False):
    """Actual ancestor membership semantics; four disjoint canonical groups."""
    did='policy' if embedded else 'attachment'
    title='[별표 7의3] 운영 산정기준'
    names=SurfaceIndex();names.add('표준약정','policy')
    names.add(title,did)
    if not embedded:names.add('표준약정',did)  # Shared folder label is not an explicit file choice.
    m=NS(documents={'policy':'표준약정',did:'표준약정' if embedded else title},
         document_names=names,title_keys={norm('표준약정'),norm(title)},structures=SurfaceIndex(),
         document_context={'policy':{'document_title':'표준약정','document_role':'body'}},
         document_aliases={},units={},stored_coordinates={},sources={},
         unit_fulltext=NS(manifest={'index_sha256':'fixed'}),unit_fulltext_db=NS())
    if not embedded:m.document_context[did]={'document_title':title,'document_role':'annex','folder_names':['표준약정']}
    layouts={'a':(None,[0,6],[0,5]),'b':('a',[1,4],[1,3]),'c':('b',[2,3],[2]),'d':('a',[4,5],[4])}
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT)')
    sources={}
    for uid,(parent,span,owned) in layouts.items():
        surface='별표 7의3' if embedded and uid=='a' else uid+'.'
        m.units[(did,uid)]={'surface':surface,'title':'원문 '+uid,'parent':parent,'span':span,
                            'coordinate_scope':'annex','coordinate_binding':{'mode':'stored'}}
        sid='source:'+uid
        rows=[{'block_id':str(b),'text':'원문 구간 '+str(b)} for b in owned]
        m.sources[sid]={'document_id':did,'unit_id':uid}
        sources[sid]={'id':sid,'document_id':did,'unit_id':uid,'document_name':m.documents[did],
                      'heading':surface,'source_artifact_sha256':'same-immutable-artifact','blocks':rows,
                      'text_sha256':text_hash('\n'.join(b['text'] for b in rows))}
        db.executemany('INSERT INTO source_block VALUES (?,?,?,?,?)',[(did,b['block_id'],uid,b['text'],'same-immutable-artifact') for b in rows])
    def members(document,uid):
        found=[]
        for sid,src in m.sources.items():
            current=src['unit_id'];seen=set()
            while src['document_id']==document and current is not None and current not in seen:
                if current==uid:found.append(sid);break
                seen.add(current);current=m.units.get((document,current),{}).get('parent')
        return sorted(found)
    m._unit_sources=members
    def source(document,bid):
        row=db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(document,str(bid))).fetchone()
        if row is None:raise KeyError((document,bid))
        return dict(row)
    store=NS(db=db,source=source,sources=lambda document,bids:[source(document,b) for b in bids])
    s=NS(matcher=m,tools=NS(sources=sources),store=store,scope=set(m.documents),
         context=NS(request={'question':'표준약정 별표7의3'},query={'generation_id':'fixed'},remaining=lambda:100,binding_hash='fixed'),
         profile={'max_read_chars':1000,'page_size':1})
    return s,did


@pytest.mark.parametrize('embedded',[False,True])
def test_one_coordinate_returns_all_nested_groups_and_exact_gap_union(embedded):
    s,did=nested_session(embedded=embedded)
    route=sq.resolve(s.context.request['question'],s.matcher,s.scope)
    assert route['status']=='MATCH' and set(route['source_ids'])==set(s.tools.sources)
    assert len(route['pairs'])==4 and all(p['source_partition']['scope_unit_id']==('a' if embedded else None) for p in route['pairs'])
    wanted=set();count=0;offset=0
    while True:
        page=sq.catalogue(s.matcher,s.scope,queries=[s.context.request['question']],offset=offset,limit=2)
        for row in page['items']:
            (hit,offer),reason=availability.article_plan(s,sq.read_identity(row))
            assert reason is None and offer['coordinate_complete'] is False
            assert lc.parent_offer(s,hit)==offer
            wanted.update(offer['block_ids']);count+=1
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert count==4 and wanted==set(map(str,range(6)))
    gap=rr.bind_gap({'issue_id':'issue','gap_id':'gap','kind':'MISSING_SOURCE','missing_target':s.context.request['question']},s)
    assert gap['target_binding']['status']=='EXACT'
    assert {p['block_id'] for p in gap['target_binding']['expected']}==wanted
    inv=NS(s=s,p={'assessment_gaps':[gap],'laws':{}},current_gap_round=lambda:{})
    inv.add_laws=lambda rows:inv.p['laws'].update({lc.token(s,'L',r['document_id']):r for r in rows})
    actions={};offered=rr.add_target_actions(inv,actions)
    assert len(offered[0]['read_actions'])==4
    assert {actions[i]['identity']['source_id'] for i in offered[0]['read_actions']}==set(s.tools.sources)


@pytest.mark.parametrize('fault',['missing_partition','source_hash','original_hash','overlap','escaped_block'])
def test_partition_read_rejects_incomplete_or_changed_union(fault):
    s,did=nested_session();route=sq.resolve(s.context.request['question'],s.matcher,s.scope)
    source=s.tools.sources['source:c']
    if fault=='missing_partition':del s.tools.sources['source:c']
    elif fault=='source_hash':source['text_sha256']='wrong'
    elif fault=='original_hash':s.store.db.execute("UPDATE source_block SET source_artifact_sha256='other' WHERE block_id='2'")
    elif fault=='overlap':source['blocks']=[deepcopy(s.tools.sources['source:b']['blocks'][0])]
    else:source['blocks'].append({'block_id':'100','text':'outside'})
    with pytest.raises(ContractError):availability.article_plan(s,sq.read_identity(route['pairs'][0]))


@pytest.mark.parametrize('fault',['duplicate_coordinate','duplicate_source','denied','another_file'])
def test_nested_union_does_not_hide_coordinate_version_or_scope_conflict(fault):
    s,did=nested_session(embedded=True)
    if fault=='duplicate_coordinate':s.matcher.units[(did,'other')]=deepcopy(s.matcher.units[(did,'a')])
    elif fault=='duplicate_source':s.matcher.sources['duplicate']=deepcopy(s.matcher.sources['source:a'])
    elif fault=='denied':s.scope=set()
    else:
        title='[별표 7의3] 별도 개정 원문'
        s.matcher.documents['other']=title
        s.matcher.document_context['other']={'document_role':'annex','document_title':title}
        s.matcher.document_names.add(title,'other');s.matcher.title_keys.add(norm(title))
        s.context.request['question']='표준약정 '+title;s.scope.add('other')
    result=sq.resolve(s.context.request['question'],s.matcher,s.scope)
    assert result['status']=='MISS' and not result['source_ids']


def test_generic_amendment_container_does_not_choose_a_dated_branch():
    s,did=nested_session(embedded=True)
    for uid,title,parent in [('a','부칙',None),('b','부칙 <2021.4.2>','a'),('d','부칙 <2024.9.7>','a')]:
        s.matcher.units[(did,uid)].update(surface='부칙',title=title,parent=parent)
    result=sq.resolve('표준약정 부칙',s.matcher,s.scope)
    assert result['failure']['code']=='AMBIGUOUS_COORDINATE'
    selected=sq.resolve('표준약정 부칙 <2021.4.2>',s.matcher,s.scope)
    assert selected['status']=='MATCH' and set(selected['source_ids'])=={'source:b','source:c'}
    assert all(p['source_partition']['scope_unit_id']=='b' for p in selected['pairs'])


@pytest.mark.parametrize('source_only_count',[1,2])
def test_source_only_prefix_survives_first_structure_entry_and_complete_union(source_only_count):
    s,did=nested_session()
    for i in range(source_only_count):
        text='구조 밖 원문 '+str(i);bid=str(6+i);sid='prefix:'+str(i)
        s.store.db.execute('INSERT INTO source_block VALUES (?,?,?,?,?)',(did,bid,None,text,'same-immutable-artifact'))
        s.matcher.sources[sid]={'document_id':did,'unit_id':None,'heading':'구조 밖 원문'}
        s.tools.sources[sid]={'id':sid,'document_id':did,'unit_id':None,'document_name':s.matcher.documents[did],
            'heading':'구조 밖 원문','source_artifact_sha256':'same-immutable-artifact',
            'blocks':[{'block_id':bid,'text':text}],'text_sha256':text_hash(text)}
    s.repo=NS(event=lambda *args:None)
    selected,record=lc.structured_discovery(s,[s.context.request['question']],[])
    assert set(selected)==set(s.tools.sources) and len(record['unit_hits'])==4+source_only_count
    offers=[ur.offers(s,h)[0] for h in record['unit_hits']]
    assert {b for offer in offers for b in offer['block_ids']}==set(map(str,range(6+source_only_count)))
    prefix=next(h for h in record['unit_hits'] if h['source_id']=='prefix:0')
    assert prefix['unit_id']=='None' and ur.offers(s,prefix)[0]['unit_id'] is None
    page=sq.catalogue(s.matcher,s.scope,queries=[s.context.request['question']],limit=8)
    row=next(r for r in page['items'] if r['source_id']=='prefix:0')
    assert row['unit_id'] is None and row['path']==[]
    gap=rr.bind_gap({'issue_id':'issue','gap_id':'gap','kind':'MISSING_SOURCE','missing_target':s.context.request['question']},s)
    assert {b['block_id'] for b in gap['target_binding']['expected']}==set(map(str,range(6+source_only_count)))


def install_reader(s,*,limit=20,fail_attempt=None):
    events=[];saved={};budget={'tool_used':0,'tool_limit':limit};attempts=[]
    def verify(item):
        src=s.tools.sources[item['source_id']]
        assert src['document_id'] in s.scope
        for span in item['spans']:
            raw=s.store.source(src['document_id'],span['block_id'])
            assert raw['text'][span['start_cp']:span['end_cp']]==span['text']
            assert raw['source_artifact_sha256']==src['source_artifact_sha256']
    s.source=NS(verify=verify)
    s.repo=NS(db=sqlite3.connect(':memory:'),budget=lambda:dict(budget),
             evidence=lambda ident=None:saved[ident] if ident is not None else list(saved.values()),
             event=lambda kind,value:events.append((kind,deepcopy(value))))
    s.handle=lambda kind,value:value
    def execute(action,action_id,actor):
        assert actor=='SYSTEM_POLICY'
        if budget['tool_used']>=budget['tool_limit']:raise BudgetExhausted('unchanged request tool budget')
        budget['tool_used']+=1;attempts.append(action_id)
        if budget['tool_used']==fail_attempt:raise OSError('interrupted original page')
        target=action['args']['target'];index=action['args']['cursor'] or 0
        part=target['read_segments'][index];raw=s.store.source(target['document_id'],part['block_id'])
        span={**part,'text':raw['text'][part['start_cp']:part['end_cp']]}
        ident='E'+str(budget['tool_used'])
        saved[ident]={'evidence_id':ident,'source_id':target['source_id'],'spans':[span]}
        verify(saved[ident]);next_cursor=index+1 if index+1<len(target['read_segments']) else None
        return {'status':'OK','items':[{'evidence':ident}],'evidence_ids':[ident],
                'budget':{'new_read_chars':len(span['text'])},'coverage':{'complete':next_cursor is None},'next_cursor':next_cursor}
    s.execute=execute
    return saved,budget,attempts,events


@pytest.mark.parametrize('fault',['budget','interruption'])
def test_partial_partition_read_retains_receipts_and_never_completes_union(fault):
    s,did=nested_session();route=sq.resolve(s.context.request['question'],s.matcher,s.scope)
    (hit,offer),reason=availability.article_plan(s,sq.read_identity(next(p for p in route['pairs'] if p['source_id']=='source:a')))
    saved,budget,attempts,events=install_reader(s,limit=1 if fault=='budget' else 20,fail_attempt=2 if fault=='interruption' else None)
    state=ur.read_state(s)
    with pytest.raises(BudgetExhausted if fault=='budget' else OSError) as failure:
        ur.read(s,hit,offer,action_state=state)
    assert saved and failure.value.read_progress['completed_receipt_refs']
    assert state['count']==budget['tool_used'] and not any(k=='UNIT_READ_FINISHED' for k,_ in events)
    all_expected=evidence.expected(s,did,list(map(str,range(6))))
    assert not evidence.covers(all_expected,[p for e in saved.values() for p in e['spans']])
    if fault=='interruption':
        before=budget['tool_used'];result=ur.read(s,hit,offer,action_state=state)
        assert result['complete'] and budget['tool_used']==before+1
        assert len({p['block_id'] for e in saved.values() for p in e['spans']})==2
        assert not evidence.covers(all_expected,[p for e in saved.values() for p in e['spans']])
        assert len(attempts)==len(set(attempts))==state['count']
