"""Record actual checks of the exact MAIN87 delivery, without claiming field deployment."""
import gzip,json,re
from build import H,R,sha,enc

source=json.loads((H/'SOURCE_BINDING.json').read_bytes())
scenarios={};contracts=None
for kind in ('prior_main84','legacy_interrupted','oracle_dp'):
    passed=json.loads((H/('PASS_'+kind+'.json')).read_bytes())
    assert passed['status']=='PASS'
    transcript=H/('TEST_'+kind+'.json.gz')
    assert sha(transcript.read_bytes())==passed['transcript_sha256']
    rows=json.loads(gzip.decompress(transcript.read_bytes()))
    for row in rows:
        if any(str(a).endswith('installed_contract_runner.py') for a in row['argv']):
            assert row['exit']==0 and 'INSTALLED_CONTRACT_IMPORTS PASS' in row['stdout']
            contracts=int(re.search(r'(\d+) passed',row['stdout']).group(1))
    scenarios[kind]={k:passed[k] for k in ('code_root','exact_rollback','data_preserved','installed_archive','transcript_sha256')}
    scenarios[kind].update(commands=len(rows),
        tls_service_boots=sum('SERVICE_TLS_BOOTSTRAP PASS MAIN87' in row['stdout'] for row in rows),
        committed_code_gates=sum(row['argv'][-1]=='gate-code' and row['exit']==0 for row in rows),
        committed_generation_gates=sum(row['argv'][-1]=='gate' and row['exit']==0 for row in rows))
    assert scenarios[kind]['tls_service_boots']==scenarios[kind]['committed_code_gates']==scenarios[kind]['committed_generation_gates']==1
assert contracts and contracts>=385
active=json.loads((H/'active-consumer.json').read_bytes())
assert active['status']=='PASS' and len(active['checks'])==10 and all(active['checks'].values())
assert '17 passed' in (H/'REPLACEMENT_TEST.log').read_text()
python=json.loads((H/'PYTHON311_CHECK.json').read_bytes());assert python['status']=='PASS'
resources={}
for name in ('replacement-resources.json','delivery-resources.json'):
    row=json.loads((H/name).read_bytes())
    assert row['returncode']==0 and row['stop_reason'] is None
    resources[name]={k:row[k] for k in ('peak_group_rss_bytes','min_available_bytes','seconds')}
    resources[name]['sha256']=sha((H/name).read_bytes())
for name,expected in (('failures/legacy-fixtures-001/delivery-resources.json',1),
                      ('working-repro-resources.json',1),('current-stream-resources.json',0)):
    row=json.loads((H/name).read_bytes())
    assert row['returncode']==expected and row['stop_reason'] is None
    resources[name]={k:row[k] for k in ('returncode','peak_group_rss_bytes','min_available_bytes','seconds')}
    resources[name]['sha256']=sha((H/name).read_bytes())
repro=json.loads((H/'WORKING_FAILURE_REPRO.json').read_bytes())
assert len(repro)==4 and all(r['outcome']=='failed' for r in repro)
assert '2 passed' in (H/'CURRENT_STREAM.log').read_text()
assert (R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()==(H/'SOURCE_POINTER.json').read_bytes()
evidence={}
for name,path in {
    'local_main_implementation':'08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/IMPLEMENTATION_RESULT.json',
    'cm8_actual_model':'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency/artifacts/run-001/result.json',
    'independent_qualification':'04_EXPERIMENTS/ADR/ADR-0896-cm-read-continuity-qualification/artifacts/run-001/result.json',
    'actual_workflow':'04_EXPERIMENTS/ADR/ADR-0897-main87-workflow-live/RESULT.txt',
}.items():
    evidence[name]={'path':path,'sha256':sha((R/path).read_bytes())}
value={'status':'PASS','main_generation':87,'main_release':source['main_basis']['release_id'],
    'scope':'Technical verification of the exact cumulative MAIN87 code package in isolated local GENOS-style checkouts.',
    'payload_files':source['payload_files'],'selected_serving_files_unchanged':source['selected_main_files_unchanged'],
    'workflow_versions':source['main_basis']['workflow_versions'],
    'installed_contracts_passed':contracts,'replacement_gate_contracts_passed':17,
    'legacy_cases_deselected':4,'current_stream_fixture_cases_passed':2,
    'legacy_disposition':{'working_reproduced':4,'product_changes':False,
        'record':'failures/legacy-fixtures-001/RECEIPT.json',
        'sha256':sha((H/'failures/legacy-fixtures-001/RECEIPT.json').read_bytes())},
    'installation_scenarios':scenarios,'python311':python,'resources':resources,'heavy_workers':1,
    'active_consumer_record':{'path':'active-consumer.json','sha256':sha((H/'active-consumer.json').read_bytes()),'checks':10,'executed_during_main87_qualification':True},
    'prior_actual_execution_evidence':evidence,'new_model_calls':0,'local_main_pointer_changed':False,
    'default_install_data_access':'Existing fixed config and small generation manifest only; no DB/index scan or data/selection mutation.',
    'test_harness_sha256':{n:sha((H/n).read_bytes()) for n in ('test_delivery.py','installed_contract_runner.py','code_smoke.py','test_current_stream.py','diagnose_legacy.py')},
    'failures_preserved':['failures/test-directory-001/RECEIPT.json','failures/legacy-fixtures-001/RECEIPT.json'],
    'genos_field_status':'NOT_VERIFIED','limitations':[
        'GENOS installation, internal model, actual Oracle, push, revision, and workflow editor verification remain field steps.',
        'Local MAIN87 CM8 returned 8 responses with 7 core answers satisfied; CM003 interpretation remains unresolved.',
        'The actual local workflow completed with partial status and two DEFERRED rows, 12 model calls, about 550 seconds, and 21685 answer characters.',
        'Referenced internal rule acquisition, source classification, applicability judgments and repetitive lengthy output still need improvement.',
        'The NFS generation gate does not establish Oracle provider/release/cache correctness; confirm the selected provider in the field workflow.',
        'Repository preflight reports a pre-existing blank line at ARCHITECTURE.md:431; that unrelated file is preserved.',
        'Final sealed ZIP execution is recorded separately in FINAL_VERIFICATION.json.'
    ]}
(H/'VALIDATION.json').write_bytes(enc(value))
print(json.dumps({'status':'PASS','contracts':contracts,'replacement':17,'installation_commands':sum(x['commands'] for x in scenarios.values()),'main':87}))
