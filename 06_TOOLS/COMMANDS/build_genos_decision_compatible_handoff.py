"""Package only the verified R2 decision-repair portion of the compatibility work."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-selective-compatible-r1'
OUT = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r2'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    if (OUT / 'EMAIL_SENT.json').exists():
        raise ValueError('R2 has been sent; preserve it and create a new revision for later changes')
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SOURCE / 'bundle/SELECTIVE_MANIFEST.json').read_bytes())
    manifest['features'] = {'decision-repair': manifest['features']['decision-repair']}
    manifest['handoff_revision'] = 'MODEL_DECISION_REPAIR_R2_PHOTO_COMPATIBLE'
    files = set(manifest['features']['decision-repair']['assets']) | {'apply.py', 'decision_transform.py'}
    bundle = OUT / 'bundle'
    bundle.mkdir(exist_ok=True)
    rows = []
    for name in sorted(files):
        raw = (SOURCE / 'bundle' / name).read_bytes()
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        rows.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    (bundle / 'SELECTIVE_MANIFEST.json').write_bytes(raw)
    rows.append({'path': 'SELECTIVE_MANIFEST.json', 'bytes': len(raw), 'sha256': sha(raw)})
    archive = OUT / 'GENOS_MODEL_DECISION_REPAIR_20260929_R2.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for row in rows:
            assert Path(row['path']).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs')
            zipped.write(bundle / row['path'], row['path'])
        zipped.writestr('CODE_MANIFEST.json', json.dumps({
            'format': '8agent-code/1', 'patch': 'model-decision-repair-20260929-r2', 'files': rows},
            ensure_ascii=False, indent=2) + '\n')
    old_sha = sha((SOURCE / 'GENOS_SELECTIVE_20260929_R1.zip').read_bytes())
    txt = (SOURCE / 'GENOS_SELECTIVE_20260929_R1_APPLY.txt').read_text()
    txt = txt.replace('GENOS_SELECTIVE_20260929_R1.zip', archive.name).replace(old_sha, sha(archive.read_bytes()))
    txt = txt.replace('START GENOS selective-compatible R1', 'START MODEL_DECISION_REPAIR R2 PHOTO_COMPATIBLE')
    txt = txt.replace('set -Eeuo pipefail\n', '''set -Eeuo pipefail
# R1 대신 이 R2 ZIP/TXT를 같은 폴더에 저장하고 실행합니다.
# 사진의 코드 판 또는 통합판에서 판단 오류 수정만 적용합니다.
# 적용: bash GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt
# 사전 확인: MODE=check bash GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt
# 복구: MODE=rollback ROLLBACK_FROM=/BACKUP_READY/경로 bash GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt
# 배포 전: 변경 코드를 commit하고 GENOS_GENERATION=/실제/세대 MODE=verify bash 이파일.txt
SELECT=decision-repair
''')
    path = OUT / 'GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt'
    path.write_text(txt)
    subprocess.run(['bash', '-n', str(path)], check=True)
    delivery = {'patch': 'model-decision-repair-20260929-r2', 'photo_sha256': manifest['photo_sha256'],
                'zip': archive.name, 'zip_sha256': sha(archive.read_bytes()),
                'txt': path.name, 'txt_sha256': sha(path.read_bytes()), 'features': ['decision-repair'],
                'generation_modified': False, 'workflow_modified': False, 'email_sent': False, 'genos_deployed': False}
    (OUT / 'DELIVERY.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(delivery, ensure_ascii=False))


if __name__ == '__main__':
    main()
