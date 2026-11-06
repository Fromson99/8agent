"""Synthetic lifecycle and failure boundaries; no external model or legal scoring."""
from copy import deepcopy
import json
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import corrected_memory as memory_module
from semantic_runtime.legal_agent import ontology_assessment as ontology
from semantic_runtime.legal_agent import review_explanation
from semantic_runtime.legal_agent.case_repository import CaseRepository
from semantic_runtime.legal_agent.unified_rag import UnifiedExecution
from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
from semantic_runtime.ontology_work import runtime, assembly_compiler
from semantic_runtime.legal_agent.errors import ContractError
from test_memory_runtime_v2 import memory, Fake, Wire, command, start
from test_domain_profile_workflow import env, add_observation, proposal, save, approve_stage
from test_review_explanation_actions import current_normalizer_wire


def test_followup_keeps_goal_facts_and_history_then_new_topic_separates(memory):
    repo,executor,wire,send,principal=memory
    first=send(command('CASE_START',task='가상 제출의 원칙은?',facts=[{'name':'주체','value':'가상 주체'}]))
    gid=first['goal_id'];initial=deepcopy(repo.events(gid))
    second=send(command('PURPOSE_REVISE',target=gid,task='같은 제출 의무의 예외는?'))
    assert second['goal_id']==gid and second['state']['facts']==first['state']['facts']
    assert second['state']['task']=='같은 제출 의무의 예외는?'
    assert second['executed']==list(memory_module.STAGES)
    assert repo.events(gid)[0]==initial[0]
    third=send(command('FACT_UPDATE',target=gid,facts=[{'name':'주체','value':'예외 주체'}]))
    assert third['executed']==['ASSESS','COMPOSE']
    assert third['state']['task']==second['state']['task']
    other=send(command('CASE_START',task='관계없는 새 주제',facts=[]))
    assert other['goal_id']!=gid and other['state']['facts']==[]
    assert repo.goal(gid,'s')['state']['facts']==third['state']['facts']


def test_generation_change_rebuilds_instead_of_rebinding_old_read(memory):
    repo,executor,wire,send,principal=memory
    first=start(send);gid=first['goal_id'];old=deepcopy(repo.parts(gid))
    executor.binding={'generation':'NEW_SYNTHETIC'}
    result=send(command('ANSWER_PRESENT',target=gid))
    assert result['executed']==list(memory_module.STAGES)
    assert repo.parts(gid)['READ']['payload']['binding']==executor.binding
    assert json.loads(repo.db.execute('SELECT payload FROM node WHERE id=?',(old['READ']['id'],)).fetchone()[0])==old['READ']['payload']


def test_partial_request_without_read_resumes_its_saved_stage(memory):
    repo,executor,wire,send,principal=memory
    executor.fails='PLAN'
    with pytest.raises(memory_module.MemoryError):start(send)
    goal=repo.db.execute('SELECT id FROM goal').fetchone()[0]
    intent=repo.parts(goal)['INTENT']['id']
    executor.fails=None
    result=send(command('RESEARCH_REENTER',target=goal,stage='COMPOSE'))
    assert result['executed']==list(memory_module.STAGES[1:])
    assert repo.parts(goal)['INTENT']['id']==intent


@pytest.mark.parametrize('fault',['empty','source_only','incomplete'])
def test_failed_judgment_cannot_be_confirmed_as_experience(memory,fault):
    repo,executor,wire,send,principal=memory
    original=executor.stage
    def stage(name,*args):
        value=original(name,*args)
        if name=='ASSESS':
            if fault=='empty':value['claims']=[]
            if fault=='source_only':value['source_excerpt_reply']={'status':'ORIGINALS_ONLY'}
            if fault=='incomplete':value['model_proposal']={'review_status':'INCOMPLETE'}
        return value
    executor.stage=stage
    gid=start(send)['goal_id']
    with pytest.raises(memory_module.Conflict,match='unsupported or incomplete'):
        send(command('EXPERIENCE_CONFIRM',target=gid))
    assert repo.db.execute('SELECT count(*) FROM knowledge').fetchone()[0]==0


@pytest.mark.parametrize('fault',['none','scope','generation','corrupt'])
def test_previous_originals_respect_current_scope_before_verification(fault):
    old={'evidence_id':'old','document_id':'denied','source_id':'secret','spans':[]}
    allowed={'evidence_id':'yes','document_id':'visible','source_id':'public','spans':[]}
    verify=Mock(side_effect=ContractError('injected corrupt original') if fault=='corrupt' else None)
    record=Mock();source_verify=Mock()
    execution=S(host=S(binding={'generation':'now'},verify=verify),
        s=S(context=S(run_id='new-run'),sources=S(scope=['visible'],source=S(verify=source_verify)),
            work=S(record_observation=record)))
    parts={'READ':{'payload':{'binding':{'generation':'old' if fault=='generation' else 'now'},
                             'evidence':[old] if fault=='scope' else [old,allowed]}}}
    if fault=='corrupt':
        with pytest.raises(ContractError):UnifiedExecution.bind_previous(execution,parts)
        record.assert_not_called()
    else:
        UnifiedExecution.bind_previous(execution,parts)
        if fault in ('scope','generation'):
            verify.assert_not_called();record.assert_not_called()
        else:
            assert [e['document_id'] for e in verify.call_args.args[0]['evidence']]==['visible']
            assert [e['document_id'] for e in record.call_args.args[2]]==['visible']


def activated(env):
    observation=add_observation(env)
    draft=save(env,observation,proposal(env,observation))
    stage=approve_stage(env,draft)
    receipt=env.w.verify_publication(stage['publication_id'])
    env.w.activate_publication(stage['publication_id'],0,receipt)
    return draft,stage,env.repo.lookup(env.source['anchor'],{'fictional'})[0]


def test_domain_publication_rechecks_all_readers_and_preserves_conflict(env):
    draft,stage,row=activated(env)
    state={'ontology_database':{'contexts':{draft['bundle_id']:row}},'ontology_context':{'plans':{
        'p':{'id':'p','bundle_id':draft['bundle_id'],'status':'COMPLETE'}}}}
    refs=runtime.workspace_references(state)
    assert refs and not draft['bundle_id'].startswith('cb-kb-ws-')
    assessment={'assessment_basis':{'workspace_publications':refs}}
    runtime.assert_assessment(assessment,{'fictional'},env.repo)
    incoming=add_observation(env,'conflict',{'judgment':'가상 예외에도 제출한다는 상반된 관찰'})
    change=proposal(env,incoming,base=env.w.load(draft['bundle_id'])['proposal']['graph'],relation='CONTRADICTION')
    next_revision=save(env,incoming,change,1)
    assert env.w.load(draft['bundle_id'])['review_state']=='REVIEW_CONFLICT'
    assert env.repo.head(draft['bundle_id'])['publication_id']==stage['publication_id']
    runtime.assert_assessment(assessment,{'fictional'},env.repo)
    env.repo.activate(draft['bundle_id'],None,1,'reviewer')
    assert env.w.load(draft['bundle_id'])['revision']==next_revision['revision']
    with pytest.raises(runtime.PublicationChanged):runtime.assert_assessment(assessment,{'fictional'},env.repo)
    assert runtime.recheck(S(scope={'fictional'},ontology_repository=env.repo),state)==[draft['bundle_id']]
    assert state['ontology_context']['plans']['p']['status']=='NEEDS_REVIEW'


def test_conversation_to_approved_knowledge_to_claim_use_then_changed_conditions(env,tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'repository',lambda:env.repo)
    holder={};wire=Wire()
    class Executor(Fake):
        def stage(self,name,state,parts,*args):
            if name=='READ':return {'binding':self.binding,'originals':[{'source_id':'S1','text':env.source['text']}]}
            if name=='SELECT':return {'final_ids':['S1']}
            if name=='ASSESS':
                value={'claims':[{'claim_id':'C1','text':'가상 제출 의무를 검토함','source_id':'S1',
                                  'quote':env.source['text'],'evidence_refs':['CURRENT']}],
                       'limitations':[],'gaps':[],'answer_coverage':'COVERED'}
                row=holder.get('publication')
                if row:
                    catalog=assembly_compiler.bind_current(row['context']['assembly_package'],[
                        {'anchor':env.source['anchor'],'text':env.source['text'],'evidence_refs':['CURRENT']}])
                    path=catalog['paths'][0]
                    payload={'ontology_bundles':[{'bundle_id':'cb-kb-rule','status':'COMPLETE',
                                                 'payload':{'assembly_catalog':catalog}}]}
                    use={'package_sha256':catalog['package_sha256'],'path_id':path['id'],
                         'node_ids':[path['nodes'][0]['id']],'claim_id':'C1'}
                    core,_,usage=ontology.usage_core({**value,'ontology_usage':[use]}, {'properties':{}},payload)
                    value=core
                    refs=runtime.workspace_references({'ontology_database':{'contexts':{'cb-kb-rule':row}}})
                    value['assessment_basis']={'workspace_publications':refs}
                    value['ontology_explanation']=ontology.explanation(payload,decision_key='synthetic',usage=usage,received=True)
                value['review_explanation']=review_explanation.build(value,[{'source_id':'S1','document_id':'fictional'}])
                value.pop('ontology_explanation',None)
                return value
            return super().stage(name,state,parts,*args)
    executor=Executor();repo=memory_module.Memory(tmp_path/'conversation.sqlite',executor,wire)
    principal={'user_id':'u','team_id':'risk_team','document_ids':['fictional']};count=0
    def send(c):
        nonlocal count
        count+=1;wire.command=c
        return repo.execute({'session_id':'s','request_id':str(count),
                             'question':c.get('task') or '후속 요청 '+str(count)},principal)
    try:
        first=send(command('CASE_START',task='가상 제출 원칙은?',facts=[]));gid=first['goal_id']
        raw=env.w.import_payload(repo.parts(gid)['ASSESS']['payload'],run_id='conversation',event_id='accepted-1')
        observation=env.w.normalize(raw['bundle_id'],profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,labels=[])
        draft=save(env,observation,proposal(env,observation));stage=approve_stage(env,draft)
        checked=env.w.verify_publication(stage['publication_id']);env.w.activate_publication(stage['publication_id'],0,checked)
        holder['publication']=env.repo.lookup(env.source['anchor'],{'fictional'})[0]
        second=send(command('PURPOSE_REVISE',target=gid,task='같은 가상 제출의 예외는?'))
        assert second['goal_id']==gid
        assessment=repo.parts(gid)['ASSESS']['payload'];uses=ontology.accepted_uses(assessment)
        assert len(uses)==1 and uses[0]['claim_id']=='C1' and uses[0]['bundle_id']=='cb-kb-rule'
        kid=send(command('EXPERIENCE_CONFIRM',target=gid))['knowledge_id']
        assert repo.checked_knowledge(kid,principal)
        changed=send(command('FACT_UPDATE',target=gid,facts=[{'name':'주체','value':'가상 예외'}]))
        assert changed['executed']==['ASSESS','COMPOSE']
        assert repo.db.execute('SELECT status FROM knowledge WHERE id=?',(kid,)).fetchone()[0]=='RETIRED'
        next_kid=send(command('EXPERIENCE_CONFIRM',target=gid))['knowledge_id']
        env.repo.activate(draft['bundle_id'],None,1,'reviewer')
        with pytest.raises(memory_module.MemoryError,match='publication changed'):repo.checked_knowledge(next_kid,principal)
        holder.clear()
        reviewed=send(command('ANSWER_PRESENT',target=gid))
        assert reviewed['executed']==['ASSESS','COMPOSE']
        assert ontology.accepted_uses(repo.parts(gid)['ASSESS']['payload'])==[]
    finally:repo.close()


@pytest.mark.parametrize('recorded',[False,True])
def test_route_and_outbox_record_only_actual_claim_use(recorded):
    use={'bundle_id':'b','package_sha256':'pkg','path_id':'p','node_ids':['n'],'claim_id':'C1'}
    explanation={'status':'RESPONSE_RECEIVED','adoption':'RECORDED','bundles':[
        {'bundle_id':'b','adoption':'ADOPTED' if recorded else 'NOT_USED','claim_uses':[{k:v for k,v in use.items() if k!='bundle_id'}] if recorded else []}]}
    assessment={'claims':[{'claim_id':'C1'}],'review_explanation':review_explanation.seal({
        'schema_version':review_explanation.VERSION,'ontology':explanation})}
    assert ontology.accepted_uses(assessment)==([use] if recorded else [])
    db=Mock();db.execute.return_value=[{'stage':s,'ref':json.dumps({'id':s})} for s in memory_module.STAGES]
    repo=S(db=db,parts=lambda gid:{'ASSESS':{'payload':assessment}})
    fields=CaseRepository.route_fields(repo,'g')
    assert fields['ontology_uses']==([use] if recorded else [])
    enqueue=Mock();repo=S(db=db,enqueue=enqueue,executor=S(model=S(session=S(context=S(run_id='r')))))
    CaseRepository.route_accepted(repo,'g',1,1,fields,{'request_id':'req'})
    assert enqueue.call_args.args[-1]['ontology_uses']==fields['ontology_uses']


@pytest.mark.parametrize('fault',['withdrawn','unavailable','disabled'])
def test_literal_repeat_reassesses_known_withdrawal_only(monkeypatch,fault):
    state={'task':'같은 질문','document_ids':['d'],'facts':[]}
    goal={'id':'g','state':state,'status':'READY','revision':2,'command_ready':True,
          'events':[{'id':1,'utterance':'같은 질문','after':deepcopy(state)}]}
    assessment={'disposition':'ANSWER','answer_coverage':'COVERED','claims':[{'text':'기존 답변'}]}
    error=ContractError('authority unavailable') if fault=='unavailable' else runtime.PublicationChanged('withdrawn')
    repo=S(context=lambda *a:{'utterance':'같은 질문','goals':[goal]},goal=lambda *a:goal,
           parts=lambda *a:{'ASSESS':{'payload':assessment}},committed_response=Mock(side_effect=error))
    body={'question':'같은 질문','session_id':'s','request_id':'new','use_llm':fault!='disabled'}
    invoked=Mock(side_effect=lambda self,*a:{'reopened':self.resolved_command['stage'],
                                           'target':self.resolved_command['target']})
    monkeypatch.setattr(memory_module.Memory,'_execute',invoked)
    if fault=='withdrawn':
        assert ShortcutCases._execute(repo,body,{'document_ids':['d']})=={'reopened':'ASSESS','target':'g'}
        assert repo.resolved_command is None
    else:
        with pytest.raises(memory_module.Conflict if fault=='disabled' else ContractError):
            ShortcutCases._execute(repo,body,{'document_ids':['d']})
        invoked.assert_not_called()


def test_native_api_usage_reaches_durable_route_and_outbox(env,tmp_path,term_glossary,monkeypatch):
    """Reuse the native source/approval/API fixture and check the new consumer."""
    from test_review_explanation_actions import test_native_typed_scenario_and_explicit_ontology_use
    from semantic_runtime import app as app_module
    # The reused fixture emits a legacy empty field which the current minimal
    # action schema no longer requests. Adapt only that empty wire artifact;
    # the product decoder/validators still run unchanged on every response.
    create=app_module.create_app
    scripted_reviews=[]
    def compatible(*args,**kwargs):
        transport=kwargs['legal_agent_transport'];send=transport.send_once
        def current_wire(*,body,ticket):
            from api_fixture_integrated import decode
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            phase=view.get('source_stage')
            wire_schema=body['response_format']['json_schema']['schema']
            common_navigation_review=(phase=='source-law-navigation-supervisor-read-choice'
                and '"PASS"' in json.dumps(wire_schema) and '"decision"' in json.dumps(wire_schema))
            if common_navigation_review or phase in ('memory-ontology-supervisor','memory-reason-decision-review',
                    'source-reason-decision-review','memory-final-reason-review'):
                from test_legal_agent_double_harness import wire
                scripted_reviews.append(deepcopy(view))
                return wire({'decision':'PASS'})
            errors=(view.get('repair_contract') or {}).get('validation',{}).get('issues',[])
            mismatch=next((r for r in errors if r['code']=='DECISION_EXECUTION_MISMATCH'),None)
            if mismatch and '-read-choice' in phase:
                # The primary now owns correction; the old fixture delegated
                # this same exact source-goal route to the former supervisor.
                from api_fixture_integrated import to_wire
                from test_legal_agent_double_harness import wire
                transport.calls.append(phase);transport.views.append(deepcopy(view))
                proposed=view['rejected_decision'];route=mismatch['expected_constraint']['source_goal_route']
                common={k:deepcopy(v) for k,v in proposed.items() if k in
                    ('read_review','answer_progress','source_targets','source_goal_exclusions')}
                row={'target':route['targets'][0],'issue_id':route['issue_refs'][0],
                    'missing_need':route['reason'],'relation':proposed.get('relation','DIRECT'),
                    'source_ref':proposed.get('source_ref'),'judgment_refs':proposed.get('judgment_refs',[])}
                answer=({**common,'choice':'READ','selections':[row]} if route['next_action']=='READ_ARTICLES'
                        else {**common,'choice':'LOCATE',**row,'structure_filter':route['structure_filter']})
                return wire(to_wire(answer))
            response=send(body=body,ticket=ticket)
            content=response['body_json']['choices'][0]['message']['content']
            value=json.loads(content)
            schema=body['response_format']['json_schema']['schema']
            if (value.get('source_goal_exclusions')==[] and
                    'source_goal_exclusions' not in json.dumps(schema)):
                value.pop('source_goal_exclusions')
            review=value.get('read_judgment_review')
            if review:
                # The current contract derives acquired source-work needs from
                # the explicit scope reviews. Only those host-owned rows are
                # omitted on wire; semantic needs and their decisions remain.
                needs=schema['properties']['read_judgment_review']['properties']['needs']
                permitted={b['properties']['id']['const'] for b in needs['items'].get('anyOf',[])}
                if permitted:
                    from api_fixture_integrated import decode
                    view=decode(json.loads(body['messages'][1]['content'])['view'])
                    previous={n['id']:n for n in view['read_judgments']['needs']}
                    for n in review['needs']:
                        if n['id'] not in permitted:
                            assert previous[n['id']]['origin'] in ('SOURCE_GOAL','STRUCTURE_SELECTION')
                    review['needs']=[n for n in review['needs'] if n['id'] in permitted]
                for row in review['judgments']:
                    for purpose in row.get('change_review',{}).get('purpose_reviews',[]):
                        purpose.pop('claim_refs',None)  # Current shared links own this join.
                rules=schema['properties']['read_judgment_review']['properties']
                if 'original_review_groups' in rules:
                    # Encode the fixture's already explicit scope decisions in
                    # the current per-original assignment format, preserving
                    # each disposition/reason/issue/gap without inventing use.
                    by_ref={}
                    for scope in review.pop('scope_reviews'):
                        for group in scope['groups']:
                            decision={k:v for k,v in group.items() if k not in ('basis_refs','claim_refs')}
                            for ref in group['basis_refs']:
                                assert ref not in by_ref or by_ref[ref]==decision
                                by_ref[ref]=decision
                    groups=[];assignments={}
                    for slot,rule in rules['original_reviews']['properties'].items():
                        ref=rule['properties']['basis_refs']['items']['const']
                        decision=by_ref[ref]
                        if decision not in groups:groups.append(decision)
                        assignments[slot]={'basis_refs':[ref],'group_index':groups.index(decision)+1}
                    review.update(original_reviews=assignments,original_review_groups=groups)
            response['body_json']['choices'][0]['message']['content']=json.dumps(value,ensure_ascii=False)
            return response
        transport.send_once=current_wire
        return create(*args,**kwargs)
    monkeypatch.setattr(app_module,'create_app',compatible)
    import need_continuity_fixture as api_fixture
    native_run=api_fixture.run_api
    def lifecycle_api(*args,**kwargs):
        def exercise(api,transport,request,runtime_path):
            request={**request,'question':request['question']+' 작업 비용은 1500000원, 서면 승인은 미확인입니다.'}
            first=api.post('/v1/rag/ask',json=request)
            assert first.status_code==200,first.text
            initial=first.json();view=initial['assembly']['term_agent']['review_explanation']
            assert view['ontology']['status']=='RESPONSE_RECEIVED'
            assert any(b['claim_uses'] for b in view['ontology']['bundles'])
            calls=deepcopy(transport.calls);reviews=len(scripted_reviews)
            duplicate=api.post('/v1/rag/ask',json=request)
            assert duplicate.status_code==200 and duplicate.json()['answer']==initial['answer']
            repeat=api.post('/v1/rag/ask',json={**request,'request_id':'literal-new'})
            assert repeat.status_code==200,repeat.text
            assert repeat.json()['goal_id']==initial['goal_id']
            assert repeat.json()['revision']==initial['revision'] and repeat.json()['executed']==[]
            assert transport.calls==calls and len(scripted_reviews)==reviews
            head=env.repo.head('cb-kb-rule')
            env.repo.activate('cb-kb-rule',None,head['sequence'],'reviewer')
            refreshed=api.post('/v1/rag/ask',json={**request,'request_id':'withdrawn-new'})
            assert refreshed.status_code==200,refreshed.text
            updated=refreshed.json()
            assert updated['goal_id']==initial['goal_id'] and updated['revision']==initial['revision']+1
            assert updated['executed']==['ASSESS','COMPOSE']
            assert updated['answer']['claims']
            assert not any(b.get('claim_uses') for b in updated['assembly']['term_agent']['review_explanation']['ontology']['bundles'])
        return native_run(*args,**{**kwargs,'exercise':exercise})
    monkeypatch.setattr(api_fixture,'run_api',lifecycle_api)
    accepted=[];original=CaseRepository.route_accepted
    def record(self,gid,revision,route_id,payload,body):
        original(self,gid,revision,route_id,payload,body)
        row=self.db.execute("SELECT payload,hash FROM outbox WHERE aggregate_id=? AND revision=? AND kind='ANSWER_ACCEPTED'",
                            (gid,revision)).fetchone()
        durable=json.loads(row['payload'])
        assert digest(durable)==row['hash']
        assert durable['ontology_uses']==payload['ontology_uses']
        assert durable['judgment_refs']['ASSESS']['payload_hash']==digest(self.parts(gid)['ASSESS']['payload'])
        accepted.append(deepcopy(payload['ontology_uses']))
    monkeypatch.setattr(CaseRepository,'route_accepted',record)
    test_native_typed_scenario_and_explicit_ontology_use(env,tmp_path,term_glossary,monkeypatch,'repair_success')
    assert any(rows for rows in accepted)
    assert all(r['claim_id'] and r['path_id'] and r['node_ids'] for rows in accepted for r in rows)
    assert scripted_reviews  # Reviewer is scripted; this is a connection test.
