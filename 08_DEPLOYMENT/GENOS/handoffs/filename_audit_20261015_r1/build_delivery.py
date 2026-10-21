"""Build a stdlib-only diagnostic handoff; no production code installation."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import textwrap
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_FILENAME_AUDIT_20261015_R1'


def sha(raw): return hashlib.sha256(raw).hexdigest()


def main():
    sources = {'genos_filename_audit.py': ROOT / '06_TOOLS/OFFLINE/genos_filename_audit.py',
        'deployment_paths.py': ROOT / '02_BACKEND/semantic_runtime/deployment_paths.py',
        'genos_generation_e2e.py': ROOT / '06_TOOLS/COMMANDS/genos_generation_e2e.py',
        'test_filename_audit.py': HERE / 'test_filename_audit.py'}
    files = {n: p.read_bytes() for n, p in sources.items()}
    manifest = {'schema_version': 'filename-audit-code-v1', 'purpose': 'read-only diagnostic; no installation',
        'required_files': [{'path': n, 'sha256': sha(raw), 'source': str(sources[n].relative_to(ROOT))} for n, raw in files.items()]}
    (HERE / 'CODE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    files['CODE_MANIFEST.json'] = (HERE / 'CODE_MANIFEST.json').read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, raw in files.items(): z.writestr(n, raw)
    payload = buf.getvalue()
    encoded = '\n'.join(textwrap.wrap(base64.b64encode(payload).decode(), 100))
    runner = '''#!/usr/bin/env bash
set -Eeuo pipefail
AUDIT_LOG_BASE="$PWD/FILENAME_AUDIT_RUNS"
mkdir -p "$AUDIT_LOG_BASE"
AUDIT_LOG_DIR="$(mktemp -d "$AUDIT_LOG_BASE/run-$(date +%Y%m%d_%H%M%S)-XXXXXX")"
exec > >(tee -a "$AUDIT_LOG_DIR/console.log") 2>&1
trap 'AUDIT_EXIT=$?; printf "%s\\n" "$AUDIT_EXIT" > "$AUDIT_LOG_DIR/exit_status.txt"; printf "AUDIT_EXIT=%s LOG=%s\\n" "$AUDIT_EXIT" "$AUDIT_LOG_DIR"' EXIT
printf 'Read-only filename audit. Working directory: %s\\n' "$PWD"
python3 -B - "$@" <<'PY_AUDIT'
import base64, hashlib, io, json, pathlib, sys, tempfile, zipfile
sys.dont_write_bytecode = True
raw = base64.b64decode("""PAYLOAD""")
if hashlib.sha256(raw).hexdigest() != 'PAYLOAD_HASH': raise ValueError('embedded code hash mismatch')
print('PYTHON=' + sys.executable + ' VERSION=' + sys.version, flush=True)
with tempfile.TemporaryDirectory(prefix='genos-filename-audit-code-') as d:
    root = pathlib.Path(d)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if pathlib.PurePosixPath(name).name != name: raise ValueError('invalid payload member')
        z.extractall(root)
    manifest = json.loads((root / 'CODE_MANIFEST.json').read_text())
    for item in manifest['required_files']:
        if hashlib.sha256((root / item['path']).read_bytes()).hexdigest() != item['sha256']: raise ValueError('code manifest mismatch')
    sys.path.insert(0, str(root))
    import genos_filename_audit
    raise SystemExit(genos_filename_audit.main(sys.argv[1:]))
PY_AUDIT
'''.replace('PAYLOAD_HASH', sha(payload)).replace('PAYLOAD', encoded)
    (HERE / (NAME + '_RUN.txt')).write_text(runner, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('audit', sources['genos_filename_audit.py'])
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    sample = HERE / 'SAMPLE'
    if not sample.exists():
        sample.mkdir()
        names = ['위험관리기준시행세칙(20240109)_clean.docx', '위험관리기준시행세칙(20240426)_전산반영.docx', '위험관리기준시행세칙(20260319).docx',
            '상품위원회운영지침(20140612).gul.docx', '상품위원회운영지침(20210423_고난도금융투자상품).docx', '상품위원회운영지침(20251205)_조직개편.docx',
            '위기대응준칙(Contingency Plan)_20161114.docx', '위기대응준칙(Contingency Plan)_20231121(직위수정).docx', '위기대응준칙(Contingency Plan)_20251230.docx',
            '~$위험관리위원회운영준칙(20160823).docx', '리스크관리위원회운영준칙_20120227.gul.docx', '위험관리위원회운영준칙(20160823).docx',
            '20140630_리스크관리시스템 운영준칙.gul.docx', '20160823_위험관리시스템 운영준칙.docx', '위험관리시스템 운영준칙(20200117).docx',
            '20201209 보유주식의 의결권행사에 관한 지침.docx', '20250401_보유주식의 의결권행사에 관한 지침.docx',
            '업무위탁 운영지침_[별첨6] 중점관리 위탁계약 선정 기준_260320.docx', '업무위탁 운영지침_[별첨7] 수탁사 실사 체크리스트_260320.docx',
            '업무위탁 운영지침_[별첨8] 업무위탁 계약서 작성 체크리스트_260320.docx', '업무위탁 운영지침_260320.docx', '업무위탁 운영지침_업무위탁 운영기준_260320.docx',
            '모의규정_20250230.docx', '모의규정_20260101.docx', '모의무날짜규정.docx']
        audit.report(sample, audit.select([{'filename': n, 'path': n, 'document_id': str(i)} for i, n in enumerate(names)]),
            {'mode': 'PHOTO_REPRESENTATIVE_NAMES_AND_SYNTHETIC_EDGE_CASES', 'field_inventory': False})
    package_files = {**files, NAME + '_RUN.txt': runner.encode()}
    for n in ('GUIDE_UTF8.txt', 'WORK_CONTRACT.txt', 'VALIDATION.json'):
        if (HERE / n).exists(): package_files[n] = (HERE / n).read_bytes()
    for f in sample.iterdir(): package_files['SAMPLE/' + f.name] = f.read_bytes()
    checksums = ''.join(sha(raw) + '  ' + n + '\n' for n, raw in sorted(package_files.items()))
    package_files['SHA256SUMS.txt'] = checksums.encode()
    with zipfile.ZipFile(HERE / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for n, raw in sorted(package_files.items()):
            if Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}: raise ValueError('JS forbidden in email archive')
            z.writestr(n, raw)
    attachments = [NAME + '.zip', NAME + '_RUN.txt', 'GUIDE_UTF8.txt']
    (HERE / 'EMAIL_ATTACHMENTS_SHA256.txt').write_text(''.join(sha((HERE / n).read_bytes()) + '  ' + n + '\n' for n in attachments))
    print(json.dumps({n: (HERE / n).stat().st_size for n in attachments}, indent=2))


if __name__ == '__main__': main()
