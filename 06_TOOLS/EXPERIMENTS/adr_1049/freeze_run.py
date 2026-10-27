"""Freeze the reviewed provider-only exception before any live call."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import sys
from common import ROOT,ADR,ART,read,save,sha,exact_write
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1048-ontology-mvp-r10-restart/artifacts/design-freeze.json'
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1049/provider-failover-r11/revisions/rev-001/snapshot'
def rel(p):return str(p.relative_to(ROOT))
def main():
 assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
 old=read(PRIOR);new=deepcopy(old)
 tested=read(ART/'contracts-api-r2-summary.json')
 assert tested['status']==0 and tested['passed']==641 and not tested['production_import_leaks'] and not tested['candidate_changed_during_tests']
 files={str(p.relative_to(CODE)):sha(p) for p in CODE.rglob('*') if p.is_file()}
 assert files==tested['files']
 assert '20 passed' in (ART/'runner-contracts-r2.log').read_text()
 for p,h in old['runner_hashes'].items():assert sha(ROOT/p)==h,p
 for p,h in old['semantic_contract_files'].items():assert files[p]==h,p
 changed=[p for p,h in files.items() if old['files'].get(p)!=h]
 allowed={'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/PIPELINE.json','02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/provider_failover.py','05_TESTS/CONTRACTS/test_provider_failover_adr1049.py'}
 assert all(p in allowed or p.startswith('02_BACKEND/ENGINES/') for p in changed),changed
 assert set(old['files'])<=set(files)
 save(ART/'candidate-files-diff.json',{'changed':changed,'files':len(files),'removed':[], 'semantic_contracts_unchanged':True})
 sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate
 candidates=[]
 for arm,name in [('A1','provider-failover-a1-r11'),('A2','provider-failover-r11')]:
  directory=CODE.parents[3]/name;assert not adr_candidate.validate(directory)
  candidate=read(directory/'candidate.json');revision=candidate['revisions'][-1]
  assert {r['target_path']:r['snapshot_sha256'] for r in candidate['files']}==files
  candidates.append({'candidate_id':name,'arm_id':arm,'experiment_id':'ADR-1049-experiment-v1','run_ids':['run-001'],'manifest_path':rel(directory/'candidate.json'),'manifest_sha256':sha(directory/'candidate.json'),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],'runner_path':rel(Path(__file__).with_name('run_matrix.py')),'runner_sha256':sha(Path(__file__).with_name('run_matrix.py'))})
 assert sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==old['policy_sha256']
 assert sha(ROOT/old['main_pointer_path'])==old['main_pointer_sha256']
 source=ROOT/old['data_path']/'store.sqlite';before=source.stat();source_sha=sha(source);after=source.stat()
 fields=lambda s:(s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 assert fields(before)==fields(after) and source_sha==old['store_sha256']
 integrity=read(ROOT/old['source_integrity_path']);assert (integrity['size'],integrity['mtime_ns'],integrity['ctime_ns'])==fields(after)
 manifest_path=ADR/'실험/manifest.json';m=read(manifest_path)
 m['design']['code_isolation']['candidates']=candidates;m['design']['criteria_frozen_before_run']=True
 stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
 previous=m['reservation']['updated_at'];m['reservation']['updated_at']=stamp
 m['reservation']['events'].append({'action':'execution_design_frozen','at':stamp,'owner':'Codex','session_id':m['reservation']['session_id'],'note':'641 candidate/API tests and20 runner tests pass. Same model FP8 provider chain, known429 only, all physical calls counted; no hidden retry or MAIN change.'})
 save(manifest_path,m)
 p=ADR/'README.md';p.write_text(p.read_text().replace('updated_at: '+previous,'updated_at: '+stamp))
 new.update(frozen_at=stamp,experiment_id=m['experiment_id'],design=m['design'],manifest_sha256_at_freeze=sha(manifest_path),code_root=rel(CODE),files=files,baseline_policy_sha256=old['policy_sha256'],policy_sha256=sha(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),validation_inheritance=False,validation_note='641 candidate contracts/API checks rerun plus20 runner checks; imports exclusively candidate. No live calls before freeze.')
 for key in ['client','judge_client']:
  new[key+'_path']=rel(CODE/'02_BACKEND/lawrag/research/experiment_client.py');new[key+'_sha256']=sha(ROOT/new[key+'_path'])
 for key,name in [('validation','contracts-api-r2-summary.json'),('validation_receipt','tested-freeze.json'),('provider_authorization','provider-authorization.json'),('candidate_diff','candidate-files-diff.json')]:
  new[key+'_path']=rel(ART/name);new[key+'_sha256']=sha(ART/name)
 new['development_parent_candidate_path']=rel((ROOT/old['code_root']).parents[2]/'candidate.json');new['development_parent_candidate_sha256']=sha(ROOT/new['development_parent_candidate_path'])
 for key in ['product_cases','evaluator_cases','corpus','authorization','evaluation_contract','dataset_preparation','snapshot','corpus_article_root_count']:
  new[key+'_path']=rel(ART/Path(old[key+'_path']).name)
  hk=key+'_file_sha256' if key=='snapshot' else key+'_sha256';assert sha(ROOT/new[key+'_path'])==old[hk]
 new['equal_operational_overrides']['max_transport_retries']=4
 new['provider_failover']=read(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_failover']
 new['reporting_rules']['provider_mixing']='Report physical requested/observed provider and errors separately by arm. Mixed provider distributions confound comparisons.'
 new['prior_design_freeze_path']=rel(PRIOR);new['prior_design_freeze_sha256']=sha(PRIOR)
 new['evaluation_scripts']={p.replace('/adr_1048/','/adr_1049/'):sha(ROOT/p.replace('/adr_1048/','/adr_1049/')) for p in old['evaluation_scripts']}
 for p in sorted(Path(__file__).parent.glob('*.py')):new['runner_hashes'][rel(p)]=sha(p)
 for p in [PRIOR]+[ART/n for n in ['provider-authorization.json','provider-endpoints.json','contracts-api-r2-summary.json','contracts-api-r2-imports.json','tested-freeze.json','identical-arm-code.json','candidate-files-diff.json','runner-contracts-r2.log']]:new['runner_hashes'][rel(p)]=sha(p)
 for key in ['execution_order','snapshot_digest','snapshot_file_sha256','data_manifest_sha256','store_sha256','product_cases_sha256','evaluator_cases_sha256','corpus_sha256','authorization_sha256','evaluation_contract_sha256','response_reception','input_output_representation','semantic_contract_files','unchanged_core_semantic_definitions']:assert new[key]==old[key],key
 exact_write(ART/'design-freeze.json',new)
 print('FROZEN provider-only exception;111 sequential cells;641 API/contracts;20 runner checks;livecalls0')
if __name__=='__main__':main()
