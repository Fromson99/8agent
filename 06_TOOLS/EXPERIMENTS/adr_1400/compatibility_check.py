"""Adapt legacy scripted happy-path reviewers to the new review wire schema.
The actual1398 regression tests use independent explicit reviews, not this adapter.
"""
from common import *
sys.path[:0]=[str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
# check.py establishes immutable product imports before this fixture is loaded.
import os,importlib
C=ROOT/read(DES/'candidate-repaired.json')['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
import lawrag;lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core','research'):
 pkg=importlib.import_module('lawrag.'+n);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_ONTOLOGY_CODE_ROOT=str(C),LOOP_TEST_CODE_ROOT=str(C),LOOP_TEST_REPOSITORY_ROOT=str(ROOT))
sys.path.insert(0,str(ROOT/'09_ARTIFACTS/AUDITS/20261105-multiturn-knowledge-lifecycle/test-fixtures'))
for n in ('test_domain_profile_workflow','test_review_explanation_actions','test_wiki_workspace','need_continuity_fixture','scope_review_fixture'):importlib.import_module(n)
from test_memory_runtime_v2 import Wire
original=Wire.__call__
def scripted_current_review(self,system,data,schema,phase):
 value=original(self,system,data,schema,phase)
 if phase=='memory-command-check' and 'requested_task' in schema.get('properties',{}):
  method=data['command']['method_id'];relation={'CASE_START':'NEW_TOPIC','FACT_UPDATE':'CONDITION_CHANGE','PURPOSE_REVISE':'FOLLOWUP','STATE_RESTORE':'RESTORE','EXPERIENCE_REUSE':'REUSE','HISTORY_EXPLAIN':'HISTORY','EXPERIENCE_CONFIRM':'CONFIRMATION','ANSWER_PRESENT':'PRESENTATION'}.get(method,'REPEAT')
  value={**value,'request_relation':relation,'requested_task':data['transition']['after']['task']}
 return value
Wire.__call__=scripted_current_review
spec=importlib.util.spec_from_file_location('scoped_check_1400',Path(__file__).with_name('check.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
