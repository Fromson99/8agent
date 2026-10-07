"""Apply only verified error-display edits; preserve checkout-specific code."""
import ast, fcntl, hashlib, json, os, shutil, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
EDITS = json.loads("[{\"path\":\"02_BACKEND/semantic_runtime/genos_backend.py\",\"old\":\"\\ndef unit_vector(values):\",\"new\":\"\\ndef error_detail(value):\\n    \\\"\\\"\\\"Keep each exception type/message and original cause, redacting credentials.\\\"\\\"\\\"\\n    if not isinstance(value, BaseException):\\n        return safe(str(value))\\n    parts, seen = [], set()\\n    current = value\\n    while current is not None and id(current) not in seen:\\n        seen.add(id(current))\\n        parts.append(f'{type(current).__name__}: {current}')\\n        current = current.__cause__ or current.__context__\\n    return safe(' <- caused by: '.join(parts))\\n\\n\\ndef unit_vector(values):\"},{\"path\":\"02_BACKEND/semantic_runtime/genos_backend.py\",\"old\":\"detail = safe(f'{type(exc).__name__}: {exc}')\",\"new\":\"detail = error_detail(exc)\"},{\"path\":\"02_BACKEND/semantic_runtime/genos_backend.py\",\"old\":\"{'error': safe(f'{type(exc).__name__}: {exc}')})\",\"new\":\"{'error': error_detail(exc)})\"},{\"path\":\"02_BACKEND/semantic_runtime/genos_backend.py\",\"old\":\"raise ValueError(f'{role} response validation failed; see {Path(receipt[\\\"path\\\"]).parent}') from None\",\"new\":\"raise ValueError(f'{role} response validation failed: {error_detail(exc)}; see {Path(receipt[\\\"path\\\"]).parent}') from None\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"from semantic_runtime.contracts import sha\",\"new\":\"from semantic_runtime.contracts import sha\\nfrom semantic_runtime.genos_backend import error_detail\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"    import fitz\\n    path = plain_path(path)\",\"new\":\"    try:\\n        import fitz\\n    except ImportError as exc:\\n        raise ImportError('PyMuPDF (fitz) is unavailable in the executing Python: ' + error_detail(exc)) from exc\\n    path = plain_path(path)\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"raise ValueError('empty/encrypted PDF')\",\"new\":\"raise ValueError('empty/encrypted PDF: ' + str(path))\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"evidence['transport_error_type'] = type(exc).__name__\",\"new\":\"evidence['transport_error_type'] = type(exc).__name__\\n        evidence['error'] = error_detail(exc)\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"raise ValueError('conversion pending; inspect saved staging job before a new run') from exc\",\"new\":\"raise ValueError('conversion pending: ' + error_detail(exc) + '; inspect saved staging job: ' + str(work)) from exc\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"    except Exception:\\n        evidence['status'] = 'PENDING' if evidence['http_status'] >= 500 else 'FAILED'\\n        builder.atomic(work / 'conversion.json', evidence)\\n        raise ValueError('converter returned no valid sidecar PDF; inspect ' + str(work))\",\"new\":\"    except Exception as exc:\\n        evidence['status'] = 'PENDING' if evidence['http_status'] >= 500 else 'FAILED'\\n        evidence['error'] = error_detail(exc)\\n        evidence['error_type'] = type(exc).__name__\\n        evidence['expected_pdf'] = str(pdf)\\n        builder.atomic(work / 'conversion.json', evidence)\\n        if isinstance(exc, ImportError):\\n            raise\\n        raise ValueError('PDF validation failed: ' + error_detail(exc)\\n                         + '; HTTP=' + str(evidence['http_status'])\\n                         + ' API code=' + str(evidence['api_code'])\\n                         + '; PDF=' + str(pdf) + '; receipt=' + str(work / 'conversion.json')) from exc\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"raise ValueError('previous conversion failed/pending; inspect ' + str(old))\",\"new\":\"raise ValueError('previous conversion ' + str(evidence.get('status'))\\n                                 + ': ' + str(evidence.get('error') or evidence.get('transport_error_type')\\n                                              or 'no original error saved by the previous code')\\n                                 + '; HTTP=' + str(evidence.get('http_status'))\\n                                 + ' API code=' + str(evidence.get('api_code')) + '; receipt=' + str(old))\"},{\"path\":\"02_BACKEND/lawrag/pipeline/raw_preprocess.py\",\"old\":\"report['errors'].append({'source': str(source), 'error': str(exc)})\",\"new\":\"report['errors'].append({'source': str(source), 'error': error_detail(exc), 'error_type': type(exc).__name__})\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_progress.py\",\"old\":\"from semantic_runtime.genos_backend import safe\",\"new\":\"from semantic_runtime.genos_backend import safe, error_detail\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_progress.py\",\"old\":\"def reason(value):\\n    text = clean(value)\",\"new\":\"def reason(value):\\n    original = clean(error_detail(value))\\n    text = original\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_progress.py\",\"old\":\"    return text\\n\\n\\ndef vlm_detail\",\"new\":\"    return original if text == original else original + ' | 설명: ' + text\\n\\n\\ndef vlm_detail\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_stages.py\",\"old\":\"from semantic_runtime.genos_backend import Genos\",\"new\":\"from semantic_runtime.genos_backend import Genos, error_detail\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_stages.py\",\"old\":\"'structure': 'FAILED', 'error': str(exc)\",\"new\":\"'structure': 'FAILED', 'error': error_detail(exc)\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_stages.py\",\"old\":\"record(did, 'structure', 'FAILED', error=str(exc)\",\"new\":\"record(did, 'structure', 'FAILED', error=error_detail(exc)\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_stages.py\",\"old\":\"report['documents'][did]['error']=str(exc)\",\"new\":\"report['documents'][did]['error']=error_detail(exc)\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_stages.py\",\"old\":\"record(did,'index','FAILED',error=str(exc)\",\"new\":\"record(did,'index','FAILED',error=error_detail(exc)\"},{\"path\":\"06_TOOLS/COMMANDS/genos_data_stages.py\",\"old\":\"status.finish('FAILED', error=str(exc))\",\"new\":\"status.finish('FAILED', error=reason(exc))\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_build.py\",\"old\":\"from semantic_runtime.genos_backend import Genos, safe\",\"new\":\"from semantic_runtime.genos_backend import Genos, safe, error_detail\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_build.py\",\"old\":\"'error': str(exc), 'type': type(exc).__name__\",\"new\":\"'error': error_detail(exc), 'type': type(exc).__name__\"},{\"path\":\"02_BACKEND/lawrag/pipeline/genos_build.py\",\"old\":\"print(safe(f'BUILD STOPPED: {type(exc).__name__}: {exc}'), file=sys.stderr)\",\"new\":\"print('BUILD STOPPED: ' + error_detail(exc), file=sys.stderr)\"},{\"path\":\"02_BACKEND/semantic_runtime/genos.py\",\"old\":\"        result.update(status=\\\"FAIL\\\", error=type(exc).__name__)\",\"new\":\"        from .genos_backend import error_detail\\n        result.update(status=\\\"FAIL\\\", error=type(exc).__name__, error_detail=error_detail(exc))\"}]")
ROOT = Path.cwd().resolve()
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def target(rel):
    p = Path(rel)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Unsafe code path: ' + rel)
    out = ROOT / p
    if any(q.is_symlink() for q in (out, *out.parents)) or not out.is_file():
        raise ValueError('Code file missing or symlink: ' + str(out))
    return out
def atomic(path, raw):
    temp = path.with_name('.error-patch-' + uuid.uuid4().hex)
    try:
        with temp.open('xb') as out:
            out.write(raw)
        if path.exists():
            os.chmod(temp, path.stat().st_mode & 0o777)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
data = Path(os.environ['GENOS_DATA_ROOT']).resolve()
run_id = os.environ['GENOS_RUN_ID']
locks = []
for lock_path in (data / '.raw-migration.lock', data / 'LOGS' / run_id / 'full-e2e-driver.lock'):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    locks.append(lock)
mode = os.environ.get('GENOS_ERROR_PATCH_MODE', 'apply')
if mode == 'rollback':
    receipt_path = Path(os.environ['GENOS_ERROR_PATCH_RECEIPT']).resolve()
    receipt = json.loads(receipt_path.read_text())
    if receipt['code_root'] != str(ROOT):
        raise ValueError('Rollback checkout differs')
    plan = []
    for row in receipt['files']:
        dest = target(row['path'])
        if sha(dest.read_bytes()) != row['after_sha256']:
            raise ValueError('Rollback current code differs: ' + row['path'])
        original = (receipt_path.parent / 'before' / row['path']).read_bytes()
        if sha(original) != row['before_sha256']:
            raise ValueError('Rollback backup hash differs: ' + row['path'])
        plan.append((dest, original))
    for dest, original in plan:
        atomic(dest, original)
    print('CODE_PATCH_ROLLBACK_PASS receipt=' + str(receipt_path), flush=True)
elif mode == 'apply':
    plan = []
    for rel in dict.fromkeys(row['path'] for row in EDITS):
        dest = target(rel)
        before = dest.read_bytes()
        text = before.decode()
        for edit in [row for row in EDITS if row['path'] == rel]:
            if edit['new'] in text:
                continue
            count = text.count(edit['old'])
            expected = 2 if rel == '02_BACKEND/semantic_runtime/genos.py' else 1
            if count != expected:
                raise ValueError('CODE_PATCH_BASE_MISMATCH path=' + rel + ' sha256=' + sha(before)
                                 + ' anchor_count=' + str(count))
            text = text.replace(edit['old'], edit['new'])
        ast.parse(text, filename=rel, feature_version=(3, 11))
        after = text.encode()
        if after != before:
            plan.append((rel, dest, before, after))
    if not plan:
        print('CODE_PATCH_ALREADY_APPLIED files=7 (no writes)', flush=True)
    else:
        backup = ROOT / 'TRANSFER/BACKUPS/actual-error-details-r1' / (
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        files = []
        for rel, dest, before, after in plan:
            saved = backup / 'before' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
            if saved.read_bytes() != before or dest.read_bytes() != before:
                raise ValueError('Code changed during backup: ' + rel)
            files.append({'path': rel, 'before_sha256': sha(before), 'after_sha256': sha(after)})
        receipt = {'schema_version': 'actual-error-details-patch-v1', 'status': 'PREPARED',
                   'code_root': str(ROOT), 'run_id': run_id, 'files': files,
                   'created_at': datetime.now(timezone.utc).isoformat(),
                   'base_generation': os.environ.get('GENOS_BASE_GENERATION')}
        receipt_path = backup / 'receipt.json'
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        for rel, dest, before, after in plan:
            if dest.read_bytes() != before:
                raise ValueError('Code changed before apply: ' + rel)
            atomic(dest, after)
            if sha(dest.read_bytes()) != sha(after):
                raise ValueError('Applied code hash differs: ' + rel)
        receipt['status'] = 'APPLIED'
        atomic(receipt_path, (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode())
        print('CODE_PATCH_APPLIED files=' + str(len(files)) + ' receipt=' + str(receipt_path), flush=True)
        print('ROLLBACK: GENOS_ERROR_PATCH_MODE=rollback GENOS_ERROR_PATCH_RECEIPT='
              + str(receipt_path) + ' bash TRANSFER/GENOS_FULL_PIPELINE_BACKUP_E2E_R7.txt', flush=True)
else:
    raise ValueError('GENOS_ERROR_PATCH_MODE must be apply or rollback')

