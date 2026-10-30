from pathlib import Path
import ast
import hashlib
import json
import shutil
import subprocess
import zipfile
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_pod_20261028_r4'
ARCHIVE='GENOS_DATAIKU_COMPUTE_20261028_R4.zip'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    template=(HERE/'runner_template.py').read_text()
    worker=template.replace('__RUNNER_SOURCE__',"''")
    code=template.replace('__RUNNER_SOURCE__',repr(worker))
    ast.parse(code,feature_version=(3,11))
    (HERE/'single_document.py').write_text(code)
    (HERE/'GENOS_ONE_DOCUMENT_TEST.txt').write_text('# 한 문서만 PDF 변환·파싱. 문서/설정 경로는 인자로 전달합니다.\nset -e\npython3 - "$@" <<\'PY_ONE_DOCUMENT\'\n'+code+'\nPY_ONE_DOCUMENT\n')
    subprocess.run(['bash','-n',str(HERE/'GENOS_ONE_DOCUMENT_TEST.txt')],check=True)
    source=BASE/ARCHIVE
    assert sha(source)=='3f7b61f916f9c6db07cc3519296276d89c120303611bcc2e7b874b34c935b8fc'
    shutil.copyfile(source,HERE/ARCHIVE)
    if not (HERE/'VALIDATION.json').exists():(HERE/'VALIDATION.json').write_text('{"status":"PENDING"}\n')
    members=['GENOS_ONE_DOCUMENT_TEST.txt','single_document.py',ARCHIVE,'GUIDE.txt','VALIDATION.json']
    manifest={'code_sha256':'8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685',
              'files':{n:{'bytes':(HERE/n).stat().st_size,'sha256':sha(HERE/n)} for n in members},
              'field_revision':'NOT_TESTED','generation':'none; one temporary document',
              'git_commit_push':False,'rag_main_changed':False}
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    members.append('CODE_MANIFEST.json')
    with zipfile.ZipFile(HERE/'GENOS_ONE_DOCUMENT_TEST_20261028_R1.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for n in members:z.write(HERE/n,n)
    import io
    def check(raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            for n in z.namelist():
                assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
                if n.endswith(('.zip','.whl')):check(z.read(n))
    check((HERE/'GENOS_ONE_DOCUMENT_TEST_20261028_R1.zip').read_bytes())
    print('PACKAGE_READY',sha(HERE/'GENOS_ONE_DOCUMENT_TEST_20261028_R1.zip'))

if __name__=='__main__':main()
