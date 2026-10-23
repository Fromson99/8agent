from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import connection_scope as cs, definition_context as dc
from semantic_runtime.legal_agent import tool_availability as av, unit_reading as ur, query_scope as qs
from semantic_runtime.legal_agent.errors import ContractError, BudgetExhausted
from test_definition_context_recovery import context_probe
from test_batch_reference_navigation import connected
from conftest import term_glossary


def test_parent_own_text_and_links_exclude_siblings(monkeypatch):
    from test_selected_connection_scope import fixture
    inv, add = fixture(monkeypatch)
    inv.policy['small_connection_context'] = True
    monkeypatch.setattr(cs.inventory,'check_presented_page',lambda *a:None)
    owners = {str(i):str(i) for i in range(11)}
    texts = {str(i):'본문'+str(i) for i in range(11)}
    inv.s.store.source = lambda d,b: {'unit_id':owners[str(b)], 'text':texts[str(b)]}
    # Exact means owned text only. Parent subtrees would contaminate 8/9.
    monkeypatch.setattr(ur,'blocks',lambda s,d,u,e: [u] if e=='exact' else
        [str(i) for i in range(*s.matcher.units[d,u]['span'])])
    inv.s.tools.sources['s']={'document_id':'d','blocks':[{'block_id':str(i)} for i in range(4,10)]}
    def span(i): return {'block_id':str(i),'start_cp':0,'end_cp':len(texts[str(i)]),'text':texts[str(i)]}
    scope=cs._scope('목',{'unit_id':'7'},[{'source_id':'s','document_id':'d','spans':[span(7)]}])
    pages=[{'source_id':'s','spans':[span(i) for i in range(4,10)]}]
    actual=cs.with_parent_bodies(inv,scope,pages)
    member=actual['members'][0]
    assert {p['block_id'] for p in member['spans']}=={'4','5','6','7'}
    assert member['parent_body_block_ids']==['4','5','6']
    assert not member['missing_parent_body_block_ids']
    assert actual['structural_selection']==scope['structural_selection']
    assert actual['id']==digest({k:v for k,v in actual.items() if k!='id'})
    assert len(scope['members'][0]['spans'])==1
    missing=cs.with_parent_bodies(inv,scope,[{'source_id':'s','spans':[span(7)]}])
    assert missing['members'][0]['missing_parent_body_block_ids']==['4','5','6']
    inv.s.matcher.units['d','5']['parent']='6'
    with pytest.raises(ContractError,match='cycle'):cs.with_parent_bodies(inv,scope,pages)


def test_real_catalog_follows_parent_body_of_selected_item_only(connected):
    s,_=connected
    s.profile.setdefault('candidate_navigation',{})['investigation_control']=True
    src=next(v for v in s.tools.sources.values() if v['document_id']=='detail')
    hit=dc.rel.hit_for(s,src['id'],'2')
    offer=next(o for o in ur.offers(s,hit) if o['id']=='subtree:2')
    state={};material=ur.read(s,hit,offer,action_state=state)
    records={'B':material};ur.ensure_context(s,records,state)
    spans=[p for r in records.values() for e in r['evidence'] for p in e['spans']]
    page={'id':'E1','branch_id':'B','source_id':src['id'],'document_id':'detail',
          'scope_id':digest(offer),'spans':spans}
    inv=S(s=s,p={'selected':{'B':material}})
    own=cs._spans(spans,{'2'})
    scope=cs._scope('제2조제1항제1호',{'unit_id':'2'},[{
        'source_id':src['id'],'document_id':'detail','spans':own}])
    scope=cs.with_parent_bodies(inv,scope,[page])
    assert {p['block_id'] for p in scope['members'][0]['spans']}=={'0','1','2'}
    assert not scope['members'][0]['missing_parent_body_block_ids']
    with cs.bound(s,scope):
        groups,_,limits,_=dc.rel.catalog(s,[src['id']],records,set())
    assert not limits
    outgoing=[g for g in groups if g['direction']=='OUTGOING']
    assert outgoing and all(g['target']['document_id']=='d' for g in outgoing)
    assert all(c['witness_block_id']=='1' for g in outgoing for c in g['connections'])
    assert all('3' not in m['parent_body_block_ids'] for m in scope['members'])


@pytest.mark.parametrize('error',[ContractError('hash mismatch'),PermissionError('ACL denied')])
def test_automatic_integrity_and_authorization_fail_closed(context_probe,monkeypatch,error):
    inv,directory,scope,_=probe(context_probe,monkeypatch)
    monkeypatch.setattr(av,'article_plan',lambda *a:(_ for _ in ()).throw(error))
    with pytest.raises(type(error),match=str(error)):cs.acquire_small_directory(inv,scope,directory)
    assert not inv.p.get('tool_failures') and 'B' not in inv.p['selected']


def test_two_equivalent_references_read_one_extent(context_probe,monkeypatch):
    inv,directory,scope,f=probe(context_probe,monkeypatch)
    copy=deepcopy(directory['groups'][0]);copy['connections'][0]['reference_id']='second witness'
    directory['groups'].append(copy)
    assert cs.acquire_small_directory(inv,scope,directory)==['B'] and f.calls==[1]
    assert next(iter(inv.p['small_connection_directories'].values()))['endpoint_count']==1


def probe(context_probe, monkeypatch):
    # Use the real registration/context/failure machinery with bounded doubles.
    inv = context_probe.inv
    inv.policy['small_connection_context']=True
    groups, *_ = dc.rel.catalog(inv.s, [], {}, set())
    directory={'status':'COMPLETE','groups':groups,'limits':[],'unresolved':[]}
    scope={'id':'chosen','members':[{'source_id':'a','document_id':'a','spans':[]}]}
    monkeypatch.setattr(qs,'action_allowed',lambda *a:True)
    return inv,directory,scope,context_probe


@pytest.mark.parametrize('mode',['three','partial','chars','budget','missing_parent'])
def test_menu_boundaries_preserve_original_without_read(context_probe,monkeypatch,mode):
    inv,directory,scope,rest=probe(context_probe,monkeypatch)
    if mode=='three':
        g=directory['groups'][0]
        for n in ('3','4'):
            h=deepcopy(g);hit,offer=h['offers']['scope'];hit['unit_id']=offer['unit_id']=n;offer['block_ids']=[n]
            directory['groups'].append(h)
    if mode=='partial':directory['status']='PARTIAL'
    if mode=='chars':monkeypatch.setattr(av,'sequence_cost',lambda *a:(12001,1))
    if mode=='budget':monkeypatch.setattr(av,'budget_reason',lambda *a:'TOOL_ACTION_LIMIT')
    if mode=='missing_parent':scope['members'][0]['missing_parent_body_block_ids']=['0']
    before=deepcopy(inv.p['selected'])
    assert cs.acquire_small_directory(inv,scope,directory)==[]
    assert inv.p['selected']==before
    row=next(iter(inv.p['small_connection_directories'].values()))
    assert row['status']=='MENU_ONLY' and row['reason'] and not row['model_called']


def test_resolved_original_is_delivered_while_unknown_reference_stays_unresolved(context_probe,monkeypatch):
    inv,directory,scope,f=probe(context_probe,monkeypatch)
    directory['unresolved']=[{'reference_id':'unknown','reason':'target unavailable'}]
    assert cs.acquire_small_directory(inv,scope,directory)==['B']
    row=next(iter(inv.p['small_connection_directories'].values()))
    assert row['status']=='PARTIAL' and row['unresolved_count']==1
    assert f.body['text'] in inv.render_page(f.group,0)['text']
    assert cs.acquire_small_directory(inv,scope,directory)==['B'] and f.calls==[1]


@pytest.mark.parametrize('failure',['body','context','budget','integrity'])
def test_failure_partial_resume_and_no_retry(context_probe,monkeypatch,failure):
    inv,directory,scope,rest=probe(context_probe,monkeypatch)
    error=ContractError('hash mismatch') if failure=='integrity' else BudgetExhausted('test budget') if failure=='budget' else TimeoutError('test read')
    def fail(*a,**kw):raise error
    monkeypatch.setattr(ur,'ensure_context' if failure=='context' else 'read',fail)
    before=deepcopy(inv.p['selected']['A'])
    if failure=='integrity':
        with pytest.raises(ContractError):cs.acquire_small_directory(inv,scope,directory)
        return
    try:added=cs.acquire_small_directory(inv,scope,directory)
    except BudgetExhausted:added=[]
    assert inv.p['selected']['A']==before
    target=next(iter(inv.p['small_connection_attempts'].values()))
    assert target['status']==('PARTIAL' if failure=='context' else 'FAILED')
    assert inv.p['tool_failures'][-1]['origin']=='SMALL_CONNECTION_CONTEXT'
    inv.p=deepcopy(inv.p)
    # A second attempt with the same or another anchor does not redo failed I/O.
    monkeypatch.setattr(ur,'read',lambda *a,**kw:pytest.fail('repeated target read'))
    cs.acquire_small_directory(inv,scope,directory)
    scope=deepcopy(scope);scope['members'][0]['spans']=[{'block_id':'other'}]
    cs.acquire_small_directory(inv,scope,directory)
    current=next(iter(inv.p['small_connection_directories'].values()))
    current['status']='tampered'
    with pytest.raises(ContractError,match='hash'):cs.acquire_small_directory(inv,{'id':'chosen','members':[{'source_id':'a','document_id':'a','spans':[]}]},directory)

