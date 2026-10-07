"""Freeze inputs, criteria, stages and code identity before model calls."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0481-reviewed-links-hard10'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0481/hard10-reviewed-links'
RUNNER=ROOT/'06_TOOLS/EXPERIMENTS/adr_0481/run_probe.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def stages():return [{'stage_id':'discovered','kind':'source','parent_stage_ids':[]},{'stage_id':'read','kind':'retrieve','parent_stage_ids':['discovered']},{'stage_id':'presented','kind':'present','parent_stage_ids':['read']},{'stage_id':'selected','kind':'select','parent_stage_ids':['presented']},{'stage_id':'answer','kind':'present','parent_stage_ids':['selected']}]

def main():
    target=ADR/'artifacts/frozen-design.json'
    if target.exists():raise RuntimeError('Design already frozen')
    m=json.loads((ADR/'실험/manifest.json').read_text());product=json.loads((ADR/'product-cases.json').read_text())
    generation=ROOT/product['generation'];source=json.loads((generation/'manifest.json').read_text());candidate=json.loads((CAND/'candidate.json').read_text())
    paths=[ADR/'PLAN.md',ADR/'product-cases.json',ADR/'gold-cases.json',CAND/'candidate.json',generation/'manifest.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'00_SYSTEM/PIPELINE.json',RUNNER,ROOT/'02_BACKEND/lawrag/research/experiment_client.py']
    design={'model':'gemini-3.1-flash-lite','arms':['baseline','reviewed-links'],
      'selection_rule':'All five single-source plus first five multi-source cases by case ID from ADR-0474 frozen 12.',
      'success_criteria':'reviewed-links >=7/10, delta >=+3, regressions <=1, execution errors <=1; linked originals actually READ/presented.',
      'limits':{'model_calls_per_case_arm':14,'tool_actions':56,'wall_seconds':300,'context_chars':60000,'output_tokens':2800},
      'order':'case ID; even index baseline first, odd reviewed-links first','stage_plan':{'baseline':stages(),'reviewed-links':stages()},
      'source_store_sha256':source['store_sha256'],'scope_document_count':len(product['public_scope_document_ids']),
      'file_hashes':{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    write(target,design);rev=candidate['revisions'][0]
    m['lineage']['hypothesis_delta']='Same latest frozen source-first RAG with versus without oracle reviewed decisive-source coordinate READs; legal application and answer remain model-owned.'
    m['design'].update(hypothesis=design['success_criteria'],primary_metric='Blind single-judge semantic correctness on 10 paired cases',success_criteria=design['success_criteria'],failure_criteria='Any threshold missed, gold leakage, or linked originals not read/presented.',criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Latest ADR-0480 frozen source-first RAG; ordinary question FTS/preread only.',controls='Same code, source, scope, Gemini, budgets and prompts.')
    m['design']['arms'][1].update(changes='After identical bootstrap, reviewed target source IDs are READ through SourceSession; no conclusion injected.',controls='Same code, source, scope, Gemini, budgets and prompts; only source-coordinate availability changes.')
    m['design']['retrieval_stage_plan']['stages_by_arm']=design['stage_plan']
    m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'hard10-reviewed-links','experiment_id':m['experiment_id'],'arm_id':'reviewed-links','run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(RUNNER.relative_to(ROOT)),'runner_sha256':sha(RUNNER)}])
    m['runs'][0].update(selection_rule=design['selection_rule'],artifact_path='04_EXPERIMENTS/ADR/ADR-0481-reviewed-links-hard10/artifacts/run-001/results.json')
    m['dataset'].update(name='CM hard-10 reviewed-link paired probe',version='adr0474-frozen12-stratified10',frozen_source=str((ADR/'product-cases.json').relative_to(ROOT)),sha256=sha(ADR/'product-cases.json'),legal_version_checked=False,reference_version_checked=False)
    m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
    write(ADR/'실험/manifest.json',m);print('Design frozen before model calls')
if __name__=='__main__':main()
