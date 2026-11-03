"""Real console entries with isolated durable stores and bounded host ports."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from test_wiki_workspace import env, ws
from test_domain_profile_workflow import Glossary
from semantic_runtime.ontology_work import configuration as cfg
from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
from semantic_runtime.legal_agent.errors import ContractError, ProposalError


@pytest.fixture
def host(env, ws, monkeypatch, tmp_path):
    config={'version':'ontology-connection-v1','environment':'local',
        'operators':{'reviewer':{'document_ids':['fictional'],'workspace_publish':True}},
        'domain_profile':{'namespace':env.w.namespace,'source_snapshot':env.w.source_snapshot,'acl_ref':env.w.acl_ref},
        'work_store':{'kind':'local','path':str(tmp_path/'objects')}}
    settings=tmp_path/'settings.json';settings.write_text(json.dumps(config))
    monkeypatch.setenv('GENOS_RAG_ONTOLOGY_CONFIG',str(settings))
    monkeypatch.setenv('GENOS_ONTOLOGY_OPERATOR','reviewer')
    monkeypatch.delenv('ONTOLOGY_DASHBOARD_DEMO',raising=False)
    from semantic_runtime.ontology_work.workflow import Workflow
    base=Workflow(env.repo,env.w.store,actor='reviewer',source_reader=env.w.source_reader)
    calls=[]
    def glossary():
        calls.append('glossary')
        return GlossaryBinding(Glossary(),snapshot=env.w.source_snapshot)
    @contextmanager
    def context():
        with cfg.authoring_context(actor='reviewer',workflow=base,glossary_factory=glossary,config=config):
            yield
    return SimpleNamespace(config=config,path=settings,context=context,base=base,calls=calls,glossary=glossary)


def test_host_ports_are_lazy_and_scoped(env,host):
    with host.context():
        assert cfg.workflow(actor='reviewer') is host.base
        assert cfg.workspace_workflow(actor='reviewer').repo is env.repo
        assert host.calls==[]
        domain=cfg.domain_workflow(actor='reviewer')
        assert domain.repo is env.repo and domain.can_publish_workspace
        domain.glossary.reader.close()
        with pytest.raises(ContractError):cfg.workflow(actor='outsider')
    assert cfg._AUTHORING.get() is None
    assert host.calls==['glossary']


@pytest.mark.parametrize('fault',['actor','grant','snapshot','workspace'])
def test_host_rejects_scope_drift(env,host,fault):
    altered=deepcopy(host.config)
    if fault=='grant':altered['operators']['reviewer']['document_ids']=[]
    if fault=='workspace':altered['workspace']={**altered['domain_profile'],'namespace':'other'}
    if fault=='snapshot':altered['domain_profile']['source_snapshot']='foreign'
    host.path.write_text(json.dumps(altered))
    with pytest.raises(ContractError):
        with cfg.authoring_context(actor='outsider' if fault=='actor' else 'reviewer',workflow=env.w,
                glossary_factory=host.glossary,config=altered):
            cfg.domain_workflow(actor='reviewer')
    assert cfg._AUTHORING.get() is None


@pytest.mark.parametrize('status',['OFF','NO_SCOPE','EMPTY','READY'])
def test_reader_readiness_is_explicit(env,host,status):
    with cfg.authoring_context(actor='reviewer',workflow=env.w,glossary_factory=host.glossary,
            config=host.config,runtime_probe=lambda:{'status':status}):
        assert cfg.connection_status(actor='reviewer')['status']==status
    with host.context():assert cfg.connection_status(actor='reviewer')['status']=='UNVERIFIED'


def test_reader_failure_is_not_empty(env,host):
    def broken():raise OSError('unavailable')
    with cfg.authoring_context(actor='reviewer',workflow=env.w,glossary_factory=host.glossary,
            config=host.config,runtime_probe=broken):
        with pytest.raises(OSError):cfg.connection_status(actor='reviewer')


@pytest.mark.parametrize('entry',['ontology_app.py','app.py'])
def test_actual_entries_store_reload_and_switch(env,ws,host,monkeypatch,entry):
    from streamlit.testing.v1 import AppTest
    module=SimpleNamespace(context=host.context)
    monkeypatch.setitem(sys.modules,'console_test_host',module)
    monkeypatch.setenv('GENOS_ONTOLOGY_HOST_FACTORY','console_test_host:context')
    front=Path(os.environ['LOOP_TEST_CODE_ROOT'])/'03_FRONTEND/APPS/legal-knowledge-streamlit'
    app=AppTest.from_file(str(front/entry),default_timeout=20).run()
    if entry=='app.py':
        next(b for b in app.button if b.key=='nav_온톨로지 관리').click().run()
    assert not app.exception and not app.error, ([x.value for x in app.exception],[x.value for x in app.error])
    next(r for r in app.radio if r.label=='관리 작업').set_value('자유 작업공간').run()
    assert not app.exception and not app.error, ([x.value for x in app.exception],[x.value for x in app.error])
    next(x for x in app.text_input if x.label=='항목 이름').set_value('공통 진입 저장')
    next(x for x in app.text_area if x.label=='기록·설명').set_value('무손실 기록')
    next(x for x in app.button if x.label=='기록 저장').click().run()
    assert not app.exception and not app.error, ([x.value for x in app.exception],[x.value for x in app.error])
    assert len(ws.list_items()['items'])==1
    for panel in ('검토 대시보드','시나리오 검증','자유 작업공간'):
        next(r for r in app.radio if r.label=='관리 작업').set_value(panel).run()
        assert not app.exception and not app.error, ([x.value for x in app.exception],[x.value for x in app.error])
    app.run();assert len(ws.list_items()['items'])==1 and host.calls==[]


def test_identity_change_clears_draft_and_activation_receipts(monkeypatch):
    import ontology_console as console
    state={'oc_identity':'old','wiki_compiled':'foreign','domain_checked_one':{'active':True},
        'od_bundle':'other','unkeyed_widget':'old text','private_review_access':'login'}
    monkeypatch.setattr(console.st,'session_state',state)
    console.reset_identity('new')
    assert state=={'oc_identity':'new','private_review_access':'login'}


def test_computed_reference_in_prose_rejected_raw_preserved():
    from test_server_computation import context,gap_schema,gap
    from semantic_runtime.legal_agent import scenario_computation as calc
    c=context();ref=calc.gap_options(c)[0]['computed_gap_ref']
    _,expand=calc.projection(gap_schema(),c)
    raw={'gaps':[gap('미확인 '+ref+' 확인')]};before=deepcopy(raw)
    with pytest.raises(ProposalError) as e:expand(raw)
    assert raw==before and e.value.proposal==before
    assert e.value.issues[0]['code']=='COMPUTED_GAP_IN_REASON'
    accepted={'gaps':[gap('computed-gap:다른문자 원문과 설명은 보존')]}
    assert expand(accepted)==accepted
    assert expand({'gaps':[{'computed_gap_ref':ref,'issue_id':'Q1'}]})['gaps'][0]['reason']==calc.gap_options(c)[0]['reason']


def test_history_separate_without_number_replacement():
    from semantic_runtime.legal_agent import review_explanation as review
    declaration='138만원 기준 조사가 필요합니다. 끝 예외도 보존합니다.'
    assessment={'read_judgment_review':{'prior_needs':[{'id':'N1','text':declaration}]}}
    old=review.need_items(assessment)[0]
    assert declaration in old['reason']
    assessment['scenario_calculation']={'server':'receipt'}
    row=review.need_items(assessment)[0]
    assert declaration==row['historical_declaration'] and '138만원' not in row['reason']
    assert row['review']=='INCOMPLETE' and row['next_action']=='REVIEW_AGAIN'
    from semantic_runtime.legal_agent import completion_contracts as cc
    from test_server_computation import gap
    assessment['gaps']=[gap('승인 확인 필요')]
    cc.refresh_limitations(assessment,[{'id':'Q1','question':declaration}])
    assert assessment['limitation_items'][0]['historical_issue']==declaration
    assert all('138만원' not in s for s in assessment['limitations'])
    view=review.build(assessment,[])
    assert view['historical_issues']==[declaration]


def test_actual_console_compile_review_activate(env,ws,host,monkeypatch):
    from test_wiki_workspace import seed,projection_generator
    from semantic_runtime.ontology_work import wiki_transport,authoring_model
    from streamlit.testing.v1 import AppTest
    item=seed(env,ws);calls=[];generate=projection_generator(env,item,calls)
    host.config['model']={'kind':'genos'};host.path.write_text(json.dumps(host.config))
    monkeypatch.setattr(wiki_transport,'generate',lambda store,actor,prompt,context,schema:generate(prompt,context,schema))
    monkeypatch.setattr(authoring_model,'generate',lambda store,prompt,context,schema:generate(prompt,context,schema))
    monkeypatch.setitem(sys.modules,'console_test_host',SimpleNamespace(context=host.context))
    monkeypatch.setenv('GENOS_ONTOLOGY_HOST_FACTORY','console_test_host:context')
    app=AppTest.from_file(str(Path(os.environ['LOOP_TEST_CODE_ROOT'])/'03_FRONTEND/APPS/legal-knowledge-streamlit/ontology_app.py'),default_timeout=20).run()
    next(r for r in app.radio if r.label=='관리 작업').set_value('자유 작업공간').run()
    next(x for x in app.checkbox if x.label=='재사용 준비·승인·게시 열기').check().run()
    next(x for x in app.multiselect if x.label=='재사용할 문장').set_value([item.sid])
    next(x for x in app.text_input if x.label=='재사용 목적').set_value('합성 UI 검토')
    def click(label):
        next(x for x in app.button if x.label==label).click().run()
        assert not app.exception and not app.error,[x.value for x in app.error]
    click('선택 문장 컴파일')
    assert len(calls)==3
    next(x for x in app.text_input if x.label=='검토 의견').set_value('원문·조건 확인')
    next(x for x in app.checkbox if x.label=='원문·포함 범위·미확인 내용을 검토했습니다.').check().run()
    click('재사용 묶음 승인');click('소비 검증 후 게시 활성화')
    assert env.repo.lookup(env.source['anchor'],{'fictional'})
    app.run();assert not app.exception and not app.error and len(calls)==3
