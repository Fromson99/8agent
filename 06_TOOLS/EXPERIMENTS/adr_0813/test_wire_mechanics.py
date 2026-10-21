"""Wire shape mechanics; fictional observations, never inferred judgments."""
from copy import deepcopy
import json

import pytest
from jsonschema import ValidationError, validate

from workflow.adapters.projection import prepare, project_sources
from workflow.risk_team_compare_workflow import compare
from workflow.risk_team_compare_workflow.contracts import BASIS, COMPARE, DIMENSIONS
from semantic_runtime.legal_agent.model_contract import genos_wire_schema
from semantic_runtime.legal_agent.output_contract import OutputContractError, strict_json


def packet(*, numeric=True):
    sources=[{'evidence_id':ident,'side':side,'document_id':side,
        'text':text,'spans':[{'text':text,'block_id':'block-'+ident,'start':0,'end':len(text)}],
        'source_complete':True,'version_verified':True}
        for ident,side,text in [('I','internal','모의 평가값은 30 이상이다.'),
                               ('E','external','모의 평가값은 45 이상이다.')]]
    citations=[{'evidence':source['evidence_id'],'quote':source['text']} for source in sources]
    pair={'pair_id':'pair-23','issue_id':'issue-17','internal':['I'],'external':['E'],
        'applicability':{'status':'MATCH','reason':'명시된 모의 대상','as_of':'2026-10-01','citations':citations},
        'basis_relation':'DIRECT','basis_path':[],'comparison_eligibility':True,
        'reason':'명시된 모의 관계','content_difference':'모의 차이','content_citations':citations}
    return {'sources':sources,'scope':{'issues':[{'id':'issue-17','numeric':numeric}]},
        'basis':{'pairs':[pair],'gaps':[]},'as_of':'2026-10-01'}


def proposal(view, *, numeric=True):
    citations=[{'citation_id':source['citation_options'][0]['citation_id']} for source in view['sources']]
    row={'item':'모의 평가값','verdict':'CONFLICT','difference':'두 원문의 모의 차이',
        'reason':'양측 원문을 비교한 모의 판단','citations':citations,'unresolved':[]}
    if numeric:
        row['dimensions']={name:{'status':'DIFFERENT' if name=='value' else 'MATCH',
            'reason':'양측 원문에서 검토한 모의 차원','citations':deepcopy(citations)} for name in DIMENSIONS}
    return {'rows':[row],'answer':'모의 판단','unresolved':[]}


@pytest.mark.parametrize('original',['조건🙂\r\n예외\t'*1300,'가'*24003])
def test_exact_native_span_is_neither_split_nor_normalized(original):
    data=packet()
    for source in data['sources']:
        source.update(text=original,spans=[{'text':original,'start':0,'end':len(original)}])
    before=deepcopy(data)
    projected,catalogue=project_sources(data)
    view,wire,expand,receipt=prepare('COMPARE',data,COMPARE)
    assert data==before and projected==view
    assert list(catalogue)==['C1','C2'] and receipt['citation_count']==2
    assert receipt['catalogue_hash']==view['citation_catalogue_hash']
    for source in view['sources']:
        assert 'text' not in source and 'spans' not in source
        assert source['citation_options']==[{'citation_id':source['citation_options'][0]['citation_id'],'text':original}]
    value=proposal(view);before_value=deepcopy(value)
    validate(value,wire)
    restored=expand(value);validate(restored,COMPARE)
    assert [citation['quote'] for citation in restored['rows'][0]['citations']]==[original,original]
    assert value==before_value


def test_labels_restart_per_packet_and_reorder_rebinds_current_catalogue():
    original=packet()
    first,_,expand_first,receipt_first=prepare('COMPARE',original,COMPARE)
    reordered=deepcopy(original);reordered['sources'].reverse()
    second,_,expand_second,receipt_second=prepare('COMPARE',reordered,COMPARE)
    assert first['sources'][0]['citation_options'][0]['citation_id']=='C1'
    assert second['sources'][0]['citation_options'][0]['citation_id']=='C1'
    assert receipt_first['catalogue_hash']!=receipt_second['catalogue_hash']
    assert receipt_first['binding_hash']!=receipt_second['binding_hash']
    assert expand_first(proposal(first))['rows'][0]['citations'][0]['evidence']=='I'
    assert expand_second(proposal(second))['rows'][0]['citations'][0]['evidence']=='E'
    # Creating a later catalogue cannot mutate an earlier expansion closure.
    assert expand_first(proposal(first))['rows'][0]['citations'][0]['evidence']=='I'


def test_span_coordinate_change_is_bound_even_when_literal_quote_is_identical():
    data=packet();view,_,_,receipt=prepare('COMPARE',data,COMPARE)
    moved=deepcopy(data);moved['sources'][0]['spans'][0]['block_id']='other-block'
    changed,_,_,other=prepare('COMPARE',moved,COMPARE)
    assert view['sources']==changed['sources']
    assert receipt['catalogue_hash']!=other['catalogue_hash']
    assert receipt['binding_hash']!=other['binding_hash']


def test_unknown_or_forged_citation_cannot_expand_against_another_catalogue():
    view,wire,expand,_=prepare('COMPARE',packet(),COMPARE)
    for citation in ({'citation_id':'C3'},{'citation_id':'C1','quote':'위조'},
                     {'evidence':'I','quote':'위조'}):
        value=proposal(view);value['rows'][0]['citations']=[citation]
        with pytest.raises(ValidationError):validate(value,wire)
        with pytest.raises(ValidationError):expand(value)


def test_exactly_one_row_restores_bound_pair_and_numeric_flag():
    data=packet();before_schema=deepcopy(COMPARE)
    view,wire,expand,_=prepare('COMPARE',data,COMPARE)
    assert COMPARE==before_schema
    assert wire['properties']['rows']['minItems']==wire['properties']['rows']['maxItems']==1
    value=proposal(view)
    restored=expand(value);validate(restored,COMPARE)
    assert restored['rows'][0]['pair_id']=='pair-23'
    assert restored['rows'][0]['numeric'] is True
    for rows in ([],[value['rows'][0],deepcopy(value['rows'][0])]):
        invalid=deepcopy(value);invalid['rows']=rows
        with pytest.raises(ValidationError):expand(invalid)
    for key,override in [('pair_id','foreign-pair'),('numeric',False)]:
        invalid=deepcopy(value);invalid['rows'][0][key]=override
        with pytest.raises(ValidationError):expand(invalid)


def test_numeric_dimension_keys_restore_only_names_and_canonical_order():
    data=packet();view,wire,expand,_=prepare('COMPARE',data,COMPARE)
    dim_schema=wire['properties']['rows']['items']['properties']['dimensions']
    assert dim_schema['type']=='object' and dim_schema['required']==list(DIMENSIONS)
    assert list(dim_schema['properties'])==list(DIMENSIONS)
    assert all(set(value['properties'])=={'status','reason','citations'} for value in dim_schema['properties'].values())
    value=proposal(view)
    value['rows'][0]['dimensions']=dict(reversed(list(value['rows'][0]['dimensions'].items())))
    restored=expand(value);validate(restored,COMPARE)
    compare.validate(restored,data['sources'],data['basis'],data['scope']['issues'])
    dimensions=restored['rows'][0]['dimensions']
    assert [dimension['name'] for dimension in dimensions]==list(DIMENSIONS)
    assert next(d for d in dimensions if d['name']=='value')['status']=='DIFFERENT'


@pytest.mark.parametrize('field',['status','reason','citations'])
def test_missing_semantic_field_is_rejected_never_filled(field):
    view,_,expand,_=prepare('COMPARE',packet(),COMPARE)
    value=proposal(view);value['rows'][0]['dimensions']['value'].pop(field)
    with pytest.raises(ValidationError):expand(value)


def test_missing_extra_or_duplicate_dimension_proposals_are_rejected():
    view,_,expand,_=prepare('COMPARE',packet(),COMPARE)
    complete=proposal(view)
    missing=deepcopy(complete);missing['rows'][0]['dimensions'].pop('value')
    extra=deepcopy(complete);extra['rows'][0]['dimensions']['value-again']=deepcopy(extra['rows'][0]['dimensions']['value'])
    embedded_name=deepcopy(complete);embedded_name['rows'][0]['dimensions']['value']['name']='definition'
    legacy_array=deepcopy(complete)
    legacy_array['rows'][0]['dimensions']=[{'name':'value',**deepcopy(complete['rows'][0]['dimensions']['value'])}]*2
    for value in (missing,extra,embedded_name,legacy_array):
        with pytest.raises(ValidationError):expand(value)
    # Product strict decoding rejects repeated object keys before dict creation.
    value_json=json.dumps(complete['rows'][0]['dimensions']['value'],ensure_ascii=False)
    duplicated='{"dimensions":{"value":'+value_json+',"value":'+value_json+'}}'
    with pytest.raises(OutputContractError):strict_json(duplicated)


def test_unknown_and_empty_citations_remain_unknown_until_canonical_validation():
    data=packet();view,_,expand,_=prepare('COMPARE',data,COMPARE)
    value=proposal(view)
    value['rows'][0]['dimensions']['value'].update(status='UNKNOWN',citations=[])
    restored=expand(value)
    dimension=next(d for d in restored['rows'][0]['dimensions'] if d['name']=='value')
    assert dimension['status']=='UNKNOWN' and dimension['citations']==[]
    with pytest.raises(ValueError,match='all dimensions resolved'):
        compare.validate(restored,data['sources'],data['basis'],data['scope']['issues'])


@pytest.mark.parametrize('explicit_empty',[True,False])
def test_nonnumeric_empty_dimensions_are_system_owned_and_legacy_compatible(explicit_empty):
    data=packet(numeric=False);view,wire,expand,_=prepare('COMPARE',data,COMPARE)
    row_schema=wire['properties']['rows']['items']
    assert 'dimensions' not in row_schema['required']
    assert row_schema['properties']['dimensions']['maxItems']==0
    assert 'dimensions' not in genos_wire_schema(wire)['properties']['rows']['items']['properties']
    value=proposal(view,numeric=False)
    if explicit_empty:value['rows'][0]['dimensions']=[]
    restored=expand(value);validate(restored,COMPARE)
    assert restored['rows'][0]['numeric'] is False and restored['rows'][0]['dimensions']==[]
    compare.validate(restored,data['sources'],data['basis'],data['scope']['issues'])


def test_nonnumeric_supplied_semantic_dimension_is_rejected_not_discarded():
    view,_,expand,_=prepare('COMPARE',packet(numeric=False),COMPARE)
    value=proposal(view,numeric=False)
    value['rows'][0]['dimensions']=[{'name':'value','status':'UNKNOWN','citations':[],'reason':'제출한 의미'}]
    with pytest.raises(ValidationError):expand(value)


def test_multiple_pairs_keep_canonical_row_identity_and_dimension_array_contract():
    data=packet();other=deepcopy(data['basis']['pairs'][0]);other['pair_id']='pair-91'
    data['basis']['pairs'].append(other)
    _,wire,_,_=prepare('COMPARE',data,COMPARE)
    rows=wire['properties']['rows'];row=rows['items']
    assert rows['minItems']==COMPARE['properties']['rows']['minItems']
    assert rows['maxItems']==COMPARE['properties']['rows']['maxItems']
    assert row['properties']['dimensions']['type']=='array'
    assert 'pair_id' in row['required'] and 'numeric' in row['required']


def test_basis_expansion_retains_existing_shape_and_system_date():
    data=packet();view,wire,expand,_=prepare('BASIS',data,BASIS)
    pair=deepcopy(data['basis']['pairs'][0]);pair.pop('pair_id');pair['applicability'].pop('as_of')
    citations=proposal(view)['rows'][0]['citations']
    pair['applicability']['citations']=citations;pair['content_citations']=citations
    value={'pairs':[pair],'gaps':[],'summary':'모의 관계'}
    validate(value,wire);restored=expand(value);validate(restored,BASIS)
    assert restored['pairs'][0]['pair_id']=='P1'
    assert restored['pairs'][0]['applicability']['as_of']==data['as_of']
    assert restored['pairs'][0]['content_citations']==data['basis']['pairs'][0]['content_citations']


def test_source_without_exact_span_is_not_assigned_an_inferred_citation():
    data={'sources':[{'evidence_id':'old','text':'좌표 없는 원문'}]}
    before=deepcopy(data);view,citations=project_sources(data)
    assert citations=={} and view==before and data==before
