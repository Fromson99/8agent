from copy import deepcopy
from contextlib import contextmanager
from types import SimpleNamespace as NS
import json,sqlite3
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import stable_references as sr,compact_model_input as cm,read_judgment as rj,output_contract as oc,independent_read_recovery as recovery
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,expand_cards
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from test_read_judgment import setup,commit,proposal
from test_output_contract_local import Journal

class RefRepo(Journal):
 def __init__(self,path):
  super().__init__(path);self.db.execute('CREATE TABLE IF NOT EXISTS navigation_handle(handle PRIMARY KEY,kind,identity_json,binding_hash)');self.db.commit()
 def run(self):return {'binding_hash':digest(self.binding)}

def j(n):return 'J'+format(n,'024x')
def e(n):return 'E'+format(n,'024x')
def view(n=5,name='가규정',did='d1'):
 return cm.bind({'source_stage':'source-read-choice','input_projection':'compact-selection-source-v3','sources':[{'id':e(n),'document_id':did,'document_name':name,'text':' 제1조\nJ1을 포함한 원문 '}],
  'read_judgments':{'current_originals':[{'id':j(n),'document_id':did,'document_name':name,'source_refs':[e(n)]}]},'read_candidates':[{'target':'T'+format(n,'024x'),'document_id':did,'document_name':name}]},{},stable=True)

def bound(repo,v):
 with repo.transaction():return sr.bind(repo,v)

@pytest.mark.parametrize('restart',[False,True])
def test_aliases_do_not_shift_when_earlier_id_new_document_or_old_page_arrives(tmp_path,restart):
 path=tmp_path/'refs';repo=RefRepo(path);first=bound(repo,view());old=deepcopy(first['reference_registry']);a=NavigationReferences(first)
 if restart:repo.db.close();repo=RefRepo(path)
 second=bound(repo,view(1,'나규정','d2'));third=bound(repo,view());b=NavigationReferences(third)
 assert a.forward==b.forward and a.forward[j(5)]!=NavigationReferences(second).forward[j(1)]
 assert third['reference_registry']['documents'][0]==old['documents'][0]
 assert cm.project(compact_wire_view(b.view(third),'investigate'))['sources'][0]['text']==' 제1조\nJ1을 포함한 원문 '
 assert cm.project(compact_wire_view(b.view(third),'investigate'))['sources'][0]['document']=='D1'
 sr.verify(repo,first['reference_registry']);sr.verify(repo,third['reference_registry'])

@pytest.mark.parametrize('tamper',['hash','binding','collision','journal','name'])
def test_registry_tampering_rejected(tmp_path,tamper):
 repo=RefRepo(tmp_path/'refs');v=bound(repo,view());registry=deepcopy(v['reference_registry'])
 if tamper=='hash':registry['hash']='bad'
 elif tamper=='binding':repo.binding['generation']='changed'
 elif tamper=='collision':registry['documents'][0]['id']=next(iter(registry['mapping'].values()));registry['hash']=digest({k:v for k,v in registry.items() if k!='hash'})
 elif tamper=='journal':repo.db.execute("UPDATE navigation_handle SET identity_json='\"changed\"' WHERE kind='model-reference-v2'")
 elif tamper=='name':
  with pytest.raises(ContractError):bound(repo,view(name='변경'))
  return
 with pytest.raises(ContractError):sr.verify(repo,registry)


def test_registry_and_view_save_are_one_transaction(tmp_path):
 repo=RefRepo(tmp_path/'refs')
 with pytest.raises(RuntimeError):
  with repo.transaction():sr.bind(repo,view());raise RuntimeError('before view save')
 assert not repo.db.execute('SELECT * FROM navigation_handle').fetchall()


def test_same_name_different_documents_and_executable_handles_do_not_collide(tmp_path):
 repo=RefRepo(tmp_path/'refs');repo.db.execute('INSERT INTO navigation_handle VALUES(?,?,?,?)',('D1','D','{}','other'));repo.db.commit()
 one=bound(repo,view());two=bound(repo,view(6,'가규정','d2'));r=cm.project(NavigationReferences(two).view(two))
 assert len(r['documents'])==2 and r['sources'][0]['document']=='D2'
 assert repo.db.execute("SELECT kind FROM navigation_handle WHERE handle='D1'").fetchone()[0]=='D'


def test_keyed_judgment_schema_and_json_pointer_use_stable_alias(tmp_path):
 repo=RefRepo(tmp_path/'refs');v=bound(repo,view());refs=NavigationReferences(v);ident=j(5);alias=refs.forward[ident]
 schema={'type':'object','properties':{'new_reviews':{'type':'object','properties':{ident:{'type':'object','properties':{},'additionalProperties':False}},'additionalProperties':False}},'required':['new_reviews']}
 wire=refs.schema(schema);raw={'new_reviews':{alias:{}}};decoded=refs.decode(raw,wire)
 assert decoded=={'new_reviews':{ident:{}}}
 assert refs.view({'path':'/read_review/new_reviews/'+ident+'/basis_refs','contract_error':ident+'의 원문 오류'})['path']=='/read_review/new_reviews/'+alias+'/basis_refs'
 assert refs.view({'finding':'J1 판단 유지'})['finding']=='J1 판단 유지'


def new_setup():
 inv,data,page,events,saved=setup();inv.policy['new_read_reviews']=True
 return inv,data,page,events,saved

def fresh(ctx,refs=None):
 row=ctx['current_originals'][0]
 return {'choice':'FINISH','read_review':{'new_reviews':{row['id']:{'use':'SUPPORT','finding':'조건 확인','reason':'실제 원문의 조건','basis_refs':refs or row['source_refs']}}}}

def validate_new(raw,ctx,data):
 validate(raw['read_review'],rj.wire_review_schema(ctx,{s['id']:s for s in data['sources']},['Q1']))
 value,changes=rj.normalize_review(raw,ctx);rj.validate_review(value,ctx,{s['id']:s for s in data['sources']},['Q1']);return value,changes


def test_new_only_defaults_host_fields_and_retains_pending_original(tmp_path):
 inv,data,page,events,saved=new_setup();data['sources'].append(page('b'));ctx=rj.context(inv,data,'a');raw=fresh(ctx);before=deepcopy(raw)
 value,changes=validate_new(raw,ctx,data);rj.record(inv,data,value,'a',ctx,{},wire_value=raw,normalizations=changes)
 state=rj.state_for(inv,data);assert len(state['heads'])==1 and len(state['pending'])==1 and raw==before
 head=next(iter(state['heads'].values()));assert head['finding']=='조건 확인' and head['issue_refs']==['Q1']
 assert all('finding' not in x for x in state['pending'].values())
 old=deepcopy(head);ctx2=rj.context(inv,data,'b');empty={'choice':'FINISH','read_review':{'new_reviews':{}}};v,ch=validate_new(empty,ctx2,data);rj.record(inv,data,v,'b',ctx2,{})
 assert rj.state_for(inv,data)['heads'][head['id']]==old


def test_existing_judgment_cannot_enter_new_reviews():
 inv,data,*_=new_setup();ctx=rj.context(inv,data,'a');raw=fresh(ctx);v,ch=validate_new(raw,ctx,data);rj.record(inv,data,v,'a',ctx,{})
 ctx2=rj.context(inv,data,'b')
 with pytest.raises(ValidationError):validate_new(raw,ctx2,data)
 jid=next(iter(raw['read_review']['new_reviews']));change={'choice':'FINISH','read_review':{'new_reviews':{},'revisions':{jid:{'operation':'SET','use':'CORE','finding':'명시적 변경','reason':'추가 대조','basis_refs':['Ba']}}}}
 v,ch=validate_new(change,ctx2,data);rj.record(inv,data,v,'b',ctx2,{})
 assert rj.state_for(inv,data)['heads'][jid]['finding']=='명시적 변경'
 assert rj.state_for(inv,data)['heads'][jid]['version']==2


def test_wrong_original_names_key_and_expected_source_and_does_not_commit():
 inv,data,page,events,saved=new_setup();data['sources'].append(page('b'));ctx=rj.context(inv,data,'a');raw=fresh(ctx,['Bb']);value,_=rj.normalize_review(raw,ctx)
 with pytest.raises(oc.OutputContractError) as caught:rj.record(inv,data,value,'a',ctx,{})
 issue=caught.value.issues[0];assert issue['path'].endswith(ctx['new_review_ids'][0]+'/basis_refs')
 assert issue['expected_constraint']['allowed_source_refs']==['Ba'] and not inv.p.get('read_judgments')


def test_duplicate_rows_six_seven_and_missing_j6_are_precise():
 inv,data,page,*_=setup();data['sources']=[page(str(i)) for i in range(7)];ctx=rj.context(inv,data,'a');value=proposal(ctx)
 # Force displayed example identities without changing any source data.
 for i,row in enumerate(ctx['current_originals']):row['id']='J'+str(i+1)
 ctx['required']=[r['id'] for r in ctx['current_originals']];value=proposal(ctx)
 value['read_review']['judgments'][5]=deepcopy(value['read_review']['judgments'][0]);value['read_review']['judgments'][6]=deepcopy(value['read_review']['judgments'][0])
 with pytest.raises(oc.OutputContractError) as caught:rj.validate_review(value,ctx,{s['id']:s for s in data['sources']},['Q1'])
 errors=caught.value.issues;assert any(i['path']=='/read_review/judgments/5/judgment_id' for i in errors)
 assert any(i['path']=='/read_review/judgments/6/judgment_id' for i in errors)
 assert any('J6' in i.get('expected_constraint',{}).get('missing_judgment_ids',[]) for i in errors)
 assert 'J1' in str(caught.value) and 'J6' in str(caught.value)


def recovery_setup(tmp_path,monkeypatch):
 inv,data,page,events,saved=new_setup();data['sources'].append(page('b'));ctx=rj.context(inv,data,'a');repo=Journal(tmp_path/'rec');repo.evidence=lambda:[];inv.s.repo=repo;inv.policy['independent_read_recovery']=True;inv.left=lambda:100;inv.s.profile={'selection_time_reserve_seconds':30};inv.p['read_state']={}
 actions={'Tnew':{'action':'READ_ARTICLES','identity':{'document_id':'d','source_id':'new','unit_id':'1'}}}
 from semantic_runtime.legal_agent import tool_availability as av
 monkeypatch.setattr(av,'article_plan',lambda *a:(({'source_id':'new','document_id':'d'},{'block_ids':['1']}),None))
 monkeypatch.setattr(av,'article_sequence',lambda s,p:[p]);monkeypatch.setattr(av,'sequence_cost',lambda *a:(100,1));monkeypatch.setattr(av,'budget_reason',lambda *a:None)
 raw=fresh(ctx,['Bb']);raw.update(choice='READ',selections=[{'target':'Tnew','issue_id':'Q1','missing_need':'필요한 직접 원문','relation':'DIRECT','source_ref':None,'judgment_refs':[]}])
 return inv,data,ctx,actions,raw,av


def test_failed_review_two_attempts_then_independent_read_preserves_rejection_and_resumes(tmp_path,monkeypatch):
 inv,data,ctx,actions,raw,av=recovery_setup(tmp_path,monkeypatch);calls=[];repo=inv.s.repo
 def check(value):
  v,_=rj.normalize_review(value,ctx);rj.validate_review(v,ctx,{s['id']:s for s in data['sources']},['Q1'])
 def invoke(payload,attempt):calls.append(payload);return deepcopy(raw)
 def run():return oc.bounded_decision(repo,'read-choice',data,{},invoke,check,identity='menu',correction_scope=rj.correction_scope(ctx),recover=lambda v,err:recovery.plan(inv,data,ctx,actions,v,err))
 value=run();assert len(calls)==2 and value['read_review']=={'new_reviews':{}} and value['selections']==raw['selections']
 assert run()==value and len(calls)==2
 logs=[json.loads(r[0]) for r in repo.db.execute('SELECT payload_json FROM event WHERE kind=?',(recovery.EVENT,))];assert len(logs)==1 and logs[0]['judgments_adopted'] is False and logs[0]['rejected_proposal']==raw
 v,ch=rj.normalize_review(value,ctx);rj.record(inv,data,v,'a',ctx,actions)
 assert not rj.state_for(inv,data)['heads'] and len(rj.state_for(inv,data)['pending'])==2
 error=oc.OutputContractError('bad',[oc.issue('READ_JUDGMENT_WRONG_ORIGINAL')],category='READ_JUDGMENT_INVALID')
 raw['selections'][0]['missing_need']='말만 바꿈';assert recovery.plan(inv,data,ctx,actions,raw,error) is None

@pytest.mark.parametrize('reason',['no_new','budget','time','dependent','failed_judgment','unoffered','state_error'])
def test_recovery_cannot_bypass_progress_dependencies_budget_or_binding(tmp_path,monkeypatch,reason):
 inv,data,ctx,actions,raw,av=recovery_setup(tmp_path,monkeypatch)
 error=oc.OutputContractError('bad',[oc.issue('READ_JUDGMENT_WRONG_ORIGINAL')],category='READ_JUDGMENT_INVALID')
 if reason=='no_new':monkeypatch.setattr(av,'sequence_cost',lambda *a:(0,0))
 if reason=='budget':monkeypatch.setattr(av,'budget_reason',lambda *a:'READ_CHARACTER_LIMIT')
 if reason=='time':inv.left=lambda:1
 if reason=='dependent':raw['selections'][0]['relation']='DEPENDENCY'
 if reason=='failed_judgment':raw['selections'][0]['judgment_refs']=[ctx['new_review_ids'][0]]
 if reason=='unoffered':raw['selections'][0]['target']='unknown'
 if reason=='state_error':error=ContractError('source hash changed')
 assert recovery.plan(inv,data,ctx,actions,raw,error) is None
