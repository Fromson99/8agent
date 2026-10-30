import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    assert not (HERE/'VALIDATION.json').exists()
    latest, runs = {}, []
    for name in ('TEST_INITIAL.xml','TEST_REPAIR.xml'):
        cases = list(ET.parse(HERE/name).iter('testcase'))
        failed = []
        for case in cases:
            key = case.get('classname')+'::'+case.get('name')
            passed = all(case.find(k) is None for k in ('failure','error','skipped'))
            latest[key] = passed
            if not passed: failed.append(key)
        runs.append({'file':name,'tests':len(cases),'failed':failed,'sha256':sha((HERE/name).read_bytes())})
    assert len(latest)==12 and all(latest.values())
    script = HERE/'DATAIKU_ONE_ATTEMPT_R2.txt'
    ast.parse(script.read_text(),feature_version=(3,9))
    client = HERE.parent/'pipeline_attempt_recovery_20261029_r1/DATAIKU_R10_RECOVERY_CLIENT_20261029_R1.zip'
    assert sha(client.read_bytes())=='34118187c25455bf1c476640529b12d873cc4c641148ac36387c19696f63862d'
    validation = {'status':'LOCAL_NOTEBOOK_INPUT_SELECTION_FIX_PASS','unique_tests_passed':12,'runs':runs,
        'initial_harness_errors_preserved':['expected ValueError instead of existing legacy RunError for invalid receipt','treated service.handle HEALTH result as an HTTP data envelope'],
        'new_script_sha256':sha(script.read_bytes()),'client_zip_sha256':sha(client.read_bytes()),
        'client_zip_changed':False,'genos_code_changed':False,'recipe_reinstall_required':False,
        'actual_field_calls':0,'default_action':'authorize_one_attempt',
        'compute_auto_started':False,'extra_attempts':1,'deadline_extended':False,'usage_reset':False,
        'original_error_reproduced':True,'whole_published_notebook_entry_exercised':True,
        'external_db_context_mocked':True,'real_receipt_parser_used':True,'local_native_health_used':True}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    archive = HERE/'DATAIKU_ONE_ATTEMPT_INPUT_FIX_20261029_R2.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in ('DATAIKU_ONE_ATTEMPT_R2.txt','GUIDE.txt','VALIDATION.json'):
            z.write(HERE/name,name)
    with zipfile.ZipFile(archive) as z:
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
        assert z.read(script.name)==script.read_bytes()
    receipt = {n:{'bytes':(HERE/n).stat().st_size,'sha256':sha((HERE/n).read_bytes())}
        for n in (archive.name,script.name,'GUIDE.txt')}
    (HERE/'DELIVERY.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    main()
