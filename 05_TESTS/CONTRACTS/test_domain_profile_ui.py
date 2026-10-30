"""Real Streamlit server-side widget reruns against the persistent synthetic store."""
from pathlib import Path
import sys
import pytest
from test_domain_profile_workflow import env, add_observation, proposal, save, Glossary


def test_streamlit_review_stage_verify_activate_and_reload(env, monkeypatch):
    runtime=Path(__file__).resolve().parents[2]/'90_RUNTIME/streamlit-knowledge-design/python'
    if runtime.exists():monkeypatch.syspath_prepend(str(runtime))
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    from semantic_runtime.ontology_work import ui, domain_ui
    from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
    from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
    observation=add_observation(env); d=save(env,observation,proposal(env,observation))
    def factory(*,actor):
        return DomainWorkflow(env.repo,env.w.store,actor=actor,source_reader=env.w.source_reader,
            generate=None,namespace=env.w.namespace,source_snapshot=env.w.source_snapshot,
            acl_ref=env.w.acl_ref,document_ids=env.w.document_ids,
            glossary=GlossaryBinding(Glossary(),snapshot=env.w.source_snapshot),producer_binding=env.w.producer_binding)
    monkeypatch.setattr(ui,'actor',lambda:'reviewer');monkeypatch.setattr(domain_ui,'actor',lambda:'reviewer')
    monkeypatch.setattr(ui,'workflow',factory);monkeypatch.setattr(domain_ui,'domain_workflow',factory)
    app=AppTest.from_string('from semantic_runtime.ontology_work.ui import render\nrender()').run()
    app.radio[0].set_value('도메인 프로필·판단 축적').run()
    assert not app.exception and not app.error
    assert any('가상 주체는 물건을 제출한다.' in t.value for t in app.text)
    next(x for x in app.text_input if x.label.startswith('문장·범위')).set_value('원문과 조건·예외 확인')
    app.checkbox[0].check().run()
    def click(label):
        next(b for b in app.button if b.label==label).click().run()
        assert not app.exception and not app.error
    click('내용 승인')
    assert env.w.load(d['bundle_id'])['status']=='APPROVED'
    click('승인 판본 게시 준비')
    assert env.repo.head(d['bundle_id'])['publication_id'] is None
    click('저장·현재 원문·소비 경로 확인')
    click('확인한 게시본 사용 전환')
    active=env.repo.head(d['bundle_id'])
    assert active['publication_id'] and active['sequence']==1
    app.run()
    assert not app.exception and not app.error
    assert env.repo.head(d['bundle_id'])==active
    assert env.repo.lookup(env.source['anchor'],{'fictional'})[0]['context']['assembly_package']['bundle_id']==d['bundle_id']
