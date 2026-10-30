import ast,io,json,subprocess,zipfile
from pathlib import Path
from build import HERE,BASE,SERVICE,PACKAGE,OLD_CODE,sha,writezip

def main():
    build=json.loads((HERE/'BUILD.json').read_text());code=build['code_sha256'];archive=SERVICE+'.zip'
    oldmanifest=json.loads((BASE/'BUILD.json').read_text());oldarchive='GENOS_DATAIKU_COMPUTE_20261028_R5.zip'
    digest=build['files'][archive]['sha256'];oldhash=oldmanifest['files'][oldarchive]['sha256']
    old=(BASE/'install_compute.py').read_text()
    installer=old.replace(oldarchive,archive).replace(oldhash,digest).replace(OLD_CODE,code).replace('install-r5','install-r6').replace('PIPELINE_R5_CHECKOUT_REQUIRED','PIPELINE_R6_CHECKOUT_REQUIRED').replace('sealed pipeline R5','sealed pipeline R6')
    installer=installer.replace("'8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685', CODE_SHA", "'8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685', '"+OLD_CODE+"', CODE_SHA")
    (HERE/'install_compute.py').write_text(installer)
    embedded=installer[:installer.index("if __name__ == '__main__':")];oldembed=old[:old.index("if __name__ == '__main__':")]
    script=(BASE/'GENOS_R5_INSTALL.txt').read_text().replace(oldembed,embedded).replace(oldarchive,archive).replace(oldhash,digest)
    script=script.replace('Add bounded Dataiku four-format document probe','Continue verified successful documents with explicit omissions')
    script=script.split('# 배포 뒤 LEGAL_RAG/ehA8dpVm에')[0]+"""# GENOS 리비전 환경: LEGAL_PIPELINE_PARSER_MODE=existing-http (기존 전체 Flow의 HTTP 전처리기)
# 기존 GENOS_PREPROCESSOR_ID/URL, SHARED_ROOT/REMOTE_ROOT, GENOS_LLM_* 연결을 유지합니다.
# 같은 Pod 파서를 쓸 때만 LEGAL_PIPELINE_PARSER_MODE=same-pod, 실제 GENOS_STRUCTURE_CONFIG 설정이 필요합니다.
# 배포 뒤 LEGAL_RAG/ehA8dpVm에 DATAIKU_COMPUTE_RECIPES_20261028_R6.zip 업로드.
# Dataiku 새 커널에서 DATAIKU_R6_INSTALL.txt 실행 후 00 → 기존 02 → 기존 03 순서.
# 기존 작업명/기한/예산을 유지하며 GUIDE.txt의 이전 작업 이행 제한을 확인합니다.
"""
    (HERE/'GENOS_R6_INSTALL.txt').write_text(script)
    (HERE/'ROLLBACK_GENOS.txt').write_text('''# 기존 legal_pipeline_serving ~/DEV에서 적용 전 파일을 복원합니다.
set -e
cd "$HOME/DEV"
python3 - <<'PY_ROLLBACK'
'''+embedded+"\nrun('rollback')\nPY_ROLLBACK\n# 복원 파일을 검토/commit/push하고 이전 리비전을 선택합니다.\n# Flow updater를 적용했다면 DATAIKU_R6_INSTALL.txt의 ACTION='rollback'.\n# Dataiku의 테스트 결과/체크포인트는 보존합니다.\n")
    for n in ('GENOS_R6_INSTALL.txt','ROLLBACK_GENOS.txt'):subprocess.run(['bash','-n',str(HERE/n)],check=True)
    for n in ('DATAIKU_R6_INSTALL.txt','DATAIKU_R6_CONTROL.txt'):ast.parse((HERE/n).read_text())
    with zipfile.ZipFile(HERE/archive) as z:pins=json.loads(z.read(SERVICE+'/CODE_PINS.json'))
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({'code_sha256':code,**pins},indent=2)+'\n')
    files=[archive,PACKAGE,'CODE_MANIFEST.json','RELEASE_BINDING.json','GENOS_R6_INSTALL.txt','DATAIKU_R6_INSTALL.txt','DATAIKU_R6_CONTROL.txt','ROLLBACK_GENOS.txt','install_compute.py','GUIDE.txt','PATCH_NOTES.txt','VALIDATION.json']
    if not all((HERE/n).exists() for n in files):return
    outer=HERE/'DATAIKU_PARTIAL_PIPELINE_20261028_R6.zip';writezip(outer,{n:(HERE/n).read_bytes() for n in files})
    def check(raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            for n in z.namelist():
                assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
                if Path(n).suffix.lower() in {'.zip','.whl'}:check(z.read(n))
    check(outer.read_bytes())
    build.update(field_revision='NOT_DEPLOYED',field_documents='NOT_TESTED',actual_model_calls=0,local_main_changed=False,git_push=False,
        delivery_files={n:{'bytes':(HERE/n).stat().st_size,'sha256':sha((HERE/n).read_bytes())} for n in files+[outer.name]})
    (HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(build,indent=2)+'\n')
    print('PACKAGED',outer.name,outer.stat().st_size)
if __name__=='__main__':main()
