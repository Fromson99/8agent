from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import definition_context as dc, law_candidates as lc, unit_reading as ur, unit_relations as rel
from semantic_runtime.legal_agent.law_navigation import Investigation
from semantic_runtime.legal_agent.errors import ContractError, ToolExecutionError
from test_batch_reference_navigation import connected
from conftest import term_glossary

@pytest.fixture
def definition_source(monkeypatch):
    import test_batch_reference_navigation as f
    original=f.source
    def source(path,documents):
        documents=deepcopy(documents)
        documents[0][2][0]='제1조(승인) 승인 항목은 세칙으로 정하는 항목이다.'
        return original(path,documents)
    monkeypatch.setattr(f,'source',source)
    original_build=f.build_generation
    def build(raw,*a,**kw):
        import sqlite3,json
        from lawrag.core.legal_coordinate import find_coordinates
        with sqlite3.connect(raw) as db:
            for did,uid,payload in db.execute('select document_id,unit_id,json from source_unit').fetchall():
                number={'d':1,'detail':2,'foreign':3}[did]
                surface=f'제{number}조'+('제1항' if uid!='0' else '')+(f'제{int(uid)-1}호' if uid not in ('0','1') else '')
                coordinate=find_coordinates(surface)[0].coordinate;unit=json.loads(payload)
                unit.update(legal_coordinate=coordinate.as_dict(),coordinate_scope='body',coordinate_key='body:'+coordinate.canonical_surface())
                db.execute('update source_unit set json=? where document_id=? and unit_id=?',(json.dumps(unit,ensure_ascii=False),did,uid))
        return original_build(raw,*a,**kw)
    monkeypatch.setattr(f,'build_generation',build)


@pytest.fixture
def inv(definition_source,connected):
    s,_=connected;s.profile.setdefault('candidate_navigation',{}).update(delegation_frontier=True)
    src=next(v for v in s.tools.sources.values() if v['document_id']=='d')
    hit=lc.structure_hit(s,src['id'],'0');offer=lc.parent_offer(s,hit)
    state={'count':0,'chars':0};record=ur.read(s,hit,offer,action_state=state)
    p={'binding':{'case':'fixture'},'laws':{},'groups':{},'selected':{},'contexts':{},'read_state':state,'requested_originals':[], 'material_history':{}}
    inv=S(s=s,p=p,policy={'definition_context':True},completion=True,control=True,save=lambda:None)
    for name in ('add_laws','add_reads','read_records','plan_pages','register_read'):
        setattr(inv,name,getattr(Investigation,name).__get__(inv))
    inv.add_reads([{**record,'hit':hit}]);gid=lc.token(s,'B',[src['id'],offer['id']]);p['selected'][gid]=record;p['groups'][gid]['status']='READ';p['requested_originals']=[gid]
    return inv,gid

@pytest.mark.parametrize('connected',['① 「모의승인규정」 제1조에서 "세칙으로 정하는 항목"이란 다음 각 호를 말한다.'],indirect=True)
def test_actual_endpoint_children_delivery_and_resume_without_recursive_read(inv):
    i,gid=inv;added=dc.acquire(i,[gid]);assert len(added)==1
    r=i.p['selected'][added[0]]
    assert r['document_id']=='detail' and r['offer']['unit_id']=='1'
    assert set(r['offer']['block_ids'])=={'1','2','3'}
    assert '책임자 확인' in r['text'] and '정해진 보고' in r['text']
    assert i.p['groups'][added[0]]['delivery']==0 and i.p['groups'][added[0]]['delivery_requested']
    assert i.p['groups'][added[0]]['status']=='READ'
    assert not any(r['document_id']=='foreign' for r in i.p['selected'].values())
    before=deepcopy(i.p['read_state']);i.p=deepcopy(i.p)
    assert dc.acquire(i,[gid])==added and i.p['read_state']==before
    with pytest.raises(ContractError):dc.acquire(i,added)
    assert i.p['definition_context']['reserved_reads']==1

@pytest.mark.parametrize('connected',['① 「모의승인규정」 제1조에 따른 일반적인 보고 절차다.'],indirect=True)
def test_mere_citation_does_not_trigger_context(inv):
    i,gid=inv;before=deepcopy(i.p['read_state']);assert dc.acquire(i,[gid])==[]
    assert i.p['read_state']==before

@pytest.mark.parametrize('connected',['① 「모의승인규정」 제1조에서 "세칙으로 정하는 다른 항목"이란 다음 각 호를 말한다.'],indirect=True)
def test_different_quoted_wording_does_not_trigger_context(inv):
    i,gid=inv;assert dc.acquire(i,[gid])==[]

@pytest.mark.parametrize('connected',['① 「모의승인규정」 제1조에서 "세칙으로 정하는 항목"이란 다음 각 호를 말한다.'],indirect=True)
@pytest.mark.parametrize('case',['bound','failure','tamper'])
def test_bounds_failures_and_fatal_integrity_keep_original(inv,monkeypatch,case):
    i,gid=inv;original=deepcopy(i.p['selected'][gid])
    if case=='bound':monkeypatch.setattr(dc,'MAX_CHARS',1)
    if case=='failure':monkeypatch.setattr(ur,'read',lambda *a,**kw:(_ for _ in ()).throw(TimeoutError('fixture')))
    if case=='tamper':
        monkeypatch.setattr(rel,'catalog',lambda *a,**kw:(_ for _ in ()).throw(ContractError('witness hash mismatch')))
        with pytest.raises(ContractError):dc.acquire(i,[gid])
    else:
        assert dc.acquire(i,[gid])==[]
        before=deepcopy(i.p['read_state']);assert dc.acquire(i,[gid])==[];assert i.p['read_state']==before
        receipt=next(iter(i.p['definition_context']['anchors'].values()))
        assert receipt['omitted'] if case=='bound' else receipt['status']=='UNAVAILABLE'
    assert i.p['selected'][gid]==original


def test_automatic_seed_does_not_claim_model_selected_origin(monkeypatch):
    from semantic_runtime.legal_agent import definition_entry as de
    from semantic_runtime.contracts import digest
    identity={'source_id':'s','document_id':'d','unit_id':'0'};target='SYSDEF:'+digest(identity)
    seed={'status':'STARTED','targets':[target],'actions':{target:{'action':'READ_ARTICLES','identity':identity}},
          'completed':[],'binding':digest(['q',['d'],[]])}
    calls=[]
    def execute(decision,data,actions,*,model_selected=False):calls.append(model_selected)
    inv=S(policy={'definition_entry':True},p={'system_definition_seed':seed,'definition_matches':[]},modern=False,
          s=S(context=S(request={'question':'q'}),scope=['d'],profile={'selection_time_reserve_seconds':1},repo=S(event=lambda *a:None)),
          save=lambda:None,left=lambda:100,execute_tool=execute)
    monkeypatch.setattr(de,'acquired_receipt',lambda *a:{'group_id':'g'})
    de.acquire_initial(inv)
    assert calls==[False] and seed['status']=='COMPLETE'


def test_actual_api_model_execution_has_explicit_origin(tmp_path,term_glossary,monkeypatch):
    from test_answer_progress_api import test_progress_actual_api_reads_link_or_structural_target_and_reuses_request as run
    seen=[];original=Investigation.execute_tool
    def execute(self,decision,data,actions,*,model_selected=False):
        if decision['next_action']=='READ_ARTICLES':
            seen.append(model_selected)
            if model_selected:assert self.p['accepted']['decision']==decision
        return original(self,decision,data,actions,model_selected=model_selected)
    monkeypatch.setattr(Investigation,'execute_tool',execute)
    run(tmp_path,term_glossary,'connection',monkeypatch)
    assert seen and all(seen)
