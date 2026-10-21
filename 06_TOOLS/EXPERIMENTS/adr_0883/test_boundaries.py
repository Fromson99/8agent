from copy import deepcopy
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent import completion_execution as ce, completion_v8 as v8, request_entry as entry
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.errors import ProposalError

def schema():return v8.assessment_schema([{'id':'Q1'}],[],[{'id':'S1','source_id':'s','text':'원문'}],[{'id':'U0','text':'실제 사실'}])

@pytest.mark.parametrize('kind',['MISSING_FACT','MISSING_SOURCE','MISSING_SCOPE','UNREAD_SAVED','UNRESOLVED_REFERENCE'])
def test_provider_minimal_gap_roundtrip_keeps_kind_and_missing_text(kind):
 canonical=schema();wire,restore=ce.assessment_projection(canonical);project=Projection(wire)
 gap={'kind':kind,'issue_id':'Q1','reason':'시험: 판정에 필요한 미확인 정보','material':True,'material_id':None,'missing_target':'' if kind=='MISSING_FACT' else '제9조','suggested_action':'REQUEST_FACT' if kind=='MISSING_FACT' else 'RESEARCH'}
 value={'claims':[],'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT'}],'gaps':[gap]}
 raw=project.project(value);before=deepcopy(raw);got=restore(project.expand(raw));validate(got,canonical)
 assert got['gaps']==[gap] and raw==before
 assert 'disposition' not in raw and 'reason' not in raw['issue_assessments'][0]
 if kind=='MISSING_FACT':assert 'material_id' not in raw['gaps'][0] and 'suggested_action' not in raw['gaps'][0]

@pytest.mark.parametrize('text',['질문 한 문장','두 줄\n문맥: 제2조','조합문자 e\u0301 / 😀\r\n질문'])
def test_whole_question_provenance_survives_wire_without_model_copy(text):
 bound,anchors=entry.bind_task_quotes(entry.schema(True),text)
 intent=next(x for x in bound['properties']['intent']['anyOf'] if x.get('type')=='object')
 quote=intent['properties']['issues']['items']['properties']['request_quote'];p=Projection({'type':'object','properties':{'request_quote':quote},'required':['request_quote'],'additionalProperties':False})
 assert p.project({'request_quote':text})=={} and p.expand({})=={'request_quote':text}
 assert anchors[0]['end_cp']==len(text)
 with pytest.raises(ProposalError):p.expand({'request_quote':text+' 변조'})

@pytest.mark.parametrize('op',['ALL','ANY','UNKNOWN'])
@pytest.mark.parametrize('width',[1,8])
def test_max_depth_fanout_preserves_every_leaf_and_operator(op,width):
 leaves=[{'text':f'요건{i} 1.50%','evidence_refs':['S1']} for i in range(width)]
 expression=f'{op}({op}({op}('+','.join(str(i+1) for i in range(width))+')))'
 out=ce.restore_condition({'leaves':leaves,'expression':expression})
 for _ in range(2):assert out['mode']==op;out=out['children'][0]
 assert out['mode']==op and out['children']==[{'mode':'LEAF',**v} for v in leaves]

@pytest.mark.parametrize('suffix',[';ALL(1)','/**/','\x00',' 2','[1]'])
def test_operator_parser_cannot_drop_unrecognized_suffix(suffix):
 with pytest.raises(ProposalError):ce.restore_condition({'leaves':[{'text':'조건','evidence_refs':['S1']}],'expression':'1'+suffix})
