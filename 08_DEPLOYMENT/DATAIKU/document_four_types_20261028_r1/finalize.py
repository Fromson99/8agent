import ast,io,json,subprocess,zipfile
from pathlib import Path
from build import HERE,BASE,SERVICE,PACKAGE,OLD_CODE,sha,writezip

def main():
    build=json.loads((HERE/'BUILD.json').read_text());code=build['code_sha256'];archive=SERVICE+'.zip'
    oldmanifest=json.loads((BASE/'BUILD.json').read_text());oldarchive='GENOS_DATAIKU_COMPUTE_20261028_R4.zip'
    digest=build['files'][archive]['sha256'];oldhash=oldmanifest['files'][oldarchive]['sha256']
    old=(BASE/'install_compute.py').read_text()
    installer=old.replace(oldarchive,archive).replace(oldhash,digest).replace(OLD_CODE,code).replace('install-r4','install-r5').replace('PIPELINE_R4_CHECKOUT_REQUIRED','PIPELINE_R5_CHECKOUT_REQUIRED').replace('sealed pipeline R3','sealed pipeline R5')
    installer=installer.replace("'8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1', CODE_SHA", "'8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1', '"+OLD_CODE+"', CODE_SHA")
    (HERE/'install_compute.py').write_text(installer)
    embedded=installer[:installer.index("if __name__ == '__main__':")];oldembed=old[:old.index("if __name__ == '__main__':")]
    script=(BASE/'GENOS_POD_INSTALL_20261028_R4.txt').read_text().replace(oldembed,embedded).replace(oldarchive,archive).replace(oldhash,digest)
    script=script.replace('Run GENOS conversion and parsing in the compute Pod','Add bounded Dataiku four-format document probe')
    script=script.split('# 배포 뒤 Dataiku 00의')[0]+'''# 배포 뒤 LEGAL_RAG/ehA8dpVm에 R5 client ZIP을 올립니다.
# 새 Python 노트북에서 DATAIKU_FOUR_FORMAT_TEST.txt 전체를 실행합니다.
# 이번 테스트에는 전체 02/03 실행이나 새 YAML 작성이 필요 없습니다.
# 기존 Flow를 이후에 쓸 때는 DATAIKU_R5_INSTALL.txt로 코드 해시를 함께 맞춥니다.
'''
    (HERE/'GENOS_R5_INSTALL.txt').write_text(script)
    (HERE/'ROLLBACK_GENOS.txt').write_text('''# 기존 legal_pipeline_serving ~/DEV에서 적용 전 파일을 복원합니다.
set -e
cd "$HOME/DEV"
python3 - <<'PY_ROLLBACK'
'''+embedded+"\nrun('rollback')\nPY_ROLLBACK\n# 복원 파일을 검토/commit/push하고 이전 리비전을 선택합니다.\n# Flow updater를 적용했다면 DATAIKU_R5_CONTROL.txt의 ACTION='rollback'.\n# Dataiku의 테스트 결과/체크포인트는 보존합니다.\n")
    for n in ('GENOS_R5_INSTALL.txt','ROLLBACK_GENOS.txt'):subprocess.run(['bash','-n',str(HERE/n)],check=True)
    for n in ('DATAIKU_FOUR_FORMAT_TEST.txt','DATAIKU_R5_INSTALL.txt','DATAIKU_R5_CONTROL.txt'):ast.parse((HERE/n).read_text())
    with zipfile.ZipFile(HERE/archive) as z:pins=json.loads(z.read(SERVICE+'/CODE_PINS.json'))
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({'code_sha256':code,**pins},indent=2)+'\n')
    files=[archive,PACKAGE,'CODE_MANIFEST.json','GENOS_R5_INSTALL.txt','DATAIKU_FOUR_FORMAT_TEST.txt','DATAIKU_R5_INSTALL.txt','DATAIKU_R5_CONTROL.txt','ROLLBACK_GENOS.txt','install_compute.py','GUIDE.txt','PATCH_NOTES.txt','VALIDATION.json']
    if not all((HERE/n).exists() for n in files):return
    outer=HERE/'DATAIKU_FOUR_FORMAT_TEST_20261028_R1.zip';writezip(outer,{n:(HERE/n).read_bytes() for n in files})
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
