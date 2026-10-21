"""Prospective software-boundary checks, to be frozen before first execution.

These are fictional source/metadata cases, NOT legal-answer holdout or quality
certification. The selected real generation currently has 0 / 1547 documents
with workflow_version.verified=true and valid_from; real applicability remains
unconfirmed. No source metadata is repaired or promoted by these tests.

Run only with the selected frozen candidate's import/pin receipt. Public
interfaces used: presentation.packets/view and projection.prepare. The source
reader is synthetic; native whole-span receipt construction remains exercised.
"""
from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest

from semantic_runtime.legal_agent.errors import BudgetExhausted
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.source_tools import canonical_evidence
from semantic_runtime.workflow_bridge import SourcePort
from workflow import presentation as p
from workflow.adapters.projection import prepare, project_sources
from workflow.contracts import WorkflowError
from workflow.risk_team_compare_workflow.contracts import BASIS


class Services:
    # presentation resolves the current semantic runtime from the service class.
    __module__ = 'semantic_runtime.workflow_bridge'
    def __init__(self, limit):
        self.profile={'max_context_chars':limit}


def source(ident, texts, *, verified=False, complete=True):
    spans=[]
    for n,text in enumerate(texts):
        spans.append({'block_id':ident+'-block-'+str(n),'start_cp':0,'end_cp':len(text),
                      'text':text,'block_hash':text_hash(text),'span_hash':text_hash(text)})
    origin={'source_id':ident,'document_id':'doc-'+ident,'unit_id':'unit-'+ident,
        'generation_id':'prospective-synthetic-generation','source_artifact_hash':text_hash('raw-'+ident),
        'role':'body','temporal_status':'UNKNOWN',
        'metadata':{'document_name':'가상 '+ident,'heading':'가상 대상 조항','read_location':'가상 대상 조항'}}
    e=canonical_evidence(origin,spans)
    return {**e,'side':'internal' if ident.startswith('I') else 'external',
            'text':'\n'.join(texts),'citation_names':['가상 '+ident],
            'version_verified':verified,'source_complete':complete,
            'parent_issue_refs':['criterion-A','exception-B']}


def harness(monkeypatch, values, *, limit=100000):
    declared=deepcopy(values);saved=[];receipts=[];split_calls=[];generated={}
    def evidence(ctx,state,ids=None):
        items=declared+list(generated.values())
        return deepcopy([e for e in items if ids is None or e['evidence_id'] in ids])
    monkeypatch.setattr(p,'evidence',evidence)
    class Port:
        services=Services(limit)
        def split_evidence(self, original, max_chars):
            split_calls.append(original['evidence_id'])
            declared_spans={json.dumps(s,sort_keys=True,ensure_ascii=False) for s in original['spans']}
            def verify(item):
                assert canonical_evidence(item,item['spans'])==item
                assert all(json.dumps(s,sort_keys=True,ensure_ascii=False) in declared_spans for s in item['spans'])
            def record(action,result,items,*,verify):
                for item in items:
                    verify(item)
                    generated[item['evidence_id']]={**item,'side':original['side'],
                        'text':'\n'.join(s['text'] for s in item['spans']),
                        'citation_names':original['citation_names'],
                        'source_complete':original['source_complete'],
                        'version_verified':original['version_verified']}
                receipts.append(deepcopy({'action':action,'result':result,'items':items}))
            native=NS(session=NS(verify=verify,repo=NS(record_observation=record)),
                      evidence=lambda:deepcopy(list(generated.values())))
            return SourcePort.split_evidence(native,original,max_chars)
    port=Port()
    ctx=NS(request={'question':'가상 기준과 예외의 차이를 비교한다.','as_of':'2027-02-19'},
           context=NS(deadline_at='2027-02-19T00:00:00+00:00'),
           rag=NS(port=port,evidence=lambda:deepcopy(declared+list(generated.values()))),
           repo=NS(work=NS(budget=lambda:{}),save=lambda state:saved.append(deepcopy(state))),
           model=NS(services=port.services))
    state={'scope':{'issues':[{'id':'criterion-A','label':'가상 기준','numeric':True},
                             {'id':'exception-B','label':'가상 예외','numeric':False}],
                    'missing_user_facts':[]},'gaps':[],'rag_results':{},
           'context_evidence':[e['evidence_id'] for e in values]}
    return ctx,state,receipts,split_calls


def projected(data):
    return prepare('BASIS',data,BASIS)[0]


def packet_texts(packets):
    return [option['text'] for data,_ in packets for s in projected(data)['sources']
            for option in s['citation_options']]


@pytest.mark.parametrize('text',[
    '정의와 조건의 원문. '*1300+'마지막 예외: A 제외.',
    ('줄바꿈\r\n따옴표 "\\"\t'*1500)+'끝에만 있는 적용 범위.',
    ('規定🙂조문\u0301 '*1700)+'최종 단서.',
])
def test_single_whole_span_that_fits_projected_payload_keeps_complete_packet(monkeypatch,text):
    item=source('I-alpha',[text])
    ctx,state,_,splits=harness(monkeypatch,[item])
    raw=p.view(ctx,state,[item])
    wire_size=p.size(projected(raw))
    ctx.model.services.profile['max_context_chars']=wire_size+6000+3000
    assert p.size(raw)>ctx.model.services.profile['max_context_chars']-6000
    before=deepcopy(item)
    packets=p.packets(ctx,state,'BASIS')
    assert len(packets)==1 and packets[0][0]['packet']['dependency_closure_complete']
    assert packet_texts(packets)==[text] and item==before
    assert splits==[]
    assert p.size(projected(packets[0][0]))<=ctx.model.services.profile['max_context_chars']-6000


def test_multiple_atomic_blocks_make_lossless_receipts_when_whole_source_cannot_fit(monkeypatch):
    texts=['첫째 조건. '+'A'*10500,'독립 예외. '+'B'*10500,'마지막 정의. '+'C'*10500]
    original=source('I-multi',texts)
    ctx,state,receipts,_=harness(monkeypatch,[original],limit=30000)
    packets=p.packets(ctx,state,'BASIS')
    assert len(packets)>1 and all(not data['packet']['dependency_closure_complete'] for data,_ in packets)
    assert sorted(packet_texts(packets))==sorted(texts)
    assert len(receipts)==1
    items=receipts[0]['items']
    assert len(items)==len(texts) and all(len(item['spans'])==1 for item in items)
    assert {json.dumps(item['spans'][0],sort_keys=True) for item in items}=={
        json.dumps(span,sort_keys=True) for span in original['spans']}
    assert all(s['parent_issue_refs']==['criterion-A','exception-B'] for data,_ in packets for s in data['sources'])
    assert all(p.size(projected(data))<=24000 for data,_ in packets)


def test_equal_text_from_two_distinct_documents_keeps_distinct_citations_across_packets(monkeypatch):
    text='공유된 형태의 가상 규정. '+'Z'*17500
    a,b=source('I-shared',[text]),source('E-shared',[text])
    ctx,state,_,_=harness(monkeypatch,[a,b],limit=30000)
    packets=p.packets(ctx,state,'BASIS')
    assert len(packets)==2 and packet_texts(packets)==[text,text]
    bindings=[];catalogues=[]
    for data,_ in packets:
        wire,_,_,receipt=prepare('BASIS',data,BASIS)
        same_wire,citations=project_sources(data)
        assert same_wire==wire
        catalogues.append(receipt['catalogue_hash'])
        for s in wire['sources']:
            for o in s['citation_options']:
                # Short labels may repeat across packets; each packet's exact
                # catalogue must still bind its own distinct native evidence.
                value=citations[o['citation_id']]
                assert value=={'evidence':s['evidence_id'],'quote':text}
                bindings.append(value['evidence'])
    assert set(bindings)=={a['evidence_id'],b['evidence_id']}
    assert len(set(catalogues))==2
    assert all(not data['packet']['dependency_closure_complete'] for data,_ in packets)


def test_atomic_source_above_real_payload_capacity_is_explicitly_incomplete(monkeypatch):
    item=source('I-oversize',['불가분 원문. '+'長'*41000])
    ctx,state,receipts,_=harness(monkeypatch,[item],limit=26000)
    before=deepcopy(item)
    with pytest.raises((BudgetExhausted,WorkflowError)):
        p.packets(ctx,state,'BASIS')
    assert item==before and not receipts
    assert not state.get('packet_evidence')


def test_projected_packet_retains_repair_reserve_including_escaped_original(monkeypatch):
    item=source('E-repair',['"\\\n'*5200+'예외 끝'])
    ctx,state,_,_=harness(monkeypatch,[item])
    ctx.model.services.profile['max_context_chars']=p.size(projected(p.view(ctx,state,[item])))+9000
    packet=p.packets(ctx,state,'BASIS')[0][0]
    wire=projected(packet)
    repair={**wire,'repair':{'error':{'message':'검증 오류. '*300},
                           'instruction':'Correct the entire proposal using the same evidence and scope.'}}
    assert p.size(wire)<=ctx.model.services.profile['max_context_chars']-6000
    assert p.size(repair)<=ctx.model.services.profile['max_context_chars']-2000
    assert packet_texts([(packet,[])])==[item['spans'][0]['text']]


def test_restored_multiissue_packet_identity_preserves_source_uncertainty(monkeypatch):
    values=[source('I-restart',['가상 조건. '+'甲'*6500],verified=False),
            source('E-restart',['가상 예외. '+'乙'*6500],verified=False,complete=False)]
    ctx,state,_,_=harness(monkeypatch,values,limit=45000)
    first=p.packets(ctx,state,'COMPARE:pair-A',ids={e['evidence_id'] for e in values})
    restored=json.loads(json.dumps(state))
    second=p.packets(ctx,restored,'COMPARE:pair-A',ids={e['evidence_id'] for e in values})
    assert [x[0]['packet'] for x in first]==[x[0]['packet'] for x in second]
    assert packet_texts(first)==packet_texts(second)
    selected={s['evidence_id']:s for data,_ in second for s in data['sources']}
    assert not any(s['version_verified'] for s in selected.values())
    assert selected[values[1]['evidence_id']]['source_complete'] is False
    assert all(s['parent_issue_refs']==['criterion-A','exception-B'] for s in selected.values())


def test_exact_wire_boundary_includes_packet_metadata_and_preserves_repair_reserve(monkeypatch):
    item=source('E-boundary',['검증할 마지막 조건. '+'界'*7200])
    ctx,state,_,splits=harness(monkeypatch,[item])
    original=p.packets(ctx,state,'BASIS')[0][0]
    exact=p.size(projected(original))
    assert p.projected_size(original)==exact
    ctx.model.services.profile['max_context_chars']=exact+6000
    fitted=p.packets(ctx,state,'BASIS')
    assert p.size(projected(fitted[0][0]))==exact
    assert fitted[0][0]['packet']['dependency_closure_complete'] is True
    ctx.model.services.profile['max_context_chars']-=1
    with pytest.raises(WorkflowError):p.packets(ctx,state,'BASIS')
    assert splits==[] and packet_texts(fitted)==[item['spans'][0]['text']]


def test_question_over_half_budget_still_allows_complete_original_units(monkeypatch):
    values=[source('I-long-question',['조건 A. '+'甲'*5000]),
            source('E-long-question',['조건 B. '+'乙'*5000])]
    ctx,state,_,splits=harness(monkeypatch,values,limit=30000)
    ctx.request['question']='허용된 긴 질문. '+'질'*14000
    assert p.projected_size(p.view(ctx,state,[],compact=True))>24000//2
    assert p.projected_size(p.view(ctx,state,values))>24000
    packets=p.packets(ctx,state,'BASIS')
    assert len(packets)==2 and splits==[]
    assert packet_texts(packets)==[e['spans'][0]['text'] for e in values]
    assert all(data['question']==ctx.request['question'] for data,_ in packets)
    assert all(p.size(projected(data))<=24000 for data,_ in packets)


def test_escaped_atomic_span_uses_json_payload_cost_without_cutting_text(monkeypatch):
    item=source('I-escaped',['"\\\n'*9000+'마지막 예외'])
    ctx,state,receipts,splits=harness(monkeypatch,[item],limit=50000)
    before=deepcopy(item)
    assert len(item['spans'][0]['text'])<44000
    assert p.size(projected(p.view(ctx,state,[item])))>44000
    with pytest.raises(WorkflowError):p.packets(ctx,state,'BASIS')
    assert item==before and not receipts and not splits


def test_two_digit_packet_count_is_included_in_each_exact_payload(monkeypatch):
    values=[source('I-number-'+str(i),['원문 '+str(i)+'. '+'文'*2200]) for i in range(12)]
    ctx,state,_,splits=harness(monkeypatch,values,limit=11000)
    packets=p.packets(ctx,state,'BASIS')
    assert len(packets)==12 and splits==[]
    assert [data['packet']['index'] for data,_ in packets]==list(range(12))
    assert all(data['packet']['count']==12 for data,_ in packets)
    assert all(p.size(projected(data))<=5000 for data,_ in packets)
    assert packet_texts(packets)==[e['spans'][0]['text'] for e in values]
