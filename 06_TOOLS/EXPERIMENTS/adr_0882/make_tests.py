from pathlib import Path
p=Path(__file__).with_name('test_focus.py');old=Path(__file__).parents[1]/'adr_0881/test_focus.py';s=old.read_text();s=s[:s.index('def test_flat_conditions_restore')]+s[s.index('def retention_fixture'):]
s+='''
def condition(expression='ANY(1,2)'):
 return {'leaves':[{'text':'A','evidence_refs':['S1']},{'text':'B','evidence_refs':['S2']}],'expression':expression}

@pytest.mark.parametrize('mode',['ALL','ANY','UNKNOWN'])
def test_expression_preserves_connective_and_provenance(mode):
 raw=condition(f'{mode}(1,2)');before=deepcopy(raw);result=ce.restore_condition(raw)
 assert result=={'mode':mode,'children':[{'mode':'LEAF',**v} for v in raw['leaves']]}
 assert raw==before

def test_nested_expression_exact():
 raw=condition('ALL(1,ANY(1,2))');out=ce.restore_condition(raw)
 assert out['mode']=='ALL' and out['children'][1]['mode']=='ANY'
 assert out['children'][0]==out['children'][1]['children'][0]

@pytest.mark.parametrize('expression',['0','3','1','ANY(1,2)junk','OTHER(1,2)','ANY(1,2','ANY()','ANY(1,,2)','ANY(1,2))','ALL(ALL(ALL(ANY(1,2))))','ANY(1,1,1,1,1,1,1,1,2)'])
def test_invalid_or_incomplete_expression_rejected(expression):
 with pytest.raises(ProposalError):ce.restore_condition(condition(expression))

def assessment():
 options=[{'id':'S1','source_id':'source','text':'원문'},{'id':'S2','source_id':'source','text':'원문2'}]
 schema=v8.assessment_schema([{'id':'Q1'}],[],options,[{'id':'U0','text':'질문'}]);wire,expand=ce.assessment_projection(schema)
 claim={'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S1','S2'],'content_contract':v8.CONTENT,'explanation':'','rule':{'kind':'GENERAL_RULE','subject':'주체','action':'행위','scope':'범위','fact_refs':[],'condition_tree':condition(),'norms':[{'kind':'OBLIGATION','text':'원문 효과','evidence_refs':['S1'],'source_ref':'S1'}],'exceptions':[]}}
 return schema,wire,expand,{'claims':[claim],'issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],'gaps':[]}

def test_real_canonical_contract_and_rejected_wire_preserved():
 from jsonschema import validate
 schema,wire,expand,raw=assessment();value=expand(raw);validate(value,schema)
 assert value['claims'][0]['rule']['condition_tree']['mode']=='ANY'
 raw['claims'][0]['rule']['condition_tree']['expression']='ANY(0,2)'
 with pytest.raises(ProposalError) as e:expand(raw)
 assert e.value.proposal==raw and 'outside' in str(e.value)
 raw['claims'][0]['rule']['condition_tree']=None
 raw['claims'][0]['rule']['fact_refs']=[{'id':'U0','quote':'질문'}]
 with pytest.raises((ValidationError,ce.output.OutputContractError)):expand(raw)

def test_gap_kind_host_contract():
 schema,wire,expand,raw=assessment()
 gap={'issue_id':'Q1','kind':'MISSING_FACT','reason':'실제 신청일 미제공','material':True,'material_id':None,'missing_target':'','suggested_action':'REQUEST_FACT'}
 raw['gaps']=[gap];raw['issue_assessments'][0]['status']='INSUFFICIENT'
 assert expand(raw)['gaps']==[gap]
 raw['gaps'][0]['missing_target']='제3조'
 with pytest.raises((ValidationError,ce.output.OutputContractError)):expand(raw)
 raw['gaps'][0].update(kind='MISSING_SOURCE',missing_target='제3조')
 with pytest.raises((ValidationError,ce.output.OutputContractError)):expand(raw)
 raw['gaps'][0]['suggested_action']='RESEARCH';assert expand(raw)['gaps']==raw['gaps']

def test_request_quote_exact_full_input():
 from semantic_runtime.legal_agent import request_entry as re
 raw=re.schema(True);question='문답인가?\\n(업무 문맥: 조건)'
 bound,options=re.bind_task_quotes(raw,question)
 intent=next(x for x in bound['properties']['intent']['anyOf'] if x.get('type')=='object')
 assert intent['properties']['issues']['items']['properties']['request_quote']['enum']==[question]
 assert options==[{'start_cp':0,'end_cp':len(question),'text':question}]
'''
p.write_text(s)
