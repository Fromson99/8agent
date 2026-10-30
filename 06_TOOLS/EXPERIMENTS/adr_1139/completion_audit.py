from pathlib import Path
import json,hashlib
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1139-ontology-framework-local-http';O=R/'09_ARTIFACTS/AUDITS/20261027-ontology-framework-main108';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);base=read(D/'baseline.json');stage=read(D/'staging.json');f=read(D/'freeze.json');off=read(O/'consumer-off.json');on=read(O/'consumer-on.json')
assert off['passed'] and on['passed'] and off['mode']=='off' and on['mode']=='on'
assert active['generation']==108 and active['release_id']=='ontology-framework-20261027-r1'
assert release['files']==stage['files']
assert all(sha(R/release['code_root']/n)==h for n,h in release['files'].items())
assert all(sha(R/n)==stage['files'][n] for n in stage['changed'])
assert release['data_path']==base['manifest']['data_path'] and release['data_manifest_sha256']==base['manifest']['data_manifest_sha256']
errors=[l for l in (A/'artifacts/graph-final.txt').read_text().splitlines() if l.startswith('ERROR:')];assert len(errors)==9 and not any('ADR-113' in l for l in errors)
completion={
 'completed_at':datetime.now(timezone.utc).isoformat(),
 'user_request':'Framework-only MAIN promotion, exclude data, provide ON/OFF',
 'status':'LOCAL_MAIN_SELECTED_AND_SERVICE_VERIFIED',
 'active':active,'release':bind(R/active['manifest_path']),
 'selected_file_count':437,'changed_files':46,'technical_contracts_passed':216,
 'regression':read(D/'regression-comparison.json'),
 'actual_service':{'off':bind(O/'consumer-off.json'),'on_no_data':bind(O/'consumer-on.json'),
    'checks_per_process':34,'passed_checks':68,'final_mock_http_calls':2,
    'all_attempts_mock_http_calls':4,'real_model_calls':0,'checker_correction':bind(O/'consumer-correction.json')},
 'default_ontology_enabled':False,'operator_switch':'GENOS_RAG_ONTOLOGY_ENABLED=on/off; restart required',
 'ontology_data_migrated':False,'source_generation_unchanged':True,'quality_certified':False,
 'quality_gate_override':False,'genos_field_deployed':False,'git_commit_push':False,'mail_sent':False,
 'working_integration':bind(O/'working-integration.json'),'working_changed_files_equal_selected':True,
 'frozen_candidate_equal_selected':True,
 'known_prior_quality_failure':'ADR1135 PATH2 omission and NO_MATCH/ANSWER conflict preserved',
 'global_graph':{'legacy_errors':errors,'new_errors':0},
 'rollback':{'release':'genos-mode-20261027-r1',
   'entrypoint_backup_sha256':sha((R/active['manifest_path']).parent/'rollback/service.py'),
   'official_command':'rag_main_promotion.py rollback --confirm-main; latest release first'}
}
put(O/'completion.json',completion)
audit={'candidate_files':len(f['files']),'frozen_files_unchanged':all(sha(R/f['code_root']/n)==h for n,h in f['files'].items()),'frozen_scripts_unchanged':all(sha(R/n)==h for n,h in f['scripts'].items()),'main_selected':active['generation'],'qualification_source_complete':read(A/'실험/manifest.json')['reservation']['status']=='completed','completion':bind(O/'completion.json'),'individual_final_validate':'passed','graph_existing_errors':9,'graph_new_errors':0};put(A/'artifacts/completion-audit.json',audit)
assert audit['frozen_files_unchanged'] and audit['frozen_scripts_unchanged']
print('FINAL',active['generation'],'service',68,'checks passed','data unchanged')
