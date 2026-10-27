"""Prepare byte-identical r10 candidates and preserve all prior failed evidence."""
from pathlib import Path
import hashlib, json, shutil, sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1048-ontology-mvp-r10-restart'
ART=ADR/'artifacts'
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1047-ontology-mvp-state-format/artifacts'
def read(p): return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p): return str(p.relative_to(ROOT))
def create(p,v):
    with p.open('x') as f: json.dump(v,f,ensure_ascii=False,indent=2); f.write('\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidate
frozen=read(PRIOR/'design-freeze.json')
oldroot=ROOT/frozen['code_root']
old=read(oldroot.parents[2]/'candidate.json')
assert {r['target_path']:r['snapshot_sha256'] for r in old['files']}==frozen['files']
present=[r['target_path'] for r in old['files'] if r['upstream_state']=='present']
for r in old['files']:
    p=ROOT/r['target_path']
    if r['upstream_state']=='present': assert sha(p)==r['upstream_sha256'],r['target_path']
    else: assert not p.exists(),r['target_path']
rows=[]
for arm,name in [('A1','state-format-a1-r10'),('A2','state-format-r10')]:
    dest=candidate.snapshot(ADR,name,present,experiment_id='ADR-1048-experiment-v1',arm_id=arm,run_ids=['run-001'])
    for row in old['files']:
        name=row['target_path']; source=oldroot/name; target=dest/'snapshot'/name
        assert sha(source)==row['snapshot_sha256']
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
        if row['upstream_state']=='absent': candidate.register_file(dest,name,upstream_state='absent')
    candidate.refresh(dest); candidate.freeze(dest)
    assert not candidate.validate(dest)
    new=read(dest/'candidate.json')
    assert {r['target_path']:r['snapshot_sha256'] for r in new['files']}==frozen['files']
    rows.append({'arm':arm,'manifest_path':rel(dest/'candidate.json'),'manifest_sha256':sha(dest/'candidate.json'),'files':len(old['files']),'all_files_byte_identical':True})
create(ART/'candidate-code-identity.json',{'schema_version':'byte-identical-restart-v1','prior_freeze_path':rel(PRIOR/'design-freeze.json'),'prior_freeze_sha256':sha(PRIOR/'design-freeze.json'),'candidates':rows,'files':frozen['files'],'upstream_drift':[],'model_calls':0})
inputs=[]
for name in ['cases-product.json','cases-evaluator-r1.json','corpus-selection-r1.json','execution-authorization-20261024-r1.json','evaluation-contract.json','dataset-freeze-r1.json','approved-bundles-20261024-r1.json','corpus-article-root-count-r1.json']:
    source=PRIOR/name; target=ART/name
    assert not target.exists(); shutil.copyfile(source,target)
    assert sha(target)==sha(source)
    inputs.append({'path':rel(target),'source_path':rel(source),'sha256':sha(source)})
prior_stops=[{'path':rel(PRIOR/name),'sha256':sha(PRIOR/name)} for name in ['matrix-stop.json','matrix-progress.json','stopped-run-closeout.json']]
create(ART/'restart-authorization.json',{'schema_version':'user-authorized-identical-restart-v1','approved_for_run':True,'user_message':'재시도 한번 해봐 자꾸 오류 뜨네 ....','effective_interpretation':'One fresh same-condition 37 x 3 sequential matrix attempt; stop on another provider/transport/integrity/resource failure. No new automatic retry policy.','new_planned_cells':111,'add_missing_laws':False,'transport_retries':0,'max_output_tokens':None,'fallback_allowed':False,'inherited_input_identity':inputs,'prior_stop_records':prior_stops,'conditions':'Same r10 product bytes, cases, corpus, approved bundles, model/provider, criteria, budgets, order and output policy as ADR1047.','prior_validation_inherited_not_rerun':True,'main_or_genos_change_authorized':False})
print('Prepared',len(old['files']),'identical files per arm;',len(inputs),'unchanged inputs; zero model calls.')
