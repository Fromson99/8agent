from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent.request_entry import schema,bind_task_quotes
from semantic_runtime.legal_agent.completion_v5 import verify_intent
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.workflow_rag import execute

@pytest.mark.parametrize('q',['외규: 유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?',
    '첫 문장\n둘째 문장\t별도 조건', '가'*2000,'가'*2001,'가'*6000,'😀한\r\n'*800])
def test_literal_quotes_preserve_every_original_character_and_schema(q):
    original=schema(True);before=deepcopy(original)
    bound,anchors=bind_task_quotes(original,q)
    assert original==before
    field=bound['properties']['intent']['anyOf'][0]['properties']['issues']['items']['properties']['request_quote']
    assert ''.join(a['text'] for a in anchors)==q
    for a in anchors:
        assert a['text']==q[a['start_cp']:a['end_cp']]
        assert 1<=len(a['text'])<=2000
        validate(a['text'],field)
        verify_intent({'issues':[{'request_quote':a['text']}],'background_quotes':[]},q)
    assert len(field['enum'])==len(set(field['enum']))
    with pytest.raises(ValidationError):validate(anchors[0]['text']+' (workflow_task: 외규 조사)',field)

@pytest.mark.parametrize('task',[[],['source_category','search_hints'],'internal',1,
    {'source_category':'external','search_hints':[]},
    {'source_category':'internal','search_hints':'hint'},
    {'source_category':'internal','search_hints':['hint']*5},
    {'source_category':'internal','search_hints':[],'extra':True}])
def test_invalid_host_task_refused_before_child_execution(task):
    port=SimpleNamespace(services=None,session=None,all_scope=[],categories={})
    with pytest.raises(ContractError,match='invalid trusted workflow task'):
        execute(port,{'operation':'ask_rag','side':'internal','args':{'question':'원래 질문','previous':None,'task':task}},'call')

def test_normal_entry_schema_remains_freeform_with_original_verifier():
    field=schema(True)['properties']['intent']['anyOf'][0]['properties']['issues']['items']['properties']['request_quote']
    assert 'enum' not in field
    with pytest.raises(Exception,match='request quote outside'):
        verify_intent({'issues':[{'request_quote':'추가된 조사 지시'}],'background_quotes':[]},'원래 질문')
