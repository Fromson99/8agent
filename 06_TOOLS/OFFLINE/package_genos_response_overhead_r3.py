"""R3 preserves fulltext diagnostics and binds the reproduced field preimage."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / '08_DEPLOYMENT/GENOS/patches'
OLD = PATCHES / 'response_overhead_20260928_r2'
NEW = PATCHES / 'response_overhead_20260928_r3'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
FIELD_SHA = 'febd2ee7639102e4c376ccbb7ea98dec7a4b0dbd8ded86d32dfc7956c1d18b40'
FIELD_EMIT_SHA = '4a00a4ad8dd1f9e2e0c9c7e772dd1edb91200703ee467fec8e5d3d579d817bd4'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def build():
    previous = load(OLD / 'structural_report.py', 'overhead_r2_previous')
    fulltext = load(PATCHES / 'fulltext_diagnostics_20260928_r1/report_fields.py', 'overhead_fulltext_display')
    thinking_dir = PATCHES / 'thinking_log_20260928_r3'
    thinking = load(thinking_dir / 'structural_report.py', 'overhead_thinking_display')
    team_dir = PATCHES / 'team_request_logs_20260928_r3'
    team = load(team_dir / 'structural_report.py', 'overhead_team_display')
    templates = previous.load_templates(OLD)
    # These are the exact released transformations which produced the field file.
    origin = (PATCHES / 'thinking_log_20260928_r2/baseline' / REPORT).read_bytes()
    field = fulltext.transform(thinking.transform(origin, thinking.load_templates(thinking_dir)))
    assert sha(field) == FIELD_SHA and len(field) == 44082
    emit = previous.functions(ast.parse(field))['_LiveLog.emit'][0]
    assert previous.signature(emit) == FIELD_EMIT_SHA
    try:
        previous.transform(field, templates)
    except ValueError as exc:
        assert str(exc) == 'incompatible report functions: _LiveLog.emit ast_sha256=' + FIELD_EMIT_SHA
    else:
        raise AssertionError('R2 field rejection must be reproduced')
    saved = NEW / 'baselines' / FIELD_SHA / REPORT
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(field)
    seeds = {}
    for folder in ['baselines', 'variants', 'payload']:
        for file in sorted((OLD / folder).rglob('request_report.py')):
            raw = file.read_bytes()
            seeds[sha(raw)] = raw
    for raw in list(seeds.values()):
        try:
            derived = thinking.transform(raw, thinking.load_templates(thinking_dir))
            seeds[sha(derived)] = derived
        except ValueError:
            pass  # Earlier R3 does not accept every later overhead program.
        try:
            derived = team.transform(raw, team.load_templates(team_dir))
            seeds[sha(derived)] = derived
        except ValueError:
            pass
    seeds[sha(origin)] = origin
    seeds[sha(field)] = field
    reviewed = {}
    for digest, raw in seeds.items():
        # Remove only the fulltext display derivation, validate the entire emit
        # against an existing R2 function contract, then reapply the SAME
        # fulltext projection. Other installed functions/fields stay untouched.
        try:
            after = previous.transform(raw, templates)
        except ValueError:
            if digest != FIELD_SHA:
                raise
            # The primary R1 preimage has the same fulltext emit as the field
            # file; R1's primary output supplies its reviewed async counterpart.
            after = (PATCHES / 'response_overhead_20260928_r1/payload' / REPORT).read_bytes()
        before_full = fulltext.transform(raw)
        after_full = fulltext.transform(after)
        before_node = previous.functions(ast.parse(before_full))['_LiveLog.emit'][0]
        after_node = previous.functions(ast.parse(after_full))['_LiveLog.emit'][0]
        key = previous.signature(before_node)
        node = copy.deepcopy(after_node); node.decorator_list = []
        row = {'new_ast_sha256': previous.signature(after_node), 'new_source': ast.unparse(node)}
        choices = templates['functions']['_LiveLog.emit']
        if key in choices and choices[key] != row:
            raise ValueError('conflicting fulltext emit transformation: ' + key)
        choices[key] = row
        choices[row['new_ast_sha256']] = row
        reviewed[sha(before_full)] = {'origin': digest, 'emit_before': key, 'emit_after': row['new_ast_sha256']}
    assert FIELD_EMIT_SHA in templates['functions']['_LiveLog.emit']
    write_json(NEW / 'REPORT_TEMPLATES.json', templates)
    structural = load(NEW / 'structural_report.py', 'overhead_r3_final')
    final = structural.transform(field, templates)
    assert structural.transform(final, templates) == final
    write_json(NEW / 'FIELD_REPRODUCTION.json', {
        'input_sha256': FIELD_SHA, 'input_bytes': len(field), 'emit_ast_sha256': FIELD_EMIT_SHA,
        'origin': 'thinking R2 baseline -> thinking R3 display -> fulltext diagnostics R1 display',
        'r2_exact_rejection_reproduced': True, 'r3_output_sha256': sha(final),
        'fulltext_derivations': reviewed, 'onsite_deployed': False})
    plan = json.loads((OLD / 'PATCH_MANIFEST.json').read_bytes())
    plan['patch'] = 'response-overhead-20260928-r3'
    plan['files'][REPORT]['assets'] = {name: sha((NEW / name).read_bytes())
                                      for name in ['structural_report.py', 'REPORT_TEMPLATES.json']}
    write_json(NEW / 'PATCH_MANIFEST.json', plan)
    rows = []
    for file in sorted(NEW.rglob('*')):
        if file.is_file() and file.name not in {'CODE_MANIFEST.json', 'LOCAL_VALIDATION.json'} and '__pycache__' not in file.parts:
            raw = file.read_bytes()
            rows.append({'path': str(file.relative_to(NEW)), 'bytes': len(raw), 'sha256': sha(raw)})
    write_json(NEW / 'CODE_MANIFEST.json', {'format': '8agent-code/1', 'patch': plan['patch'], 'files': rows})
    archive_path = PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R3.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in [row['path'] for row in rows] + ['CODE_MANIFEST.json']:
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            info = zipfile.ZipInfo(name, (2026, 9, 28, 0, 0, 0))
            archive.writestr(info, (NEW / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    txt = (PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R2_APPLY.txt').read_text()
    old_hash = sha((PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R2.zip').read_bytes())
    txt = txt.replace('RESPONSE_OVERHEAD_20260928_R2', 'RESPONSE_OVERHEAD_20260928_R3')
    txt = txt.replace('response-overhead-20260928-r2', 'response-overhead-20260928-r3').replace('response-overhead-r2', 'response-overhead-r3')
    txt = txt.replace(old_hash, sha(archive_path.read_bytes()))
    (PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R3_APPLY.txt').write_text(txt)
    shutil.copy2(NEW / 'PATCH_NOTES.txt', PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R3_PATCH_NOTES.txt')
    print(json.dumps({'zip_sha256': sha(archive_path.read_bytes()), 'zip_bytes': archive_path.stat().st_size,
                      'field_input_sha256': sha(field), 'field_bytes': len(field),
                      'field_emit_sha256': FIELD_EMIT_SHA, 'r2_reproduced': True,
                      'r3_field_output_sha256': sha(final), 'fulltext_derivations': len(reviewed)}))


if __name__ == '__main__':
    build()
