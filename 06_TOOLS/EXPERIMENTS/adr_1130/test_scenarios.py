from copy import deepcopy
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_scenarios as sc
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from semantic_runtime.legal_agent import completion_contracts as cc

def fixture():
 text='대상 거래는 승인한다. 예외 거래는 별도 검토한다.'
 s={'id':'P1','anchor':{'document_id':'d','version':'v','unit_id':'0','label':'합성 제1조','content_sha256':sc.hashlib.sha256(text.encode()).hexdigest()},'text':text}
 part=lambda id,t,req=[]:{'id':id,'text':t,'requires':req,'basis':[{'source':'P1','quote':text}]}
 recipe={'version':sc.VERSION,'authority':sc.AUTHORITY,'bundle_id':'bundle','authoring':{'synthetic':True},'components':[part('A','대상 거래인 경우'),part('B','승인한다',['A']),part('X','예외 거래이면 별도 검토한다')],'paths':[{'id':'PATH1','title':'일반 승인','business_use':'일반 승인 업무','conditions':['A'],'calculations':[],'outcomes':['B'],'notes':['X']}],'unused_components':{}}
 fragments=[{'anchor':s['anchor'],'text':text,'evidence_refs':['S1']}]
 return recipe,[s],fragments

def compiled():
 r,s,f=fixture();p=sc.compile_package(r,s);return p,sc.bind_current(p,f)

def issues():return [{'id':'Q1','question':'승인 절차는?'}]
def choice(status='GENERAL_RULE',paths=['PATH1'],facts=[]):return {'choices':[{'issue_id':'Q1','path_ids':paths,'status':status,'reason':'해당 업무의 사전 경로','missing_facts':facts}]}

def test_precompile_then_bind_without_recompilation(monkeypatch):
 r,s,f=fixture();p=sc.compile_package(r,s)
 monkeypatch.setattr(sc,'compile_package',lambda *a,**k:(_ for _ in ()).throw(AssertionError('runtime compilation')))
 catalog=sc.bind_current(p,f);assert catalog['paths'][0]['body']==p['paths'][0]['body'];assert catalog['runtime_compilation'] is False
 f[0]['evidence_refs']=['CURRENT9'];assert sc.bind_current(p,f)['paths'][0]['source_refs']==['CURRENT9']

@pytest.mark.parametrize('mutation',['quote','cycle','unknown','unused','duplicate'])
def test_invalid_recipe_rejected(mutation):
 r,s,f=fixture()
 if mutation=='quote':r['components'][0]['basis'][0]['quote']='없는 인용'
 if mutation=='cycle':r['components'][0]['requires']=['B']
 if mutation=='unknown':r['paths'][0]['outcomes']=['MISSING']
 if mutation=='unused':r['paths'][0]['notes']=[]
 if mutation=='duplicate':r['components'].append(deepcopy(r['components'][0]))
 with pytest.raises(ContractError):sc.compile_package(r,s)

def test_explicit_unused_receipt():
 r,s,f=fixture();r['paths'][0]['notes']=[];r['unused_components']={'X':'별도 예외 경로는 다음 버전에 작성'}
 assert sc.compile_package(r,s)['unused_components']['X']

@pytest.mark.parametrize('mutation',['body','source','hash','authority'])
def test_package_tampering_rejected(mutation):
 p,c=compiled()
 if mutation=='body':p['paths'][0]['body']='다르게 승인한다'
 if mutation=='source':p['originals'][0]['text']='변경'
 if mutation=='hash':p['package_sha256']='0'*64
 if mutation=='authority':p['authority']='APPROVED'
 with pytest.raises(ContractError):sc.verify_package(p)

def test_missing_or_different_version_withholds_entire_path():
 r,s,f=fixture();p=sc.compile_package(r,s)
 assert not sc.bind_current(p,[])['paths']
 f[0]['anchor']={**f[0]['anchor'],'version':'changed'}
 c=sc.bind_current(p,f);assert not c['paths'] and c['withheld'][0]['missing_originals']==['P1']

def test_current_text_tampering_blocks():
 r,s,f=fixture();p=sc.compile_package(r,s);f[0]['text']='틀린 원문'
 with pytest.raises(ContractError):sc.bind_current(p,f)

@pytest.mark.parametrize('mutation',['unknown_path','empty_selected','nonempty_no_match','facts_on_general','conditional_without_facts','duplicate_issue','duplicate_path'])
def test_choice_contract(mutation):
 p,c=compiled();v=choice()
 if mutation=='unknown_path':v['choices'][0]['path_ids']=['UNKNOWN']
 if mutation=='empty_selected':v['choices'][0]['path_ids']=[]
 if mutation=='nonempty_no_match':v['choices'][0]['status']='NO_MATCH'
 if mutation=='facts_on_general':v['choices'][0]['missing_facts']=['거래 사실']
 if mutation=='conditional_without_facts':v['choices'][0]['status']='CONDITIONAL'
 if mutation=='duplicate_issue':v['choices']*=2
 if mutation=='duplicate_path':v['choices'][0]['path_ids']*=2
 with pytest.raises(ProposalError):sc.validate_choice(v,c,issues())

def options():return [{'id':'S1','source_id':'SRC1','document_id':'d','block_id':'0','start_cp':0,'end_cp':3,'text':'대상 거래는 승인한다. 예외 거래는 별도 검토한다.'}]

def test_selected_legal_body_is_immutable_through_composition():
 p,c=compiled();v=sc.materialize_choice(choice(),c,issues(),options());sc.verify_selected_text(v)
 ans=cc.compose(v,cc.default_plan(v,'text',issues()));cc.verify_composition(v,ans)
 assert p['paths'][0]['body'] in ans['text']
 v['claims'][0]['text']='승인 없이 처리한다'
 with pytest.raises(ContractError):sc.verify_selected_text(v)

def test_no_match_and_unknown_facts_remain_distinct():
 p,c=compiled();v=sc.materialize_choice(choice('NO_MATCH',[]),c,issues(),options())
 assert not v['claims'] and v['gaps'][0]['kind']=='MISSING_SCOPE'
 v=sc.materialize_choice(choice('CONDITIONAL',['PATH1'],['대상 거래 여부']),c,issues(),options())
 assert v['claims'] and v['gaps'][0]['kind']=='MISSING_FACT' and v['disposition']=='LIMITED_ANSWER'

def test_unknown_current_refs_block():
 p,c=compiled();c['paths'][0]['source_refs']=['FOREIGN']
 with pytest.raises(ContractError):sc.materialize_choice(choice(),c,issues(),options())
