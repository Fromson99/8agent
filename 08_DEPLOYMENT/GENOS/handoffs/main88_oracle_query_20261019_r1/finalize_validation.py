from pathlib import Path
import hashlib,json,re,zipfile,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[3]
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists()
assert (H/'SOURCE_POINTER.json').read_bytes()==(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes(),'Latest MAIN changed'
text=(H/'MERGED_CONTRACTS_02.txt').read_text();assert '120 passed' in text and 'INSTALLED_CONTRACT_IMPORTS PASS; modules=268' in text
passes=[json.loads((H/('PASS_'+k+'.json')).read_bytes()) for k in ('preserved-config-interruption','no-config-standalone')]
assert all(v['status']=='PASS' for v in passes)
assert '2 passed' in (H/'DELIVERY_TESTS_02.txt').read_text()
with zipfile.ZipFile(H/'code.zip') as z:
    manifest=json.loads(z.read('CODE_MANIFEST.json'))
    for row in manifest['files']:
        raw=z.read(row['path']);assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
        assert (H/'test-code'/row['path']).read_bytes()==raw
    assert json.loads(z.read('00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'))['candidate_navigation']['answer_first'] is True
value={'status':'PASS_LOCAL_FIELD_UNVERIFIED','main_release':'answer-first-followup-20261019-r1','main_pointer_generation':88,
    'main_pointer_unchanged':True,'payload_files':len(manifest['files']),'code_zip_sha256':sha((H/'code.zip').read_bytes()),
    'merged_contracts':{'passed':120,'warnings':2,'product_modules_from_packaged_code':268,'seconds':41.72,
        'scope':['Oracle selective query','SQLite compatibility','MAIN88 answer-first and follow-up','team/session identity','actual service entry','deployment path override regression']},
    'delivery':passes,'python_311':json.loads((H/'PYTHON311.json').read_bytes()),
    'prior_oracle_sql_evidence':{'path':'09_ARTIFACTS/AUDITS/20261019-oracle-query','final_tests_sha256':sha((R/'09_ARTIFACTS/AUDITS/20261019-oracle-query/FINAL_TESTS.txt').read_bytes()),
       'passed':59,'real_oracle_sql_cases':1,'oracle_version':'23','this_package_reran_live_oracle':False,
       'limits':'Local driver replaces ORDS HTTP; scripted model; synthetic NFS proof; no field Oracle19/ORDS/model/NFS certification'},
    'integration_fix':'Oracle mode ignores retained SQLite deployment-path configuration; preserves explicit external runtime/state paths',
    'failures_preserved':['MERGED_CONTRACTS_01.txt: 113 pass/7 fixture-root failures; isolated workspace directories and product workflow imports fixed in harness',
        'DELIVERY_TESTS_01.txt: installer smoke referenced a nonexistent module name; corrected to oracle_query_db before final installation tests'],
    'field':{'code_commit':None,'code_serving_revision':None,'query_release_id':None,'query_pointer_revision':None,'workflow_test':'NOT_RUN'},
    'not_done':['GENOS apply/push/deploy','Dataiku schema creation/publication/activation','daily Dataiku schedule','internal LLM and full corpus performance'],
    'evidence':{p.name:sha(p.read_bytes()) for p in [H/'MERGED_CONTRACTS_02.txt',H/'DELIVERY_TESTS_02.txt',H/'PYTHON311.json',H/'INTEGRATION_OVERRIDES.json']}}
(H/'VALIDATION.json').write_bytes(enc(value))
print(json.dumps({'status':value['status'],'tests':122,'code_zip_sha256':value['code_zip_sha256']}))
