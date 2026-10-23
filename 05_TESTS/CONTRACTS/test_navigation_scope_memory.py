"""Small deterministic state tests: past reads remain visible after returning."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import evidence_inventory as inv, request_repair as rr, tool_availability as tools
from semantic_runtime.legal_agent.errors import ContractError, ProposalError


@pytest.fixture
def memory():
    texts = {'1':'abc', '2':'def', '3':'ghi'}
    def span(b):
        return {'block_id':b, 'start_cp':0, 'end_cp':3, 'text':texts[b]}
    def record(name, blocks):
        offer={'id':name, 'unit_id':blocks[0], 'extent':'subtree', 'block_ids':blocks}
        return {'source_id':'s','document_id':'d','article_unit_id':'1', 'complete':True,
            'document_name':'모의법','heading':'제1조','offer':offer,
            'evidence':[{'evidence_id':name,'source_id':'s','document_id':'d','generation':'g',
                         'spans':[span(b) for b in blocks]}]}
    checked=[]
    def verify(e):
        if e['generation']!='g': raise ContractError('source generation changed')
        checked.append(e['evidence_id'])
    session=S(scope=['d'], context=S(query={'generation_id':'g'}),
        matcher=S(units={('d',n):{'surface':'제1조' if n=='1' else n, 'parent':None if n=='1' else '1'} for n in texts}),
        store=S(source=lambda did,b:{'text':texts[str(b)]}), source=S(verify=verify),
        tools=S(sources={'s':{'document_id':'d','blocks':[{'block_id':b} for b in texts]}}))
    wide=record('wide',['1','2','3']); narrow=record('narrow',['2'])
    group={'id':'B','status':'READ','reason':'조사','source_id':'s','page_plan':[[]],
           'hit':{'document_id':'d','document_name':'모의법','unit_id':'2','article_unit_id':'1'}}
    page={'id':'E','branch_id':'B','source_id':'s','document_id':'d','page':1,'total_pages':1,
          'scope_id':digest(wide['offer']),'spans':[span(b) for b in texts],'accepted':True}
    state={'selected':{'B':narrow},'groups':{'B':group},'contexts':{},'basis_history':{'E':page},
           'material_history':{digest(['B',wide['offer']]):wide},'requested_originals':['B']}
    return session,state,wide,page,checked


def test_historical_delivered_scope_covers_current_subrange(memory):
    session,state,wide,page,checked=memory
    row=inv.saved_projection(session,state)[0]
    assert row['availability']=='DELIVERED' and row['delivered_complete'] and row['article_delivered_complete']
    assert {tuple(r['block_ids']) for r in row['available_scopes']}=={('2',),('1','2','3')}
    assert 'text' not in str(row['available_scopes'])
    assert set(checked)=={'wide','narrow'}


def test_unaccepted_page_does_not_become_delivered(memory):
    session,state,_,page,_=memory
    page['accepted']=False
    assert not inv.inventory(session,state)[0]['receipt']['delivered_complete']
    state['delivery_history']={'attempt:E':{**page,'delivery_contract':inv.DELIVERY}}
    assert inv.inventory(session,state)[0]['receipt']['delivered_complete']


def test_same_source_other_branch_delivery_is_verified(memory):
    session,state,wide,page,_=memory
    state['selected']['B2']=wide; state['groups']['B2']={**state['groups']['B'],'id':'B2'}
    page['branch_id']='B2'
    assert inv.inventory(session,state)[0]['receipt']['article_delivered_complete']
    page['branch_id']='unknown'
    with pytest.raises(ContractError,match='binding'):inv.inventory(session,state)


@pytest.mark.parametrize('corruption',['key','source','generation','text','acl'])
def test_history_rejects_changed_bindings_and_originals(memory,corruption):
    session,state,wide,page,_=memory
    if corruption=='key':state['material_history']={'invented':wide}
    elif corruption=='source':wide['source_id']='other'
    elif corruption=='generation':wide['evidence'][0]['generation']='other'
    elif corruption=='text':page['spans'][0]['text']='bad'
    else:session.scope=[]
    with pytest.raises(ContractError):inv.inventory(session,state)


def test_undelivered_history_is_in_bounded_handoff_without_duplicate_character_cost(memory):
    session,state,_,_,_=memory;state['basis_history']={}
    originals,evidence,omitted=inv.acquired_originals_for(session,state,9)
    assert originals[0]['text']=='abc\ndef\nghi' and originals[0]['article_complete']
    assert originals[0]['delivered_context_only'] and not omitted
    assert {e['evidence_id'] for e in evidence}=={'wide','narrow'}
    assert not state['basis_history']
    assert not inv.acquired_originals_for(session,state,8)[0]


def test_partial_current_page_is_not_complete_and_reports_missing_coordinates(memory):
    session,state,wide,page,_=memory
    partial={**page,'spans':page['spans'][:1]}
    result=inv.presentation_receipt(session,state['groups']['B'],wide,[partial])
    assert result['currently_presented'] and result['presented_any'] and not result['presented_complete']
    assert result['missing_spans']==[{'block_id':b,'start_cp':0,'end_cp':3} for b in ('2','3')]
    assert all('text' not in r for r in result['presented_spans']+result['missing_spans'])


def test_history_group_filter_does_not_restore_excluded_other_group(memory):
    _,state,_,_,_=memory
    assert inv.acquired_records(state,group_ids=[])=={}
    before=deepcopy(state)
    assert len(inv.acquired_records(state,group_ids=['B']))==2
    assert state==before


def test_whole_article_read_without_unit_is_removed_only_if_fully_present(memory,monkeypatch):
    session,state,wide,page,_=memory;called=[]
    def plan(s,identity):
        called.append(identity)
        return ({'source_id':'s','document_id':'d'},wide['offer']),None
    monkeypatch.setattr(tools,'article_plan',plan)
    action={'id':'T','action':'READ_ARTICLES','label':'모의법 제1조 전체','identity':{'source_id':'s','document_id':'d'}}
    actor=S(s=session,p=state)
    data={'sources':[page]};actions={'T':deepcopy(action)}
    removed=rr.annotate_reused_reads(actor,data,actions)
    assert called==[action['identity']] and not actions
    assert removed[0]['label']==action['label'] and removed[0]['source_id']=='s'
    assert len(removed[0]['covered_spans'])==3
    partial={**page,'spans':page['spans'][:1]};actions={'T':deepcopy(action)}
    assert not rr.annotate_reused_reads(actor,{'sources':[partial]},actions) and actions


@pytest.mark.parametrize('failed_scope,expected',[
    ({'source_id':'s','document_id':'d','block_ids':['1','2','3']},True),
    ({'source_id':'s','document_id':'d','block_ids':['1']},False),
    (None,False),
])
def test_definition_failure_matches_actual_scope_not_augmented_inline_identity(memory,monkeypatch,failed_scope,expected):
    session,state,wide,_,_=memory
    monkeypatch.setattr(tools,'article_plan',lambda s,i:(({'source_id':'s','document_id':'d'},wide['offer']),None))
    failure={'origin':'DEFINITION_CONTEXT','failed_scope':failed_scope,'action':'READ_ARTICLES',
             'targets':[{'source_id':'s','document_id':'d'}],'code':'TIMEOUT','queries':[],
             'status':'UNRESOLVED','absence_proven':False,'operation_key':'old'}
    state['tool_failures']=[failure]
    identity={'source_id':'s','document_id':'d','connection_group':'new-route'}
    action={'id':'T','action':'READ_ARTICLES','identity':identity,'label':'본문'}
    actions={'T':action};data={'actions':[action]};actor=S(s=session,p=state)
    rr.recovery_menu(actor,data,actions)
    assert ('T' not in actions)==expected
    if expected:
        with pytest.raises(ProposalError):rr.validate_failed_operation(actor,{'next_action':'READ_ARTICLES','targets':['T']},{'T':action})
    assert data['tool_recovery'][0]['absence_proven'] is False


def test_unplannable_definition_target_is_not_assumed_equal(memory,monkeypatch):
    session,state,_,_,_=memory
    monkeypatch.setattr(tools,'article_plan',lambda *args:(None,'STRUCTURE_NOT_AVAILABLE'))
    failure={'origin':'DEFINITION_CONTEXT','failed_scope':{'source_id':'s','document_id':'d','block_ids':['1']}}
    assert not rr.failed_definition_scope(S(s=session,p=state),failure,{'action':'READ_ARTICLES','identity':{}})
