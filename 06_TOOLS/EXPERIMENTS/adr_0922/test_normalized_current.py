"""New deterministic contracts for defects discovered in completed ADR0921."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest
from test_batch_reference_navigation import connected
from test_structure_reading import value
from semantic_runtime.legal_agent import connected_exploration as ce
from semantic_runtime.legal_agent.errors import ContractError
P=Path(__file__).resolve().parent/'test_connected_exploration.py'
spec=importlib.util.spec_from_file_location('parent_connected_contracts',P);parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)


def test_unsegmented_term_matches_real_index_without_broad_or_expansion(connected,monkeypatch):
    inv=parent.start(connected[0],monkeypatch)
    monkeypatch.setattr(ce,'term_keys',lambda _:['긴급승인'])
    data,_=parent.read_document(inv,'d')
    page=data['document_term_candidates']['documents'][0]
    assert page['terms']==['긴급승인'] and page['query_terms']==['긴급 승인']
    assert page['total']==1 and page['items'][0]['preview']
    assert not page['items'][0]['citation_eligible'] and not inv.active_records()
    assert ce.query_forms(['긴급승인','긴급 승인'])==['긴급 승인']


def fresh_unacknowledged(inv):
    data,actions=inv.view()
    src=next(s for s in inv.s.tools.sources.values() if s['document_id']=='d')
    act={'id':'fixture','action':'READ_ARTICLES','identity':{'source_id':src['id'],'document_id':'d','unit_id':src['unit_id']},'label':'read original'}
    inv.execute_tool(value(data,'READ_ARTICLES',act['id']),data,{act['id']:act})
    # Definition acquisition intentionally restores earlier navigation origin.
    inv.p.update(window='search',window_groups=[],focus=None)
    assert not inv.p['basis_history']
    return inv.view()


def test_current_original_enables_incoming_before_acknowledgment(connected,monkeypatch):
    inv=parent.start(connected[0],monkeypatch);data,actions=fresh_unacknowledged(inv)
    assert not inv.active_records() and not any(b.get('accepted') for b in inv.p['basis_history'].values())
    card=next(c for c in data['references']['dependency_cards'] if c['target']['document_id']=='detail')
    assert card['read_action'] in actions and card['direction']=='INCOMING'
    assert data['sources'] and {s['document_id'] for s in data['sources']}=={'d'}
    assert card['applicability']=='UNDETERMINED'


@pytest.mark.parametrize('change',['text','scope'])
def test_forged_current_page_cannot_authorize_reference(connected,monkeypatch,change):
    inv=parent.start(connected[0],monkeypatch);data,_=fresh_unacknowledged(inv);pages=deepcopy(data['sources'])
    if change=='text':pages[0]['spans'][0]['text']='fabricated'
    else:pages[0]['document_id']='foreign'
    with pytest.raises(ContractError):inv.reference_overview(current_pages=pages)


def test_empty_indexable_term_is_partial_without_database_query(connected,monkeypatch):
    inv=parent.start(connected[0],monkeypatch);monkeypatch.setattr(ce,'query_forms',lambda _:[])
    data,_=parent.read_document(inv,'d');page=data['document_term_candidates']['documents'][0]
    assert page['status']=='PARTIAL' and page['reason']=='NO_INDEXABLE_TERM'
    assert not ce.state(inv)['documents']['d']['absence_proven']
    assert inv.read_records() and not inv.active_records()
