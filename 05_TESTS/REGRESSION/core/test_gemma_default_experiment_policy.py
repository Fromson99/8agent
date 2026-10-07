import json
from pathlib import Path
import sys

import httpx


ROOT = next(p for p in Path(__file__).resolve().parents
            if (p/'00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT/'02_BACKEND'))
sys.path.insert(0, str(ROOT))

from lawrag.research.experiment_client import ExperimentClient, GemmaExperimentClient
from scripts.adr_structure import scaffold_adr, validate_adr


def test_new_adr_scaffold_uses_gemma(tmp_path):
    adr=scaffold_adr(tmp_path,538,'gemma-default-test','Gemma default test','audit',[])
    manifest=json.loads((adr/'실험/manifest.json').read_text())
    assert manifest['llm_policy']['required_model']=='google/gemma-4-31b-it'
    assert manifest['llm_policy']['llm_calls'][0]['model']=='google/gemma-4-31b-it'
    assert validate_adr(adr)==[]


def test_default_client_pins_gemma_parasail_fp8(tmp_path,monkeypatch):
    monkeypatch.setenv('OPEN_ROUTER','test-only-key')
    seen=[]
    def respond(request):
        payload=json.loads(request.content)
        seen.append(payload)
        return httpx.Response(200,json={'model':'google/gemma-4-31b-it','provider':'Parasail',
            'choices':[{'finish_reason':'stop','message':{'content':'{"selected":[]}'}}],
            'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}})
    client=ExperimentClient(ROOT,tmp_path/'calls',max_calls=1,transport=httpx.MockTransport(respond))
    assert isinstance(client,GemmaExperimentClient)
    schema={'type':'object','additionalProperties':False,'properties':{'selected':{
        'type':'array','items':{'type':'string'}}},'required':['selected']}
    assert client.generate('select',{'question':'정관 변경'},schema,phase='route')=={'selected':[]}
    assert seen[0]['model']=='google/gemma-4-31b-it'
    assert seen[0]['provider']=={'only':['parasail/fp8'],'order':['parasail/fp8'],
        'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True}
    assert seen[0]['reasoning']=={'enabled':False}
