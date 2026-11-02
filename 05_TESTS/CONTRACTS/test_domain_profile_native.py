"""Existing native API, exact working engine pins, synthetic provider only."""
from copy import deepcopy
import ast
import inspect
import json
import os
from pathlib import Path
import sqlite3
import pytest
from conftest import term_glossary
from test_domain_profile_workflow import env, add_observation, proposal, save, approve_stage


@pytest.mark.parametrize('mode', ['active', 'off', 'empty'])
def test_native_assembly_delivery_claim_answer_and_duplicate(env, tmp_path, term_glossary, monkeypatch, mode):
    root=Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'06_TOOLS/EXPERIMENTS/adr_1188'))
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT',os.environ.get('WORKFLOW_TEST_CODE_ROOT',str(root)))
    monkeypatch.setenv('GENOS_AUTO_WARMUP','0');monkeypatch.setenv('AD_WORKER_ENABLED','0')
    from semantic_runtime import app as app_module
    from semantic_runtime.ontology_work import runtime
    from semantic_runtime.legal_agent import ontology_context
    from semantic_runtime.legal_agent.ontology_compiler import content_hash
    real_create=app_module.create_app; delivered=[]; packages=[]

    def create(*args, **kwargs):
        # The native fixture has finished building its synthetic corpus here.
        with sqlite3.connect(tmp_path/'raw.sqlite') as db:
            version=db.execute("SELECT source_artifact_sha256 FROM document WHERE document_id='d'").fetchone()[0]
            text=db.execute("SELECT text FROM source_block WHERE document_id='d' AND unit_id='1'").fetchone()[0]
        env.source.update(id='S1',anchor={'document_id':'d','version':version,'unit_id':'1',
                           'content_sha256':content_hash(text),'label':'가상 규정 제2조'},text=text)
        env.w.document_ids=frozenset(['d'])
        env.w.source_reader=lambda a: text if a==env.source['anchor'] else None
        wrong='이 확인 업무는 서면 승인 없이 시행한다.'
        a=add_observation(env,payload=wrong);first=proposal(env,a)
        first['graph']['nodes'][0]['text']=wrong;first['graph']['nodes'][0]['slots']['statement']['value']=wrong
        save(env,a,first)
        statement='이 확인 업무는 서면 승인 후 시행한다.'
        b=add_observation(env,'B',payload='앞선 무승인 의견을 철회한다. '+statement)
        p=proposal(env,b,relation='CONTRADICTION')
        p['graph']['nodes'][0]['text']=statement;p['graph']['nodes'][0]['slots']['statement']['value']=statement
        d=save(env,b,p,rev=1)
        assert d['revision']==2 and len(env.w.load(d['bundle_id'])['comparison_history'])==2
        stage=approve_stage(env,d);receipt=env.w.verify_publication(stage['publication_id'])
        if mode!='empty':env.w.activate_publication(stage['publication_id'],0,receipt)
        packages.append(env.repo.publication(stage['publication_id'],{'d'})['context']['assembly_package'])
        from semantic_runtime.ontology_work import assembly_compiler
        def no_runtime_compile(*a,**k):raise AssertionError('runtime recompiled a publication')
        monkeypatch.setattr(assembly_compiler,'compile_package',no_runtime_compile)
        policy=kwargs['legal_agent_profile']['candidate_navigation']
        policy.update(ontology_enabled=mode!='off',ontology_direct_assessment=True,ontology_context={'mode':'DB'})
        transport=kwargs['legal_agent_transport'];original_send=transport.send_once
        def send_once(*,body,ticket):
            from api_fixture_integrated import decode
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            response=original_send(body=body,ticket=ticket)
            if view.get('source_stage','').startswith('memory-assess'):
                catalogs=[c['payload']['assembly_catalog'] for c in view.get('ontology_bundles',[])
                          if c.get('payload',{}).get('assembly_catalog')]
                if mode=='active':
                    assert len(catalogs)==1 and catalogs[0]['paths'][0]['body']==statement
                    assert catalogs[0]['paths'][0]['source_refs']
                    # Explicit synthetic-model use of the delivered approved text;
                    # the existing requirement/read-review proposal remains intact.
                    raw=response['body_json']['choices'][0]['message']['content']
                    out=json.loads(raw) if isinstance(raw,str) else raw
                    assert out['claims'][0]['rule']['norms'][0]['text']==catalogs[0]['paths'][0]['body']
                    delivered.append(deepcopy(catalogs[0]))
                else:assert not catalogs
            return response
        transport.send_once=send_once
        return real_create(*args,**kwargs)
    monkeypatch.setattr(app_module,'create_app',create)
    monkeypatch.setattr(runtime,'repository',lambda: env.repo)
    import need_continuity_fixture as fixture
    original_change=fixture.change_review
    def change_review(head):
        # Ontology arrival can hand off an unreviewed DEFER row (version zero).
        # The old native fixture assumes every row already has change_from.
        value=deepcopy(head)
        if not value.get('change_from'):value['change_from']={'version':0,'finding':''}
        value['review_purposes']=value.get('review_purposes') or []
        return original_change(value)
    monkeypatch.setattr(fixture,'change_review',change_review)
    tree=ast.parse(inspect.getsource(fixture.run_api));fn=tree.body[0];fn.name='setup'
    end=next(i for i,node in enumerate(fn.body) if isinstance(node,ast.With)
             and any(isinstance(item.context_expr,ast.Call) and isinstance(item.context_expr.func,ast.Name)
                     and item.context_expr.func.id=='TestClient' for item in node.items))
    fn.body=fn.body[:end]+ast.parse('return app, transport, question').body
    namespace=dict(vars(fixture));exec(compile(ast.fix_missing_locations(tree),fixture.__file__,'exec'),namespace)
    app,transport,question=namespace['setup'](tmp_path,term_glossary,'goal_control',monkeypatch)
    from fastapi.testclient import TestClient
    try:
        with TestClient(app) as api:
            request={'question':question,'session_id':'domain-profile','request_id':'profile-c'}
            response=api.post('/v1/rag/ask',json=request)
            assert response.status_code==200,response.text
            result=response.json();calls=list(transport.calls)
            again=api.post('/v1/rag/ask',json=request)
            assert again.status_code==200 and again.json()['answer']==result['answer']
            assert transport.calls==calls
        from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
        from semantic_runtime.legal_agent.unified_publication import validate_saved
        journal=next(tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        repo=UnifiedRepository(journal)
        try:
            validate_saved(repo,result)
            reviews=[json.loads(r[0]) for r in repo.db.execute("SELECT payload_json FROM event WHERE kind='REQUIREMENT_COVERAGE_REVIEWED'")]
        finally:repo.close()
    finally:app.state.pipeline.store.close()
    if mode=='active':
        assert len(delivered)==1
        assert packages[0]['paths'][0]['body'] in result['answer']['text']
        assert delivered[0]['package_sha256']==packages[0]['package_sha256']
    else:assert not delivered
    assert reviews and not any('compose' in phase for phase in calls)
