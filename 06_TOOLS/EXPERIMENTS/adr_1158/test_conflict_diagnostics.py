from copy import deepcopy
import pytest
from test_stable_recovery_isolated import new_setup,fresh,recovery_setup
from semantic_runtime.legal_agent import read_judgment as rj,output_contract as oc,independent_read_recovery as recovery

@pytest.mark.parametrize('fault',['conflict_no_partner','undeclared_conflict','self_conflict','blank_reason','blank_finding'])
def test_error_names_exact_judgment_field_and_dependency(fault):
 inv,data,page,*_=new_setup();ctx=rj.context(inv,data,'a');raw=fresh(ctx);jid=ctx['new_review_ids'][0];row=raw['read_review']['new_reviews'][jid]
 if fault=='conflict_no_partner':row['operation']='CONFLICT'
 if fault=='undeclared_conflict':row['conflicts_with']=[jid]
 if fault=='self_conflict':row.update(operation='CONFLICT',use='DEFER',conflicts_with=[jid])
 if fault=='blank_reason':row['reason']=' '
 if fault=='blank_finding':row['finding']=' '
 raw.update(choice='FOLLOW_CONNECTION',relation='DEPENDENCY',issue_id='Q1',judgment_refs=[])
 value,_=rj.normalize_review(raw,ctx)
 with pytest.raises(oc.OutputContractError) as exc:rj.validate_review(value,ctx,{s['id']:s for s in data['sources']},['Q1'])
 assert exc.value.category=='READ_JUDGMENT_INVALID'
 assert any('/new_reviews/'+jid+'/' in x['path'] for x in exc.value.issues)
 assert any(x['path']=='/judgment_refs' for x in exc.value.issues)
 assert jid in str(exc.value)

@pytest.mark.parametrize('fault',['conflict_no_partner','undeclared_conflict','self_conflict','blank_reason','blank_finding'])
def test_conflict_or_invalid_review_cannot_block_separate_direct_read(tmp_path,monkeypatch,fault):
 inv,data,ctx,actions,raw,av=recovery_setup(tmp_path,monkeypatch);jid=ctx['new_review_ids'][0];row=raw['read_review']['new_reviews'][jid];row['basis_refs']=ctx['current_originals'][0]['source_refs']
 if fault=='conflict_no_partner':row['operation']='CONFLICT'
 if fault=='undeclared_conflict':row['conflicts_with']=[jid]
 if fault=='self_conflict':row.update(operation='CONFLICT',use='DEFER',conflicts_with=[jid])
 if fault=='blank_reason':row['reason']=' '
 if fault=='blank_finding':row['finding']=' '
 calls=[]
 def validate(v):
  v,_=rj.normalize_review(v,ctx);rj.validate_review(v,ctx,{s['id']:s for s in data['sources']},['Q1'])
 def invoke(p,a):calls.append(a);return deepcopy(raw)
 value=oc.bounded_decision(inv.s.repo,'read-choice',data,{},invoke,validate,identity='menu',correction_scope=rj.correction_scope(ctx),recover=lambda v,err:recovery.plan(inv,data,ctx,actions,v,err))
 assert calls==[0,1] and value['selections']==raw['selections'] and value['read_review']=={'new_reviews':{}}
 assert not inv.p.get('read_judgments')
