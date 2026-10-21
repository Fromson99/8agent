from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent;R=H.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
passes=[json.loads((H/('PASS_'+mode+'.json')).read_text()) for mode in ('preserved-config-interruption','no-config-standalone')]
assert all(v['status']=='PASS' for v in passes)
assert '125 passed, 8 deselected' in (H/'CONTRACT_TESTS_01.txt').read_text()
assert 'INSTALLED_CONTRACT_IMPORTS PASS' in (H/'CONTRACT_TESTS_01.txt').read_text()
assert '2 passed' in (H/'DELIVERY_TESTS_01.txt').read_text()
python=json.loads((H/'PYTHON311.json').read_text());assert python['status']=='PASS' and python['code_zip_sha256']==sha(H/'code.zip')
binding=json.loads((H/'SOURCE_BINDING.json').read_text())
value={'status':'LOCAL_DELIVERY_VERIFIED_FIELD_PENDING','version':'GENOS_WORKFLOW_PROGRESS_20261019_R1',
 'base':'GENOS_MAIN88_ORACLE_QUERY_20261019_R1','code_zip_sha256':sha(H/'code.zip'),
 'changes':{'sources':11,'with_manifests_and_pins':len(binding['changes']),'unchanged':binding['unchanged_files']},
 'contract_tests':{'passed':125,'deselected':8,'product_imports_from_packaged_code':240,
   'coverage':'display/logging/source cards/transport/process traces/current API/SSE/resume/duplicate/stale state',
   'fixture':'two synthetic documents with scripted model, no network/model calls',
   'log':'CONTRACT_TESTS_01.txt','resource_receipt':'CONTRACT_RESOURCES_01.json'},
 'working_source_verification':{'passed':126,'receipt':'09_ARTIFACTS/AUDITS/20261019-workflow-progress/VALIDATION.json'},
 'delivery_tests':{'passed':2,'scenarios':passes,'commands':sum(v['commands'] for v in passes),
   'coverage':'actual uploaded TRANSFER ZIP/TXT, existing Git checkout, physical symlink resolution, interrupted apply recovery, idempotence, same committed checkout code gate, tamper refusal, exact rollback',
   'resource_receipt':'DELIVERY_RESOURCES_01.json'},
 'python311':python,'streaming':'investigation progress live; final answer chunks after durable verified result; no model-generation token streaming',
 'source_pointer_sha256':sha(H/'SOURCE_POINTER.json'),'selected_local_main_changed':False,
 'field':{'checkout':'existing DEV, earlier field physical root /workspace','commit':None,'generation_path':None,
          'generation_manifest_sha256':None,'oracle_query_release':None,'codeserving_revision':None,'workflow_editor_saved':False,'verified':False},
 'remaining':['GENOS import/commit/push/revision deployment','separate workflow editor source update',
              'same question in workflow test UI with internal model/Oracle/NFS','real proxy/browser buffering behavior'],
 'file_sha256':{n:sha(H/n) for n in ['CODE_MANIFEST.json','SOURCE_BINDING.json','PACKAGE_SPEC.json','run.py','replace.py','code_smoke.py','CONTRACT_TESTS_01.txt','DELIVERY_TESTS_01.txt']}}
(H/'VALIDATION.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('Validation recorded; installation commands:',value['delivery_tests']['commands'])
