"""Run the exact frozen editor artifact, never a repository-path substitute."""
from pathlib import Path
import asyncio,importlib.util,os
import pytest
import test_ad_language as legacy
from test_ad_language import records
ROOT=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])

def test_pinned_editor_existing_ad_without_legal_bootstrap(records,monkeypatch):
    monkeypatch.setattr(legacy,'ROOT',ROOT)
    legacy.test_gateway_workflow_calls_internal_interpreter_without_legal_bootstrap(records,monkeypatch)

@pytest.mark.parametrize('operation',['BASIS_LINKS_LIST','BASIS_LINKS_PROPOSE','BASIS_LINKS_REVIEW','BASIS_LINKS_HISTORY','BASIS_MIGRATION_STATUS','WORKFLOW_RUN','WORKFLOW_STATUS','WORKFLOW_RESUME'])
@pytest.mark.parametrize('status',['completed','failed'])
def test_pinned_control_operation(operation,status,monkeypatch):
    spec=importlib.util.spec_from_file_location('pinned_basis_editor',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    sent=[];body={'status':status,'answer':{'text':'완료' if status=='completed' else '실패'}}
    def send(value):sent.append(value);return {'status':200 if status=='completed' else 503,'body':body}
    monkeypatch.setattr(w,'_post_code_serving',send)
    request={'API_TYPE':operation,'request_id':'same','session_id':'s','json':{'view_id':'review-view','rows':[1]},'run_id':'run'}
    out=asyncio.run(w.run(request));assert out['basis_result']==body and out['answer_status']==status
    assert len(sent)==1 and sent[0]['API_TYPE']==operation and sent[0]['json']==request['json'] and sent[0]['request_id']=='same'

def test_pinned_implicit_discovery(monkeypatch):
    spec=importlib.util.spec_from_file_location('pinned_discovery_editor',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    sent=[]
    def send(value):sent.append(value);return {'status':200,'body':{'status':'partial','answer':{'text':'조사 일부 완료'}}}
    monkeypatch.setattr(w,'_post_code_serving',send)
    out=asyncio.run(w.run({'workflow_id':'internal_basis_discovery_workflow','input':{'internal_document_id':'inside'},'session_id':'s','request_id':'one'}))
    assert sent[0]['API_TYPE']=='WORKFLOW_RUN' and sent[0]['input']['internal_document_id']=='inside'
    assert out['answer_status']=='partial' and out['text']=='조사 일부 완료'
