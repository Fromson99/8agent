from copy import deepcopy
import pytest
from workflow.risk_team_compare_workflow import task_board as tb, basis, compare
from workflow.adapters.projection import prepare
from workflow.risk_team_compare_workflow.contracts import COMPARE

def evidence():
    return [{'evidence_id':side,'document_id':side,'side':side,'text':text,
        'metadata':{'document_name':side},'spans':[{'text':text,'block_id':'1','start_cp':0,'end_cp':len(text)}],
        'source_complete':False,'version_verified':False} for side,text in [('internal','검토 후 보고한다.'),('external','보고한다.')]]

def citation(e):return {'evidence':e['evidence_id'],'quote':e['text']}

def item():
    es=evidence()
    return {'field':'procedure','internal':{'status':'MISSING','text':'대응 절차를 확인하지 못했습니다.','citations':[],'dependencies':[],'scope_sufficient':False,'missing':'내부 절차'},
        'external':{'status':'CONFIRMED','text':'보고한다.','citations':[citation(es[1])],'dependencies':[],'scope_sufficient':True,'missing':''},
        'content_status':'UNKNOWN','difference':'외규만 확인했습니다.','next_tasks':[]}


def test_missing_explanation_is_not_rejected():
    value={'items':[item()]};tb.checked(value,evidence(),['procedure'],{})
    assert value['items'][0]['internal']['text']

@pytest.mark.parametrize('mutation',['wrong_side','invented','altered'])
def test_original_guards_remain(mutation):
    row=item();c=row['external']['citations'][0]
    if mutation=='wrong_side':row['internal']['citations']=[deepcopy(c)]
    elif mutation=='invented':c['evidence']='missing'
    else:c['quote']='보고할 필요가 없다.'
    with pytest.raises(ValueError):tb.checked({'items':[row]},evidence(),['procedure'],{})

@pytest.mark.parametrize('new_status',['MISSING','PARTIAL','CONFIRMED','CONFLICT'])
def test_retention_does_not_invent_or_overwrite_semantic_judgment(new_status):
    old=item();old['internal'].update(status='CONFIRMED',text='검토 후 보고한다.',citations=[citation(evidence()[0])])
    new=deepcopy(old);new['internal'].update(status=new_status,text='보고에 앞서 검토한다.')
    before=deepcopy(new);tb.retain_previous(new,old)
    assert new['internal']['status']==new_status and new['internal']['text']==before['internal']['text']
    assert new['internal']['alternatives'][0]['citations']==old['internal']['citations']
    tb.retain_previous(new,old);assert len(new['internal']['alternatives'])==1


def test_locator_expands_its_own_verified_anchor():
    es=evidence();data={'sources':es,'fields':{'procedure':'절차'},'locators':{'L1':{'side':'internal','origin_evidence_id':'internal'}}}
    view,schema,expand,receipt=prepare('ITEMS',data,tb.REVIEW)
    props=schema['properties']['items']['items']['properties']
    assert set(props['internal']['properties'])=={'status','text','citations','missing'}
    assert 'anchor_ids' not in props['next_tasks']['items']['properties']
    row=item()
    for side in ('internal','external'):
        row[side].pop('dependencies');row[side].pop('scope_sufficient')
    row['external']['citations']=[{'citation_id':'C2'}]
    row['next_tasks']=[{'side':'internal','operation':'read_node','locator_id':'L1','query':'담당 확인','reason':'추가 확인'}]
    result=expand({'items':[row]});tb.checked(result,es,['procedure'],data['locators'])
    assert result['items'][0]['next_tasks'][0]['anchor_ids']==['internal']
    row['next_tasks'][0]['locator_id']='invented'
    with pytest.raises(Exception):expand({'items':[row]})


def pair():
    es=evidence();return {'pair_id':'p','issue_id':'q','internal':['internal'],'external':['external'],
        'applicability':{'status':'UNKNOWN','reason':'기준일 미확인','citations':[],'as_of':None},
        'basis_relation':'CONTENT_ONLY','basis_path':[],'comparison_eligibility':False,'reason':'내용상 대응',
        'content_difference':'내규는 사전 검토를 추가한다.','content_citations':list(map(citation,es))}

@pytest.mark.parametrize('verdict',['CONFORMS','ADDITIONAL_INTERNAL','CONFLICT','POSSIBLE_GAP','DEFERRED'])
def test_llm_verdict_not_blocked_by_metadata_or_dimension_inventory(verdict):
    es=evidence();p=pair();issues=[{'id':'q','numeric':True}]
    basis.validate({'pairs':[p],'gaps':[]},es,issues,None)
    row={'pair_id':'p','item':'절차','verdict':verdict,'difference':'모델이 확인한 범위','reason':'원문을 함께 검토',
         'citations':list(map(citation,es)),'numeric':True,'dimensions':[],'unresolved':[]}
    compare.validate({'rows':[row]},es,{'pairs':[p]},issues)
    # No semantic correction is applied to the original model verdict.
    assert row['verdict']==verdict


def test_numeric_inventory_is_optional_on_wire():
    data={'sources':evidence(),'basis':{'pairs':[pair()]},'scope':{'issues':[{'id':'q','numeric':True}]}}
    _,schema,expand,_=prepare('COMPARE',data,COMPARE)
    row={'item':'산식','verdict':'DEFERRED','difference':'분모만 미확인','reason':'일부를 비교했습니다.','citations':[{'citation_id':'C1'},{'citation_id':'C2'}],'unresolved':['분모 확인']}
    out=expand({'rows':[row],'answer':'현재 확인 범위','unresolved':['분모 확인']})
    assert out['rows'][0]['dimensions']==[] and out['rows'][0]['reason']==row['reason']


def test_unknown_citation_still_blocks_numeric_review():
    p=pair();row={'pair_id':'p','verdict':'CONFORMS','citations':list(map(citation,evidence())),
        'dimensions':[{'citations':[{'evidence':'missing','quote':'조작'}]}]}
    with pytest.raises(ValueError):compare.validate({'rows':[row]},evidence(),{'pairs':[p]},[{'id':'q','numeric':True}])
