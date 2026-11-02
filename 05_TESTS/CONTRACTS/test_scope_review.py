from copy import deepcopy
from types import SimpleNamespace as NS
import json, os, gzip
from pathlib import Path
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import need_continuity as nc, read_judgment_final as final
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from jsonschema import ValidationError


def fixture():
    specs=[('a','h','운영기준'),('a','one','담당자가 요청을 승인한다.'),('a','two','긴급 요청은 관리자가 승인한다.'),
           ('b','h','처리안내'),('b','one','처리 내용을 기록한다.'),('b','two','종이 문서는 별도 창고에 보관한다.')]
    opts=[{'id':'S'+str(i),'document_id':d,'source_id':'source-'+d,'block_id':b,'start_cp':0,'end_cp':len(t),'text':t,'text_hash':digest(t)} for i,(d,b,t) in enumerate(specs,1)]
    targets=[{'id':'GN'+d,'kind':'SOURCE_GOAL','origin_id':'goal-'+d,'document_id':d,'issue_refs':['Q1' if d=='a' else 'Q2'],
        'acquired':True,'available_complete':True,'available_evidence_refs':[o['id'] for o in opts if o['document_id']==d],
        'expected':[{k:o[k] for k in ('block_id','start_cp','end_cp')} for o in opts if o['document_id']==d]} for d in ('a','b')]
    ctx={'change_review':False,'judgments':[{'id':'J1','available_evidence_refs':['S1','S2','S3']},{'id':'J2','available_evidence_refs':['S4','S5','S6']}],
        'needs':[{'id':'N1','origin':'ANSWER_PROGRESS','issue_refs':['Q1']},{'id':'N2','origin':'ANSWER_PROGRESS','issue_refs':['Q2']},
                 *[{'id':t['id'],'origin':'SOURCE_GOAL','issue_refs':t['issue_refs'],'target_refs':[t['id']]} for t in targets]],'conflicts':[],
        'need_continuity':{'version':nc.VERSION,'question':'전자 요청의 일반 승인과 긴급 처리·기록 절차는?','issue_refs':['Q1','Q2'],'targets':targets,'scope_input_hash':digest([targets,opts])}}
    def n(id,claims,refs,ts):return {'id':id,'status':'RESOLVED','material':False,'reason':'현재 원문 검토','basis_refs':refs,'claim_refs':claims,'target_refs':ts,'gap_indices':[],'scope_quote':''}
    def g(refs,cs,q,dis='USE'):return {'basis_refs':refs,'claim_refs':cs,'issue_refs':q,'disposition':dis,'reason':'제시된 원문을 요청의 범위와 대조','gap_indices':[],'scope_quote':''}
    v={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S2']},{'claim_id':'C2','issue_refs':['Q2'],'evidence_refs':['S3','S5']}],
       'issue_assessments':[{'issue_id':'Q1','status':'COVERED'},{'issue_id':'Q2','status':'COVERED'}],'gaps':[],
       'read_judgment_review':{'judgments':[{'id':'J1','disposition':'USE','basis_refs':['S2','S3'],'claim_refs':['C1','C2'],'reason':'현재 내용 사용'},
                                          {'id':'J2','disposition':'USE','basis_refs':['S5'],'claim_refs':['C2'],'reason':'현재 내용 사용'}],
          'needs':[n('N1',['C1'],['S2'],['GNa']),n('N2',['C2'],['S3','S5'],['GNa','GNb']),
                   n('GNa',['C1','C2'],['S1','S2','S3'],['GNa']),n('GNb',['C2'],['S4','S5','S6'],['GNb'])],
          'conflicts':[], 'scope_reviews':[{'target_id':'GNa','groups':[g(['S1'],[],['Q1'],'EXCLUDE'),g(['S2'],['C1'],['Q1']),g(['S3'],['C2'],['Q2'])]},
                                         {'target_id':'GNb','groups':[g(['S4','S6'],[],['Q2'],'EXCLUDE'),g(['S5'],['C2'],['Q2'])]}]}}
    return ctx,opts,v


def verify(ctx,opts,v):final.validate_review(v,ctx,opts)

def seal(ctx,opts):ctx['need_continuity']['scope_input_hash']=digest([ctx['need_continuity']['targets'],opts])

def test_full_read_subset_citation_multiissue_and_multisource():
    c,o,v=fixture();before=deepcopy((c,o,v));verify(c,o,v);assert (c,o,v)==before
    assert v['claims'][0]['evidence_refs']==['S2']  # no forced title or other issue

@pytest.mark.parametrize('fault',['missing_review','duplicate_review','missing_range','duplicate_range','foreign_document','missing_original','unacquired',
 'claim_other_issue','borrowed_judgment','unrelated_claim','fake_claim','foreign_need_target','omit_need','exclude_with_claim','use_uncited_range',
 'exclude_adopted','empty_reason','fake_quote','open_covered','open_without_gap','scope_binding','version','need_claim_does_not_use_target'])
def test_rejects_invalid_scope_and_claim_edges(fault):
    c,o,v=fixture();r=v['read_judgment_review'];groups=r['scope_reviews'][0]['groups']
    if fault=='missing_review':r['scope_reviews'].pop()
    if fault=='duplicate_review':r['scope_reviews'][1]=deepcopy(r['scope_reviews'][0])
    if fault=='missing_range':groups.pop(0)
    if fault=='duplicate_range':groups[1]['basis_refs'].append('S1')
    if fault=='foreign_document':groups[0]['basis_refs']=['S4']
    if fault=='missing_original':c['need_continuity']['targets'][0]['expected'].append({'block_id':'unread-exception','start_cp':0,'end_cp':4});seal(c,o)
    if fault=='unacquired':c['need_continuity']['targets'][0]['acquired']=False;seal(c,o)
    if fault=='claim_other_issue':r['needs'][0]['claim_refs']=['C2'];r['needs'][0]['basis_refs']=['S3']
    if fault=='borrowed_judgment':r['judgments'][0]['basis_refs']=['S2','S5'];r['judgments'][1]['basis_refs']=['S3','S5']
    if fault=='unrelated_claim':v['claims'][0]['evidence_refs']=['S3']
    if fault=='fake_claim':groups[1]['claim_refs']=['C404']
    if fault=='foreign_need_target':r['needs'][0]['target_refs']=['GNb']
    if fault=='omit_need':r['needs'].pop(0)
    if fault=='exclude_with_claim':groups[0]['claim_refs']=['C1']
    if fault=='use_uncited_range':groups[0].update(disposition='USE',claim_refs=['C1'])
    if fault=='exclude_adopted':groups[1].update(disposition='EXCLUDE',claim_refs=[])
    if fault=='empty_reason':groups[0]['reason']=' '
    if fault=='fake_quote':groups[0]['scope_quote']='사용자가 말하지 않은 범위'
    if fault.startswith('open_'):
        groups[1].update(disposition='OPEN',claim_refs=[],gap_indices=[1]);v['gaps']=[{'issue_id':'Q1','material':True}]
        if fault=='open_without_gap':v['gaps']=[]
    if fault=='scope_binding':o[0]['text']='changed'
    if fault=='version':c['need_continuity']['version']='unknown'
    if fault=='need_claim_does_not_use_target':r['needs'][0]['target_refs']=['GNb']
    with pytest.raises((ProposalError,ValidationError,ContractError)):verify(c,o,v)


def test_open_material_range_and_need_preserve_partial():
    c,o,v=fixture();r=v['read_judgment_review'];v['issue_assessments'][0]['status']='PARTIAL';v['gaps']=[{'issue_id':'Q1','material':True}]
    r['scope_reviews'][0]['groups'][1].update(disposition='OPEN',claim_refs=[],gap_indices=[1])
    # The shared target has an open portion; no dependent need asserts full completion.
    for n in r['needs'][:3]:
        if n['id']=='N2':
            n['target_refs']=['GNb'];n['basis_refs']=['S5'];continue
        n.update(status='OPEN',material=True,claim_refs=[],gap_indices=[1])
    verify(c,o,v)

@pytest.mark.parametrize('seed',[1,2,3])
def test_identifier_order_and_document_name_invariance(seed):
    c,o,v=fixture()
    tokens={x for x in ['GNa','GNb','N1','N2','C1','C2','Q1','Q2','J1','J2','a','b',*[f'S{i}' for i in range(1,7)]]}
    def transform(x):
        if isinstance(x,str):return 'renamed-'+str(seed)+'-'+x if x in tokens else x
        if isinstance(x,list):return [transform(y) for y in x]
        if isinstance(x,dict):return {k:transform(y) for k,y in x.items()}
        return x
    c,o,v=transform(c),transform(o),transform(v);o.reverse();v['claims'].reverse();v['read_judgment_review']['scope_reviews'].reverse();seal(c,o);verify(c,o,v)


def test_partitioned_spans_cover_same_source_without_forcing_extra_claims():
    c,o,v=fixture();old=o[1];cut=5;o[1]={**old,'end_cp':cut,'text':old['text'][:cut],'text_hash':digest(old['text'][:cut])};o.append({**old,'id':'S2tail','start_cp':cut,'text':old['text'][cut:],'text_hash':digest(old['text'][cut:])})
    c['need_continuity']['targets'][0]['available_evidence_refs'].append('S2tail');c['judgments'][0]['available_evidence_refs'].append('S2tail')
    for rows in (v['claims'],v['read_judgment_review']['judgments'],v['read_judgment_review']['needs'],v['read_judgment_review']['scope_reviews'][0]['groups']):
        for row in rows:
            for key in ('basis_refs','evidence_refs'):
                if 'S2' in row.get(key,[]):row[key].append('S2tail')
    seal(c,o);verify(c,o,v)


def test_old_failed_output_not_implicitly_accepted_or_mutated():
    root=Path(__file__).resolve().parents[2];p=root/'04_EXPERIMENTS/ADR/ADR-1249-model-error-sqlite-retest/artifacts/live/gold-369/canonical'
    with gzip.open(p/'005.json.gz','rt') as h:old=json.load(h)['view']
    with gzip.open(p/'005-output.json.gz','rt') as h:value=json.load(h)
    errors=[];nc.validate_review(value,old['read_judgments'],old['evidence_options'],lambda *args:errors.append(args))
    assert len(errors)==5
    ctx=deepcopy(old['read_judgments']);ctx['need_continuity'].update(version=nc.VERSION,issue_refs=[i['id'] for i in old['issues']]);seal(ctx,old['evidence_options'])
    with pytest.raises(ValidationError):verify(ctx,old['evidence_options'],value)


def test_range_error_reports_missing_ids_and_claim_error_reports_specific_pair():
    c,o,v=fixture();v['read_judgment_review']['scope_reviews'][0]['groups'].pop(0)
    with pytest.raises(ProposalError) as err:verify(c,o,v)
    assert any(x['code']=='SCOPE_RANGE_COVERAGE' and x['expected_constraint']['missing_evidence_refs']==['S1'] for x in err.value.issues)
    c,o,v=fixture();v['read_judgment_review']['needs'][0].update(claim_refs=['C2'],basis_refs=['S3'])
    with pytest.raises(ProposalError) as err:verify(c,o,v)
    assert any(x['code']=='NEED_CLAIM_LINK' and x['expected_constraint']['claim_id']=='C2' for x in err.value.issues)


def test_excluded_original_still_requires_current_bytes_and_hash():
    c,o,v=fixture();texts={(x['document_id'],x['block_id']):x['text'] for x in o}
    session=NS(store=NS(source=lambda d,b:{'text':texts[(d,b)]}))
    nc._verify_scope_originals(c['need_continuity']['targets'],o,session)
    texts[('a','h')]='다른 판본의 표제'
    with pytest.raises(ContractError):nc._verify_scope_originals(c['need_continuity']['targets'],o,session)


def test_reference_schema_projection_roundtrip_keeps_scope_dispositions():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences,expand_cards
    from semantic_runtime.legal_agent import compact_model_input as compact
    from semantic_runtime.legal_agent.minimal_output import Projection
    c,o,v=fixture()
    # Opaque canonical source identities exercise real wire aliases.
    mapping={x['id']:'S'+digest(x['id'])[:28] for x in o}
    def replace(x):
        if isinstance(x,str):return mapping.get(x,x)
        if isinstance(x,list):return [replace(y) for y in x]
        if isinstance(x,dict):return {k:replace(y) for k,y in x.items()}
        return x
    c,o,v=replace(c),replace(o),replace(v);seal(c,o)
    schema=final.review_schema(c,o)
    data={'source_stage':'memory-assess','question':c['need_continuity']['question'],'read_judgments':c,'evidence_options':o}
    refs=NavigationReferences(data);wire_schema=refs.schema(schema);wire_review=refs.view(v['read_judgment_review'])
    from jsonschema import validate
    validate(wire_review,wire_schema)
    assert refs.decode(wire_review,wire_schema)==v['read_judgment_review']
    projected=expand_cards(compact.project(refs.view(data),wire_schema))
    assert len(projected['read_judgments']['need_continuity']['targets'])==2
    assert [x['text'] for x in projected['evidence_options']]==[x['text'] for x in o]


def test_repeated_diagnostic_signature_survives_wording_change(tmp_path):
    from semantic_runtime.legal_agent import output_contract as oc
    from test_output_contract_recovery import Journal
    repo=Journal(tmp_path/'decisions.sqlite');j=oc.DecisionJournal(repo,'assessment',{'request':'bound'}, {'type':'object'})
    issue=oc.issue('SCOPE_RANGE_COVERAGE','/scope',expected={'missing_evidence_refs':['S1']})
    j.reserve(0);j.reject(0,oc.OutputContractError('first wording',[issue]),{'reason':'one'})
    assert not j.state()['repeated_failure']
    j.reserve(1);j.reject(1,oc.OutputContractError('different wording',[issue]),{'reason':'two'})
    # Reservation is a separate event; rejection compares the preceding rejection, not wording.
    assert j.state()['repeated_failure']
    repo.db.close()
