import ast,io,json,subprocess,zipfile
from pathlib import Path
from build import HERE,BASE,SERVICE,PACKAGE,OLD_CODE,sha,writezip

def main():
    build=json.loads((HERE/'BUILD.json').read_text());code=build['code_sha256'];archive=SERVICE+'.zip'
    oldmanifest=json.loads((BASE/'BUILD.json').read_text());oldarchive='GENOS_DATAIKU_COMPUTE_20261028_R6.zip'
    digest=build['files'][archive]['sha256'];oldhash=oldmanifest['files'][oldarchive]['sha256']
    old=(BASE/'install_compute.py').read_text()
    installer=old.replace(oldarchive,archive).replace(oldhash,digest).replace(OLD_CODE,code).replace('install-r6','install-r7').replace('PIPELINE_R6_CHECKOUT_REQUIRED','PIPELINE_R7_CHECKOUT_REQUIRED').replace('sealed pipeline R6','sealed pipeline R7')
    installer=installer.replace("'78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c', CODE_SHA", "'78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c', '"+OLD_CODE+"', CODE_SHA")
    (HERE/'install_compute.py').write_text(installer)
    embedded=installer[:installer.index("if __name__ == '__main__':")];oldembed=old[:old.index("if __name__ == '__main__':")]
    script=(BASE/'GENOS_R6_INSTALL.txt').read_text().replace(oldembed,embedded).replace(oldarchive,archive).replace(oldhash,digest)
    script=script.replace('Continue verified successful documents with explicit omissions','Skip PDF preprocessor and converter by user request')
    script=script.split('# GENOS 리비전 환경:')[0]+"""# R7은 전처리기를 사용하지 않습니다. 주소/공유 경로/YAML/검수 모델 설정이 필요 없습니다.
# 이전 LEGAL_PIPELINE_PARSER_MODE 등 파서 관련 값이 남아 있어도 전체 Flow의 skip 정책이 우선합니다.
# GENOS 새 R7 리비전 배포 후 LEGAL_RAG/ehA8dpVm에 동봉 R7 client ZIP 업로드.
# Dataiku 새 커널에서 DATAIKU_R7_INSTALL.txt 전체 실행 → 기존 00 → 02 → 03.
# 기존 작업명/기한/예산은 보존합니다. 이전 작업 이행 제한은 GUIDE.txt 참고.
"""
    (HERE/'GENOS_R7_INSTALL.txt').write_text(script)
    (HERE/'ROLLBACK_GENOS.txt').write_text('''# 기존 legal_pipeline_serving ~/DEV에서 적용 전 파일을 복원합니다.
set -e
cd "$HOME/DEV"
python3 - <<'PY_ROLLBACK'
'''+embedded+"\nrun('rollback')\nPY_ROLLBACK\n# 복원 파일을 검토/commit/push하고 이전 리비전을 선택합니다.\n# Flow updater를 적용했다면 DATAIKU_R7_INSTALL.txt의 ACTION='rollback'.\n# Dataiku의 테스트 결과/체크포인트는 보존합니다.\n")
    for n in ('GENOS_R7_INSTALL.txt','ROLLBACK_GENOS.txt'):subprocess.run(['bash','-n',str(HERE/n)],check=True)
    for n in ('DATAIKU_R7_INSTALL.txt','DATAIKU_R7_CONTROL.txt'):ast.parse((HERE/n).read_text())
    with zipfile.ZipFile(HERE/archive) as z:pins=json.loads(z.read(SERVICE+'/CODE_PINS.json'))
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({'code_sha256':code,**pins},indent=2)+'\n')
    files=[archive,PACKAGE,'CODE_MANIFEST.json','RELEASE_BINDING.json','GENOS_R7_INSTALL.txt','DATAIKU_R7_INSTALL.txt','DATAIKU_R7_CONTROL.txt','ROLLBACK_GENOS.txt','install_compute.py','GUIDE.txt','PATCH_NOTES.txt','VALIDATION.json']
    if not all((HERE/n).exists() for n in files):return
    outer=HERE/'DATAIKU_SKIP_PARSER_20261028_R7.zip';writezip(outer,{n:(HERE/n).read_bytes() for n in files})
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
