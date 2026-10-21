"""Synthetic source handoff contracts; no external model or legal scoring."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import importlib.util,json,sqlite3
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import investigation_leads as leads
from semantic_runtime.legal_agent import source_handoff as handoff,connected_exploration as ce
from semantic_runtime.legal_agent.errors import ContractError
from test_batch_reference_navigation import connected

def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
T=Path(__file__).parents[1]
connected_helpers=module('connected_922_tests',T/'adr_0922/test_connected_exploration.py')
sources=module('source_844_tests',T/'adr_0930/test_sources_compact.py')
tree=sources.tree


def setup(inv):
    data,actions=connected_helpers.read_document(inv,'d')
    value=leads.capture(inv,data)
    return data,actions,value


def test_incoming_lead_preserves_header_only_acquisition_without_promoting_preview(connected,monkeypatch):
    inv=connected_helpers.start(connected[0],monkeypatch)
    data,_,catalogue=setup(inv)
    b=next(r for r in catalogue['items'] if r['target']['document_id']=='detail')
    assert b['acquisition']=='PARTIAL' and b['citation_eligible'] is False
    before=deepcopy(inv.s.repo.evidence())
    assert any(o['kind']=='INCOMING_REFERENCE' for o in b['origins'])
    returned=handoff.selection(inv,{'reason':'원문 A와 미열람 단서 B 반환'})
    assert returned['source_return']['schema_version']=='source-investigation-v2'
    assert returned['selected_evidence']==before
    assert [p['text'] for e in before if e['document_id']=='detail' for p in e['spans']]==['제2조 예외']
    assert '책임자 확인' not in json.dumps(returned['selected_evidence'],ensure_ascii=False)
    assert returned['source_return']['leads']==catalogue
    assert returned['source_return']['absence_proven'] is False


def test_new_B_read_changes_scope_without_automatically_adopting_A(connected,monkeypatch):
    inv=connected_helpers.start(connected[0],monkeypatch);_,_,before=setup(inv)
    connected_helpers.read_document(inv,'detail')
    after=leads.export(inv)
    row=next(r for r in after['items'] if r['target']['document_id']=='detail')
    assert row['acquisition'] in ('PARTIAL','ACQUIRED') and row['read_scopes']
    assert before['catalogue_hash']!=after['catalogue_hash']
    assert not inv.active_records()
    out=handoff.selection(inv,{'reason':'A와 B의 판단은 부모에게 전달'})
    assert {'d','detail'}<={e['document_id'] for e in out['selected_evidence']}


def parent(inv,catalogue):
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE workflow_child_export(call_id TEXT PRIMARY KEY,bundle_json TEXT,bundle_hash TEXT)')
    bundle={'side':'external','investigation_return':{'schema_version':'source-investigation-v2','leads':catalogue}}
    bundle['bundle_hash']=digest(bundle)
    db.execute('INSERT INTO workflow_child_export VALUES(?,?,?)',('call',json.dumps(bundle),digest(bundle)))
    repo=NS(db=db,evidence=lambda ident:None)
    session=NS(repo=repo,tools=inv.s.tools,matcher=inv.s.matcher,verify=lambda e:None)
    port=NS(session=session,all_scope=inv.s.scope,categories={d:'external' for d in inv.s.scope})
    result={'request_id':'call','side':'external','bundle':bundle,'evidence_ids':[]}
    return port,result


@pytest.mark.parametrize('tamper',['scope','target','bundle','catalogue','eligibility'])
def test_parent_rejects_untrusted_leads(connected,monkeypatch,tamper):
    inv=connected_helpers.start(connected[0],monkeypatch);_,_,value=setup(inv)
    port,result=parent(inv,value)
    catalogue=leads.parent_catalogue(port,[result]);assert catalogue['items']
    lead=next(r for r in catalogue['items'] if r['target']['document_id']=='detail')
    loc=leads.lead_locator(port,lead);assert leads.validate_locator(port,loc)==loc
    if tamper=='scope':port.all_scope=['d']
    elif tamper=='target':loc['unit_id']='forged'
    elif tamper=='bundle':loc['lead_ref']['bundle_hash']='forged'
    elif tamper=='catalogue':loc['lead_ref']['catalogue_hash']='forged'
    else:
        result['bundle']['investigation_return']['leads']['items'][0]['citation_eligible']=True
        with pytest.raises(ContractError):leads.parent_catalogue(port,[result])
        return
    with pytest.raises((ContractError,KeyError)):leads.validate_locator(port,loc)


def test_same_catalogue_is_idempotent_and_empty_return_valid(connected,monkeypatch):
    inv=connected_helpers.start(connected[0],monkeypatch)
    empty=handoff.selection(inv,{'reason':'미확보 반환'})
    assert empty['source_return']['leads']['recording_status']=='NOT_RECORDED'
    data,_,value=setup(inv)
    assert leads.capture(inv,data)==value
    assert leads.projection(value)['items']
    from jsonschema import validate
    validate(empty,handoff.schema())
    old=deepcopy(empty);old['source_return'].pop('leads');old['source_return']['schema_version']='source-investigation-v1'
    validate(old,handoff.schema())


def test_oracle_document_scope_does_not_materialize_source_ids():
    inv,_,_=connected_helpers.fake_inv()
    class Scope:
        document_ids=frozenset(['d'])
        def __contains__(self,value):return value=='a'
        def __iter__(self):raise AssertionError('Oracle source IDs must remain a document predicate')
    scope=Scope();inv.s.tools.sources.ids_for_documents=lambda ids:scope
    original=inv.idx.article_groups_page
    def query(db,terms,did,allowed,**kw):
        assert allowed is scope
        return original(db,terms,did,allowed,**kw)
    inv.idx.article_groups_page=query
    entry={'status':'NEW','query_terms':['승인'],'terms':['승인'],'binding':'b'}
    ce.load_page(inv,'d',entry)
    assert entry['status']=='READY'


def test_actual_workflow_api_v2_export_parent_view_and_duplicate(tmp_path,tree):
    app,t=sources.app_for(tmp_path,tree)
    with TestClient(app) as client:
        first=client.post('/v1/workflows/run',json={**sources.BODY,'workflow_id':'risk_team_compare_workflow'})
        assert first.status_code==200,first.text
        value=first.json()
        for side in ('internal','external'):
            child=value['rag_results'][side]
            assert child['investigation_return']['schema_version']=='source-investigation-v2'
            assert child['bundle']['schema_version']=='workflow-comparison-bundle-v3'
            leads.validate(child['investigation_return']['leads'])
        views=[v for stage,v in t.views if stage=='workflow-items']
        assert views and all('investigation_leads' in v for v in views)
        count=len(t.views)
        second=client.post('/v1/workflows/run',json={**sources.BODY,'workflow_id':'risk_team_compare_workflow'})
        assert second.status_code==200 and second.json()['answer']==value['answer']
        assert len(t.views)==count
        saved=client.get('/v1/workflows/runs/'+value['run_id'],params={'session_id':'s'})
        assert saved.status_code==200 and saved.json()['answer']==value['answer']


@pytest.fixture
def two_articles(tmp_path,term_glossary):
    base=sources.prior._base
    raw=base.source(tmp_path/'leads.sqlite',[
        ('inside','모의내규',['제1조(승인) 승인 후 보고한다.']),
        ('outside','모의승인규정',['제1조(승인 원칙) 승인은 위원회가 한다.','제2조(승인 예외) 긴급 승인은 담당자가 하고 사후 보고한다.'])])
    with sqlite3.connect(raw) as db:
        for did in ('inside','outside'):
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({'document_category':'external' if did=='outside' else 'internal','document_metadata':{'team':'risk_team'},'workflow_version':{'verified':True,'valid_from':'2020-01-01','valid_to':None}}),did))
    base.build_generation(raw,term_glossary,tmp_path/'leads-built',serving=True)
    gen=tmp_path/'leads-built/generation';index=tmp_path/'leads-index'
    base.build(gen,gen/'navigation',index,workers=1)
    return gen,base.UnitFulltextIndex(index,json.loads((gen/'navigation/manifest.json').read_text()))


def test_parent_selects_unread_term_locator_then_receives_original(tmp_path,two_articles,monkeypatch):
    from semantic_runtime import comparison_research_bridge as bridge
    from test_legal_agent_double_harness import wire
    original=bridge.preferred_documents
    monkeypatch.setattr(bridge,'preferred_documents',lambda port,q,side:[] if side=='external' else original(port,q,side))
    monkeypatch.setattr(ce,'term_keys',lambda inv:['승인'])
    class Choose(sources.Sources):
        def __init__(self):super().__init__();self.chosen=None;self.later_seen=False
        def send_once(self,*,body,ticket):
            v=json.loads(body['messages'][1]['content'])['view'];stage=v.get('source_stage',v['phase'])
            if stage.startswith('source-law-sources-') and not v.get('sources') and not v.get('preferred_originals'):
                first=next((a for a in v.get('actions',[]) if a['action']=='READ_ARTICLES' and '제1조' in a['label']),None)
                if first:
                    self.views.append((stage,deepcopy(v)))
                    return wire({'target_id':first['id'],'query':None,'reason':'원칙 조문 먼저 확인'})
            raw=super().send_once(body=body,ticket=ticket)
            if stage=='workflow-items':
                if self.chosen:
                    self.later_seen= self.later_seen or any(e['document_id']=='outside' and '긴급' in json.dumps(e,ensure_ascii=False) for e in v['sources'])
                unread={r['lead_id'] for r in v.get('investigation_leads',{}).get('items',[]) if r['acquisition']=='NOT_READ' and not r.get('parent_read_evidence_ids')}
                candidates=[(loc['locator_id'],loc) for loc in (dict(zip(v['locators']['columns'],r)) for r in v['locators']['rows']) if loc.get('lead_id') in unread and loc['side']=='external' and '2' in str(loc.get('coordinate',''))]
                if candidates and self.chosen is None:
                    key,loc=candidates[0];self.chosen=deepcopy(loc)
                    out=json.loads(raw['body_json']['choices'][0]['message']['content'])
                    out['items'][0]['next_tasks']=[{'side':'external','locator_id':key,'query':'승인 예외를 확인한다','reason':'원칙과 예외를 함께 검토'}]
                    return wire(out)
            return raw
    app,_=sources.app_for(tmp_path,two_articles);transport=Choose();app.state.pipeline.term_agent.transport=transport
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json={**sources.BODY,'workflow_id':'risk_team_compare_workflow'})
        assert response.status_code==200,response.text
        out=response.json()
        assert transport.chosen is not None,out
        assert any(r['status']=='COMPLETE' for r in out['research_attempts'].values()),out
        assert transport.later_seen,transport.views


def test_empty_original_journal_return_is_valid():
    from jsonschema import validate
    inv=NS(p={'binding':'empty-fixture'},s=NS(repo=NS(evidence=lambda:[])))
    out=handoff.selection(inv,{'reason':'조회 범위 내 원문 미확보'})
    validate(out,handoff.schema())
    assert out['selected_evidence']==[] and out['source_return']['read_evidence_ids']==[]
    assert out['source_return']['leads']['items']==[]
    assert out['source_return']['absence_proven'] is False
    assert out['source_return']['semantic_quality_certified'] is False
