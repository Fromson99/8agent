"""Small-model wire contracts with synthetic HTTP responses; no model experiment."""
import copy
import json

import pytest

from lawrag.core.structure import recipe_runtime as runtime, recipe_regions as regions
from lawrag.core.structure import recipe_compact as compact, recipe_template as grammar, pipeline
from .test_recipe_runtime import isolated_env, install_transport, regional_document, response
from .test_recipe_regions import make


def provider(monkeypatch, *, opinions=(), decision='reject', revise=False, noop=False,
             bad_rule=False, cutoff=False, status=None):
    monkeypatch.setenv('STRUCTURE_RECIPE_PROTOCOL', 'compact')
    seen=[]; actions=0; invalid=False
    def http(session,url,payload):
        nonlocal actions,invalid
        content=payload['messages'][1]['content']
        data=json.loads(content if isinstance(content,str) else next(b['text'] for b in content if b['type']=='text'))
        seen.append(copy.deepcopy(data))
        schema=json.loads(payload['messages'][0]['content'].rsplit('\n',1)[1])
        assert 'allOf' not in schema and 'reviewed_state_id' not in schema['properties']
        assert len(schema['properties'])<=5
        assert 'reviewed_state_id' not in data
        task=data.get('task')
        if 'outline' in data:
            value={'regions':[{'start_block':0,'template_id':'body','label':'body','reason':'continuous source'}]}
        elif task=='family_rule':
            if status:return status
            if cutoff:return response({'broken':True},'length')
            value={'parent_family':'ROOT','heading_position':'line_start','sequence':'consecutive',
                   'reset_scope':'document','rationale':'Synthetic source'}
            if bad_rule and not invalid:
                invalid=True;value['sequence']='sequential'
            if 'current_rule' in data:
                value=copy.deepcopy(data['current_rule'])
                if not noop:value['sequence']='increasing'
        elif task=='visual_opinions':
            value={'opinions':list(opinions) if actions==0 or noop else [],'summary':'Synthetic visual review'}
        elif task=='opinion_decision':
            value={'decision':decision,'blocks':[] if decision=='hold' else [0],'reason':'Synthetic evidence'}
        elif task=='review_action':
            actions+=1
            verdict='revise' if revise and (actions==1 or noop) else 'approve'
            if noop and data.get('correction'):verdict='hold'
            value={'verdict':verdict,'blocks':[0] if verdict=='revise' else [],'reason':'Synthetic decision'}
        else:raise AssertionError(data)
        body=response(value)
        body['choices'][0]['message']['content']=json.dumps(value)
        return body
    install_transport(monkeypatch,http)
    return seen


def test_explicit_compact_protocol_and_cache_identity_binds_it(monkeypatch,tmp_path):
    provider(monkeypatch)
    calls=runtime.GenosCalls(runtime.Journal(tmp_path,'default'),[])
    assert calls.protocol=='compact'
    compact_policy=runtime.policy_identity()
    monkeypatch.setenv('STRUCTURE_RECIPE_PROTOCOL','legacy')
    assert runtime.policy_identity()!=compact_policy


def test_compact_complete_pipeline_and_cache_replay(tmp_path,monkeypatch):
    seen=provider(monkeypatch,opinions=['First concern','Second concern'])
    pdf,blocks=regional_document(tmp_path)
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='compact')
    assert meta['status']=='visual_approved' and len(tree.nodes())==2
    assert [x['opinion'] for x in seen if x.get('task')=='opinion_decision']==['First concern','Second concern']
    action=next(x for x in seen if x.get('task')=='review_action')
    assert [d['opinion_id'] for d in action['opinion_decisions']]==['opinion-1','opinion-2']
    initial=next(x for x in seen if x.get('task')=='family_rule')
    assert [b['text'] for b in initial['source_blocks']]==[b.text for b in blocks]
    assert 'families' not in initial['response_example'] and initial['target_family']=='F1'
    count=len(seen)
    _,cached=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='compact')
    assert cached['reused'] and len(seen)==count


def test_accepted_opinion_regenerates_rules_and_rechecks(tmp_path,monkeypatch):
    seen=provider(monkeypatch,opinions=['Numbering allows gaps'],decision='accept',revise=True)
    pdf,blocks=regional_document(tmp_path)
    tree,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='revise')
    assert meta['status']=='visual_approved'
    updates=[x for x in seen if x.get('task')=='family_rule' and 'current_rule' in x]
    assert len(updates)==1 and updates[0]['correction_issues']
    assert sum(x.get('task')=='visual_opinions' for x in seen)==2
    assert len(tree.nodes())==2


def test_hold_opinion_prevents_approval_without_extra_action(tmp_path,monkeypatch):
    seen=provider(monkeypatch,opinions=['Cannot see parent'],decision='hold')
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview,match='reviewer_hold'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='hold')
    assert not any(x.get('task')=='review_action' for x in seen)
    assert not (tmp_path/'structure-recipes.json').exists()


def test_noop_gets_field_comparison_and_can_hold(tmp_path,monkeypatch):
    seen=provider(monkeypatch,opinions=['Needs correction'],decision='accept',revise=True,noop=True)
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview,match='reviewer_hold'):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='noop')
    retry=next(x for x in seen if x.get('task')=='review_action' and x.get('correction'))
    assert retry['rule_comparison'][0]['changed_fields']==[]
    assert 'NO_EXECUTABLE_CHANGE' in retry['correction']['message']
    assert not (tmp_path/'structure-recipes.json').exists()


def test_bad_enum_gets_short_targeted_feedback(tmp_path,monkeypatch):
    seen=provider(monkeypatch,bad_rule=True)
    pdf,blocks=regional_document(tmp_path)
    _,meta=runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='enum')
    retry=next(x for x in seen if 'previous_answer' in x)
    assert retry['correction']['path']==['sequence']
    assert retry['correction']['expected']==grammar.SEQUENCE
    assert retry['previous_answer']['sequence']=='sequential'
    assert 'repair_feedback' not in retry and meta['status']=='visual_approved'


@pytest.mark.parametrize('mode',['http','cutoff','budget'])
def test_infrastructure_and_minimal_cutoff_do_not_retry_as_schema(tmp_path,monkeypatch,mode):
    seen=provider(monkeypatch,status=401 if mode=='http' else None,cutoff=mode=='cutoff')
    if mode=='budget':monkeypatch.setenv('STRUCTURE_RECIPE_MAX_CALLS','1')
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='failure')
    assert not any('previous_answer' in x for x in seen)
    assert len(seen)==(1 if mode=='budget' else 2)
    assert not (tmp_path/'structure-recipes.json').exists()


def test_parent_swaps_are_validated_after_all_edits():
    _,recipe=make();tid='outer_number';rules=recipe['templates'][tid]['heading_rules']
    outer=next(f for f,r in rules.items() if r['parent_family']==grammar.ROOT)
    inner=next(f for f,r in rules.items() if r['parent_family']==outer)
    changes=[{'template_id':tid,'family':outer,'rule':{**rules[outer],'parent_family':inner}},
             {'template_id':tid,'family':inner,'rule':{**rules[inner],'parent_family':grammar.ROOT}}]
    changed=regions.apply(recipe,changes)
    assert changed['templates'][tid]['parent_map'][outer]==inner
    assert changed['templates'][tid]['parent_map'][inner]==grammar.ROOT
    with pytest.raises(ValueError,match='Parent cycle'):
        regions.apply(recipe,changes[:1])


def test_accepted_findings_cannot_be_approved_by_action(tmp_path,monkeypatch):
    seen=provider(monkeypatch,opinions=['Real defect'],decision='accept')
    pdf,blocks=regional_document(tmp_path)
    with pytest.raises(runtime.NeedsReview) as failure:
        runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='conflict')
    assert failure.value.diagnostic['code']=='COMPACT_RESPONSE_INVALID'
    assert sum(x.get('task')=='review_action' for x in seen)==2
    assert not (tmp_path/'structure-recipes.json').exists()


def test_aliases_are_local_and_cross_family_parents_resolve():
    from types import SimpleNamespace
    seen=[]
    def call(phase,system,data,schema,vision):
        seen.append(copy.deepcopy(data))
        target=data['target_family']
        return {'parent_family':'F2' if target=='F1' else 'ROOT','heading_position':'line_start',
                'sequence':'increasing','reset_scope':'parent','rationale':'Source'}
    rules=compact.families(call,SimpleNamespace(save=lambda *a:None),'initial',
                          {'source_blocks':[{'idx':0,'text':'Whole source'}]},['child:key','parent:key'],False)
    assert rules['child:key']['parent_family']=='parent:key'
    grammar.compile_recipe(rules,{'child:key':{},'parent:key':{}})
    assert seen[1]['completed_rules']['F1']['parent_family']=='F2'
