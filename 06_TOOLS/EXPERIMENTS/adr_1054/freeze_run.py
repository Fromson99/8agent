"""Bind tested candidate, inherited approved data and new execution before live calls."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import sys
from common import ROOT,ADR,ART,read,save,sha,exact_write
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1049-ontology-mvp-provider-failover/artifacts/design-freeze.json'
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1054/step-state-r1/revisions/rev-001/snapshot'
def rel(p):return str(p.relative_to(ROOT))
def main():
 assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
 old=read(PRIOR);new=deepcopy(old);tested=read(ART/'contracts-api-final-summary.json');frozen_test=read(ART/'frozen-state-summary.json')
 files={str(p.relative_to(CODE)):sha(p) for p in CODE.rglob('*') if p.is_file()}
 for t,n in [(tested,140),(frozen_test,22)]:
  assert t['status']==0 and t['passed']==n and not t['production_import_leaks'] and not t['candidate_changed_during_tests'] and t['files']==files
 assert '31 passed' in (ART/'runner-contracts.log').read_text()
 for p,h in old['runner_hashes'].items():assert sha(ROOT/p)==h,p
 for p,h in old['unchanged_core_semantic_definitions'].items():assert files[p]==h,p
 parent=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1052/law-overview-r1';parent_files={r['target_path']:r['snapshot_sha256'] for r in read(parent/'candidate.json')['files']}
 changed=[p for p,h in files.items() if parent_files.get(p)!=h]
 allowed={'05_TESTS/CONTRACTS/test_model_binding_adr1054.py','00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json','00_SYSTEM/PIPELINE.json','02_BACKEND/lawrag/research/provider_failover.py','02_BACKEND/semantic_runtime/legal_agent/gateway.py','02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','02_BACKEND/semantic_runtime/legal_agent/step_state.py','05_TESTS/CONTRACTS/test_step_state_adr1053.py','05_TESTS/CONTRACTS/test_provider_failover_adr1049.py'}
 assert all(p in allowed or p.startswith('02_BACKEND/ENGINES/') for p in changed),changed
 assert set(parent_files)<=set(files)
 save(ART/'candidate-files-diff.json',{'parent':rel(parent),'changed':changed,'files':len(files),'removed':[], 'core_semantic_definitions_unchanged':True,'representation_contract_files_updated':{p:{'old':h,'new':files[p]} for p,h in old['semantic_contract_files'].items() if h!=files[p]}})
 sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
 candidates=[]
 for arm,name in [('A1','step-state-a1-r1'),('A2','step-state-r1')]:
  directory=CODE.parents[3]/name;assert not c.validate(directory)
  manifest=read(directory/'candidate.json');revision=manifest['revisions'][-1]
  assert {r['target_path']:r['snapshot_sha256'] for r in manifest['files']}==files
  candidates.append({'candidate_id':name,'arm_id':arm,'experiment_id':'ADR-1054-experiment-v1','run_ids':['run-001'],'manifest_path':rel(directory/'candidate.json'),'manifest_sha256':sha(directory/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],'runner_path':rel(Path(__file__).with_name('run_matrix.py')),'runner_sha256':sha(Path(__file__).with_name('run_matrix.py'))})
 assert sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==old['baseline_policy_sha256']
 assert sha(ROOT/old['main_pointer_path'])==old['main_pointer_sha256']
 # Stream the immutable corpus once, then retain its identity receipt; no DB load.
 source=ROOT/old['data_path']/'store.sqlite';before=source.stat();source_sha=sha(source);after=source.stat();fields=lambda s:(s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 assert fields(before)==fields(after) and source_sha==old['store_sha256']
 integrity=read(ROOT/old['source_integrity_path']);assert (integrity['size'],integrity['mtime_ns'],integrity['ctime_ns'])==fields(after)
 mp=ADR/'실험/manifest.json';m=read(mp);m['design']['code_isolation']['candidates']=candidates;m['design']['criteria_frozen_before_run']=True
 stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z');previous=m['reservation']['updated_at'];m['reservation']['updated_at']=stamp;m['reservation']['events'].append({'action':'execution_design_frozen','at':stamp,'owner':m['reservation']['owner'],'session_id':m['reservation']['session_id'],'note':'140 contract/API checks,22 repeated from exact frozen path,31 runner checks.692files; state instructions common to all111cells; original scope/budgets/recovery maintained.'});save(mp,m)
 p=ADR/'README.md';p.write_text(p.read_text().replace('updated_at: '+previous,'updated_at: '+stamp))
 new.update(frozen_at=stamp,experiment_id=m['experiment_id'],design=m['design'],manifest_sha256_at_freeze=sha(mp),code_root=rel(CODE),files=files,baseline_policy_sha256=old['baseline_policy_sha256'],policy_sha256=sha(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),validation_inheritance=False,validation_note='140 targeted contracts/API,22 exact frozen checks,31 runner tests; no live calls before freeze.')
 for key in ['client','judge_client']:
  new[key+'_path']=rel(CODE/'02_BACKEND/lawrag/research/experiment_client.py');new[key+'_sha256']=sha(ROOT/new[key+'_path'])
 for key,name in [('validation','contracts-api-final-summary.json'),('validation_receipt','tested-freeze.json'),('provider_authorization','provider-authorization.json'),('candidate_diff','candidate-files-diff.json')]:new[key+'_path']=rel(ART/name);new[key+'_sha256']=sha(ART/name)
 new['development_parent_candidate_path']=rel(parent/'candidate.json');new['development_parent_candidate_sha256']=sha(parent/'candidate.json')
 for key in ['product_cases','evaluator_cases','corpus','authorization','evaluation_contract','dataset_preparation','snapshot','corpus_article_root_count']:
  new[key+'_path']=rel(ART/Path(old[key+'_path']).name);hk=key+'_file_sha256' if key=='snapshot' else key+'_sha256';assert sha(ROOT/new[key+'_path'])==old[hk]
 new['provider_failover']=read(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_failover']
 new['input_output_representation']={**old['input_output_representation'],'server_step_state':'server-step-state-v1','canonical_view_unchanged_by_step_state':True,'navigation_base':'ADR1052overview'}
 new['semantic_contract_files']={p:files[p] for p in old['semantic_contract_files']}
 new['prior_design_freeze_path']=rel(PRIOR);new['prior_design_freeze_sha256']=sha(PRIOR)
 new['evaluation_scripts']={p.replace('/adr_1049/','/adr_1054/'):sha(ROOT/p.replace('/adr_1049/','/adr_1054/')) for p in old['evaluation_scripts']}
 for p in sorted(Path(__file__).parent.glob('*.py')):new['runner_hashes'][rel(p)]=sha(p)
 for p in [PRIOR]+[ART/n for n in ['provider-authorization.json','provider-endpoints.json','contracts-api-final-summary.json','contracts-api-final-imports.json','frozen-state-summary.json','frozen-state-imports.json','tested-freeze.json','identical-arm-code.json','candidate-files-diff.json','runner-contracts.log','implementation-plan.json']]:new['runner_hashes'][rel(p)]=sha(p)
 for key in ['execution_order','snapshot_digest','snapshot_file_sha256','data_manifest_sha256','store_sha256','product_cases_sha256','evaluator_cases_sha256','corpus_sha256','authorization_sha256','evaluation_contract_sha256','response_reception','unchanged_core_semantic_definitions']:assert new[key]==old[key],key
 exact_write(ART/'design-freeze.json',new)
 old_art=PRIOR.parent
 preserved={rel(p):sha(p) for p in sorted((old_art/'matrix').glob('*/result.json'))}
 for p in [ROOT/'04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state/artifacts/design-freeze.json',ROOT/'04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state/artifacts/matrix/001-fsc-hard-002-A0/result.json',PRIOR,ROOT/new['main_pointer_path'],ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',old_art/'matrix-stop.json']:preserved[rel(p)]=sha(p)
 save(ART/'execution-plan.json',{'scope':'new111cells; never replay1049','preserved_files':preserved,'preserved_completed_cells':43,'resume_ordinal':1,'pinned_files':{**{rel(p):sha(p) for p in Path(__file__).parent.glob('*.py')},rel(ART/'design-freeze.json'):sha(ART/'design-freeze.json')}})
 print('FROZEN1054;692files;37x3;no live calls yet')
if __name__=='__main__':main()
