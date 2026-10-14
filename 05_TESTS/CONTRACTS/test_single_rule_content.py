from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import completion_v7 as v7,completion_v5 as v5,completion_contracts as cc
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from test_focused_input_modality import FocusedTransport,v6_proposal
from test_main50_request_repair import tree,GAP
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from test_unified_legal_agent import ok

def proposal(ids=('S1',),quote='신고를 갈음할 수 있다.',kind='PERMISSION'):
    p=v6_proposal(ids,quote,kind)
    for c in p['claims']:
        c.pop('conclusion');c.pop('details');c.update(content_contract=v7.CONTENT,explanation='')
    return p

ISSUES=[{'id':'Q1','question':'신고 대체'}]
OPTIONS=[{'id':'S1','source_id':'s','text':'신고를 갈음할 수 있다.'}]

def test_structured_rule_has_one_authoritative_body_and_no_narrative_duplicates():
    p=proposal();s=v7.assessment_schema(ISSUES,[],OPTIONS,[])
    value,model=v7.prepare(p,s,ISSUES,OPTIONS,[])
    a=v7.materialize(value,OPTIONS,ISSUES,model);out=cc.compose(a,cc.default_plan(a))
    cc.verify_composition(a,out);v5.verify_content(out['claims'][0])
    assert out['text'].count('신고를 갈음할 수 있다.')==1 and '허용:' in out['text']
    bad=deepcopy(p);bad['claims'][0]['explanation']='같은 내용을 요약합니다.'
    with pytest.raises(ValidationError):v7.prepare(bad,s,ISSUES,OPTIONS,[])
    bad=deepcopy(p);bad['claims'][0]['conclusion']='신고로 갈음할 수 있다는 뜻이다.'
    with pytest.raises(ValidationError):v7.prepare(bad,s,ISSUES,OPTIONS,[])
    bad=deepcopy(out['claims'][0]);bad['text']+=' 신고로 갈음할 수 있다.'
    with pytest.raises(ContractError):v5.verify_content(bad)

def test_paraphrased_repeated_source_clause_must_be_consolidated():
    p=proposal();c=deepcopy(p['claims'][0]);c['claim_id']='C2'
    c['rule']['norms'][0]['text']='이 신고로 대체하는 것이 허용된다.';p['claims'].append(c)
    with pytest.raises(ProposalError,match='Repeated source clause'):
        v7.prepare(p,v7.assessment_schema(ISSUES,[],OPTIONS,[]),ISSUES,OPTIONS,[])

def test_distinct_documents_with_same_wording_do_not_collapse():
    p=proposal();c=deepcopy(p['claims'][0]);c.update(claim_id='C2',evidence_refs=['S2']);c['rule']['norms'][0]['evidence_refs']=['S2'];p['claims'].append(c)
    options=OPTIONS+[{'id':'S2','source_id':'other','text':OPTIONS[0]['text']}]
    a,_=v7.prepare(p,v7.assessment_schema(ISSUES,[],options,[]),ISSUES,options,[])
    assert len(a['claims'])==2

def test_narrative_mode_is_single_prose_and_cannot_append_to_rules():
    p=proposal();p['claims'][0].update(rule=None,explanation='신고를 대체할 수 있다는 설명이다.')
    a,_=v7.prepare(p,v7.assessment_schema(ISSUES,[],OPTIONS,[]),ISSUES,OPTIONS,[])
    assert a['claims'][0]['text']==p['claims'][0]['explanation']
    c=proposal()['claims'][0];c['claim_id']='C2';p['claims'].append(c)
    with pytest.raises(ProposalError,match='narrative repetitions'):
        v7.prepare(p,v7.assessment_schema(ISSUES,[],OPTIONS,[]),ISSUES,OPTIONS,[])

class SingleTransport(FocusedTransport):
    def send_once(self,*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            out=proposal([o['id'] for o in v['evidence_options']],quote='승인 후 보고한다.',kind=getattr(self,'contextual_kind','UNSPECIFIED'))
            if self.reentry and not v['gap_history']:out['gaps']=[deepcopy(GAP)]
            return wire(out)
        result=super().send_once(body=body,ticket=ticket)
        if getattr(self,'direct_note',False):
            message=result['body_json']['choices'][0]['message']
            value=json.loads(message['content'])
            for row in value.get('exploration',[]):
                if row['relation']=='DIRECT':row['source_quote']='미열람 미확인 메모'
            message['content']=json.dumps(value,ensure_ascii=False)
        return result

@pytest.mark.parametrize('contextual_kind',['UNSPECIFIED','OBLIGATION'])
@pytest.mark.parametrize('direct_note',[False,True])
@pytest.mark.parametrize('reentry,reject_once',[(False,False),(True,False),(False,True)])
def test_native_v7_publication_reentry_repair_and_reuse(tmp_path,tree,reentry,reject_once,direct_note,contextual_kind):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen,idx=tree;t=SingleTransport(reentry,reject_once);t.direct_note=direct_note;t.contextual_kind=contextual_kind
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
      'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
        'completion_policy_version':cc.V7,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
      legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:{'user_id':'u','team_id':'t','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'v7','request_id':'r1'}
        out=ok(api.post('/v1/rag/ask',json=body));calls=len(t.phases)
        assert out['assembly']['term_agent']['completion_contract']==cc.V7
        assert out['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
        assert out['answer']['text'].count('승인 후 보고한다.')==1
        assert '미열람 미확인 메모' not in out['answer']['text']
        assert len(out['assembly']['term_agent']['case']['judgment_refs'])==7
        again=ok(api.post('/v1/rag/ask',json=body))
        assert again['answer']==out['answer'] and len(t.phases)==calls
        if reentry:assert t.phases.count('memory-assess')==2


@pytest.mark.parametrize('mode', ['ALL','ANY'])
def test_unary_display_preserves_raw_condition_evidence_and_historical_text(mode):
    p=proposal();c=p['claims'][0]
    leaf={'mode':'LEAF','text':'신고 조건','evidence_refs':['S1']}
    c['rule']['condition_tree']={'mode':mode,'children':[{'mode':mode,'children':[leaf]}]}
    original=deepcopy(c)
    compiled=v7.compile_claim(c)
    assert compiled['text'].count('신고 조건')==1
    assert '모두 충족' not in compiled['text'] and '하나 이상 충족' not in compiled['text']
    assert c==original and compiled['answer_content']==original
    v5.verify_content(compiled)
    historical=deepcopy(c);historical['content_contract']='source-modality-v2'
    old=v7.compile_claim(historical)
    assert old['text'].count('모두 충족' if mode=='ALL' else '하나 이상 충족')==2
    v5.verify_content(old)


def test_condition_display_keeps_mixed_and_unknown_operators():
    leaf=lambda text:{'mode':'LEAF','text':text,'evidence_refs':['S1']}
    a,b,c=map(leaf,['A','B','C'])
    mixed={'mode':'ALL','children':[a,{'mode':'ALL','children':[a,{'mode':'ANY','children':[b,c]}]}]}
    assert v7.display_condition(mixed)=={'mode':'ALL','children':[a,{'mode':'ANY','children':[b,c]}]}
    unknown={'mode':'UNKNOWN','children':[{'mode':'UNKNOWN','children':[a]}]}
    assert v7.display_condition(unknown)==unknown


def test_simplified_display_keeps_all_boolean_assignments():
    from itertools import product
    leaf=lambda text:{'mode':'LEAF','text':text,'evidence_refs':['S1']}
    a,b,c=map(leaf,['A','B','C'])
    trees=[{'mode':'ALL','children':[a,{'mode':'ALL','children':[a,{'mode':'ANY','children':[b,c]}]}]},
        {'mode':'ANY','children':[a,{'mode':'ANY','children':[b,{'mode':'ALL','children':[b,c]}]}]}]
    def evaluate(node,values):
        if node['mode']=='LEAF':return values[node['text']]
        return (all if node['mode']=='ALL' else any)(evaluate(x,values) for x in node['children'])
    for tree in trees:
        for row in product((False,True),repeat=3):
            values=dict(zip(('A','B','C'),row))
            assert evaluate(tree,values)==evaluate(v7.display_condition(tree),values)
