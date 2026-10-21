"""Prepare exact verified attachments for an explicitly requested Samsung handoff."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
NAME = 'GENOS_LENGTH_RECOVERY_20261015_R2'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
sealed = json.loads((OUT / 'SEALED_UNPACK_CHECK.json').read_bytes())
validation = json.loads((OUT / 'VALIDATION.json').read_bytes())
assert sha((OUT / (NAME + '.zip')).read_bytes()) == sealed['sha256']
assert sealed['standalone_txt_identical'] and sealed['no_javascript']
assert validation['installer_contracts'] == dict(tests=15, failures=0, errors=0, skipped=0)
assert validation['service_gate_integrations'] == dict(tests=2, failures=0, errors=0, skipped=0)
with zipfile.ZipFile(OUT / (NAME + '.zip')) as archive:
    assert archive.testzip() is None
    assert archive.read(NAME + '_RUN.txt') == (OUT / (NAME + '_RUN.txt')).read_bytes()
    assert all(Path(n).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs') for n in archive.namelist())
    manifest = json.loads(archive.read('CODE_MANIFEST.json'))
    for row in manifest['files']:
        raw = archive.read(row['path'])
        assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
subprocess.run(['bash', '-n', str(OUT / (NAME + '_RUN.txt'))], check=True)
subprocess.run(['sha256sum', '-c', 'SHA256SUMS.txt'], cwd=OUT, check=True, capture_output=True)
body = (OUT / 'EMAIL_BODY_UTF8.html').read_text()
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
metadata = []
for name in (NAME + '.zip', NAME + '_RUN.txt', 'GUIDE_UTF8.txt', 'FIX_REPORT_UTF8.txt',
             'VALIDATION_SUMMARY.txt', 'VALIDATION.json', 'SHA256SUMS.txt'):
    raw = (OUT / name).read_bytes()
    mime = 'application/zip' if name.endswith('.zip') else 'application/json' if name.endswith('.json') else 'text/plain'
    parts.append({'mime_type': mime, 'content_disposition': 'attachment', 'filename': name,
                  'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
    metadata.append({'name': name, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
args = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[GENOS 설치 오류 수정·누적 R2] 기존 스키마 충돌 해결 — R1 대신 이 ZIP 사용',
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
        'response_fields': ['id', 'thread_id', 'label_ids']}
text = json.dumps(args, ensure_ascii=True)
(OUT / 'EMAIL_ARGS.json').write_text(text)
(OUT / 'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'args_characters': len(text), 'args_sha256': sha(text.encode()),
                  'to': args['to'], 'subject': args['subject'], 'attachments': metadata}, ensure_ascii=False))
