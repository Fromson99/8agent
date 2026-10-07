"""Reserve first; freeze the current two tool protocols without production edits."""
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0485-tool-exploration-v3-cm3'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0485/tools-v3-cm3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def tool(*args):subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_candidate.py',*args],cwd=ROOT,check=True)
def main():
    m=json.loads((ADR/'실험/manifest.json').read_text())
    source=ROOT/'04_EXPERIMENTS/ADR/ADR-0474-double-harness-live-quality-probe/artifacts/frozen-inputs.json'
    base=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring/fixture.json').read_text())
    cases=[c for c in json.loads(source.read_text())['cases'] if c['case_id'] in ('cm-003','cm-018','cm-038')]
    product={'generation':base['generation'],'public_scope_document_ids':base['public_scope_document_ids'],
             'cases':[{k:c[k] for k in ('case_id','question')} for c in cases]}
    write(ADR/'product-cases.json',product)
    write(ADR/'gold-cases.json',{'source':str(source.relative_to(ROOT)),'sha256':sha(source),
        'cases':[{k:c[k] for k in ('case_id','reference_answer','decisive_source_ids')} for c in cases]})
    selection='CM003 classification/reference, CM018 explicit article structure, CM038 reporting delegation; chosen before outputs from completed CM12; original punctuation/context preserved.'
    criteria='v3 substantive reference agreement >=2/3, no regression against v2, zero execution errors, <=14 calls and <=300 controller seconds each; all unmet criteria and unresolved relations retained.'
    m['lineage']['hypothesis_delta']='Current tools-v2 baseline versus audited relation-aware tools-v3 working implementation; new root, no inherited quality result.'
    m['design'].update(hypothesis='Audited source and relationship reasoning produces usable CM answers within existing budgets.',primary_metric='Stored-reference agreement plus valid cited answer rate; not current-law certification',success_criteria=criteria,failure_criteria='Any threshold missed; no tuning or retries after outcomes.',criteria_frozen_before_run=True)
    for a in m['design']['arms']:
        a.update(changes='Frozen current '+('tools-v2' if a['id']=='baseline' else 'tools-v3 with previews, audit and six relation families'),controls='Same current snapshot, public145 corpus, Gemini, original questions, default common budgets; no hints/gold/preloads.')
    stages=[{'stage_id':'discovered','kind':'source','parent_stage_ids':[]}]
    for s,k,p in [('read','retrieve','discovered'),('presented','present','read'),('selected','select','presented'),('answer','present','selected')]:stages.append({'stage_id':s,'kind':k,'parent_stage_ids':[p]})
    m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','relations-v3')}
    m['runs'][0].update(selection_rule=selection,artifact_path=str((ADR/'artifacts/run-001/results.json').relative_to(ROOT)))
    m['dataset'].update(name='CM3 paired tools-v2/v3 probe',version='adr0474-cm003-018-038',frozen_source=str((ADR/'product-cases.json').relative_to(ROOT)),sha256=sha(ADR/'product-cases.json'))
    m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
    write(ADR/'실험/manifest.json',m)
    (ADR/'PLAN.md').write_text('# 사전 설계\n\n'+selection+'\n\n'+criteria+'\n\nEach case sequential; alternate v2/v3 first. One run each; default 14 attempts, 56 tools, 300s controller, 60000 context chars, 2800 output tokens. Single blind paired Gemini judge, alternating anonymous slots; no calibration. Known CM data: in_sample=true, decision_eligible=false. Product never loads gold. Execution errors count as wrong; no baseline historical output. Measure raw source READ/presentation/adoption and relation coverage separately from answer correctness. No production, active release, or GENOS changes.\n')
    args=['snapshot','--adr',str(ADR),'--candidate-id','tools-v3-cm3','--experiment-id',m['experiment_id'],'--arm-id','relations-v3','--run-id','run-001']
    files=sorted(p for p in (ROOT/'02_BACKEND/semantic_runtime').rglob('*') if p.is_file() and p.suffix in ('.py','.sql'))
    files += [ROOT/'02_BACKEND/lawrag/research/experiment_client.py']
    for p in files:args.extend(['--source',str(p.relative_to(ROOT))])
    tool(*args)
    print('Prepared',len(files),'snapshot files and 3 paired cases; no model calls')
if __name__=='__main__':main()
