"""Materialize the exact already-tested R1 from email body on GENOS Linux."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PREVIOUS = OUT.parent / 'data_transfer_list_20261007_r1'
NAME = 'GENOS_TRANSFER_NFS_LIST_20261007_R2_CREATE_PLAIN'
EXPECTED = '24eff33bc244e73b97d4390ca70d785a5c7f2d13075abd21d174a9544f2f4922'


def main():
    runner = PREVIOUS / 'GENOS_TRANSFER_NFS_LIST_20261007_R1_RUN.txt'
    raw = runner.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED or b'\0' in raw:
        raise ValueError('Original tested R1 source differs')
    encoded = '\n'.join(textwrap.wrap(base64.b64encode(gzip.compress(raw, mtime=0)).decode(), 76))
    body = '''#!/usr/bin/env bash
# Paste this entire block from the email body into the GENOS terminal.
# Or, if saved as plain ASCII TXT, run: bash <this>.txt
set -euo pipefail
python3 - <<'GENOS_CREATE_VERIFIED_R1_PY'
import base64,gzip,hashlib,io,json,os,shlex,subprocess,tempfile
from pathlib import Path

expected='__SHA__'
payload=''' + "'''" + '\n' + encoded + '\n' + "'''" + '''
source=base64.b64decode(''.join(payload.split()),validate=True)
with gzip.GzipFile(fileobj=io.BytesIO(source)) as compressed:
    raw=compressed.read(91175)
if len(raw)!=91174 or hashlib.sha256(raw).hexdigest()!=expected or b'\\0' in raw:
    raise SystemExit('FAIL: pasted source differs; no runner created')
dev=Path(os.environ.get('GENOS_DEV_ROOT') or os.environ.get('GENOS_DEV') or str(Path.home()/'DEV')).expanduser().resolve(strict=True)
directory=(dev/'TRANSFER').resolve(strict=True)
old=directory/'GENOS_TRANSFER_NFS_LIST_20261007_R1_RUN.txt'
if old.is_file() and not old.is_symlink():
    with old.open('rb') as stream:
        sample=stream.read(256)
    print('OLD_RUN_HEADER_HEX='+sample[:16].hex())
    print('OLD_RUN_FIRST256_NULS='+str(sample.count(b'\\0')))
target=directory/'GENOS_TRANSFER_NFS_LIST_R1_PLAIN.txt'
if target.exists() or target.is_symlink():
    if target.is_symlink() or not target.is_file():
        raise SystemExit('FAIL: existing output is not a regular file; preserved')
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    if digest!=expected:raise SystemExit('FAIL: existing output differs; preserved')
    print('REUSED_VERIFIED_RUN='+str(target))
else:
    fd,name=tempfile.mkstemp(prefix='.verified-r1-',dir=directory)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        subprocess.run(['bash','-n',str(temporary)],check=True)
        # Atomic publication cannot overwrite a concurrent file.
        os.link(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    print('CREATED_VERIFIED_RUN='+str(target))
print('R1_SHA256='+expected)
print('NEXT: bash '+shlex.quote(str(target))+' inspect genos-rag-data-20261007T002029Z-7c0b050f.zip.parts')
print('Only the verified text runner was created. Original upload, ZIP parts, NFS data and Git remain unchanged.')
GENOS_CREATE_VERIFIED_R1_PY
'''.replace('__SHA__', EXPECTED)
    target = OUT / (NAME + '.txt')
    if target.exists():
        raise FileExistsError('Preserve completed delivery; build a new revision')
    target.write_text(body, encoding='ascii')
    subprocess.run(['bash', '-n', str(target)], check=True)
    record = {'version': NAME, 'file': target.name, 'bytes': target.stat().st_size,
              'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'materialized_runner': 'GENOS_TRANSFER_NFS_LIST_R1_PLAIN.txt',
              'materialized_sha256': EXPECTED, 'materialized_bytes': len(raw),
              'original_preserved': True, 'original_code_or_data_decrypted': False,
              'code_or_NFS_or_Git_changed_by_materializer': False,
              'delivery': 'Complete copy/paste code in email body plus full executable TXT',
              'field_result': 'Screenshot: Bash cannot execute binary file; R1 inspect body not started',
              'field_binary_file_cause': 'Unconfirmed: transferred binary/DRM or UTF-16 encoding; field bytes not available',
              'GENOS_accessed': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
