"""Freeze design, then copy exact completed parent bytes into an isolated candidate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0625-exact-anchor-delegation-read'
PARENT = ROOT/'04_EXPERIMENTS/ADR/ADR-0624-required-unit-delegation-read'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0625/exact-anchor'

def read(path): return json.loads(Path(path).read_text())
def put(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    m = read(ADR/'실험/manifest.json')
    assert m['results']['status'] == 'not_run'
    assert not CANDIDATE.exists()
    design = ADR/'artifacts/design'
    for name in ('inputs.json', 'gold.json', 'source-coordinates.json', 'source-binding.json'):
        design.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PARENT/'artifacts/design'/name, design/name)
    put(design/'inputs.json', [c for c in read(design/'inputs.json') if c['case_id']=='cm-003'])
    put(design/'gold.json', {'cm-003': read(design/'gold.json')['cm-003']})
    hypothesis = ('Focus verified references on question-mentioned structural units; complete only '
        'explicit delegated-case paragraphs and their children before optional navigation. '
        'Record immutable evidence, bounded reads and unresolved coverage; keep the same legal_agent.')
    hypothesis += ' Mandatory reads additionally require the exact referenced anchor original to contain the delegated-case proviso; inverse role alone is insufficient.'
    m['lineage']['hypothesis_delta'] = hypothesis
    stages = [('corpus','source'), ('recall','retrieve'), ('read','filter'),
              ('initial_selection','select'), ('relations','expand'), ('selection','select'), ('present','present')]
    plans = [{'stage_id':s, 'kind':k, 'parent_stage_ids':[] if i==0 else [stages[i-1][0]]}
             for i,(s,k) in enumerate(stages)]
    m['design'].update(hypothesis=hypothesis,
        primary_metric='CM003 exception body delivered before final selection, direct required scopes covered, no unrelated mandatory READ, and bounded/shared-consumer contracts.',
        success_criteria='All applicable inherited/new contracts pass. Candidate completes CM003 selection with both required source roots and the verbatim delegated exception conditions delivered. Mandatory READ excludes unrelated article23 paragraphs and article-root subtree. No extra LLM answer judge; zero source/index rebuilds.',
        failure_criteria='Required unread conditions reported complete; inaccessible/unverified/ambiguous scope auto-read; unrelated mandatory expansion; source/evidence lost downstream; selector cannot finish or required source body absent.',
        criteria_frozen_before_run=True,
        controls='Inherited completed ADR0624 baseline and fresh candidate once, same completed ADR0624 implementation base, 145 public documents, original queries and index, Qwen3.8 Parasail FP8 reasoning none; one unit-pair repair remains. No final legal-answer score.',
        product_scope='Source selection only; source-issue review is existing selection, not answer verification. No live ASSESS/COMPOSE judge. CM051 and automatic memory accuracy are outside this narrow probe.',
        limits={'required_scopes':8, 'required_chars':12000, 'reference_rounds':2, 'groups_per_batch':16,
                'total_model_calls_per_arm':5, 'selector_context_chars':80000},
        retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1',
            'accounting_unit':'case_id + canonical article-root coordinate',
            'stages_by_arm':{arm:plans for arm in ('baseline','exact-anchor')}},
        index_reuse=read(PARENT/'실험/manifest.json')['design']['index_reuse'])
    for arm in m['design']['arms']:
        arm.update(changes='Immutable completed ADR0624 raw candidate records' if arm['id']=='baseline'
                   else 'Question-unit focus, explicit delegated-case/local-list minimum reads, coverage receipts and shared bounded adoption',
                   controls='Original source/index bytes, queries, product model and selector limits fixed')
    m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None)
    m['runs'][0].update(selection_rule='Known CM003 case; completed ADR0624 exact raw baseline reused, fresh candidate once; no reruns',
        artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
    m['dataset']={**read(PARENT/'실험/manifest.json')['dataset'],
        'name':'Known public CM003 source-selection failure',
        'frozen_source':str((design/'inputs.json').relative_to(ROOT)), 'sha256':sha(design/'inputs.json')}
    m['llm_policy']['llm_calls']=[{'role':'source_unit_selection_and_optional_reference_navigation',
        'class':'product','model':m['llm_policy']['required_model'],'repeats':1,
        'temperature':0,'max_calls_per_case':{'baseline':0,'exact-anchor':5}}]
    m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
        artifact_path=str((ADR/'artifacts/run-001/stage-ledger.json').relative_to(ROOT)),
        sha256='PENDING',not_applicable_reason=None)
    m['design']['frozen_inputs']={str(p.relative_to(ROOT)):sha(p) for p in design.glob('*.json')}
    for name in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','08_DEPLOYMENT/CONFIG/legal-source-export.json',
                 '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'):
        m['design']['frozen_inputs'][name]=sha(ROOT/name)
    for key in ('manifest','database'):
        name=m['design']['index_reuse'][key];m['design']['frozen_inputs'][name]=sha(ROOT/name)
    put(ADR/'실험/manifest.json',m)
    sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
    spec=importlib.util.spec_from_file_location('candidate_tool',ROOT/'06_TOOLS/COMMANDS/adr_candidate.py')
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    parent_path=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0624/required-unit-closure/candidate.json'
    parent=read(parent_path); files=parent['revisions'][-1]['files']
    targets=[row.get('target_path') or row['frozen_path'].split('/snapshot/',1)[1] for row in files]
    present=[p for p in targets if (ROOT/p).is_file()]
    tool.snapshot(ADR,'exact-anchor',present,experiment_id=m['experiment_id'],
                  arm_id='exact-anchor',run_ids=['run-001'])
    for row,target in zip(files,targets):
        src=ROOT/row['frozen_path'];assert sha(src)==row['snapshot_sha256']
        dst=CANDIDATE/'snapshot'/target;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
    for name in targets:
        if name not in present:tool.register_file(CANDIDATE,name,upstream_state='absent')
    tool.refresh(CANDIDATE)
    put(ADR/'artifacts/parent-copy-receipt.json',{'parent_arm':'ADR-0624-experiment-v1/required-unit-closure',
        'parent_candidate_sha256':sha(parent_path),'files':len(files),'exact_parent_bytes_copied':True})
    print(CANDIDATE)

if __name__=='__main__':main()
