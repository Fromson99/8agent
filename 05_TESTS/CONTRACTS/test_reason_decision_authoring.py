"""Actual ontology repository writes with synthetic author/reviewer responses."""
from copy import deepcopy
import pytest

from test_domain_profile_workflow import env, normalized_output
from test_wiki_workspace import ws, seed, compiled, wire_normalization
from test_reason_decision_review import conflict
from semantic_runtime.legal_agent import reason_decision_review as review
from semantic_runtime.legal_agent.errors import ContractError, TransportError, ProposalError
from semantic_runtime.ontology_work.wiki_projection import compare_judgment
from semantic_runtime.ontology_work import reason_review as authoring_review
from semantic_runtime.ontology_work.schema import obj, text


def pass_reviews(model):
    def generate(prompt,context,schema):
        if context.get('contract_version')==review.VERSION:
            return {'decision':'PASS'},{'physical_calls':1,'synthetic':True}
        return model(prompt,context,schema)
    return generate


@pytest.mark.parametrize('case',['corrected','repeated','reason_only','unknown','invalid','stale','deadline'])
def test_authoring_owner_repair_and_persisted_failure_boundaries(env,case):
    w=env.w;w.review_generate=None;primary=[];seen=[];binding_ok=[True];now=[1.0];w.clock=lambda:now[0]
    first={'decision':'SAME','reason':'기존 규칙과 충돌한다.'}
    corrected={'decision':'CONTRADICTION','reason':'기존 규칙과 충돌하므로 별도 검토로 보존한다.'}
    shape=obj({'decision':{'enum':['SAME','CONTRADICTION']},'reason':text()})
    def current():
        if not binding_ok[0]:raise ContractError('source version changed')
    def generate(prompt,context,schema):
        if context.get('contract_version')==review.VERSION:
            seen.append(deepcopy(context))
            if case=='unknown':raise TransportError('review timeout',unknown=True)
            if case=='invalid':return {'decision':'PASS','action':'SAME'},{}
            if case=='stale':binding_ok[0]=False;return {'decision':'PASS'},{}
            if case=='deadline':now[0]=1000;return {'decision':'PASS'},{}
            if len(seen)==1 or case in ('repeated','reason_only'):
                return conflict(context['proposal']),{'synthetic':True}
            return {'decision':'PASS'},{'synthetic':True}
        primary.append(deepcopy(context))
        value=first if len(primary)==1 or case=='repeated' else corrected
        if case=='reason_only' and len(primary)>1:value={**first,'reason':'이제 일치한다.'}
        return deepcopy(value),{'primary':len(primary)}
    w.generate=generate
    def validate(p):
        from semantic_runtime.ontology_work.profile import validate
        validate(p,shape)
    def run():return w._job('ACCUMULATE',{'original':'검증된 원문'},'판단한다',shape,validate,current)
    if case=='corrected':
        value,receipt=run()
        assert value==corrected and receipt['reason_decision_review']['decision']=={'decision':'PASS'}
        assert len(primary)==2 and len(seen)==2
        assert run()==(value,receipt) and len(primary)==2
        assert seen[1]['previous_rejections'][0]['proposal']==first
        assert primary[1]['repair']['previous']['review_issues']
    else:
        with pytest.raises((ContractError,TransportError)):run()
        before=(len(primary),len(seen))
        with pytest.raises(ContractError):run()
        assert (len(primary),len(seen))==before
        jobs=[w.load(r['bundle_id']) for r in w.repo.list(prefix='job-')]
        assert jobs and not any(j['phase']=='READY' for j in jobs)
        if case=='repeated':assert before==(2,1)
        if case in ('unknown','invalid','stale','deadline'):assert before==(1,1)


def test_corrected_comparison_reaches_real_conflict_revision_and_preserves_graph(env,ws):
    env.w.generate=pass_reviews(env.w.generate)
    item=seed(env,ws);row,_=compiled(env,ws,item);base=ws.load(row['bundle_id'])
    raw=ws.import_payload('새 질문에서 얻은 실제 판단',event_id='next-judgment',run_id='next')
    primary=[];seen=[]
    def generate(prompt,context,schema):
        if context.get('contract_version')==review.VERSION:
            if context['stage']=='WIKI_COMPARE':
                seen.append(deepcopy(context))
                if len(seen)==1:
                    return conflict(context['proposal'],reason='/J1/reason',decision='/J1/relation'),{}
            return {'decision':'PASS'},{}
        if 'raw' in context:return wire_normalization(normalized_output(context)),{}
        primary.append(deepcopy(context))
        return {alias:{'relation':'SAME' if len(primary)==1 else 'CONTRADICTION',
            'verdict':'SUPPORTED' if len(primary)==1 else 'CONTRADICTED',
            'reason':'기존 규칙과 충돌한다.','basis':[{'source':'S1','quote':env.source['text']}],
            'node_ids':['N1']} for alias in context['judgments']},{}
    ws.generate=generate;ws.review_generate=None
    args=dict(bundle_id=row['bundle_id'],revision=row['revision'],work_hash=row['work_hash'],raw_id=raw['bundle_id'])
    saved=compare_judgment(env.w,ws,**args);after=ws.load(row['bundle_id'])
    assert after['review_state']=='REVIEW_CONFLICT' and saved['revision']==row['revision']+1
    assert after['proposal']['graph']==base['proposal']['graph']
    assert after['comparison_history'][:-1]==base['comparison_history']
    assert after['proposal']['comparisons'][0]['relation']=='CONTRADICTION'
    assert after['judgment_review']['model_receipt']['reason_decision_review']['decision']=={'decision':'PASS'}
    assert ws.repo.head(row['bundle_id'])['publication_id'] is None
    assert compare_judgment(env.w,ws,**args)['reused']
    assert len(primary)==2 and len(seen)==2


def test_authoring_ledger_reservation_cas_cannot_overwrite_another_owner(env):
    first=authoring_review.Ledger(env.w,{'scope':'same'});second=authoring_review.Ledger(env.w,{'scope':'same'})
    key='a'*64
    assert first.output_decision_state(key) is None and second.output_decision_state(key) is None
    record={'decision_key':key,'status':'RESERVED'}
    first.output_decision_event(record)
    with pytest.raises(ContractError):second.output_decision_event(record)
    assert first.output_decision_state(key)==record


def test_workspace_five_attempt_limit_does_not_repeat_same_semantic_conflict(env):
    w=env.w;w.review_generate=None;w.job_attempt_limit=5;primary=[];seen=[]
    shape=obj({'decision':{'const':'SAME'},'reason':text()})
    def generate(prompt,context,schema):
        if context.get('contract_version')==review.VERSION:
            seen.append(context)
            return conflict(context['proposal']),{}
        primary.append(context)
        return {'decision':'SAME','reason':'기존 지식과 충돌한다. '+str(len(primary))},{}
    w.generate=generate
    from semantic_runtime.ontology_work.profile import validate
    with pytest.raises(review.ReviewConflict):
        w._job('WIKI_COMPARE',{'original':'원문'},'판단',shape,lambda p:validate(p,shape))
    assert len(primary)==len(seen)==2
    assert primary[1]['repair']['instruction']==review.RECONSIDER
    job=w.load(w.repo.list(prefix='job-')[0]['bundle_id'])
    assert job['phase']=='INVALID' and job['attempt_limit']==5


@pytest.mark.parametrize('case',['pass','corrected','repeated','unknown','invalid','stale','late'])
def test_legacy_scenario_proposal_uses_shared_owner_and_durable_budget(env,monkeypatch,case):
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.ontology_work import schema
    import time
    now=[100.0];monkeypatch.setattr(time,'time',lambda:now[0])
    work={'version':schema.VERSION,'concept':'승인 절차','originals':[env.source],
          'judgments':[],'origin':{'run_id':'synthetic-scenario'}}
    first={'components':[
        {'id':'A','text':'사전 승인이 반드시 필요하다.','requires':[],
         'basis':[{'source':'S1','quote':env.source['text']}]},
        {'id':'B','text':'승인 후 시행한다.','requires':['A'],
         'basis':[{'source':'S1','quote':env.source['text']}]}],
        'paths':[{'id':'P1','title':'시행','business_use':'승인 없이 시행한다.',
                  'conditions':['A'],'calculations':[],'outcomes':['B'],'notes':[]}],
        'unused_components':{}}
    corrected=deepcopy(first);corrected['paths'][0]['business_use']='승인을 받은 후 시행한다.'
    primary=[];seen=[]
    w=Workflow(env.repo,env.w.store,actor='reviewer',source_reader=env.w.source_reader)
    def generate(prompt,context,shape):
        if context.get('contract_version')==review.VERSION:
            seen.append(deepcopy(context))
            if case=='unknown':raise TransportError('scenario review lost',unknown=True)
            if case=='invalid':return {'decision':'PASS','replacement':{}},{}
            if case=='stale':w.source_reader=lambda _: 'changed'
            if case=='late':now[0]+=181
            if case in ('corrected','repeated') and len(seen)==1:
                return conflict(context['proposal'],reason='/components/0/text',decision='/paths/0/business_use'),{}
            return {'decision':'PASS'},{}
        primary.append(deepcopy(context))
        return deepcopy(first if len(primary)==1 or case=='repeated' else corrected),{'synthetic':True}
    w.generate=generate
    if case in ('pass','corrected'):
        saved=w.propose(work);count=(len(primary),len(seen))
        value=w.load(saved['bundle_id'])
        assert value['proposal']==(first if case=='pass' else corrected)
        assert count==((1,1) if case=='pass' else (2,2))
        now[0]+=1000
        assert w.propose(work)['reused'] and (len(primary),len(seen))==count
    else:
        with pytest.raises((ContractError,TransportError,ProposalError)):w.propose(work)
        count=(len(primary),len(seen))
        with pytest.raises((ContractError,TransportError,ProposalError)):w.propose(work)
        assert (len(primary),len(seen))==count
        assert not env.repo.list(prefix='cb-')
