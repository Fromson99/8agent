"""Package the exact tested R3 bytes with reversible installers."""
import ast
import io
import json
from pathlib import Path
import subprocess
import zipfile
from build import HERE, BASE, SERVICE, PACKAGE, OLD_CODE, sha, writezip


def main():
    manifest = json.loads((HERE / 'BUILD.json').read_text())
    name = SERVICE + '.zip'
    archive_sha = manifest['files'][name]['sha256']
    code_sha = manifest['code_sha256']
    oldinstaller = (BASE / 'install_compute.py').read_text()
    installer = oldinstaller.replace('GENOS_DATAIKU_COMPUTE_20261027_R2.zip', name).replace(
        '02a93e5caceb2f18428e608620dbfafc0923832edee6a00cb314a64dd96690af', archive_sha).replace(
        OLD_CODE, code_sha).replace('.dataiku-preprocessor-install-r2', '.dataiku-preprocessor-install-r3')
    installer=installer.replace("'868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa', CODE_SHA", "'868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa', '"+OLD_CODE+"', CODE_SHA")
    installer=installer.replace("        if (root/'parser_config.py').exists():\n            raise ValueError('NEW_FILE_COLLISION: parser_config.py')\n", '')
    installer=installer.replace("        for before_name,before_hash in before_pins['files'].items():", "        for new_name in ('parser_config.py','review_audit.py'):\n            if new_name not in before_pins['files'] and (root/new_name).exists():\n                raise ValueError('NEW_FILE_COLLISION: '+new_name)\n        for before_name,before_hash in before_pins['files'].items():")
    installer=installer.replace('PIPELINE_R2_CHECKOUT_REQUIRED','PIPELINE_R3_CHECKOUT_REQUIRED').replace('sealed pipeline R2','sealed pipeline R3')
    (HERE / 'install_compute.py').write_text(installer)
    oldembedded = oldinstaller[:oldinstaller.index("if __name__ == '__main__':")]
    embedded = installer[:installer.index("if __name__ == '__main__':")]
    script = (BASE / 'GENOS_PREPROCESSOR_INSTALL_20261027_R2.txt').read_text().replace(oldembedded, embedded)
    script = script.replace('GENOS_DATAIKU_COMPUTE_20261027_R2.zip', name).replace(
        '02a93e5caceb2f18428e608620dbfafc0923832edee6a00cb314a64dd96690af', archive_sha)
    script=script.replace('Restore GENOS PDF preprocessor and validate its environment','Reuse preprocessor 187 chunk response and existing GENOS review')
    script=script.replace('R2 Dataiku','R3 Dataiku')
    (HERE / 'GENOS_PREPROCESSOR_INSTALL_20261027_R3.txt').write_text(script)
    rollback = '# legal_pipeline_serving의 ~/DEV. Dataiku 02가 중지된 상태에서 실행.\nset -e\ncd "$HOME/DEV"\npython3 - <<\'PY_ROLLBACK\'\n' + embedded + "\nrun('rollback')\nPY_ROLLBACK\n# 복원 파일 검토/commit/push 및 이전 리비전 선택. Dataiku 설치 TXT의 ACTION='rollback'도 사용.\n# R3로 시작한 시도의 이력/상태는 되돌리거나 삭제하지 않습니다.\n"
    (HERE / 'ROLLBACK_GENOS.txt').write_text(rollback)
    for p in (HERE / 'GENOS_PREPROCESSOR_INSTALL_20261027_R3.txt', HERE / 'ROLLBACK_GENOS.txt'):
        subprocess.run(['bash', '-n', str(p)], check=True)
    ast.parse(installer, feature_version=(3, 9))
    # During first packaging validation has not run yet. Mark it explicitly.
    validation = HERE / 'VALIDATION.json'
    if not validation.exists(): validation.write_text('{"status":"PENDING"}\n')
    files = [name, PACKAGE, 'GENOS_PREPROCESSOR_INSTALL_20261027_R3.txt',
             'DATAIKU_PREPROCESSOR_INSTALL_20261027_R3.txt', 'DATAIKU_PREPROCESSOR_CONTROL_20261027_R3.txt',
             'GENOS_ENVIRONMENT.txt', 'GUIDE.txt', 'WORK_CONTRACT.txt', 'ROLLBACK_GENOS.txt',
             'install_compute.py', 'VALIDATION.json']
    archive = HERE / 'DATAIKU_GENOS_PREPROCESSOR_20261027_R3.zip'
    writezip(archive, {n: (HERE / n).read_bytes() for n in files})
    def inspect(raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            for n in z.namelist():
                assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
                if n.endswith('.zip'): inspect(z.read(n))
    inspect(archive.read_bytes())
    manifest['files'].update({n: {'sha256': sha((HERE / n).read_bytes()), 'bytes': (HERE / n).stat().st_size}
                              for n in files + [archive.name]})
    manifest['field_revision'] = 'NOT_DEPLOYED'
    manifest['field_environment'] = 'USER_WILL_CONFIGURE'
    manifest['generation'] = 'PER_JOB_TEMPORARY; no RAG generation selected'
    (HERE / 'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('DELIVERY_READY', archive.name, archive.stat().st_size)


if __name__ == '__main__': main()
