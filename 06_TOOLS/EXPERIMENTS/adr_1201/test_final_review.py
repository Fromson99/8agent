from copy import deepcopy
from types import SimpleNamespace
import json,sqlite3
import pytest
from semantic_runtime.legal_agent import final_original_review as r
from semantic_runtime.legal_agent.errors import ProposalError,ContractError,TransportError,StaleProposal
from semantic_runtime.contracts import digest

def data():return {'question':'신고 기한과 예외는?','sources':[{'source_id':'s1','document_id':'d','text':'대상자는 10일 내 신고한다. 재난 시 20일이다.'}], 'draft':{'text':'대상자는 10일 내 신고한다.','claims':[{'claim_id':'C1','text':'대상자는 10일 내 신고한다.'}]},'scope':'selected'}
def valid():return {'source_reviews':[{'source_id':'s1','status':'ISSUES_FOUND','reason':'예외 누락'}],'claim_reviews':[{'claim_id':'C1','status':'ISSUES_FOUND','reason':'기한 예외 누락'}],'findings':[{'kind':'OMISSION','source_id':'s1','source_quote':'재난 시 20일이다.','claim_refs':['C1'],'answer_quote':'','reason':'재난 예외 기한이 빠짐'}]}

def test_grounded_missing_content():assert r.validate(valid(),data())=='ISSUES_FOUND'
@pytest.mark.parametrize('mode',['source_quote','answer_quote','foreign_id','duplicate','missing_source','status','claim_status','missing_finding','blank','foreign_claim'])
def test_invalid_review(mode):
 v=valid()
 if mode=='source_quote':v['findings'][0]['source_quote']='일치하지 않는 문구'
 if mode=='answer_quote':v['findings'][0]['answer_quote']='미전달 답변'
 if mode=='foreign_id':v['findings'][0]['source_id']='hidden'
 if mode=='duplicate':v['findings'].append(deepcopy(v['findings'][0]))
 if mode=='missing_source':v['source_reviews']=[]
 if mode=='status':v['source_reviews'][0]['status']='COVERED'
 if mode=='claim_status':v['claim_reviews'][0]['status']='CONSISTENT'
 if mode=='missing_finding':v['findings']=[]
 if mode=='blank':v['findings'][0]['reason']=' '
 if mode=='foreign_claim':v['findings'][0]['claim_refs']=['C9']
 with pytest.raises(ProposalError):r.validate(v,data())
@pytest.mark.parametrize('status',['COVERED','NOT_REQUIRED','UNCERTAIN'])
def test_no_findings_status(status):
 v=valid();v['findings']=[];v['source_reviews'][0]['status']=status;v['claim_reviews'][0]['status']='CONSISTENT'
 assert r.validate(v,data())==('UNCERTAIN' if status=='UNCERTAIN' else 'NO_ISSUES_FOUND')
@pytest.mark.parametrize('change',['answer','source','receipt','incomplete_pass'])
def test_receipt_tamper(change):
 d=data();v=r.receipt(d,'ISSUES_FOUND',valid());r.verify(v,d)
 if change=='answer':d['draft']['text']='changed'
 if change=='source':d['sources'][0]['text']='changed'
 if change=='receipt':v['status']='NO_ISSUES_FOUND'
 if change=='incomplete_pass':v=r.receipt(d,'NO_ISSUES_FOUND',reason='timeout')
 with pytest.raises(ContractError):r.verify(v,d)

class Repo:
 def __init__(self):
  self.db=sqlite3.connect(':memory:');self.db.execute('CREATE TABLE event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash)');self.limit=2
 def event(self,k,v):self.db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',(k,json.dumps(v),digest(v)))
 def budget(self):return {'model_limit':self.limit,'model_reserved':0}
@pytest.mark.parametrize('mode',['normal','invalid','unknown','budget','interrupted','stale'])
def test_durable_single_review(monkeypatch,mode):
 repo=Repo();calls=[];monkeypatch.setattr(r,'input_data',lambda *args:data())
 if mode=='budget':repo.limit=0
 if mode=='interrupted':repo.event('FINAL_ORIGINAL_REVIEW_STARTED',{'input_hash':digest(data())})
 def invoke(*args):
  calls.append(args)
  if mode=='invalid':raise ProposalError('bad ID')
  if mode=='unknown':raise TransportError('timeout',unknown=True)
  if mode=='stale':raise StaleProposal('late')
  return valid()
 e=SimpleNamespace(s=SimpleNamespace(work=repo),invoke=invoke)
 if mode=='stale':
  with pytest.raises(StaleProposal):r.run(e,'q',{}, {'text':'x'},[])
  assert len(calls)==1;return
 one=r.run(e,'q',{}, {'text':'x'},[]);two=r.run(e,'q',{}, {'text':'x'},[])
 assert one==two and len(calls)==(0 if mode in ('budget','interrupted') else 1)
 assert one['status']==('ISSUES_FOUND' if mode=='normal' else 'INCOMPLETE')
