"""New frozen operator/framework qualification matrix. No real legal dataset."""
import ast,json,os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_context as oc,ontology_assessment as oa,ontology_scenarios as sc,law_candidates as lc
from semantic_runtime.legal_agent.errors import ContractError
from test_scenarios import fixture
from test_ontology_context import inv,bundle,configure,plans,original,connected,definition_source
from conftest import term_glossary

ROOT=Path(os.environ['QUALIFICATION_CODE_ROOT'])
@pytest.fixture
def service_policy():
    names={'_ontology_environment','_ontology_status','_investigation_profile'}
    tree=ast.parse((ROOT/'service.py').read_text());tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    ns={'os':os};exec(compile(tree,str(ROOT/'service.py'),'exec'),ns);return ns

@pytest.mark.parametrize('raw,expected',[('',None),('on',True),('off',False),('TRUE',True),('false',False),('1',True),('0',False)])
def test_operator_switch_has_strict_explicit_boolean(service_policy,monkeypatch,raw,expected):
    monkeypatch.setenv('GENOS_RAG_ONTOLOGY_ENABLED',raw)
    assert service_policy['_ontology_environment']() is expected
    profile=json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text());before=deepcopy(profile)
    out=service_policy['_investigation_profile'](profile);validated=lc.validate_policy(out['candidate_navigation'])
    assert validated['ontology_enabled'] is (expected is True) and profile==before
    assert service_policy['_ontology_status'](out)=={'enabled':expected is True,'data_configured':False,'active':False,'fallback':'ordinary-rag'}
    for key in ('max_output_tokens','max_model_attempts','max_tool_actions','wall_seconds'):assert out[key]==profile[key]

@pytest.mark.parametrize('raw',['yes','auto','disabled','ON;1'])
def test_invalid_operator_switch_is_not_silently_enabled(service_policy,monkeypatch,raw):
    monkeypatch.setenv('GENOS_RAG_ONTOLOGY_ENABLED',raw)
    with pytest.raises(ValueError):service_policy['_ontology_environment']()

@pytest.mark.parametrize('bad',['false',0,None,[]])
def test_profile_rejects_non_boolean_switch(bad):
    with pytest.raises(ContractError):lc.validate_policy({'mode':'legacy','ontology_enabled':bad})

def test_off_skips_acquisition_and_clears_stale_presentation(inv,monkeypatch):
    i,gid=inv;configure(i,[bundle(i.s)]);i.policy['ontology_enabled']=False
    # A disabled runtime does not inspect a data binding or expand originals.
    i.policy['ontology_context']['snapshot']['bundles'][0]['review_notes'].append('stale after operator off')
    monkeypatch.setattr(oc,'resolve',lambda *a:(_ for _ in ()).throw(AssertionError('unexpected original access')))
    before=deepcopy(i.p);assert oc.acquire(i,[gid])==[]
    view={'sources':[],'basis':[],'ontology_bundles':[{'old':'stale'}],'ontology_context_limits':{'old':True}}
    oc.attach(i,view);assert view=={'sources':[],'basis':[]} and i.p==before
    i.s.profile['candidate_navigation']={**i.policy,'ontology_direct_assessment':True,'completion_contract':True}
    assert oa.project(i.s,{'ontology_context':{'old':'stale'}},[],[])=={} and not oa.ready(i)

def test_empty_on_has_no_catalog_or_side_effects(inv):
    i,gid=inv;i.policy.update(ontology_enabled=True,ontology_context={'mode':'A0'})
    before=deepcopy(i.p);assert oc.acquire(i,[gid])==[] and i.p==before
    assert oc.config(i)=={'mode':'A0'}

def test_default_profile_has_no_ontology_data():
    profile=json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    p=lc.validate_policy(profile['candidate_navigation'])
    assert p['ontology_enabled'] is False and p['ontology_context']=={'mode':'A0'}
    assert p['ontology_direct_assessment'] is True
    assert not oa.enabled(profile)

def published():
    recipe,originals,fragments=fixture();recipe['authority']=sc.APPROVED_AUTHORITY
    recipe['authoring']={'approval_ref':'synthetic-publication-qualification-only'}
    return sc.compile_package(recipe,originals),fragments

def test_approved_package_preserves_authority_text_and_hash():
    package,fragments=published();catalog=sc.bind_current(package,fragments)
    assert catalog['authority']==sc.APPROVED_AUTHORITY and catalog['paths'][0]['body']==package['paths'][0]['body']
    assert package['authoring']['approval_ref']=='synthetic-publication-qualification-only'
    bad=deepcopy(package);bad['paths'][0]['body']+='changed'
    with pytest.raises(ContractError):sc.verify_package(bad)

def test_approved_authority_cannot_be_claimed_without_reference():
    recipe,originals,_=fixture();recipe['authority']=sc.APPROVED_AUTHORITY
    with pytest.raises(ContractError):sc.compile_package(recipe,originals)

def test_research_package_cannot_be_bound_to_serving(inv):
    i,_=inv;configure(i,[bundle(i.s)]);recipe,originals,_=fixture()
    config=deepcopy(i.policy['ontology_context']);config['scenario_package']=sc.compile_package(recipe,originals)
    with pytest.raises(ContractError,match='research data'):oc.configuration(config)
    package,_=published();config['scenario_package']=package
    assert oc.configuration(config)['scenario_package']==package

def test_switch_is_part_of_request_binding():
    profile=json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text());before=digest(profile)
    profile['candidate_navigation']['ontology_enabled']=True
    assert digest(profile)!=before
