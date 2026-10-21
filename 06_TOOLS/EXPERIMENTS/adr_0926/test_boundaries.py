"""Independent finite boundaries; no model calls or legal gold."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import investigation_leads as leads
from semantic_runtime.legal_agent.errors import ContractError
from test_batch_reference_navigation import connected
from test_leads import setup, parent, connected_helpers


def fixture(connected, monkeypatch):
    inv=connected_helpers.start(connected[0],monkeypatch)
    _,_,value=setup(inv)
    port,result=parent(inv,value)
    row=next(r for r in leads.parent_catalogue(port,[result])['items'] if r['target']['document_id']=='detail')
    return inv,port,result,leads.lead_locator(port,row)


@pytest.mark.parametrize('kind',['category','return_side','missing_export','stale_export'])
def test_parent_boundary_rejects_stale_or_cross_side(connected,monkeypatch,kind):
    inv,port,result,loc=fixture(connected,monkeypatch)
    if kind=='category':port.categories['detail']='internal'
    elif kind=='return_side':result['side']='internal'
    elif kind=='missing_export':port.session.repo.db.execute('DELETE FROM workflow_child_export')
    else:port.session.repo.db.execute("UPDATE workflow_child_export SET bundle_hash='changed'")
    with pytest.raises(ContractError):
        if kind=='return_side':leads.parent_catalogue(port,[result])
        else:leads.validate_locator(port,loc)


@pytest.mark.parametrize('kind',['artifact','membership'])
def test_current_source_binding_is_required(connected,monkeypatch,kind):
    inv,port,result,loc=fixture(connected,monkeypatch)
    session=port.session
    source=deepcopy(session.tools.sources[loc['source_id']])
    if kind=='artifact':source['source_artifact_sha256']='changed'
    else:source['document_id']='d'
    session.tools=NS(sources={loc['source_id']:source})
    # Catalogue contains multiple leads; use the bound locator's catalogue only.
    bundle=deepcopy(result['bundle']);v=bundle['investigation_return']['leads']
    v['items']=[r for r in v['items'] if r['lead_id']==loc['lead_ref']['lead_id']]
    v['catalogue_hash']=digest({k:x for k,x in v.items() if k!='catalogue_hash'})
    with pytest.raises(ContractError):leads.validate(v,session,port.all_scope)


def test_duplicate_committed_return_does_not_multiply_locations(connected,monkeypatch):
    inv,port,result,loc=fixture(connected,monkeypatch)
    one=leads.parent_catalogue(port,[result])
    two=leads.parent_catalogue(port,[result,result])
    assert one['items']==two['items']
    assert all(r['citation_eligible'] is False for r in two['items'])


def test_unicode_parent_view_is_bounded_and_does_not_promote_previews(connected,monkeypatch):
    inv,port,result,loc=fixture(connected,monkeypatch)
    value=leads.parent_catalogue(port,[result]);row=value['items'][0]
    value['items']=[{**deepcopy(row),'lead_id':str(i),'preview':'연결된 원문을 읽어야 한다🙂'*30} for i in range(80)]
    before=deepcopy(value);view=leads.parent_projection(value)
    assert len(view['items'])<=16
    assert sum(len(json.dumps(r,ensure_ascii=False)) for r in view['items'])<=6000
    assert view['omitted_count']==value['omitted_count']+80-len(view['items'])
    assert value==before and all(r['citation_eligible'] is False for r in view['items'])
