"""Real synthetic journal repeat-delivery regression; no model or real corpus."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
import pytest
from conftest import term_glossary
from test_batch_reference_navigation import connected
from test_definition_context import inv, definition_source
from test_ontology_review_adr1061 import prepare
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_review as review, evidence_inventory as inventory
from semantic_runtime.legal_agent.errors import ContractError


def deliver(i, data, number):
    i.p['state_version'] = number
    data.update(presentation_id=f'P-display-{number}', state_version=number,
                source_stage='source-law-navigation-1-read-choice')
    repo=i.s.repo
    view=repo.save_view('investigate',deepcopy(data),[])
    wire={'messages':[{'role':'system','content':'Synthetic exact delivery contract.'},{'role':'user','content':json.dumps({'view':view},ensure_ascii=False)}]}
    attempt=repo.reserve_attempt(view,wire,f'redisplay-{number}',1,'investigate')
    repo.attempt_sent(attempt)
    assert repo.finish_attempt(attempt,'SUCCEEDED',{'synthetic':True},{})=='SUCCEEDED'
    inventory.record_delivery(repo,view,attempt)
    assert inventory.reconcile_delivery(i.s,i.p,data,'source-law-navigation-1-read-choice')


def test_same_original_with_changed_source_presentation_preserves_first_receipt(inv):
    i,_,data=prepare(inv)
    review.project(data);deliver(i,data,1)
    assert review.reconcile(i,data)
    first=deepcopy(i.p['ontology_context']['delivery_pages'])
    changed=deepcopy(data)
    changed['sources'][0]['presentation_id']='P-accepted-again'
    changed['ontology_review']['sources_sha256']=digest(changed['sources'])
    assert changed['ontology_review']['pages']==data['ontology_review']['pages']
    deliver(i,changed,2)
    assert review.reconcile(i,changed) is False
    assert i.p['ontology_context']['delivery_pages']==first
    assert i.s.repo.db.execute("SELECT count(*) FROM event WHERE kind='NAVIGATION_INPUT_DELIVERED'").fetchone()[0]==2
    assert i.s.repo.db.execute("SELECT count(*) FROM event WHERE kind='ONTOLOGY_REVIEW_PAGE_DELIVERED'").fetchone()[0]==1
    assert review.reconcile(i,changed) is False


@pytest.mark.parametrize('field,value',[('source_id','other'),('document_id','other'),('scope_id','other'),('text','changed')])
def test_display_equivalence_does_not_ignore_source_identity_or_content(inv,field,value):
    i,_,data=prepare(inv);review.project(data);deliver(i,data,1);assert review.reconcile(i,data)
    prior=next(iter(i.p['ontology_context']['delivery_pages'].values()))
    sources=deepcopy(data['sources']);sources[0][field]=value
    current={**prior,'sources_sha256':digest(sources),'view_id':'new','presentation_id':'new'}
    assert not review._same_repeated_delivery(i.s.repo,prior,current,sources)


def test_repeat_delivery_rejects_corrupt_legacy_view_hash(inv):
    i,_,data=prepare(inv);review.project(data);deliver(i,data,1);assert review.reconcile(i,data)
    prior=next(iter(i.p['ontology_context']['delivery_pages'].values()))
    with pytest.raises(sqlite3.IntegrityError, match='immutable model_view'):
        i.s.repo.db.execute('UPDATE model_view SET body_hash=? WHERE view_id=?',('forged',prior['view_id']))
    stored=dict(i.s.repo.db.execute('SELECT body_json,body_hash FROM model_view WHERE view_id=?',(prior['view_id'],)).fetchone())
    stored['body_hash']='forged'
    corrupt_repo=SimpleNamespace(db=SimpleNamespace(execute=lambda *a:SimpleNamespace(fetchone=lambda:stored)))
    sources=deepcopy(data['sources']);sources[0]['presentation_id']='P-new'
    current={**prior,'sources_sha256':digest(sources)}
    with pytest.raises(ContractError,match='prior delivery view hash'):
        review._same_repeated_delivery(corrupt_repo,prior,current,sources)


def test_display_equivalence_keeps_number_and_boolean_types(inv):
    i,_,data=prepare(inv)
    data['sources'][0]['page']=1
    review.project(data);deliver(i,data,1);assert review.reconcile(i,data)
    prior=next(iter(i.p['ontology_context']['delivery_pages'].values()))
    for value in (1.0, True):
        sources=deepcopy(data['sources']);sources[0]['page']=value
        current={**prior,'sources_sha256':digest(sources)}
        assert not review._same_repeated_delivery(i.s.repo,prior,current,sources)
