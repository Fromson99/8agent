"""Package the exact tested R2 bytes with reversible installers."""
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
    installer = oldinstaller.replace('GENOS_DATAIKU_COMPUTE_20261027_R1.zip', name).replace(
        '516d594e54a619ab572febe89dec8d46a954fa3e4c6d39dc441ae7d2cfbd97db', archive_sha).replace(
        OLD_CODE, code_sha).replace(
        '771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46', OLD_CODE).replace(
        '.dataiku-compute-install-r1', '.dataiku-preprocessor-install-r2')
    installer = installer.replace("        before_pins=json.loads((root/'CODE_PINS.json').read_text())", "        if (root/'parser_config.py').exists():\n            raise ValueError('NEW_FILE_COLLISION: parser_config.py')\n        before_pins=json.loads((root/'CODE_PINS.json').read_text())")
    (HERE / 'install_compute.py').write_text(installer)
    oldembedded = oldinstaller[:oldinstaller.index("if __name__ == '__main__':")]
    embedded = installer[:installer.index("if __name__ == '__main__':")]
    script = (BASE / 'GENOS_COMPUTE_INSTALL_20261027_R1.txt').read_text().replace(oldembedded, embedded)
    script = script.replace('GENOS_DATAIKU_COMPUTE_20261027_R1.zip', name).replace(
        '516d594e54a619ab572febe89dec8d46a954fa3e4c6d39dc441ae7d2cfbd97db', archive_sha)
    script = script.replace('git commit -m "Move pipeline lifecycle to Dataiku; cancellable ephemeral compute"',
        'if ! git diff --cached --quiet; then\n  git commit -m "Restore GENOS PDF preprocessor and validate its environment"\nfi')
    script = script.replace('# 성공 뒤 02 → 03. 기존 01 원문이 완료되어 있으면 재실행하지 않습니다.',
        '# GENOS_ENVIRONMENT.txt의 전처리기 환경변수를 실제 코드서빙에 넣습니다.\n# R2 Dataiku 설치 TXT 실행 후 00 → 02 → 03. 원래 job 이름/기한/예산 유지.\n# 00은 로컬 설정 검사이며 전처리기 HTTP/공유 마운트의 원격 측 검증은 아닙니다.')
    (HERE / 'GENOS_PREPROCESSOR_INSTALL_20261027_R2.txt').write_text(script)
    rollback = '# legal_pipeline_serving의 ~/DEV. Dataiku 02가 중지된 상태에서 실행.\nset -e\ncd "$HOME/DEV"\npython3 - <<\'PY_ROLLBACK\'\n' + embedded + "\nrun('rollback')\nPY_ROLLBACK\n# 복원 파일 검토/commit/push 및 이전 리비전 선택. Dataiku 설치 TXT의 ACTION='rollback'도 사용.\n# R2로 시작한 시도의 이력/상태는 되돌리거나 삭제하지 않습니다.\n"
    (HERE / 'ROLLBACK_GENOS.txt').write_text(rollback)
    for p in (HERE / 'GENOS_PREPROCESSOR_INSTALL_20261027_R2.txt', HERE / 'ROLLBACK_GENOS.txt'):
        subprocess.run(['bash', '-n', str(p)], check=True)
    ast.parse(installer, feature_version=(3, 9))
    # During first packaging validation has not run yet. Mark it explicitly.
    validation = HERE / 'VALIDATION.json'
    if not validation.exists(): validation.write_text('{"status":"PENDING"}\n')
    files = [name, PACKAGE, 'GENOS_PREPROCESSOR_INSTALL_20261027_R2.txt',
             'DATAIKU_PREPROCESSOR_INSTALL_20261027_R2.txt', 'DATAIKU_PREPROCESSOR_CONTROL_20261027_R2.txt',
             'GENOS_ENVIRONMENT.txt', 'GUIDE.txt', 'WORK_CONTRACT.txt', 'ROLLBACK_GENOS.txt',
             'install_compute.py', 'VALIDATION.json']
    archive = HERE / 'DATAIKU_GENOS_PREPROCESSOR_20261027_R2.zip'
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
