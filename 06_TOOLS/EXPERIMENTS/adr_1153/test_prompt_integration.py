"""Finite technical contract matrix, independent of legal question outcomes."""
from copy import deepcopy
import ast,json,itertools,os
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import ontology_scenarios as sc,ontology_scenario_runtime as rt
from test_scenarios import fixture,issues,options,choice
from test_sufficiency import Journal,Host

REPO_ROOT=Path(__file__).resolve().parents[3]
DES=REPO_ROOT/'04_EXPERIMENTS/ADR/ADR-1153-ontology-selection-main-qualification/artifacts/design'
CODE=Path(os.environ['QUALIFICATION_CODE_ROOT'])

@pytest.mark.parametrize('mask',range(8))
def test_delivered_prompt_and_exact_model_subset_without_forced_pair(tmp_path,mask):
 recipe,originals,fragments=fixture();template=recipe['paths'][0];ids=['BASIC_A7','BOUNDARY_Z2','OTHER_K9']
 recipe['paths']=[{**deepcopy(template),'id':pid,'title':'Synthetic '+pid} for pid in ids]
 catalog=sc.bind_current(sc.compile_package(recipe,originals),fragments)
 selected=[pid for i,pid in enumerate(ids) if mask&(1<<i)]
 value=choice('GENERAL_RULE' if selected else 'NO_MATCH',selected)
 journal=Journal(tmp_path/'journal');host=Host(journal,[value]);seen=[];invoke=host.invoke
 def capture(system,data,schema,phase):
  seen.append((system,deepcopy(data),deepcopy(schema)));return invoke(system,data,schema,phase)
 host.invoke=capture
 assessment=rt.assess(host,catalog,[],options(),issues(),'General conditions of this synthetic business?',{},None)
 assert len(seen)==1 and seen[0][0]==json.loads((DES/'prompt.json').read_text())['new']
 assert [p['id'] for p in assessment['assessment_basis']['scenario_choice']['selected_paths']]==selected
 assert len(assessment['claims'])==len(selected)
 sc.verify_selected_text(assessment)
 again=rt.assess(host,catalog,[],options(),issues(),'General conditions of this synthetic business?',{},None)
 assert again==assessment and len(seen)==1
 journal.db.close()

def test_only_prompt_ast_changed_and_same_input_schema():
 base=json.loads((DES/'baseline.json').read_text());path='02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py'
 def without_prompt(p):
  tree=ast.parse(p.read_text());tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='PROMPT' for t in n.targets))];return ast.dump(tree)
 assert without_prompt(CODE/path)==without_prompt(REPO_ROOT/base['manifest']['code_root']/path)
 assert len(sc.PROMPT)==365

def test_profile_switches_recovery_and_empty_data_are_exact_main109():
 base=json.loads((DES/'baseline.json').read_text());name='00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'
 assert (CODE/name).read_bytes()==(REPO_ROOT/base['manifest']['code_root']/name).read_bytes()
 profile=json.loads((CODE/name).read_text());p=profile['candidate_navigation']
 assert p['ontology_enabled'] is False and p['ontology_context']=={'mode':'A0'}
 assert all(p[k] is True for k in ('stable_navigation_references','new_read_reviews','independent_read_recovery'))
