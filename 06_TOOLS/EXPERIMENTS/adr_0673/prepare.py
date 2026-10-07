"""Freeze six question-only CM requests against unchanged completed parent code."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, sys
sys.dont_write_bytecode = True
R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0673-investigation-chain-cm-six'
P = R/'04_EXPERIMENTS/ADR/ADR-0672-investigation-chain-parent-collision'
T = R/'06_TOOLS/EXPERIMENTS/adr_0673'
ARM = 'chain-cm-six'
IDS = ['cm-003','cm-018','cm-038','cm-039','cm-043','cm-051']
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
m = read(A/'실험/manifest.json'); pm = read(P/'실험/manifest.json')
source = R/'01_DATA/review/cm_core_e2e_v3.json'; suite = read(source)
selected = [next(c for c in suite['cases'] if c['id']==cid) for cid in IDS]
dataset = {'schema_version':'question-only-probe-v1','source_generation':pm['dataset']['version'],
    'source_suite':str(source.relative_to(R)), 'source_suite_sha256':sha(source),
    'selection_rule':'Six previously known difficult CM domains, fixed before calls; no replacement or forced returns.',
    'cases':[{'case_id':c['id'],'question':c['question'],'user_original':c['source_question']} for c in selected]}
put(A/'artifacts/design/dataset.json',dataset)
put(A/'artifacts/offline-only/gold.json',{'source_suite_sha256':sha(source),'cases':selected,
    'product_visible':False,'use':'Only post-run local coordinate coverage and source/gold comparison; never an external model input.'})
delta = 'Retest completed ADR0672 unchanged product code, prompts, indexes, model and limits on six new CM question-only requests. Each has isolated runtime; no original gold, old answers, chosen coordinates or forced navigation injected.'
m['lineage']['hypothesis_delta'] = delta
m['design'].update(hypothesis='The unchanged persistent investigation chain supports additional CM domains without losing prior choices and decision reasons; answer completion and source acquisition are measured separately.',
    primary_metric='Six-request HTTP completion, chain-prefix preservation in later inputs, final-step coverage, actual return/multi-read actions, and offline required-original acquisition.',
    success_criteria='All six HTTP200 complete with history reasons preserved and final steps visible; no pointer changes, private originals, product gold or provider/model fallback. Required-source coverage reported independently, not treated as answer accuracy.',
    failure_criteria='Any request failure, invalid chain, missing later history or scope/pointer drift is retained as a failure. No changes or repeats after observing results in this ADR.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':ARM,'role':'candidate','derived_from':['ADR-0672-experiment-v1/chain-parent-fix'],'changes':delta,
    'controls':'Exact completed frozen parent product code, public145 generation, Qwen3.8 Parasail FP8 reasoning none/no fallback, output6400, physical calls40/request, runtime1800sec. Six requests ascending CM order; separate runtimes, no cross-case memory.'}]
plan=pm['design']['retrieval_stage_plan']; plan['stages_by_arm']={ARM:plan['stages_by_arm']['chain-parent-fix']};m['design']['retrieval_stage_plan']=plan
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Six question-only CM v3 cases; gold physically separate',version=suite['version'],
    frozen_source=str((A/'artifacts/design/dataset.json').relative_to(R)),sha256=sha(A/'artifacts/design/dataset.json'),legal_version_checked=False,reference_version_checked=False)
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':[ARM],'selection_rule':dataset['selection_rule'],'status':'planned',
    'artifact_path':str((A/'artifacts/run-001/results.json').relative_to(R)),'sha256':'PENDING'}]
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/stage-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
put(A/'artifacts/design/preimplementation-design.json',{k:m[k] for k in ['design','dataset','runs','lineage','llm_policy']})
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
spec=importlib.util.spec_from_file_location('candidate_tools',R/'06_TOOLS/COMMANDS/adr_candidate.py');ac=importlib.util.module_from_spec(spec);spec.loader.exec_module(ac)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0672/chain-parent-fix';cm=read(parent/'candidate.json')
source_code=parent/'revisions/rev-001/snapshot'
c=ac.snapshot(A,ARM,[x['target_path'] for x in cm['files'] if (R/x['target_path']).is_file()],experiment_id=m['experiment_id'],arm_id=ARM,run_ids=['run-001'])
for row in cm['files']:
    target=row['target_path'];dest=c/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_code/target,dest)
    if not (R/target).is_file():ac.register_file(c,target,upstream_state='absent')
for name in ['run_probe.py','freeze.py','summarize_probe.py','audit_chain.py']:
    text=(R/'06_TOOLS/EXPERIMENTS/adr_0672'/name).read_text()
    text=text.replace('ADR-0672-investigation-chain-parent-collision','ADR-0673-investigation-chain-cm-six').replace('adr0672','adr0673')
    text=text.replace('adr_0672/chain-parent-fix','adr_0673/chain-cm-six').replace('adr_0672/run_probe','adr_0673/run_probe')
    if name=='freeze.py':text=text.replace("'chain-parent-fix'", "'chain-cm-six'")
    if name=='run_probe.py':
        text=text.replace("source=ROOT/b['source_generation'];generation=directory/'generation-shadow'", "source=ROOT/b['source_generation'];generation=directory/'generation-shadow'")
    if name=='summarize_probe.py':
        text=text.replace('contracts_count=73','contracts_count=73  # inherited unchanged parent contracts, not rerun')
        text=text.replace('Two sequential local requests','Six sequential local requests')
    if name=='audit_chain.py':
        text=text.replace('20261006-investigation-chain-r2','20261006-investigation-chain-cm-six')
        text=text.replace("for cid in ['venture-stock-option','accounting-manager']:", "for cid in [c['case_id'] for c in read(A/'artifacts/design/dataset.json')['cases']]:")
        text=text.replace('로컬 격리 후보 구현·두 질문 실행','로컬 격리 후보 CM 추가 6질문 실행')
        text=text.replace('73개 계약 통과.','변경 없는 부모 후보의 73개 계약 통과 기록을 계승.')
    (T/name).write_text(text)
print(c)
