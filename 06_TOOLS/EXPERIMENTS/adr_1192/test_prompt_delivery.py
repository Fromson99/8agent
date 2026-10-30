"""Prompt delivery and contract preservation; synthetic outputs are not quality evidence."""
import ast,json,gzip,os
from pathlib import Path
from copy import deepcopy
import pytest
from conftest import term_glossary
from common import ROOT,DES,ART,read,sha,put,bind

CHANGED={'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py':'MODERN_ASSESS_PROMPT',
         '02_BACKEND/semantic_runtime/legal_agent/completion_v8.py':'PROMPT'}

def constant(path,name):
    tree=ast.parse(path.read_text())
    return ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)))

def without_prompt(path,name):
    tree=ast.parse(path.read_text())
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets):n.value=ast.Constant('PROMPT')
    return ast.dump(tree,include_attributes=False)

def test_only_two_prompt_constants_and_consumer_pins_change():
    code=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])
    base=read(DES/'baseline.json');selected=ROOT/base['manifest']['code_root']
    pins={v['manifest'] for v in read(code/'00_SYSTEM/PIPELINE.json')['engines'].values()}|{'00_SYSTEM/PIPELINE.json'}
    for name,h in base['manifest']['files'].items():
        if name in CHANGED:
            assert without_prompt(code/name,CHANGED[name])==without_prompt(selected/name,CHANGED[name])
            assert constant(code/name,CHANGED[name])!=constant(selected/name,CHANGED[name])
        elif name not in pins:assert sha(code/name)==h,name
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
    assert all((sha(ROOT/n) if (ROOT/n).is_file() else None)==h for n,h in base['working_files'].items())

@pytest.mark.parametrize('number',[11,12])
def test_stored_actual_request_reconstruction_preserves_evidence_schema_routing(number):
    code=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])
    base=ROOT/read(DES/'baseline.json')['manifest']['code_root']
    path=ROOT/f'04_EXPERIMENTS/ADR/ADR-1191-main115-parasail-cm007/artifacts/live/cm-007/raw/call-{number:03}/request.json.gz'
    original=json.loads(gzip.decompress(path.read_bytes()));new=deepcopy(original)
    for file,name in CHANGED.items():
        before=constant(base/file,name);after=constant(code/file,name)
        assert new['messages'][0]['content'].count(before)==1
        new['messages'][0]['content']=new['messages'][0]['content'].replace(before,after,1)
    old_prompt=original['messages'][0]['content'];new_prompt=new['messages'][0]['content']
    old_rest=deepcopy(original);new_rest=deepcopy(new)
    old_rest['messages'][0]['content']=new_rest['messages'][0]['content']=''
    assert old_rest==new_rest
    for marker in ('cm-007','CM007','제13조','국내에서 모집','50억원','S40'):
        assert marker not in new_prompt
    assert '국내에서 모집·매출한' in new['messages'][1]['content']
    assert '원문 대조를 다시 적용한다' in new_prompt
    put(ART/f'input-integrity-{number:03}.json',{'original_request':bind(path),
        'mode':'reconstructed_system_only_not_sent','user_schema_model_provider_identical':True,
        'before_system_chars':len(old_prompt),'after_system_chars':len(new_prompt),
        'external_model_calls':0,'model_response_replayed':False})

@pytest.mark.parametrize('mode,fault',[('supported',None),('limited_source',None),('limited_fact',None),('limited_source','first'),('limited_source','twice')])
def test_native_api_delivers_check_to_first_and_repair_without_extra_stage(tmp_path,term_glossary,monkeypatch,mode,fault):
    from native_fixture import run_api
    from semantic_runtime.legal_agent.gateway import ModelGateway
    from semantic_runtime.legal_agent import completion_execution as ce,completion_v8 as v8
    captured=[];old=ModelGateway.__init__
    def capture(self,*args,**kwargs):
        old(self,*args,**kwargs)
        transport=self.transport
        if getattr(transport,'_prompt_capture',False):return
        send=transport.send_once
        def wrapped(*,body,ticket):
            system=body['messages'][0]['content']
            if ce.MODERN_ASSESS_PROMPT in system:captured.append(deepcopy(body))
            return send(body=body,ticket=ticket)
        monkeypatch.setattr(transport,'send_once',wrapped)
        transport._prompt_capture=True
    monkeypatch.setattr(ModelGateway,'__init__',capture)
    result=run_api(tmp_path,term_glossary,mode,monkeypatch,fault)
    assert len(captured)==(2 if fault else 1)
    for body in captured:
        prompt=body['messages'][0]['content']
        assert prompt.count(ce.MODERN_ASSESS_PROMPT)==1
        assert prompt.count(v8.PROMPT)==1
        assert '원문검토검증규정' not in prompt
        view=json.loads(body['messages'][1]['content'])['view']
        assert '이 확인 업무는 서면 승인 후 시행한다.' in json.dumps(view,ensure_ascii=False)
        assert 'self_review' not in body['response_format']['json_schema']['schema'].get('properties',{})
    if fault:
        one=json.loads(captured[0]['messages'][1]['content'])['view']
        two=json.loads(captured[1]['messages'][1]['content'])['view']
        assert one['evidence_options']==two['evidence_options']
        assert one.get('documents')==two.get('documents')
        assert two['repair_feedback']
    if result:
        response,calls,reviews=result
        assert not any('scope-review' in p or 'self-review' in p for p in calls)
        assert len(reviews)==1
