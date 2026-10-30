import ast,hashlib,io,json,re,subprocess,xml.etree.ElementTree as ET,zipfile
from pathlib import Path
from build import HERE,SERVICE,PACKAGE

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    build=json.loads((HERE/'BUILD.json').read_text());suite=ET.parse(HERE/'TEST.xml').getroot().find('testsuite')
    assert suite is not None and int(suite.attrib['tests'])==46 and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    for n,v in build['files'].items():
        b=(HERE/n).read_bytes();assert len(b)==v['bytes'] and sha(b)==v['sha256']
    with zipfile.ZipFile(HERE/(SERVICE+'.zip')) as z:
        pins=json.loads(z.read(SERVICE+'/CODE_PINS.json'))['files']
        assert sha(z.read(SERVICE+'/CODE_PINS.json'))==build['code_sha256']
        assert set(z.namelist())=={SERVICE+'/'+n for n in pins}|{SERVICE+'/CODE_PINS.json'}
        assert all(sha(z.read(SERVICE+'/'+n))==h for n,h in pins.items())
    with zipfile.ZipFile(HERE/PACKAGE) as z:
        pins=json.loads(z.read('PACKAGE_FILES.json'))
        assert set(z.namelist())==set(pins)|{'PACKAGE_FILES.json'}
        assert all(sha(z.read(n))==h for n,h in pins.items())
        assert z.read('COMPUTE_CODE_SHA256.txt').decode().strip()==build['code_sha256']
    installer=(HERE/'install_compute.py').read_text();embedded=installer[:installer.index("if __name__ == '__main__':")]
    script=(HERE/'GENOS_R5_INSTALL.txt').read_text()
    for tag in ('PY_INSTALL','PY_STAGE'):
        cell=script.split("<<'"+tag+"'\n")[1].split('\n'+tag)[0]
        assert cell.startswith(embedded);ast.parse(cell)
    for name in ('GENOS_R5_INSTALL.txt','ROLLBACK_GENOS.txt'):subprocess.run(['bash','-n',str(HERE/name)],check=True)
    for name in ('DATAIKU_FOUR_FORMAT_TEST.txt','DATAIKU_R5_INSTALL.txt','DATAIKU_R5_CONTROL.txt'):
        source=(HERE/name).read_text();ast.parse(source)
        assert build['files'][PACKAGE]['sha256'] in source
    validation={'status':'LOCAL_MOCK_PASS','tests':46,'failures':0,'errors':0,'actual_model_calls':0,
      'tests_from_final_compute_and_client_archives':True,'code_sha256':build['code_sha256'],'archive_hashes':build['files'],
      'covered':['actual RAW sampling one per extension','receipt/snapshot/source binding','inner ZIP selection and missing formats','same Pod configuration discovery/ambiguity/missing/change','four-document real worker branch with mocked converter/parser','conversion vs parsing failure and remaining documents','missing/extra inputs','actual service purpose isolation and auth','Dataiku upload/read/hash/publication','uncertain RUN reply resumes same handle','completed results avoid repeated compute','partial cancellation has four terminal rows','original source mismatch not published','full pipeline transport/cancel/deadline supervision','R4 migration preserves review proof/deadline/budgets','R1/R3/R4 installer commit/hash/rollback','Dataiku SDK update/rollback','delivered notebook package/bootstrap and stale kernel rejection'],
      'mock_boundaries':['upstream GENOS parser facade','OS soffice converter','Dataiku SDK/storage','HTTP transport routed to local service handler; no field network'],
      'preserved_initial_failure':'TEST_INITIAL_TMP_CAPACITY_FAILURE.log (29 passed, 4 failures, 5 setup errors caused by /tmp tmpfs full; moved test scratch to filesystem, no integrity checks bypassed)',
      'field_documents':'NOT_TESTED','field_model_connectivity':'NOT_TESTED','field_revision':'NOT_DEPLOYED','local_main_changed':False,'root_git_commit_push':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':validation['status'],'tests':46,'code_sha256':build['code_sha256']}))
if __name__=='__main__':main()
