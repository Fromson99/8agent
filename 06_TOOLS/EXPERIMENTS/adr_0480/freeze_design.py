"""Seal probe plan, code, fixture and source binding before retrieval measurement."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def main():
    out=ADR/'artifacts/frozen-design.json'
    if out.exists():raise ValueError('immutable design exists')
    m=json.loads((ADR/'실험/manifest.json').read_text())
    fixture=json.loads((ADR/'fixture.json').read_text())
    stages=[{'stage_id':'start','kind':'source','parent_stage_ids':[]},
            {'stage_id':'linked','kind':'expand','parent_stage_ids':['start']},
            {'stage_id':'read','kind':'select','parent_stage_ids':['linked']},
            {'stage_id':'presented','kind':'present','parent_stage_ids':['read']}]
    runner=ROOT/'06_TOOLS/EXPERIMENTS/adr_0480/run_probe.py'
    paths=[ADR/'PLAN.md',ADR/'fixture.json',CAND/'candidate.json',runner,
           ROOT/'05_TESTS/CONTRACTS/test_source_relations_candidate.py',
           ROOT/fixture['generation']/'manifest.json',ROOT/'06_TOOLS/EXPERIMENTS/adr_0475/check_cm003.py',
           ROOT/'00_SYSTEM/PIPELINE.json']
    criteria='One exact typed inverse relation retrieves rules article23 paragraph4 including item2 through real SourceSession READ; all 9 blocks, 3 pages; no unrelated paragraphs, model calls, fabricated human approvals, or MAIN changes.'
    design={'file_hashes':{str(p.relative_to(ROOT)):sha(p) for p in paths},
            'stage_plan':{a:stages for a in ('baseline','explicit-link')},
            'success_criteria':criteria,'model_calls':0,'judge_calls':0,'repetitions':1,
            'manual_in_sample_edge':True,'page_size':3,'autonomous_search':False,
            'baseline':'same explicit starting article; empty fixture relation release; NOT old full retrieval benchmark'}
    write(out,design)
    m['lineage']['hypothesis_delta']='Typed source-coordinate relation with proof span and subtree READ instead of generic read-together context; no model or answer quality test.'
    m['design'].update(hypothesis=criteria,primary_metric='Exact target subtree READ via explicit data relation',
        success_criteria=criteria,failure_criteria='Wrong extent/hash/scope, missing pages, implicit activation, false human approval or network calls',criteria_frozen_before_run=True)
    m['design']['retrieval_stage_plan']['stages_by_arm']=design['stage_plan']
    for arm in m['design']['arms']:
        arm.update(changes=design['baseline'] if arm['id']=='baseline' else 'one experiment_fixture SPECIFIES_DELEGATED_CASES_OF relation',
                   controls='same explicit start source, generation, 145-document scope, page size, no-model READ')
    rev=json.loads((CAND/'candidate.json').read_text())['revisions'][-1]
    m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
        'candidate_id':'explicit-link','experiment_id':m['experiment_id'],'arm_id':'explicit-link','run_ids':['run-001'],
        'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),
        'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
        'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
    m['runs'][0].update(selection_rule='User-selected CM003, explicit known source anchor, one manual relation; no gold answer used',
                        artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
    m['llm_policy']['llm_calls']=[]
    m['dataset'].update(name='CM003 manual one-hop original-source wiring',version='parent0479-source-generation',
                        frozen_source=str((ADR/'fixture.json').relative_to(ROOT)),sha256=sha(ADR/'fixture.json'))
    m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
    write(ADR/'실험/manifest.json',m)
    print('Probe plan frozen; model calls forbidden')

if __name__=='__main__':main()
