"""Actual HTTP/wire and integrity contracts. Synthetic sources and model only."""
import ast
from copy import deepcopy
import inspect,json,sqlite3
from pathlib import Path
import pytest
from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_assessment as oa, ontology_context as oc
from semantic_runtime.legal_agent import completion_contracts as cc, compact_model_input as minimal
from semantic_runtime.legal_agent import evidence_inventory as inventory
from semantic_runtime.legal_agent.errors import ContractError
from test_ontology_context import inv, bundle, configure, plans, direct_scope, original, connected, definition_source


def prepared(i,gid):
    configure(i,[bundle(i.s)])
    i.s.profile['candidate_navigation'].update(ontology_enabled=True,ontology_direct_assessment=True,completion_contract=True,
        ontology_context=deepcopy(i.policy['ontology_context']))
    oc.acquire(i,[gid])
    sources,evidence,omitted=inventory.acquired_originals_for(i.s,i.p,100000)
    return sources,cc.evidence_options(sources)


def test_projection_has_current_refs_and_one_original_copy(inv):
    i,gid=inv;sources,options=prepared(i,gid);before=deepcopy(i.p)
    out=oa.project(i.s,i.p,sources,options);card=out['ontology_bundles'][0]
    assert card['status']=='COMPLETE'
    assert all('text' not in p and p['source_refs'] for p in card['payload']['provisions'])
    assert {ref for p in card['payload']['provisions'] for ref in p['source_refs']} <= {o['id'] for o in options}
    assert i.p==before and out['ontology_assessment']['automatic_adoption'] is False


@pytest.mark.parametrize('missing',['source','option','option_piece'])
def test_omission_keeps_knowledge_pending(inv,missing):
    i,gid=inv;sources,options=prepared(i,gid)
    sid=sources[-1]['source_id']
    if missing=='source':sources=sources[:-1];options=[o for o in options if o['source_id']!=sid]
    elif missing=='option':options=[o for o in options if o['source_id']!=sid]
    else:
        option=next(o for o in options if o['source_id']==sid)
        option['end_cp']-=1;option['text']=option['text'][:-1]
    out=oa.project(i.s,i.p,sources,options);card=out['ontology_bundles'][0]
    assert card['status']=='PARTIAL' and not card['payload']['review_notes']
    pending=[p for p in card['payload']['provisions'] if not p['source_refs']]
    assert pending and all('value' not in p and 'note' not in p for p in pending)
    assert all(p['acquisition_status']=='ACQUIRED' and p['delivery_status']=='NOT_SENT' for p in pending)
    assert not any(r['reason']=='SOURCE_NOT_ACQUIRED' for r in card['payload']['unresolved'])
    assert card['payload']['review_notes_status']=='WITHHELD_UNTIL_ALL_ORIGINALS_PRESENTED'


@pytest.mark.parametrize('change',['snapshot','plan','anchor','extent','source','text','option_text','acl'])
def test_binding_corruption_is_rejected(inv,change):
    i,gid=inv;sources,options=prepared(i,gid);row=plans(i)[0]['fragments'][0]
    if change=='snapshot':i.p['ontology_context']['snapshot_sha256']='0'*64
    elif change=='plan':plans(i)[0]['id']='wrong'
    elif change=='anchor':row['anchor']['label']='changed'
    elif change=='extent':row['block_ids']=['unread']
    elif change=='source':row['source_id']='unknown'
    elif change=='text':
        source=next(s for s in sources if s['source_id']==row['source_id'])
        span=next(p for p in source['adopted_spans'] if p['evidence_id'] in row['evidence_ids'])
        span['text']='X'+span['text'][1:]
    elif change=='option_text':
        option=next(o for o in options if o['evidence_id'] in row['evidence_ids'])
        option['text']='X'+option['text'][1:]
    elif change=='acl':i.s.scope=set()
    with pytest.raises(ContractError):oa.project(i.s,i.p,sources,options)


def test_disabled_and_no_bundle_keep_old_route(inv):
    i,gid=inv
    assert not oa.ready(i) and oa.project(i.s,i.p,[],[])=={}
    sources,options=prepared(i,gid)
    i.s.profile['candidate_navigation']['ontology_context']={'mode':'A0'}
    assert not oa.ready(i) and oa.project(i.s,i.p,sources,options)=={}


def test_same_material_handoff_cannot_loop_and_resume_keeps_counter(inv):
    from semantic_runtime.legal_agent.law_navigation import Investigation
    i,gid=inv;sources,options=prepared(i,gid)
    i.modern=True;i.question='합성 기준';i.acquired_handoff_result=lambda *args:args
    i.policy['ontology_context']=deepcopy(i.s.profile['candidate_navigation']['ontology_context'])
    i.p['reentry_counters']={'ASSESS_GAP_REENTRY':1}
    before=deepcopy(i.p['read_state'])
    assert Investigation.assessment_handoff(i) is not None
    i.p=deepcopy(i.p)
    assert Investigation.assessment_handoff(i) is not None  # same uncommitted handoff resumes
    i.p['assessment_reviews']=[{'assessment_hash':'next-assessment'}]
    assert Investigation.assessment_handoff(i) is None  # ASSESS consumed this material
    assert len(i.p['assessment_handoffs'])==1 and i.p['read_state']==before
    assert i.p['reentry_counters']=={'ASSESS_GAP_REENTRY':1}


