"""Rebuild the R2 installer from preserved R1 and the earlier R3 repairs."""
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
OLD = PATCHES / 'response_overhead_20260928_r1'
NEW = PATCHES / 'response_overhead_20260928_r2'
REPORT = '02_BACKEND/semantic_runtime/request_report.py'
PATCH_ID = 'response-overhead-20260928-r2'


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
    structural = load(NEW / 'structural_report.py', 'overhead_r2_structural')
    team_dir = PATCHES / 'team_request_logs_20260928_r3'
    team = load(team_dir / 'structural_report.py', 'overhead_previous_team_r3')
    thinking_dir = PATCHES / 'thinking_log_20260928_r3'
    thinking = load(thinking_dir / 'structural_report.py', 'overhead_previous_thinking_r3')
    team_templates = team.load_templates(team_dir)
    thinking_templates = thinking.load_templates(thinking_dir)
    target_raw = (OLD / 'payload' / REPORT).read_bytes()
    target_nodes = structural.functions(ast.parse(target_raw))
    before_after = []
    for path in sorted((OLD / 'baselines').glob('*/' + REPORT)):
        after = OLD / 'variants' / path.relative_to(OLD / 'baselines')
        before_after.append((path.read_bytes(), after.read_bytes()))
    changed = set()
    additions = set()
    for before, after in before_after:
        a = structural.functions(ast.parse(before)); b = structural.functions(ast.parse(after))
        changed.update(k for k in a if structural.signature(a[k][0]) != structural.signature(b[k][0]))
        additions.update(b.keys() - a.keys())
    templates = {'signature_format': 'canonical-ast-fields-v1', 'functions': {}, 'add_methods': {}}

    def source(node):
        node = copy.deepcopy(node)
        node.decorator_list = []  # Existing decorator bytes are retained by the editor.
        return ast.unparse(node)

    def register(before_nodes, after_nodes, preserve_existing=False):
        for name in sorted(changed):
            old = structural.one(before_nodes[name], name)
            new = structural.one(after_nodes[name], name)
            digest = structural.signature(old)
            row = {'new_ast_sha256': structural.signature(new), 'new_source': source(new)}
            choices = templates['functions'].setdefault(name, {})
            if digest in choices and choices[digest] != row:
                if preserve_existing:
                    continue
                raise ValueError('conflicting reviewed transformation: ' + name)
            choices[digest] = row

    def optimized(raw):
        nodes = structural.functions(ast.parse(raw))
        init = nodes['_LiveLog.__init__'][0]
        if not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute)
                   and isinstance(t.value, ast.Name) and t.value.id == 'self' and t.attr == 'writer'
                   for t in n.targets) for n in ast.walk(init)):
            init.body.extend(ast.parse('self.writer = obs.AsyncHandler(self, max_records=512, max_bytes=1024 * 1024)').body)
        return nodes

    def with_thinking_emit(after_nodes, thinking_nodes):
        result = copy.deepcopy(after_nodes)
        # Keep the reviewed R3 typed projection and revision marker in the emit
        # function while adding R1's asynchronous detail/opening handling.
        emit = result['_LiveLog.emit'][0]
        old_emit = thinking_nodes['_LiveLog.emit'][0]
        field_loop = next(n for n in old_emit.body if isinstance(n, ast.For))
        marker = next(n for n in old_emit.body if isinstance(n, ast.If)
                      and ast.unparse(n.test) == "'diagnostics_version' in fields")
        replaced = False
        body = []
        for n in emit.body:
            if isinstance(n, ast.If) and ast.unparse(n.test) == "'diagnostics_version' in fields":
                continue
            if isinstance(n, ast.For):
                body.extend([copy.deepcopy(marker), copy.deepcopy(field_loop)])
                replaced = True
            else:
                body.append(n)
        assert replaced
        emit.body = body
        return result

    def register_teams(raw, optimized_nodes):
        transformed = team.transform(raw, team_templates)
        before_nodes = structural.functions(ast.parse(transformed))
        after_nodes = copy.deepcopy(optimized_nodes)
        for name in changed & team_templates['functions'].keys():
            after_nodes[name] = target_nodes[name]
        register(before_nodes, after_nodes, preserve_existing=True)

    for before, after in before_after:
        register(structural.functions(ast.parse(before)), optimized(after))
        register(structural.functions(ast.parse(after)), optimized(after))
    for before, after in before_after:
        b = optimized(after)
        register_teams(before, b)
        typed = thinking.transform(before, thinking_templates)
        t = structural.functions(ast.parse(typed))
        typed_after = with_thinking_emit(b, t)
        register(t, typed_after)
        register_teams(typed, typed_after)
    # Every reviewed output is also an accepted, byte-preserving rerun input.
    for name, choices in templates['functions'].items():
        for row in list(choices.values()) + [{'new_ast_sha256': structural.signature(target_nodes[name][0]),
                                            'new_source': source(target_nodes[name][0])}]:
            digest = row['new_ast_sha256']
            if digest in choices and choices[digest]['new_ast_sha256'] != digest:
                raise ValueError('non-idempotent reviewed transformation: ' + name)
            choices[digest] = row
    sample_after = structural.functions(ast.parse(before_after[0][1]))
    for name in sorted(additions):
        accepted = {structural.signature(target_nodes[name][0])}
        for _, after in before_after:
            accepted.add(structural.signature(structural.functions(ast.parse(after))[name][0]))
        templates['add_methods'][name] = {
            'accepted_ast_sha256': sorted(accepted), 'new_source': source(sample_after[name][0])}
    write_json(NEW / 'REPORT_TEMPLATES.json', templates)
    plan = json.loads((OLD / 'PATCH_MANIFEST.json').read_bytes())
    plan['patch'] = PATCH_ID
    plan['files'][REPORT]['strategy'] = 'structural-report'
    plan['files'][REPORT]['assets'] = {n: sha((NEW / n).read_bytes())
                                       for n in ['structural_report.py', 'REPORT_TEMPLATES.json']}
    for folder in ['payload', 'variants', 'baselines']:
        shutil.copytree(OLD / folder, NEW / folder, dirs_exist_ok=True)
    write_json(NEW / 'PATCH_MANIFEST.json', plan)
    rows = []
    for file in sorted(NEW.rglob('*')):
        if file.is_file() and file.name not in {'CODE_MANIFEST.json', 'LOCAL_VALIDATION.json'} and '__pycache__' not in file.parts:
            raw = file.read_bytes()
            rows.append({'path': str(file.relative_to(NEW)), 'bytes': len(raw), 'sha256': sha(raw)})
    write_json(NEW / 'CODE_MANIFEST.json', {'format': '8agent-code/1', 'patch': PATCH_ID, 'files': rows})
    archive_path = PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R2.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in [r['path'] for r in rows] + ['CODE_MANIFEST.json']:
            info = zipfile.ZipInfo(name, (2026, 9, 28, 0, 0, 0))
            archive.writestr(info, (NEW / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    txt = (ROOT / '08_DEPLOYMENT/GENOS/handoffs/response_overhead_20260928_r1/GENOS_RESPONSE_OVERHEAD_20260928_R1_APPLY.txt').read_text()
    txt = txt.replace('RESPONSE_OVERHEAD_20260928_R1', 'RESPONSE_OVERHEAD_20260928_R2')
    txt = txt.replace('response-overhead-20260928-r1', PATCH_ID).replace('response-overhead-r1', 'response-overhead-r2')
    txt = txt.replace('89caf4c25ea12e4c10020f37038a4da2a580e634aaf3b834898ad3620c830494', sha(archive_path.read_bytes()))
    txt = txt.replace('git -C "$DEPLOY_ROOT" diff --check',
                      'git -C "$DEPLOY_ROOT" -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check')
    txt = txt.replace('case "$MODE" in\n', 'case "$MODE" in\n    check)\n        "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT" --check-only\n        ;;\n')
    txt = txt.replace('MODE must be apply, verify, rollback or summary', 'MODE must be check, apply, verify, rollback or summary')
    txt = txt.replace('diagnostic_revision=response-overhead-20260928-r2', 'observability_revision=response-overhead-20260928-r1 (runtime unchanged)')
    (PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R2_APPLY.txt').write_text(txt)
    notes = NEW / 'PATCH_NOTES.txt'
    if notes.exists():
        shutil.copy2(notes, PATCHES / 'GENOS_RESPONSE_OVERHEAD_20260928_R2_PATCH_NOTES.txt')
    print(json.dumps({'zip': str(archive_path), 'sha256': sha(archive_path.read_bytes()),
                      'bytes': archive_path.stat().st_size, 'reviewed_functions': len(changed),
                      'added_methods': sorted(additions)}, ensure_ascii=False))


if __name__ == '__main__':
    build()
