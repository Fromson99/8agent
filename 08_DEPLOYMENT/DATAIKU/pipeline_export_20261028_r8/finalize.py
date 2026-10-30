"""Bind the actual tested ZIP bytes and local installer checkouts; no deployment."""
import ast
import io
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from build import HERE,ROOT,SERVICE,PACKAGE,sha,save,writezip

def suite(name):
    root=ET.parse(HERE/name).getroot()
    tests=root.findall('.//testcase')
    failed=[t.attrib['name'] for t in tests if t.find('failure') is not None or t.find('error') is not None]
    return {'tests':len(tests),'passed':len(tests)-len(failed),'failed':failed}

def main():
    build=json.loads((HERE/'BUILD.json').read_text())
    results={n:suite(n) for n in ('TEST.xml','NATIVE_TEST.xml','QUERY_TEST.xml','BASELINE_COMPAT_TEST.xml')}
    assert results['TEST.xml']=={'tests':91,'passed':91,'failed':[]}
    assert results['NATIVE_TEST.xml']=={'tests':4,'passed':4,'failed':[]}
    failure=['test_export_resume_and_cli_uses_same_bundled_code']
    assert results['QUERY_TEST.xml']['failed']==results['BASELINE_COMPAT_TEST.xml']['failed']==failure
    for name,record in build['files'].items():
        raw=(HERE/name).read_bytes();assert sha(raw)==record['sha256'] and len(raw)==record['bytes']
    with zipfile.ZipFile(HERE/(SERVICE+'.zip')) as z:
        pins_raw=z.read(SERVICE+'/CODE_PINS.json');pins=json.loads(pins_raw)['files']
        assert sha(pins_raw)==build['code_sha256']
        assert set(z.namelist())=={SERVICE+'/'+n for n in pins}|{SERVICE+'/CODE_PINS.json'}
        assert all(sha(z.read(SERVICE+'/'+n))==h for n,h in pins.items())
        for name in ('oracle_query_publish','oracle_query_package'):
            path='02_BACKEND/lawrag/pipeline/'+name+'.py'
            def selected(raw):
                nodes=ast.parse(raw).body
                return {n.name:ast.dump(n,include_attributes=False) for n in nodes if isinstance(n,ast.FunctionDef) and n.name in {'asset_schema','_asset_rows','export','_export'}}
            assert selected(z.read(SERVICE+'/'+path))==selected((ROOT/path).read_bytes())
    with zipfile.ZipFile(HERE/PACKAGE) as z:
        files=json.loads(z.read('PACKAGE_FILES.json'))
        assert set(z.namelist())==set(files)|{'PACKAGE_FILES.json'}
        assert all(sha(z.read(n))==h for n,h in files.items())
        assert z.read('COMPUTE_CODE_SHA256.txt').decode().strip()==build['code_sha256']
    embedded=(HERE/'install_compute.py').read_text().split("if __name__ == '__main__':")[0]
    install=(HERE/'GENOS_R8_INSTALL.txt').read_text()
    for tag in ('PY_INSTALL','PY_STAGE'):
        cell=install.split("<<'"+tag+"'\n")[1].split('\n'+tag)[0]
        assert cell.startswith(embedded);ast.parse(cell)
    for name in ('GENOS_R8_INSTALL.txt','ROLLBACK_GENOS.txt'):
        subprocess.run(['bash','-n',str(HERE/name)],check=True)
    for name in ('DATAIKU_R8_INSTALL.txt','DATAIKU_R8_CONTROL.txt'):
        text=(HERE/name).read_text();ast.parse(text)
        assert build['files'][PACKAGE]['sha256'] in text
    checkouts=[]
    for dev in sorted((ROOT/'09_ARTIFACTS/TEMP/export-r8-lifecycle-final2').glob('test_genos_install_same_checko*/DEV')):
        if 'current' in str(dev):continue
        raw=subprocess.check_output(['git','show','HEAD:CODE_PINS.json'],cwd=dev)
        assert sha(raw)==build['code_sha256']
        checkouts.append({'path':str(dev),'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=dev,text=True).strip(),
                          'committed_pins_sha256':sha(raw),'installed_checked_then_rolled_back':True})
    assert len(checkouts)==6
    real=json.loads((HERE/'REAL_GLOSSARY_PROJECTION.json').read_text());assert real['status']=='PASS' and real['byte_mismatches']==0
    binding={'baseline':'sealed R7','code_zip':build['files'][SERVICE+'.zip'],'code_pins_sha256':build['code_sha256'],
             'local_installer_checkouts':checkouts,'critical_files':{n:pins[n] for n in build['changed_files'] if n in pins},
             'field_checkout':'~/DEV legal_pipeline_serving (actual absolute path unconfirmed)',
             'field_commit':None,'field_revision':None,'field_generation':None,
             'generation_policy':'Ephemeral compute generation; original/results/checkpoints owned by Dataiku',
             'root_repository_commit_push':False,'rag_main_changed':False,'onsite_executed':False}
    save('RELEASE_BINDING.json',binding)
    validation={'status':'LOCAL_DELIVERY_PASS_WITH_EXISTING_HISTORICAL_COMPATIBILITY_TEST_FAILURE',
        'suites':results,'delivery_tests_passed':95,'working_query_tests_passed':results['QUERY_TEST.xml']['passed'],
        'historical_compatibility_failure':'Same named test fails with pre-change HEAD publisher/package too (navigation compiler fingerprints). R8 additionally declares the intentional base64 response schema; historical package remains unchanged.',
        'real_glossary':real,'code_sha256':build['code_sha256'],'server_files':build['service_files'],
        'changed_server_files':build['changed_files'],'unchanged_server_files':build['unchanged_baseline_files'],
        'actual_model_calls':0,'speedup_percentage':None,'onsite_total_latency_measured':False,
        'current_failed_generation_recovered':False,'resume_failed_added_offset':False,
        'preserved_failures':['INITIAL_TEST.log/xml: 76 passed, 4 missing SDK failures','INTERRUPTED_TEST.log: user interrupted before completion','QUERY_TEST.log/xml and BASELINE_COMPAT_TEST.log/xml'],
        'onsite_oracle':'NOT_RUN','onsite_genos':'NOT_DEPLOYED','email_sent':False,'main_changed':False}
    save('VALIDATION.json',validation)
    names=[SERVICE+'.zip',PACKAGE,'CODE_MANIFEST.json','RELEASE_BINDING.json','VALIDATION.json',
           'GENOS_R8_INSTALL.txt','DATAIKU_R8_INSTALL.txt','DATAIKU_R8_CONTROL.txt','ROLLBACK_GENOS.txt',
           'install_compute.py','GUIDE.txt','PATCH_NOTES.txt']
    outer=HERE/'DATAIKU_EXPORT_FIX_20261028_R8.zip'
    writezip(outer,{n:(HERE/n).read_bytes() for n in names})
    with zipfile.ZipFile(outer) as z:
        assert z.testzip() is None and set(z.namelist())==set(names)
        for n in names:assert z.read(n)==(HERE/n).read_bytes()
    save('DELIVERY_MANIFEST.json',{**build,'delivery_files':{n:{'bytes':(HERE/n).stat().st_size,'sha256':sha((HERE/n).read_bytes())} for n in names+[outer.name]},
        'field_revision':'NOT_DEPLOYED','email_sent':False})
    print(json.dumps({'status':validation['status'],'delivery_tests':95,'working_query_passed':validation['working_query_tests_passed'],'archive':str(outer),'bytes':outer.stat().st_size}))

if __name__=='__main__':main()
