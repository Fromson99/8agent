"""Summarize only actual delivery/consumer evidence before final archive sealing."""
import gzip,json,re
from pathlib import Path
from build import H,R,NAME,sha,enc

source=json.loads((H/'SOURCE_BINDING.json').read_bytes());scenarios={};contracts=None
for kind in ('prior_main82','legacy_interrupted','oracle_dp'):
    passed=json.loads((H/('PASS_'+kind+'.json')).read_bytes());assert passed['status']=='PASS'
    transcript=H/('TEST_'+kind+'.json.gz');assert sha(transcript.read_bytes())==passed['transcript_sha256']
    rows=json.loads(gzip.decompress(transcript.read_bytes()))
    for row in rows:
        if any(str(a).endswith('installed_contract_runner.py') for a in row['argv']):
            assert row['exit']==0
            contracts=int(re.search(r'(\d+) passed',row['stdout']).group(1))
            assert 'INSTALLED_CONTRACT_IMPORTS PASS' in row['stdout']
    scenarios[kind]={'commands':len(rows),'transcript_sha256':passed['transcript_sha256'],
                     'exact_rollback':passed['exact_rollback'],'data_preserved':passed['data_preserved'],
                     'installed_archive':passed['installed_archive'],'code_root':passed['code_root'],
                     'tls_service_boots':sum('SERVICE_TLS_BOOTSTRAP PASS MAIN83' in row['stdout'] for row in rows),
                     'committed_code_gates':sum(row['argv'][-1]=='gate-code' and row['exit']==0 for row in rows),
                     'committed_generation_gates':sum(row['argv'][-1]=='gate' and row['exit']==0 for row in rows)}
    assert scenarios[kind]['tls_service_boots']==scenarios[kind]['committed_code_gates']==scenarios[kind]['committed_generation_gates']==1
assert contracts is not None and contracts>=330,contracts
active=json.loads((H/'active-consumer.json').read_bytes());assert active['status']=='PASS' and len(active['checks'])==10 and all(active['checks'].values())
assert '17 passed' in (H/'REPLACEMENT_TEST.log').read_text()
python=json.loads((H/'PYTHON311_CHECK.json').read_bytes());assert python['status']=='PASS'
resources={}
for name in ('replacement-resources.json','delivery-resources.json'):
    row=json.loads((H/name).read_bytes())
    assert row['returncode']==0 and row['stop_reason'] is None
    resources[name]={'sha256':sha((H/name).read_bytes()),'peak_group_rss_bytes':row['peak_group_rss_bytes'],
                     'min_available_bytes':row['min_available_bytes'],'seconds':row['seconds']}
assert (R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()==(H/'SOURCE_POINTER.json').read_bytes()
value={'status':'PASS','scope':'Technical delivery verification of selected MAIN83 plus its qualified non-serving dependencies.',
       'main_release':source['main_basis']['release_id'],'main_generation':83,
       'main_pointer_changed':False,'selected_main_files':370,'selected_main_files_unchanged':source['selected_main_files_unchanged'],
       'workflow_versions':source['main_basis']['workflow_versions'],'payload_files':source['payload_files'],
       'installed_contracts_passed':contracts,'replacement_gate_contracts_passed':17,
       'installation_scenarios':scenarios,'python311':python,
       'actual_local_service':{'checks':len(active['checks']),'code_root':active['code_root'],
           'service_entry':active['service_entry'],'service_sha256':active['service_sha256'],
           'data_manifest_sha256':active['data_manifest_sha256'],
           'search_selection_fingerprint':active['search_selection_fingerprint'],
           'record_sha256':sha((H/'active-consumer.json').read_bytes())},
       'external_fulltext_audit':{'path':'04_EXPERIMENTS/ADR/ADR-0871-host-owned-fulltext-live/artifacts/summary.json','sha256':sha((R/'04_EXPERIMENTS/ADR/ADR-0871-host-owned-fulltext-live/artifacts/summary.json').read_bytes())},
       'actual_model_calls':0,'genos_field_deployment':'NOT_VERIFIED',
       'resource_checks':resources,'heavy_workers':1,
       'default_install_data_access':'Existing fixed path config and small generation manifest only; no DB/index/selection mutation.',
       'oracle_dp':'Selected Oracle serving code and qualified publishing helpers retained; runtime tested with simulated Oracle, not internal Oracle.',
       'test_harness_sha256':{n:sha((H/n).read_bytes()) for n in ('test_delivery.py','installed_contract_runner.py','code_smoke.py')},
       'actual_consumer_script':{'path':'06_TOOLS/EXPERIMENTS/adr_0870/consumer.py','sha256':sha((R/'06_TOOLS/EXPERIMENTS/adr_0870/consumer.py').read_bytes())},
       'failures_preserved':['failures/test-import-001/RECEIPT.json'],
       'limitations':['No GENOS network, internal model, production push, revision or workflow editor access.',
          'Synthetic protocol tests do not certify legal correctness, speed improvement or field timeout resolution.',
          'Existing GENOS_SERVING_PATHS binding is required by the full-code installer.',
          'Full generation gate verifies the existing generation; Oracle provider/release must also be checked in the field workflow.',
          'Final transfer archive execution is recorded separately in FINAL_VERIFICATION.json.']}
(H/'VALIDATION.json').write_bytes(enc(value))
print(json.dumps({'status':'PASS','contracts':contracts,'replacement':17,'active_service':10,
                  'installation_commands':sum(v['commands'] for v in scenarios.values()),'main_generation':83}))
