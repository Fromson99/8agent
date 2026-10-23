from common import *
from datetime import datetime,timezone
import sys
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'freeze.json').exists()
meta=read(DES/'candidate.json');candidate=ROOT/meta['path']
assert read(ART/'preflight-r6/result.json')['status']=='PASS'
criteria=read(DES/'criteria.json');criteria['storage_unit']='Source document version + article coordinate + concept; question IDs occur only in Agent provenance, offline evaluation, public export authorization.'
criteria['source_units']=4;criteria['ontology_records']=9;criteria['same_question_is_answer_cache']=False
put(DES/'criteria.json',criteria)
put(DES/'steering.json',{'instruction':'우리의 일차 저장단위는 원문기반이야 질문 기반이아니라',
 'applied_before_any_model_call':True,'primary_wiki_units':'4 source-article/concept units, no CM question keys',
 'ontology':'4 source METHOD +2 abstract METHOD dependencies +2 FIELD +1 typed AND APPLICATION',
 'question_role':'Agent provenance and lookup input only. Exact-question hashes are export authorization, not retrieval index.',
 'preflight_fixes':'Prior model0 preflights preserved: section return contract, canonical/physical document name, correct financial_team selection. No scope bypass; selected public documents intersect native financial_team metadata.'})
ac.refresh(candidate);ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('e2e.py')
m=read(ADR/'실험/manifest.json');m['design']['execution']=criteria
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'knowledge','arm_id':'knowledge','experiment_id':m['experiment_id'],'run_ids':['run-001'],
 'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
files=[*DES.glob('*.json'),ART/'agent_layer/corrected-experiences.json',ART/'offline/criteria.json',*Path(__file__).parent.glob('*.py'),ROOT/'06_TOOLS/EXPERIMENTS/resource_guard.py']
put(DES/'freeze.json',{'at':datetime.now(timezone.utc).isoformat(),'revision_sha256':rev['revision_sha256'],
 'candidate_manifest_sha256':sha(candidate/'candidate.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in files},
 'source_data_path':read(DES/'selected.json')['release']['data_path'],'model_calls_at_freeze':0})
print('FROZEN',rev['revision_id'],len(rev['files']),'files;4source units9ontology records;8native requests;model0')
