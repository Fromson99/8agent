import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ssot_validator', ROOT/'06_TOOLS/AUDIT/legal_semantic_contract.py')
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
EX = ROOT/'01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2'
def get(name): return json.loads((EX/(name+'.json')).read_text())

def test_all_profiles_share_one_contract():
    assert V.check_examples() == []
    registry, schema = V.load_contract()
    assert schema['$defs']['Observation']['properties']['payload'] == schema['$defs']['CanonicalBundle']['properties']['payload']
    assert set(registry['record_profiles']) == {'OBSERVATION','CANONICAL_BUNDLE','ASSEMBLY_TEMPLATE','QUERY_PLAN','RULE_BUNDLE','FEEDBACK'}

@pytest.mark.parametrize('mutate,expected', [
    (lambda g:g['rules'][0].update(antecedent={'operator':'ALL','operands':[]}), 'schema'),
    (lambda g:g['rules'][0].update(consequent_clause_ids=['concept:0']), 'wrong_reference_type'),
    (lambda g:g['provisos'][0].update(attached_rule_id='rule:absent'), 'dangling_reference'),
    (lambda g:g['provisos'][0].update(effect_type='EXCEPTION_TO'), 'schema'),
    (lambda g:g['provisos'][0].update(dependency_relation_ids=[]), 'external_proviso_without_dependency'),
    (lambda g:g['relations'][0].update(source={'type':'Rule','id':'rule:main'}), 'proviso_dependency_source'),
    (lambda g:g['clauses'][0]['role_bindings'][0].update(evidence_ids=['evidence:1']), 'role_evidence_outside_clause'),
    (lambda g:g['evidence'][0].update(quote_sha256='0'*64), 'quote_hash'),
    (lambda g:g['evidence'][0].update(document_version_id='wrong:version'), 'evidence_outside_scope'),
    (lambda g:g['mentions'][0].update(surface='원문에없는표현'), 'mention_surface'),
    (lambda g:g['concepts'].append(copy.deepcopy(g['concepts'][0])), 'schema'),
])
def test_malformed_graph_rejected(mutate, expected):
    obs=get('observation');mutate(obs['payload'])
    assert any(expected in e for e in V.validate(obs))

def test_nested_conditions_and_unresolved_candidates_preserved():
    obs=get('observation');g=obs['payload']
    g['rules'][0]['antecedent']={'operator':'ALL','operands':[{'operator':'CLAUSE','clause_id':'clause:0'},{'operator':'ANY','operands':[{'operator':'CLAUSE','clause_id':'clause:1'},{'operator':'UNKNOWN','reason':'요건 미확인','evidence_ids':['evidence:1']}]}]}
    g['relations'][0].update(target=None,resolution='UNRESOLVED',unresolved_reason='외부 규칙 미확인')
    assert V.validate(obs)==[]

def test_source_mismatch_even_when_quote_hash_matches():
    sources=get('source-blocks');sources[0]['text']='다른 원문'
    assert any('source_quote' in e for e in V.validate(get('observation'),sources=sources))

def test_llm_cannot_return_approved_observation():
    obs=get('observation');obs['status']='ACCEPTED'
    assert V.validate(obs)

def test_partial_card_does_not_claim_complete():
    b=get('bundle');b['slots'][0].update(state='UNKNOWN',refs=[],reason='적용 범위 불명')
    ctx={'canonical':get('canonical'),'templates':[get('template')]}
    assert any('complete_missing_required' in e for e in V.validate(b,**ctx))
    b['structural_completeness']='PARTIAL'
    assert V.validate(b,**ctx)==[]

def test_card_references_exact_generation_and_graph():
    b=get('bundle');b['canonical_generation_id']='stale'
    assert any('generation_mismatch' in e for e in V.validate(b,canonical=get('canonical'),templates=[get('template')]))

def test_query_quotes_and_multiple_cards():
    q=get('query');second=copy.deepcopy(q['cards'][0]);second['id']='card:second';q['cards'].append(second)
    ctx={'canonical':get('canonical'),'templates':[get('template')]}
    assert V.validate(q,**ctx)==[]
    q['cards'][0]['facts'][0]['quote']='추측'
    assert any('question_fact_quote' in e for e in V.validate(q,**ctx))

def test_ssot_hash_drift_is_rejected(tmp_path):
    registry,schema=V.load_contract();path=tmp_path/registry['normative_schema']['path'];path.parent.mkdir(parents=True);path.write_text(json.dumps(schema)+' ')
    (tmp_path/V.REGISTRY).write_text(json.dumps(registry))
    with pytest.raises(ValueError,match='hash drift'):V.load_contract(tmp_path)
