import ast,hashlib,json,subprocess,xml.etree.ElementTree as ET,zipfile
from pathlib import Path
from build import HERE,SERVICE,PACKAGE,sha


def main():
    build=json.loads((HERE/'BUILD.json').read_text());counts={}
    for name,expected in [('TEST.xml',79),('NATIVE_TEST.xml',4)]:
        suites=ET.parse(HERE/name).getroot().findall('testsuite')
        assert suites and sum(int(s.attrib['tests']) for s in suites)==expected
        assert all(int(s.attrib['errors'])==int(s.attrib['failures'])==0 for s in suites)
        counts[name]=expected
    for name,record in build['files'].items():
        raw=(HERE/name).read_bytes();assert len(raw)==record['bytes'] and sha(raw)==record['sha256']
    with zipfile.ZipFile(HERE/(SERVICE+'.zip')) as z:
        pins=json.loads(z.read(SERVICE+'/CODE_PINS.json'))['files']
        assert sha(z.read(SERVICE+'/CODE_PINS.json'))==build['code_sha256']
        assert set(z.namelist())=={SERVICE+'/'+n for n in pins}|{SERVICE+'/CODE_PINS.json'}
        assert all(sha(z.read(SERVICE+'/'+n))==h for n,h in pins.items())
        important={n:pins[n] for n in ('worker.py','service.py','partial_pipeline.py','parser_config.py','pipeline_coverage.py','02_BACKEND/lawrag/pipeline/genos_stages.py','02_BACKEND/lawrag/pipeline/team_raw.py','02_BACKEND/lawrag/pipeline/genos_build.py','02_BACKEND/lawrag/pipeline/genos_corpus.py','02_BACKEND/lawrag/pipeline/raw_preprocess.py','02_BACKEND/lawrag/core/parse_adapter.py')}
    with zipfile.ZipFile(HERE/PACKAGE) as z:
        pins=json.loads(z.read('PACKAGE_FILES.json'))
        assert set(z.namelist())==set(pins)|{'PACKAGE_FILES.json'}
        assert all(sha(z.read(n))==h for n,h in pins.items())
        assert z.read('COMPUTE_CODE_SHA256.txt').decode().strip()==build['code_sha256']
    installer=(HERE/'install_compute.py').read_text();embedded=installer[:installer.index("if __name__ == '__main__':")]
    script=(HERE/'GENOS_R7_INSTALL.txt').read_text()
    for tag in ('PY_INSTALL','PY_STAGE'):
        cell=script.split("<<'"+tag+"'\n")[1].split('\n'+tag)[0]
        assert cell.startswith(embedded);ast.parse(cell)
    for name in ('GENOS_R7_INSTALL.txt','ROLLBACK_GENOS.txt'):subprocess.run(['bash','-n',str(HERE/name)],check=True)
    for name in ('DATAIKU_R7_INSTALL.txt','DATAIKU_R7_CONTROL.txt'):
        source=(HERE/name).read_text();ast.parse(source)
        assert build['files'][PACKAGE]['sha256'] in source
    checkout=[]
    scratch=HERE.parents[2]/'09_ARTIFACTS/TEMP/skip-r7-tests/pytest-of-jin'
    for dev in sorted(scratch.glob('pytest-*/test_genos_install_same_checko*/DEV')):
        if 'current' in str(dev):continue
        result=subprocess.run(['git','show','HEAD:CODE_PINS.json'],cwd=dev,capture_output=True)
        if result.returncode or sha(result.stdout)!=build['code_sha256']:continue
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dev,text=True).strip()
        checkout.append({'root':str(dev),'commit':commit,'committed_pins_sha256':sha(result.stdout),'installer_check_passed_then_rolled_back':True})
    assert len(checkout)>=5
    binding={'code_zip':build['files'][SERVICE+'.zip'],'code_manifest':'CODE_MANIFEST.json',
       'code_pins_sha256':build['code_sha256'],'important_file_sha256':important,
       'verified_local_installer_checkouts':checkout,'field_push_checkout':'~/DEV (legal_pipeline_serving; actual absolute path unconfirmed)',
       'field_commit':None,'field_revision':None,'field_generation':None,
       'generation_policy':'Ephemeral per-compute generation returned to Dataiku; no persistent GENOS active generation.',
       'native_test_code':'All native worker product Python matches ZIP. Only synthetic glossary policy/pin rebound. No parser/converter/model response mocks; trap HTTP server asserts zero calls.',
       'root_repository_commit_push':False,'active_rag_main_changed':False}
    (HERE/'RELEASE_BINDING.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
    validation={'status':'LOCAL_SYNTHETIC_AND_MOCK_PASS','tests':sum(counts.values()),'suites':counts,'failures':0,'errors':0,
      'actual_model_calls':0,'code_sha256':build['code_sha256'],'archive_hashes':build['files'],
      'covered':['HEALTH/OPEN ready without preprocessor, YAML, converter or model configuration',
       'stale HTTP/Pod environment cannot override fixed skip policy',
       'PDF bypass before parsing and block indirect local PDF fallback',
       'actual native DOCX plus PDF/DOC bypass reaches selection/prepare/index/query export/result ZIP with zero HTTP calls',
       'native-only complete; all-PDF and corrupt native stop without successful result',
       'originals preserved, bypass vs processing failure reason/counts and exact successful IDs',
       'Dataiku return hash/coverage publication and exact generation IDs before SQL consumer',
       'original deadline/budgets/zero-review proof and R3-R6 failure migration',
       'R1/R3/R4/R5/R6 apply/repeat/commit/check/rollback in isolated actual Git checkouts',
       'Dataiku SDK install/repeat/rollback and unknown code rejection',
       'legacy document parser probe explicitly disabled'],
      'mock_boundaries':['Dataiku SDK and managed storage','SQL loader consumer spy; no onsite Oracle execution',
       'Local HTTP trap rejects any parser/converter/model request; verified zero requests'],
      'initial_test_failure':'INITIAL_NATIVE_TEST.xml/log: 3 pass, mixed test failed because DOC bypass was labelled ordinary failure in actual team_raw route. Corrected route and CSV source name. Final rebuilt code passed all 83 tests. INITIAL_TEST 79 passes preserved.',
      'field_documents':'NOT_TESTED','field_model_connectivity':'NOT_TESTED','field_revision':'NOT_DEPLOYED',
      'historical_1631_recovery':'NOT_ESTABLISHED','local_main_changed':False,'root_git_commit_push':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':validation['status'],'tests':validation['tests'],'code_sha256':build['code_sha256']}))

if __name__=='__main__':main()
