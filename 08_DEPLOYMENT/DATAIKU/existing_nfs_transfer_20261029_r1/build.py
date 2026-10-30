"""Build the existing-data handoff from sealed R10; no MAIN selection changes."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent/'pipeline_single_cpu_20261029_r10'
CLIENT_BASE = HERE.parent/'pipeline_attempt_recovery_20261029_r1'
OLD_SERVICE = 'GENOS_DATAIKU_COMPUTE_20261029_R10'
SERVICE = 'GENOS_EXISTING_NFS_20261029_R1'
PACKAGE = 'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip'
OLD_CODE = '55ab3cf767199ed70f29475e15403874b7ccacc1e306130f6467da04c5b3499d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def writezip(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            if Path(name).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('JAVASCRIPT_NOT_ALLOWED')
            item = zipfile.ZipInfo(name, (2026, 10, 29, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            z.writestr(item, raw)


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def build():
    assert not (HERE/'VALIDATION.json').exists(), 'Do not replace validated delivery'
    with zipfile.ZipFile(BASE/(OLD_SERVICE+'.zip')) as z:
        old = {name.split('/', 1)[1]: z.read(name) for name in z.namelist()}
    assert sha(old['CODE_PINS.json']) == OLD_CODE
    pins = json.loads(old['CODE_PINS.json'])
    assert all(sha(old[n]) == h for n, h in pins['files'].items())
    payload = dict(old)
    payload['service.py'] = replace(old['service.py'].decode(),
        "    op = data.get('API_TYPE')\n",
        "    op = data.get('API_TYPE')\n    if op in {'EXISTING_NFS_INFO', 'EXISTING_NFS_READ'}:\n        import nfs_source\n        return nfs_source.handle(data)\n").encode()
    for name in ('nfs_source.py', 'NFS_VERIFY.py'):
        payload[name] = (HERE/name).read_bytes()
    for name in ('oracle_existing_nfs.py', 'oracle_full_package.py'):
        rel = '02_BACKEND/lawrag/pipeline/'+name
        payload[rel] = (ROOT/rel).read_bytes()
    payload['CODE_PINS.json'] = (json.dumps({**pins, 'files': {n: sha(b) for n,b in payload.items()
                                                          if n != 'CODE_PINS.json'}}, sort_keys=True, indent=2)+'\n').encode()
    code = sha(payload['CODE_PINS.json'])
    writezip(HERE/(SERVICE+'.zip'), {SERVICE+'/'+n: b for n,b in payload.items()})
    with zipfile.ZipFile(CLIENT_BASE/'DATAIKU_R10_RECOVERY_CLIENT_20261029_R1.zip') as z:
        client = {n: z.read(n) for n in z.namelist()}
    client['COMPUTE_CODE_SHA256.txt'] = (code+'\n').encode()
    client['existing_client.py'] = (HERE/'existing_client.py').read_bytes()
    for name in ('oracle_existing_nfs.py', 'oracle_full_package.py'):
        rel = '02_BACKEND/lawrag/pipeline/'+name
        client['client/'+rel] = (ROOT/rel).read_bytes()
    client['PACKAGE_FILES.json'] = (json.dumps({n: sha(b) for n,b in client.items() if n != 'PACKAGE_FILES.json'}, sort_keys=True, indent=2)+'\n').encode()
    writezip(HERE/PACKAGE, client)
    boot = (CLIENT_BASE/'bootstrap.txt').read_text()
    boot = boot.replace('DATAIKU_R10_RECOVERY_CLIENT_20261029_R1.zip', PACKAGE)
    boot = boot.replace('34118187c25455bf1c476640529b12d873cc4c641148ac36387c19696f63862d', sha((HERE/PACKAGE).read_bytes()))
    boot = re.sub(r'PACKAGE_BYTES = \d+', 'PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size), boot)
    command = "# LEGAL_RAG 새 Python 노트북. 기존 00/01/02/03 레시피는 실행하지 않습니다.\nACTION = 'check' # check → transfer → load, 상태만 확인: status\n" + boot + '''
work, root = verified_package()
sys.path[:0] = [str(root), str(root/'client'), str(root/'client/02_BACKEND')]
import existing_client
NFS_RESULT = existing_client.run(ACTION)
'''
    (HERE/'DATAIKU_EXISTING_NFS_RUN.txt').write_text(command)
    ast.parse(command)
    original = (BASE/'install_compute.py').read_text()
    installer = original.replace(OLD_SERVICE, SERVICE).replace(sha((BASE/(OLD_SERVICE+'.zip')).read_bytes()), sha((HERE/(SERVICE+'.zip')).read_bytes())).replace(OLD_CODE, code)
    installer = installer.replace('.dataiku-preprocessor-install-r10', '.existing-nfs-install-20261029-r1')
    installer = replace(installer, ', CODE_SHA):', ", '"+OLD_CODE+"', CODE_SHA):")
    installer = replace(installer, "'--code-root', str(root), '--require-committed'], check=True)",
                        "'--code-root', str(root), '--require-committed'], check=True)\n                subprocess.run([sys.executable, str(root/'NFS_VERIFY.py')], check=True)")
    (HERE/'install_compute.py').write_text(installer)
    old_embed = original.split("if __name__ == '__main__':")[0]
    new_embed = installer.split("if __name__ == '__main__':")[0]
    for src, dst in [('GENOS_R10_INSTALL.txt','GENOS_EXISTING_NFS_INSTALL.txt'), ('ROLLBACK_GENOS.txt','ROLLBACK_GENOS.txt')]:
        text = (BASE/src).read_text().replace(old_embed, new_embed).replace(OLD_SERVICE, SERVICE)
        text = text.replace(sha((BASE/(OLD_SERVICE+'.zip')).read_bytes()), sha((HERE/(SERVICE+'.zip')).read_bytes()))
        text = text.replace('Match pipeline indexing to one CPU; preserve R9 export fixes', 'Add read-only existing NFS data transfer; preserve compute code')
        if src.startswith('GENOS_'):
            # Replace obsolete follow-up instructions rather than telling the user to rebuild.
            text = text[:text.index('# 여기까지는 Git 적용/전송입니다.')]
            text = replace(text, 'python3 VERIFY_PIPELINE_RELEASE.py --code-root "$HOME/DEV" --require-committed\ngit push',
                           'python3 VERIFY_PIPELINE_RELEASE.py --code-root "$HOME/DEV" --require-committed\npython3 NFS_VERIFY.py\ngit push')
            text += '''# 위 출력의 commit을 기존 legal_pipeline_serving 새 리비전으로 배포합니다.
# 기존 LEGAL_PIPELINE_URL/TOKEN을 유지합니다. 새 client ZIP을 ehA8dpVm에 업로드한 뒤
# Dataiku 새 Python 노트북에서 DATAIKU_EXISTING_NFS_RUN.txt를 check → transfer → load로 실행합니다.
# 기존 00/01/02/03은 이 NFS 이관에 실행하지 않습니다. 구조화/재색인 없음.
'''
        (HERE/dst).write_text(text)
    for name, raw in list(payload.items())+list(client.items()):
        if name.endswith('.py'): compile(raw, name, 'exec')
    manifest = {'server_code_sha256': code, 'baseline_code_sha256': OLD_CODE,
                'server_files': len(payload), 'changed_server_files': [n for n in payload if payload[n] != old.get(n)],
                'preserved_server_files': sum(payload[n] == b for n,b in old.items()),
                'generation': '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation',
                'field_manifest_sha256': 'verified by NFS_VERIFY at actual checkout; not transcribed from photo',
                'field_revision': None, 'main_changed': False,
                'files': {n: {'sha256': sha((HERE/n).read_bytes()), 'bytes': (HERE/n).stat().st_size} for n in
                          (SERVICE+'.zip', PACKAGE, 'GENOS_EXISTING_NFS_INSTALL.txt','DATAIKU_EXISTING_NFS_RUN.txt','ROLLBACK_GENOS.txt')}}
    (HERE/'BUILD.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    (HERE/'CODE_MANIFEST.json').write_bytes(payload['CODE_PINS.json'])
    print(json.dumps({k: v for k,v in manifest.items() if k != 'files'}, ensure_ascii=False))


if __name__ == '__main__':
    build()
