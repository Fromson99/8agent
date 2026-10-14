"""Independent synthetic scenarios fixed before the measured A/B run."""
import copy
import json
import pytest
from semantic_runtime.legal_agent import structure_query as sq, law_navigation as ln
from semantic_runtime.legal_agent.errors import ProposalError
from test_followup_structure_lookup import investigation, apply, hierarchy_matcher
from test_unit_fulltext_adaptive_read import tree, session
from test_genos_chat_flow import journal, workflow
from test_law_grouped_navigation import decide

FIELDS = {'coordinate': '제1조', 'title': '', 'coordinate_scope': 'body'}

def choose(actions, kind):
    return next(key for key, action in actions.items() if action['action'] == kind)

def page_only(inv, data, actions, count=3):
    # Actual original index hits, with deterministic distinct synthetic cursors.
    # Repeated paging must not be treated as new original delivery.
    original = inv.idx.article_groups_page
    page = original(inv.db, inv.p['catalogue']['terms'], 'd', set(inv.s.tools.sources), limit=8)
    pages = [0]
    def paging(*args, **kwargs):
        pages[0] += 1
        return {**copy.deepcopy(page), 'next_cursor': 'synthetic-page-'+str(pages[0])}
    inv.idx.article_groups_page = paging
    try:
        for i in range(count):
            kind = 'OPEN_LAW' if i == 0 else 'NEXT_ARTICLES'
            data, actions = apply(inv, data, actions, kind, choose(actions, kind))
    finally:
        inv.idx.article_groups_page = original
    return data, actions

def test_typed_query_history_survives_resume_result_and_return(session):
    native, _ = session
    inv = investigation(native); data, actions = inv.view()
    old = copy.deepcopy(data)
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', data['laws'][0]['structure_search_action'], structure_filter=FIELDS)
    saved = copy.deepcopy(inv.p)
    resumed = ln.Investigation(inv.s, inv.question, inv.record, inv.invoke, 120, saved, None)
    data, actions = resumed.view()
    assert resumed.p['action_chain']['steps'][-1]['structure_filter'] == FIELDS
    assert resumed.p['action_chain']['steps'][-1]['structure_lookup']['lookup_status'] == 'MATCH'
    target = next(k for k,a in actions.items() if a['action']=='RETURN_TO' and a['identity']['frame_id']==old['chain_frame_id'])
    data, actions = apply(resumed, data, actions, 'RETURN_TO', target)
    result = resumed.result(decide(data, 'PENDING'))
    assert result['structure_search_history'][0]['structure_filter'] == FIELDS
    assert any(s.get('structure_filter')==FIELDS for s in result['investigation_chain']['steps'])

def test_three_pages_retain_structure_and_forbid_fourth_even_after_return(session):
    native, _ = session
    inv = investigation(native); initial, actions = inv.view()
    archived = next(a for a in actions.values() if a['action']=='OPEN_LAW')
    data, actions = page_only(inv, initial, actions)
    assert data['structure_recovery'][0]['active']
    assert data['structure_recovery'][0]['pages_without_new_original'] == 3
    assert not any(a['action'] in ('OPEN_LAW','NEXT_ARTICLES','NEXT_HITS') for a in actions.values())
    assert data['laws'][0]['document_structure']['search_fields']==['coordinate','title','coordinate_scope']
    assert any(a['action']=='SEARCH_STRUCTURE' for a in actions.values())
    target = next(k for k,a in actions.items() if a['action']=='RETURN_TO' and a['identity']['frame_id']==initial['chain_frame_id'])
    data, actions = apply(inv, data, actions, 'RETURN_TO', target)
    assert not any(a['action'] in ('OPEN_LAW','NEXT_ARTICLES','NEXT_HITS') for a in actions.values())
    assert data['laws'][0]['open_action'] is None
    forged = decide(data, archived['action'], archived['id'])
    forged.update(expected_state_version=data['state_version'],law_decisions=[],branch_decisions=[])
    with pytest.raises(ProposalError):
        inv.validate(forged, data, {**actions,archived['id']:archived})

def test_new_original_delivery_resets_but_preview_does_not(session):
    native, _ = session
    inv = investigation(native); data, actions = inv.view()
    data, actions = page_only(inv, data, actions)
    read = choose(actions, 'READ_PARENT')
    data, actions = apply(inv, data, actions, 'READ_PARENT', read)
    assert data['sources']
    # A subsequent real decision acknowledges the delivered source page.
    data, actions = apply(inv, data, actions, 'SEARCH_STRUCTURE', data['laws'][0]['structure_search_action'], structure_filter=FIELDS)
    assert not data['structure_recovery']
    assert not inv.recovery_blocked({'action':'OPEN_LAW','identity':{'document_id':'d'}})

def test_recovery_is_document_query_specific_and_resumes(session):
    native, _ = session
    inv = investigation(native); data, actions = inv.view()
    data, actions = page_only(inv, data, actions)
    saved = copy.deepcopy(inv.p)
    resumed = ln.Investigation(inv.s,inv.question,inv.record,inv.invoke,120,saved,None)
    data, actions = resumed.view()
    assert data['structure_recovery'][0]['active']
    other = {'action':'OPEN_LAW','identity':{'document_id':'other'}}
    assert not resumed.recovery_blocked(other)
    resumed.p['catalogue']['query_fingerprint'] = 'distinct-synthetic-expression'
    data, actions = resumed.view()
    assert data['structure_recovery']==[] and any(a['action']=='OPEN_LAW' for a in actions.values())

@pytest.mark.parametrize('fields,expected', [
    ({'coordinate':'제999조','title':'','coordinate_scope':'body'},'MISSING_COORDINATE'),
    ({'coordinate':'invalid','title':'','coordinate_scope':'body'},'INVALID_COORDINATE'),
    ({'coordinate':'','title':'없는제목','coordinate_scope':'body'},'MISSING_TITLE'),
    ({'coordinate':'제6조','title':'다른제목','coordinate_scope':'body'},'TITLE_FILTER_MISMATCH'),
    ({'coordinate':'제6조','title':'','coordinate_scope':'annex'},'MISSING_STRUCTURE_BRANCH'),
])
def test_failure_reason_is_specific_no_fallback_and_tree_is_retained(fields,expected):
    m = hierarchy_matcher()
    before = sq.document_structure(m,['law'],'law',unit_id='article6')
    result = sq.catalogue(m,['law'],document_id='law',structure_filter=fields)
    assert result['lookup_status']=='MISS' and result['failure']['code']==expected
    assert result['failure']['automatic_fulltext_fallback'] is False
    assert result['failure']['suggested_action']
    assert sq.document_structure(m,['law'],'law',unit_id='article6')==before

@pytest.mark.parametrize('fault,expected', [
    ('duplicate','AMBIGUOUS_COORDINATE'),('missing','MISSING_ORIGINAL'),
    ('multiple','NON_UNIQUE_ORIGINAL'),('unresolved','UNRESOLVED_COORDINATE_BINDING')])
def test_original_or_binding_fault_never_offers_automatic_read(fault,expected):
    m = hierarchy_matcher()
    if fault=='duplicate':
        m.units[('law','duplicate')]=dict(m.units[('law','article6')])
        m.stored_coordinates[('law','duplicate')]=m.stored_coordinates[('law','article6')]
        m.sources['lawduplicate']={'document_id':'law','unit_id':'duplicate'}
    elif fault=='unresolved':
        m.units[('law','article6')]['coordinate_binding']={'mode':'unresolved'}
    else:
        m._unit_sources=lambda did,uid: [] if fault=='missing' else ['fake-a','fake-b']
    result = sq.catalogue(m,['law'],document_id='law',structure_filter={'coordinate':'제6조','title':'','coordinate_scope':'body'})
    assert result['failure']['code']==expected
    assert all(not row.get('readable') for row in result['items'])
    assert not result['citation_eligible']

def test_missing_and_ambiguous_document_stay_distinct():
    m = hierarchy_matcher()
    assert sq.resolve('제6조',m,['law'])['failure']['code']=='MISSING_DOCUMENT'
    m.document_names.add('자본시장법','decree')
    assert sq.resolve('자본시장법 제6조',m,['law','decree'])['failure']['code']=='AMBIGUOUS_DOCUMENT'

def test_actual_journal_events_reach_scoped_progress_without_source_bodies(journal):
    repo, projection, events = journal
    repo.event('LAW_STRUCTURE_DIRECTORY',{'document_id':'allowed','queries':[], 'structure_filter':FIELDS,
        'lookup_status':'MISS','failure':sq.failure('MISSING_COORDINATE'),'items':[]})
    repo.event('LAW_DOCUMENT_STRUCTURE',{'document_id':'allowed','document_name':'모의법',
        'path':[{'coordinate':'제1편'},{'coordinate':'제6조'}],'total':10,'text':'DO NOT SEND BODY'})
    repo.event('LAW_STRUCTURE_RECOVERY',{'document_id':'allowed','document_name':'모의법',
        'pages_without_new_original':3,'reason':'새 원문 없이 반복','next_step':'구조 번호 조회'})
    repo.event('LAW_DOCUMENT_STRUCTURE',{'document_id':'other','document_name':'PRIVATE OUTSIDE','path':[]})
    projection.poll_journal()
    rendered = json.dumps(events,ensure_ascii=False)
    for marker in ('MISSING_COORDINATE','제1편 → 제6조','구조 탐색으로 전환','coordinate'):
        assert marker in rendered
    assert 'PRIVATE OUTSIDE' not in rendered and 'DO NOT SEND BODY' not in rendered
    assert not any(e['kind'] in ('selected','reading') for e in events)
    count = len(events); projection.poll_journal(); assert len(events)==count

def test_workflow_renders_fields_outcome_path_and_recovery_safely():
    view={'stages':[{'id':'5','stage':'SELECT','label':'근거 선택','status':'수행','actions':[],'decisions':[],
        'investigation_chain':{'steps':[{'number':1,'action':'SEARCH_STRUCTURE','status':'APPLIED',
            'structure_filter':{'coordinate':'제6조','title':'<script>','coordinate_scope':'body'},
            'structure_lookup':{'lookup_status':'MISS','total':0,'failure':sq.failure('MISSING_TITLE')},
            'structure_path':[{'coordinate':'제1편'},{'coordinate':'제6조'}]}]},
        'structure_recovery':[{'document_name':'모의법','reason':'후보 반복','next_step':'구조 조회'}]}]}
    module = workflow()
    module._judgment_view = lambda body: view
    text = module._judgment_html({})
    for marker in ('문서 구조 검색','조문 번호: 제6조','MISSING_TITLE','제1편','후보 반복'):
        assert marker in text
    assert '<script>' not in text and '&lt;script&gt;' in text

def test_final_judgment_consumer_preserves_scoped_recovery_and_typed_history():
    from test_genos_judgment_view import sample
    from semantic_runtime.legal_agent.judgment_view import build
    from semantic_runtime.contracts import digest
    parts, case, state = sample()
    payload = parts['SELECT']['payload']
    payload.update(law_navigation={'laws':[{'id':'law','document_id':'d','name':'모의규정'}]},
        control_contract='investigation-control-v2',investigation_chain={'steps':[{'structure_filter':FIELDS}]},
        return_points=[],saved_inventory=[],evidence_inventory=[],
        structure_recovery=[{'document_id':'d','reason':'후보 반복'}, {'document_id':'other','reason':'PRIVATE OUTSIDE'}])
    case['judgment_refs']['SELECT']['payload_hash']=digest(payload)
    view=build(parts,case,state=state,run_id='r1',allowed_documents=['d'])
    selected=next(s for s in view['stages'] if s['stage']=='SELECT')
    assert selected['investigation_chain']['steps'][0]['structure_filter']==FIELDS
    assert selected['structure_recovery']==[{'document_id':'d','reason':'후보 반복'}]

def test_same_original_with_another_delivery_id_does_not_reset_recovery(session):
    native, _ = session
    inv = investigation(native); data, actions = inv.view()
    data, actions = page_only(inv,data,actions)
    data, actions = apply(inv,data,actions,'READ_PARENT',choose(actions,'READ_PARENT'))
    page=copy.deepcopy(data['sources'][0])
    inv.p['navigation_recovery']['delivered_spans']={'d':copy.deepcopy(page['spans'])}
    page['id']='same-body-different-delivery-id'
    inv.observe_navigation({'next_action':'BROWSE_STRUCTURE'}, {'sources':[page]}, {})
    assert inv.recovery_view()[0]['pages_without_new_original']==3
