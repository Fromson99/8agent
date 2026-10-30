import os,sys,json
from pathlib import Path
from test_workflow import setup,fixture

def test_existing_screen_review_and_publish(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from semantic_runtime.ontology_work import ui
    w,work,p,_=setup(tmp_path)
    w.generate=lambda *args:(p,{'id':'synthetic-model'})
    w.enqueue(work)
    monkeypatch.setattr(ui,'workflow',lambda **kw:w);monkeypatch.setattr(ui,'actor',lambda:'reviewer')
    monkeypatch.setenv('GENOS_RAG_ONTOLOGY_CONFIG','configured-test')
    root=Path(os.environ['QUALIFICATION_CODE_ROOT'])
    monkeypatch.setenv('GENOS_ONTOLOGY_CODE_ROOT',str(root))
    app=AppTest.from_file(str(root/'03_FRONTEND/APPS/legal-knowledge-streamlit/app.py'),default_timeout=15).run()
    assert not app.exception
    state=app.session_state['studio'];state['page']='온톨로지 관리';app.session_state['studio']=state;app.run()
    assert not app.exception
    def button(label):return next(x for x in app.button if x.label==label)
    button('저장된 판단으로 시나리오 생성').click().run();assert not app.exception
    assert any('일반 산정' in x.value for x in app.markdown)
    next(x for x in app.text_input if x.label=='검토 의견').set_value('두 경로와 원문을 확인함')
    next(x for x in app.checkbox if '조립된 경로' in x.label).check()
    button('승인').click().run();assert not app.exception
    assert w.repo.list()[0]['status']=='APPROVED'
    button('승인 판본을 DB에 게시').click().run();assert not app.exception
    assert w.repo.lookup(work['originals'][0]['anchor'],{'d'})
    state=app.session_state['studio'];state['page']='시뮬레이션';app.session_state['studio']=state;app.run()
    next(x for x in app.multiselect if '업무에 필요한' in x.label).set_value(['NORMAL','EXCEPTION']).run()
    assert not app.exception
    assert len(next(x for x in app.multiselect if '업무에 필요한' in x.label).value)==2
