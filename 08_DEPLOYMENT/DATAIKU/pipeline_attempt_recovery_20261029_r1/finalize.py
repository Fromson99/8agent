import ast
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from build import writezip, PACKAGE

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    assert not (HERE/'VALIDATION.json').exists(), 'Preserve sealed validation'
    tests, runs = {}, []
    for filename in ('TEST_INITIAL.xml', 'REGRESSION.xml', 'REGRESSION_REPAIR.xml'):
        cases = list(ET.parse(HERE/filename).iter('testcase'))
        failed = []
        for case in cases:
            key = case.get('classname') + '::' + case.get('name')
            success = all(case.find(k) is None for k in ('failure','error','skipped'))
            tests[key] = success
            if not success: failed.append(key)
        runs.append({'file':filename, 'tests':len(cases), 'failed':failed, 'sha256':sha((HERE/filename).read_bytes())})
    assert all(tests.values()) and len(tests) == 78
    with zipfile.ZipFile(HERE/PACKAGE) as z:
        manifest = json.loads(z.read('PACKAGE_FILES.json'))
        assert set(manifest) | {'PACKAGE_FILES.json'} == set(z.namelist())
        for n, expected in manifest.items():
            assert sha(z.read(n)) == expected
            if n.endswith('.py'): compile(z.read(n), n, 'exec')
    for filename in ('DATAIKU_RECOVERY_INSTALL.txt', 'DATAIKU_ONE_ATTEMPT.txt'):
        ast.parse((HERE/filename).read_text())
    build = json.loads((HERE/'BUILD.json').read_text())
    assert build['server_changed'] is False
    validation = {**build, 'status':'LOCAL_EXPLICIT_ONE_ATTEMPT_RECOVERY_PASS', 'unique_tests_passed':len(tests), 'test_runs':runs,
        'initial_test_harness_failure':'Regression selection also selected the sealed R10 GENOS installer fixture; its copied helper pointed to a missing local installer. Corrected fixture path to original sealed R10 installer and reran that case successfully. Original REGRESSION.xml retained.',
        'default_action':'inspect', 'grant_requires_explicit_operator_action':True,
        'counter_reset':False, 'deadline_extended':False, 'usage_reset':False,
        'maximum_additional_compute_attempts':1, 'old_checkpoints_preserved':True,
        'original_input_reusable':True, 'stage02_restarts_from_beginning':True,
        'actual_genos_contacted':False, 'actual_dataiku_changed':False,
        'actual_grant_written':False, 'new_performance_run':False, 'model_calls':0, 'main_changed':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2)+'\n')
    names = [PACKAGE, 'DATAIKU_RECOVERY_INSTALL.txt','DATAIKU_ONE_ATTEMPT.txt','GUIDE.txt','BUILD.json','VALIDATION.json']
    writezip(HERE/'DATAIKU_R10_ATTEMPT_RECOVERY_20261029_R1.zip', {n:(HERE/n).read_bytes() for n in names})
    def check_archive(raw):
        count = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert len(z.namelist()) == len(set(z.namelist()))
            for n in z.namelist():
                assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
                count += 1
                if n.lower().endswith('.zip'): count += check_archive(z.read(n))
        return count
    outer = HERE/'DATAIKU_R10_ATTEMPT_RECOVERY_20261029_R1.zip'
    receipt = {'outer_zip':outer.name,'bytes':outer.stat().st_size,'sha256':sha(outer.read_bytes()),'recursive_archive_members':check_archive(outer.read_bytes()),'javascript_members':0,
        'attachments':{n:{'bytes':(HERE/n).stat().st_size,'sha256':sha((HERE/n).read_bytes())} for n in [outer.name,'DATAIKU_RECOVERY_INSTALL.txt','DATAIKU_ONE_ATTEMPT.txt','GUIDE.txt']}}
    (HERE/'DELIVERY.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
