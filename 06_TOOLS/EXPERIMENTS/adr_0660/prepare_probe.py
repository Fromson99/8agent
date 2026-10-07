"""Freeze the existing law-navigation implementation against the selected public data."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, sys

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0660-law-navigation-accounting-manager-probe'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
manifest_path=ADR/'실험/manifest.json'
m=json.loads(manifest_path.read_text())
release_path=ROOT/'08_DEPLOYMENT/RELEASES/local-genos-unit-v6-20261006-r1/release.json'
release=json.loads(release_path.read_text());active=ROOT/release['code_root']
source=ROOT/release['data_path'];data=json.loads((source/'manifest.json').read_text())
dataset={'question':'내부회계관리자는 누가 지정하나요?','source_generation':release['data_path'],
         'source_manifest_sha256':sha(source/'manifest.json'),'source_store_sha256':data['store_sha256'],
         'fulltext':data['fulltext'],'glossary':data['glossary'],'model_policy_sha256':sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),
         'public_grant_sha256':sha(active/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),
         'active_pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
         'active_release_sha256':sha(release_path),'question_selection':'User-supplied known failing single question; one run; no golden answer in model context.'}
put(ADR/'artifacts/design/dataset.json',dataset)
m['lineage']['hypothesis_delta']='Replace the old positive choices list and blocking reference gate with existing law-first explicit decisions and allowed unresolved completion. Parent is historical diagnosis, not a paired baseline.'
m['design'].update(hypothesis='The implemented law-first route selects the governing law explicitly and completes the supplied question without accidental adoption from a negative choices reason.',
    primary_metric='HTTP READY final answer and actual law navigation trace; operational success only.',
    success_criteria='One fresh run returns HTTP200/READY, final answer identifies the company representative with an original citation, law-first phase is used, and no old source-unit choices decision executes. Report unresolved references honestly.',
    failure_criteria='Any HTTP failure, non-READY final state, wrong actor, old source-unit selector, or unintended adopted branch is preserved as a failed probe. No model quality or general performance claim.',
    criteria_frozen_before_run=True,
    arms=[{'id':'law-first','role':'candidate','derived_from':['ADR-0659-experiment-v1/shipped-r1'],
           'changes':'Frozen working law-first code. Reuse active compact glossary compiler, approved grant and data bindings for the current generation.',
           'controls':'Same current local public source data, 145 approved documents, Qwen3.8 Parasail FP8 reasoning none. Separate empty runtime. No active release/pointer writes.'}])
m['design']['retrieval_stage_plan']['stages_by_arm']={'law-first':[
    {'stage_id':'source','kind':'source','parent_stage_ids':[]},
    {'stage_id':'recall','kind':'retrieve','parent_stage_ids':['source']},
    {'stage_id':'select','kind':'select','parent_stage_ids':['recall']},
    {'stage_id':'present','kind':'present','parent_stage_ids':['select']}]}
m['runs']=[{'id':'run-001','purpose':'Single known-case operational probe, not paired quality comparison','parent_run_id':None,
    'arm_ids':['law-first'],'selection_rule':'Exact user supplied question, one attempt; no additional question selected after results.',
    'status':'planned','artifact_path':str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)),'sha256':'PENDING'}]
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset']={'name':'User supplied accounting manager query on current approved public scope','version':data['generation_id'],
    'frozen_source':str((ADR/'artifacts/design/dataset.json').relative_to(ROOT)),
    'sha256':sha(ADR/'artifacts/design/dataset.json'),'legal_version_checked':False,'reference_version_checked':False}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
    artifact_path=str((ADR/'artifacts/stage-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(manifest_path,m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
spec=importlib.util.spec_from_file_location('adr_candidate_tool',ROOT/'06_TOOLS/COMMANDS/adr_candidate.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
sources=[p for p in release['files'] if (ROOT/p).is_file()]
sources += ['02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','02_BACKEND/semantic_runtime/legal_agent/law_navigation.py']
candidate=tool.snapshot(ADR,'law-first',sources,experiment_id=m['experiment_id'],arm_id='law-first',run_ids=['run-001'])
snapshot=candidate/'snapshot'
# These compatibility files come from the already approved selected release.
for p in ['02_BACKEND/semantic_runtime/full_glossary.py','00_SYSTEM/LEGAL_AGENT/local-gemma-public.json']:
    shutil.copy2(active/p,snapshot/p)
for p in release['files']:
    if not (ROOT/p).is_file():
        (snapshot/p).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(active/p,snapshot/p)
        tool.register_file(candidate,p,upstream_state='absent')
pipe_path=snapshot/'00_SYSTEM/PIPELINE.json';pipe=json.loads(pipe_path.read_text())
current=pipe['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']
bound=json.loads((active/'00_SYSTEM/PIPELINE.json').read_text())['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']
for key in ['index','fulltext','glossary','origin_projections','alias_projections']:
    current[key]=bound[key]
put(pipe_path,pipe)
old=sha(ROOT/'02_BACKEND/semantic_runtime/full_glossary.py');new=sha(snapshot/'02_BACKEND/semantic_runtime/full_glossary.py')
for p in (snapshot/'00_SYSTEM').rglob('*.json'):
    text=p.read_text()
    if old in text:p.write_text(text.replace(old,new))
tool.freeze(candidate)
errors=tool.validate(candidate)
if errors:raise ValueError(errors)
cm=json.loads((candidate/'candidate.json').read_text());rev=cm['revisions'][-1]
runner=ROOT/'06_TOOLS/EXPERIMENTS/adr_0660/run_probe.py'
m=json.loads(manifest_path.read_text())
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
    'candidate_id':'law-first','experiment_id':m['experiment_id'],'arm_id':'law-first','run_ids':['run-001'],
    'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)), 'manifest_sha256':sha(candidate/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
    'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
put(manifest_path,m)
bindings={'candidate':str(candidate.relative_to(ROOT)),'revision_id':rev['revision_id'],
          'candidate_manifest_sha256':sha(candidate/'candidate.json'),'source_generation':release['data_path'],
          'files':{str(p.relative_to(ROOT)):sha(p) for p in [runner,ROOT/'02_BACKEND/lawrag/research/experiment_client.py',
                   ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',source/'manifest.json',release_path,ADR/'artifacts/design/dataset.json']}}
put(ADR/'artifacts/design/bindings.json',bindings)
print(json.dumps({'candidate':str(candidate),'revision':rev['revision_id'],'files':len(rev['files']),'errors':errors}))
