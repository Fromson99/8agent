from copy import deepcopy
import gzip,json,os
from pathlib import Path
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import need_continuity as nc,read_judgment_final as final
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from jsonschema import ValidationError
ROOT=Path(__file__).resolve().parents[3]

def historical():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1269-qwen-small-source-loop-recovery/artifacts/live/malformed-json/canonical'
    with gzip.open(p/'007.json.gz','rt') as f:d=json.load(f)['view']
    with gzip.open(p/'007-output.json.gz','rt') as f:v=json.load(f)
    return d['read_judgments'],d['evidence_options'],v

def test_exact_failed_qwen_review_binds_only_missing_explicit_edge():
    c,o,v=historical();before=deepcopy((c,o,v))
    with pytest.raises(ProposalError,match='scope/need review'):final.validate_review(v,c,o)
    fixed,receipt=nc.bind_reviewed_targets(v,c,o)
    final.validate_review(fixed,c,o)
    assert len(receipt['changes'])==1 and receipt['extra_model_calls']==0
    change=receipt['changes'][0];assert change['claim_id']=='C1'
    assert receipt['original_hash']==digest(v) and receipt['bound_hash']==digest(fixed)
    reverse=deepcopy(fixed);reverse['read_judgment_review']['needs'][0]['target_refs'].remove(change['target_id'])
    assert reverse==v and (c,o,v)==before
    again,audit=nc.bind_reviewed_targets(fixed,c,o);assert again==fixed and audit is None

@pytest.mark.parametrize('fault',['unknown_claim','unknown_target','missing_review','duplicate_review',
    'missing_range','excluded_range','wrong_issue','unacquired','tampered_original','open_need',
    'missing_judgment','unknown_basis','claim_changed','gap_deleted'])
def test_binding_never_replaces_other_validation(fault):
    c,o,v=historical();r=v['read_judgment_review'];target=c['need_continuity']['targets'][0]
    if fault=='unknown_claim':r['needs'][0]['claim_refs'].append('unknown')
    if fault=='unknown_target':r['needs'][0]['target_refs'].append('unknown')
    if fault=='missing_review':r['scope_reviews'].pop()
    if fault=='duplicate_review':r['scope_reviews'].append(deepcopy(r['scope_reviews'][0]))
    if fault=='missing_range':r['scope_reviews'][0]['groups']=[]
    if fault=='excluded_range':r['scope_reviews'][0]['groups'][0].update(disposition='EXCLUDE',claim_refs=[])
    if fault=='wrong_issue':v['claims'][0]['issue_refs']=['other']
    if fault=='unacquired':target['acquired']=False;c['need_continuity']['scope_input_hash']=digest([c['need_continuity']['targets'],o])
    if fault=='tampered_original':o[0]['text']='changed'
    if fault=='open_need':r['needs'][0].update(status='OPEN',material=True)
    if fault=='missing_judgment':r['judgments'].pop()
    if fault=='unknown_basis':r['needs'][0]['basis_refs'].append('unknown')
    if fault=='claim_changed':v['claims'][0]['evidence_refs']=[]
    if fault=='gap_deleted':r['needs'][0]['gap_indices']=[1]
    before=deepcopy((c,o,v))
    with pytest.raises((ProposalError,ContractError,ValidationError)):
        fixed,_=nc.bind_reviewed_targets(v,c,o);final.validate_review(fixed,c,o)
    assert (c,o,v)==before

def test_ambiguous_target_is_not_arbitrarily_selected():
    c,o,v=historical();original=c['need_continuity']['targets'][0]
    target=deepcopy(original);target['id']='GNanother'
    c['need_continuity']['targets'].append(target)
    scope=deepcopy(v['read_judgment_review']['scope_reviews'][0]);scope['target_id']=target['id']
    v['read_judgment_review']['scope_reviews'].append(scope)
    c['need_continuity']['scope_input_hash']=digest([c['need_continuity']['targets'],o])
    fixed,receipt=nc.bind_reviewed_targets(v,c,o)
    assert fixed==v and receipt is None
    with pytest.raises(ProposalError):final.validate_review(fixed,c,o)

def test_exhausted_review_delivers_sources_then_fact_followup_in_same_case(tmp_path,term_glossary,monkeypatch):
    from need_continuity_fixture import run_api
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT',os.environ['LOOP_TEST_CODE_ROOT'])
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    def exercise(api,t,request,runtime):
        from api_fixture_integrated import decode
        from test_legal_agent_double_harness import wire
        from test_agent_loop_fault_recovery import journal_snapshot
        from semantic_runtime.legal_agent.shortcut_store import selected_store
        from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
        original=t.send_once;sent=[];reject=True;first_goal=None
        def send(*,body,ticket):
            nonlocal reject
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            phase=view.get('source_stage') or view['phase'];sent.append(phase)
            if phase.startswith('source-request-route'):
                return wire({'mode':'CASE','answer':'','reason':'같은 사건의 사실 보완'})
            if phase=='memory-command-check':
                assert view['command']['method_id']=='FACT_UPDATE'
                return wire({'valid':True,'reason':'사용자의 명시 승인 사실 보완과 같은 사건 대상이 일치한다.'})
            if not reject and phase.startswith('memory-assess'):
                from api_fixture_integrated import to_wire
                from test_source_span_norm import proposal
                from test_native import coverage_rows
                from need_continuity_fixture import change_review
                from scope_review_fixture import scope_rows
                assert any(f['value']=='서면 승인을 받음' for f in view['current_facts'])
                option=next(o for o in view['evidence_options'] if '서면 승인' in o['text'])
                value=proposal('서면 승인을 받아야 한다.','OBLIGATION',[option['id']],option['id'])
                value.pop('disposition');value['issue_assessments'][0].update(status='COVERED',reason='현재 원문에서 일반 승인 기준 확인')
                value['gaps']=[];ctx=view['read_judgments'];used={option['id']}
                review={'judgments':[],'needs':[],'conflicts':[]}
                for h in ctx['judgments']:
                    refs=sorted(used & set(h['available_evidence_refs']))
                    row={'id':h['id'],'disposition':'USE' if refs else 'NOT_USED','claim_refs':['C1'] if refs else [],
                         'basis_refs':refs,'reason':'현재 승인 기준과 원문을 다시 대조했다.'}
                    if not refs and h.get('change_from'):row['change_review']=change_review(h)
                    review['judgments'].append(row)
                for n in ctx['needs']:
                    review['needs'].append({'id':n['id'],'status':'RESOLVED','material':False,
                        'reason':'현재 승인 기준 원문으로 확인했다.','basis_refs':[option['id']],
                        'claim_refs':['C1'],'gap_indices':[],'target_refs':n.get('target_refs',[]),'scope_quote':''})
                assert not ctx['conflicts'];scope_rows(value,ctx,review)
                value['read_judgment_review']=review;value['requirement_review']=coverage_rows(value,view['requirement_context'])
                t.calls.append(phase);t.views.append(deepcopy(view))
                return wire(to_wire(value))
            if phase.startswith('memory-resolve'):
                goal=view['goals'][0]
                assert goal['id']==first_goal
                assert goal['previous_response']['review_status']=='INCOMPLETE'
                return wire({'method_id':'FACT_UPDATE','target':goal['id'],'knowledge_id':None,
                    'stage':'ASSESS','task':None,'source_category':'KEEP','document_scope_mode':'KEEP',
                    'document_ids':None,'facts':[{'name':'승인 여부','value':'서면 승인을 받음'}],
                    'queries':None,'restore_event':None,'restore_fields':[], 'format':'prose',
                    'reason':'사용자가 같은 사건의 승인 사실을 추가했다.',
                    'search_scope_change':{'operation':'KEEP','targets':[],'user_quote':''}})
            raw=original(body=body,ticket=ticket)
            if reject and phase.startswith('memory-assess'):
                value=json.loads(raw['body_json']['choices'][0]['message']['content'])
                value['read_judgment_review']['needs']=[]
                raw['body_json']['choices'][0]['message']['content']=json.dumps(value,ensure_ascii=False)
            return raw
        t.send_once=send
        response=api.post('/v1/rag/ask',json=request);assert response.status_code==200,response.text
        result=response.json();first_goal=result['goal_id'];assessment=result['assembly']['term_agent']['accepted_outcome']
        assert assessment['disposition']=='LIMITED_ANSWER' and not result['answer']['claims']
        assert assessment['answer_coverage']!='COVERED' and assessment['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED'
        assert '검토를 완료하지 못했습니다' in result['answer']['text']
        assert any('같은 대화' in s['reason'] for s in result['answer']['unresolved'])
        assert sum(p.startswith('memory-assess') for p in sent)==2
        assert not any('compose' in p for p in sent)
        before=len(sent);again=api.post('/v1/rag/ask',json=request)
        assert again.status_code==200 and again.json()['answer']==result['answer'] and len(sent)==before
        cases=ShortcutCases(selected_store(runtime),None,None)
        try:
            assert cases.db.execute("SELECT COUNT(*) FROM sw_event WHERE kind='ANSWER_PUBLISHED'").fetchone()[0]==0
        finally:cases.close()
        reject=False;follow={**request,'request_id':'fact-followup','question':'같은 사건입니다. 서면 승인을 받았다는 사실을 추가해서 판단해 주세요.'}
        next_response=api.post('/v1/rag/ask',json=follow);assert next_response.status_code==200,next_response.text
        next_result=next_response.json();assert next_result['goal_id']==first_goal
        assert next_result['investigation_id']==result['investigation_id']
        assert next_result['revision']>result['revision'] and next_result['answer']['claims']
        assert not any(p.startswith(('source-law','memory-plan','memory-recall')) for p in sent[before:])
        more=len(sent);assert api.post('/v1/rag/ask',json=follow).status_code==200 and len(sent)==more
        journals=journal_snapshot(runtime)
        assert any(k=='ASSESSMENT_REVIEW_STOPPED' for r in journals for k,_ in r['events'])
        outcome={'first_calls':before,'followup_calls':more-before,'same_case':True,
                 'first_phases':sent[:before],'followup_phases':sent[before:],
                 'first_status':'SOURCE_ONLY_REVIEW_INCOMPLETE','followup_status':'ANSWER',
                 'duplicate_extra_calls':0,'external_model_calls':0}
        (tmp_path/'multiturn-outcome.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+'\n')
        return outcome
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)
