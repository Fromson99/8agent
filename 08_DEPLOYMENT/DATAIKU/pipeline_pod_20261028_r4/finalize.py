import ast
import io
import json
import re
from pathlib import Path
import subprocess
import zipfile
from build import HERE, BASE, SERVICE, PACKAGE, OLD_CODE, sha, writezip


def main():
    manifest=json.loads((HERE/'BUILD.json').read_text());code=manifest['code_sha256']
    archive=SERVICE+'.zip';digest=manifest['files'][archive]['sha256']
    old=(BASE/'install_compute.py').read_text()
    installer=old.replace('GENOS_DATAIKU_COMPUTE_20261027_R3.zip',archive).replace('633562ec8fa3e8a4955f4237245cccb956685fd3ab6058336887dbadafcb14dc',digest).replace(OLD_CODE,code).replace('install-r3','install-r4').replace('PIPELINE_R3_CHECKOUT_REQUIRED','PIPELINE_R4_CHECKOUT_REQUIRED')
    installer=installer.replace("'6903032227143a1b94fe0eec8a701592d819a2e08f061ce76453b42df687121c', CODE_SHA", "'6903032227143a1b94fe0eec8a701592d819a2e08f061ce76453b42df687121c', '"+OLD_CODE+"', CODE_SHA")
    point="        if action in ('stage', 'check'):"
    installer=installer.replace(point,"        if action == 'apply' and not (audit/'plan.json').exists():\n            before_files=json.loads((root/'CODE_PINS.json').read_text())['files']\n            for name in expected:\n                if name!='CODE_PINS.json' and name not in before_files and (root/name).exists():\n                    raise ValueError('NEW_FILE_COLLISION: '+name)\n"+point)
    (HERE/'install_compute.py').write_text(installer)
    embedded=installer[:installer.index("if __name__ == '__main__':")]
    oldembedded=old[:old.index("if __name__ == '__main__':")]
    script=(BASE/'GENOS_PREPROCESSOR_INSTALL_20261027_R3.txt').read_text().replace(oldembedded,embedded)
    script=script.replace('GENOS_DATAIKU_COMPUTE_20261027_R3.zip',archive).replace('633562ec8fa3e8a4955f4237245cccb956685fd3ab6058336887dbadafcb14dc',digest)
    script=script.replace('Reuse preprocessor 187 chunk response and existing GENOS review','Run GENOS conversion and parsing in the compute Pod').replace('R3 Dataiku','R4 Dataiku')
    script=script.replace('00은 로컬 설정 검사이며 전처리기 HTTP/공유 마운트의 원격 측 검증은 아닙니다.', '00은 Pod 런타임 사전 검사이며 실제 문서 변환/모델 접속 성공은 별도입니다.')
    # Preserve user review: installer stages only matching files and checks commit;
    # existing script's explicit git commit/push sequence remains user-run.
    (HERE/'GENOS_POD_INSTALL_20261028_R4.txt').write_text(script)
    rollback='# 기존 legal_pipeline_serving checkout. Dataiku 02 실행 중에는 적용하지 마세요.\nset -e\ncd "$HOME/DEV"\npython3 - <<\'PY\'\n'+embedded+"\nrun('rollback')\nPY\n# 복원 파일 검토/commit/push, 이전 리비전 선택 후 Dataiku ACTION='rollback'.\n# 작업 체크포인트와 실패 이력은 삭제하지 않습니다.\n"
    (HERE/'ROLLBACK_GENOS.txt').write_text(rollback)
    for p in HERE.glob('*.txt'):
        if p.name.startswith(('GENOS_POD_INSTALL','POD_RUNTIME','ROLLBACK')):
            subprocess.run(['bash','-n',str(p)],check=True)
    ast.parse(installer,feature_version=(3,9))
    if not (HERE/'VALIDATION.json').exists():(HERE/'VALIDATION.json').write_text('{"status":"PENDING"}\n')
    runtime_txt=HERE/'POD_RUNTIME_CHECK_20261028_R4.txt'
    runtime_txt.write_text(re.sub(r"expected_runtime_sha='[^']*'","expected_runtime_sha='"+manifest['files']['GENOS_POD_RUNTIME_20261028_R4.zip']['sha256']+"'",runtime_txt.read_text()))
    with zipfile.ZipFile(HERE/archive) as z:
        pins=json.loads(z.read(SERVICE+'/CODE_PINS.json'))['files']
    (HERE/'CODE_MANIFEST.json').write_text(json.dumps({'code_sha256':code,'service_archive_sha256':digest,'upstream_revision':manifest['upstream_revision'],'files':pins},indent=2)+'\n')
    files=['CODE_MANIFEST.json',archive,PACKAGE,'GENOS_POD_RUNTIME_20261028_R4.zip','GENOS_POD_INSTALL_20261028_R4.txt',
           'DATAIKU_POD_INSTALL_20261028_R4.txt','DATAIKU_POD_CONTROL_20261028_R4.txt',
           'POD_RUNTIME_CHECK_20261028_R4.txt','GENOS_ENVIRONMENT.txt','GUIDE.txt','PATCH_NOTES.txt',
           'WORK_CONTRACT.txt','ROLLBACK_GENOS.txt','install_compute.py','VALIDATION.json']
    outer=HERE/'DATAIKU_GENOS_POD_20261028_R4.zip'
    writezip(outer,{n:(HERE/n).read_bytes() for n in files})
    def check(raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            for n in z.namelist():
                assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
                if Path(n).suffix.lower() in {'.zip','.whl'}:check(z.read(n))
    check(outer.read_bytes())
    manifest['files'].update({n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in files+[outer.name]})
    manifest.update(field_revision='NOT_DEPLOYED',field_environment='NOT_VERIFIED',generation='PER_JOB_TEMPORARY; RAG MAIN unchanged',git_commit='NOT_PERFORMED',git_push=False)
    (HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PACKAGED',outer.name,outer.stat().st_size)

if __name__=='__main__':main()
