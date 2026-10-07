"""Build a pinned, standalone fulltext diagnostic handoff; no data/model calls."""
import ast
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

from lawrag.platform.workspace import load_layout

ROOT=Path(__file__).resolve().parents[4]
LAYOUT=load_layout(ROOT)
BASE=LAYOUT.path('deployment')/'GENOS/patches'
PATCH=Path(__file__).resolve().parent
STEM='GENOS_FULLTEXT_DIAGNOSTICS_20260928_R1'
REPORT='02_BACKEND/semantic_runtime/request_report.py'
PREIMAGE=LAYOUT.path('runtime')/'diagnostics/fulltext-20260928-r1-preimage'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def dump(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
def ast_hash(raw):return sha(ast.dump(ast.parse(raw,feature_version=(3,11)),include_attributes=False).encode())


def method(raw):
    tree=ast.parse(raw,feature_version=(3,11))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RelationsTools')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='search')
    offsets=[0]
    for line in raw.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    return node,offsets[node.lineno-1]+node.col_offset,offsets[node.end_lineno-1]+node.end_col_offset


def main():
    fields=module('fulltext_report_builder',PATCH/'report_fields.py')
    report_paths=[ROOT/REPORT,PREIMAGE/REPORT]
    report_paths.extend(p for p in BASE.rglob('request_report.py') if PATCH not in p.parents)
    versions={};origins={}
    structural=module('thinking_r3_catalog_builder',BASE/'thinking_log_20260928_r3/structural_report.py')
    templates=structural.load_templates(BASE/'thinking_log_20260928_r3')
    for path in report_paths:
        raw=path.read_bytes();versions[sha(raw)]=raw;origins.setdefault(sha(raw),[]).append(str(path.relative_to(ROOT)))
        try:
            derived=structural.transform(raw,templates)
        except ValueError:continue
        versions[sha(derived)]=derived
        origins.setdefault(sha(derived),[]).append('verified thinking R3 display derivation of '+sha(raw))
    for digest,raw in list(versions.items()):
        try:after=fields.transform(raw)
        except ValueError:continue
        versions[sha(after)]=after
        origins.setdefault(sha(after),[]).append('verified fulltext display derivation of '+digest)
    catalog={'format':'8agent-report-repair-catalog/1',
             'known_sha256':sorted(versions),'known_ast_sha256':sorted({ast_hash(raw) for raw in versions.values()}),
             'origins':origins,'policy':'Only a valid existing pin, or a known expected report hash and an approved installed report program'}
    (PATCH/'REPORT_CATALOG.json').write_bytes(dump(catalog))
    spec={'format':'8agent-fulltext-diagnostics-patch/1','patch':'fulltext-diagnostics-20260928-r1',
          'generation_change':False,'code_serving_revision':None,'onsite_verified':False,'files':{},
          'assets':{name:sha((PATCH/name).read_bytes()) for name in ('report_fields.py','REPORT_CATALOG.json')}}
    for name in ('02_BACKEND/semantic_runtime/fulltext.py','02_BACKEND/semantic_runtime/term_index.py',
                 '02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py'):
        raw=(ROOT/name).read_bytes();target=PATCH/'payload'/name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        spec['files'][name]={'base_sha256':sha((PREIMAGE/name).read_bytes()),'new_sha256':sha(raw)}
    name='02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py'
    old=(BASE/'latency_20260928_r2/payload'/name).read_bytes()
    baseline=(PREIMAGE/name).read_bytes();new=(ROOT/name).read_bytes()
    original,start,end=method(old);before,_,_=method(baseline);_,ns,ne=method(new)
    assert ast.dump(original,include_attributes=False)==ast.dump(before,include_attributes=False)
    variant=old[:start]+new[ns:ne]+old[end:]
    variant=variant.replace(b'import time\n',b'import time\nfrom contextlib import nullcontext\n',1)
    ast.parse(variant,feature_version=(3,11))
    variant_path='variants/'+sha(old)+'/'+name
    dest=PATCH/variant_path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(variant)
    spec['files'][name]['variants']=[{'base_sha256':sha(old),'new_sha256':sha(variant),'payload_path':variant_path}]
    spec['files'][REPORT]={'strategy':'structural-report'}
    (PATCH/'PATCH_MANIFEST.json').write_bytes(dump(spec))
    document=LAYOUT.path('docs')/'REFERENCE/OPERATIONS/GENOS_FULLTEXT_DIAGNOSTICS_20260928.md'
    analysis=(PATCH/'ANALYSIS.txt');analysis.write_text(document.read_text())
    names={'apply.py','verify.py','gate.py','report_fields.py','REPORT_CATALOG.json','PATCH_MANIFEST.json','ANALYSIS.txt','PATCH_NOTES.txt'}
    names.update(str(p.relative_to(PATCH)) for folder in ('payload','variants') for p in (PATCH/folder).rglob('*') if p.is_file())
    rows=[]
    archive=BASE/(STEM+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            raw=(PATCH/name).read_bytes();rows.append({'path':name,'bytes':len(raw),'sha256':sha(raw)})
            z.writestr(name,raw)
        z.writestr('CODE_MANIFEST.json',dump({'format':'8agent-code/1','patch':spec['patch'],'files':rows}))
    zip_hash=sha(archive.read_bytes())
    shell=r'''#!/usr/bin/env bash
set -Eeuo pipefail
# Run in the existing GENOS checkout: bash GENOS_FULLTEXT_DIAGNOSTICS_20260928_R1_APPLY.txt
# MODE=check / MODE=verify / MODE=code-only / MODE=rollback ROLLBACK_FROM=/actual/BACKUP_READY/path
RUN_LOG="$(mktemp "${TMPDIR:-/tmp}/genos-fulltext-diagnostics-r1-XXXXXXXX.log")"
exec > >(tee -a "$RUN_LOG") 2>&1
trap 'result=$?; printf "FINISHED status=%s log=%s\n" "$result" "$RUN_LOG"' EXIT
printf 'START patch=fulltext-diagnostics-20260928-r1 log=%s\n' "$RUN_LOG"
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/DEV}"
MODE="${MODE:-apply}"
[[ -d "$DEPLOY_ROOT/.git" || -f "$DEPLOY_ROOT/.git" ]] || { printf 'ERROR: existing Git checkout required: %s\n' "$DEPLOY_ROOT"; exit 2; }
if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$DEPLOY_ROOT/.venv/bin/python" ]]; then PYTHON_BIN="$DEPLOY_ROOT/.venv/bin/python";
    else PYTHON_BIN="$(command -v python3 || true)"; fi
fi
[[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]] || { printf 'ERROR: existing Python 3 required\n'; exit 2; }
mkdir -p "$DEPLOY_ROOT/TRANSFER"
PATCH_DIR="$(mktemp -d "$DEPLOY_ROOT/TRANSFER/fulltext-diagnostics-r1-unpack-XXXXXXXX")"
PATCH_ZIP="$PATCH_DIR/package.zip"
printf 'MODE=%s CHECKOUT=%s PYTHON=%s PACKAGE=%s\n' "$MODE" "$DEPLOY_ROOT" "$PYTHON_BIN" "$PATCH_DIR"
base64 --decode > "$PATCH_ZIP" <<'FULLTEXT_DIAGNOSTICS_PAYLOAD'
'''+base64.encodebytes(archive.read_bytes()).decode()+r'''FULLTEXT_DIAGNOSTICS_PAYLOAD
"$PYTHON_BIN" - "$PATCH_ZIP" "$PATCH_DIR" "'''+zip_hash+r'''" <<'VERIFY_FULLTEXT_PACKAGE'
import hashlib,json,sys,zipfile
from pathlib import Path,PurePosixPath
raw=Path(sys.argv[1]).read_bytes()
if hashlib.sha256(raw).hexdigest()!=sys.argv[3]:raise ValueError('ZIP SHA-256 mismatch')
with zipfile.ZipFile(sys.argv[1]) as z:
    names=z.namelist()
    if len(names)!=len(set(names)):raise ValueError('duplicate ZIP paths')
    inventory=json.loads(z.read('CODE_MANIFEST.json'))
    if inventory['format']!='8agent-code/1':raise ValueError('invalid manifest format')
    rows={r['path']:r for r in inventory['files']}
    if len(rows)!=len(inventory['files']) or set(names)!=set(rows)|{'CODE_MANIFEST.json'}:raise ValueError('ZIP inventory mismatch')
    for name,row in rows.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or str(path)!=name:raise ValueError('unsafe ZIP path')
        if path.suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise ValueError('excluded JavaScript')
        data=z.read(name)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('ZIP member hash mismatch: '+name)
        target=Path(sys.argv[2])/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
print('PACKAGE_HASHES PASS')
VERIFY_FULLTEXT_PACKAGE
case "$MODE" in
 check) "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT" --check-only ;;
 apply)
    "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT"
    git -C "$DEPLOY_ROOT" diff --check
    printf 'Review and commit only changed_files (diagnostic code, request_report, engine manifests, PIPELINE.json).\n'
    printf 'After commit: MODE=verify bash GENOS_FULLTEXT_DIAGNOSTICS_20260928_R1_APPLY.txt\n'
    ;;
 verify) "$PYTHON_BIN" "$PATCH_DIR/verify.py" "$DEPLOY_ROOT" ;;
 code-only)
    "$PYTHON_BIN" "$PATCH_DIR/gate.py" --code-only --code-zip "$DEPLOY_ROOT/TRANSFER/fulltext-diagnostics-20260928-r1/applied-code.zip" --deploy-root "$DEPLOY_ROOT"
    ;;
 rollback)
    : "${ROLLBACK_FROM:?Set ROLLBACK_FROM to the actual BACKUP_READY path}"
    "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT" --rollback-from "$ROLLBACK_FROM"
    git -C "$DEPLOY_ROOT" diff --check
    ;;
 *) printf 'ERROR: MODE must be apply, check, verify, code-only or rollback\n'; exit 2 ;;
esac
'''
    (BASE/(STEM+'_APPLY.txt')).write_text(shell)
    shutil.copyfile(analysis,BASE/(STEM+'_ANALYSIS.txt'))
    shutil.copyfile(PATCH/'PATCH_NOTES.txt',BASE/(STEM+'_PATCH_NOTES.txt'))
    attachments=[archive,BASE/(STEM+'_APPLY.txt'),BASE/(STEM+'_ANALYSIS.txt'),BASE/(STEM+'_PATCH_NOTES.txt')]
    (BASE/(STEM+'_SHA256SUMS.txt')).write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in attachments))
    attachments.append(BASE/(STEM+'_SHA256SUMS.txt'))
    receipt={'patch':spec['patch'],'files':[{'name':p.name,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in attachments],
             'tested_code_root':str(ROOT),'push_checkout':None,'commit':None,'generation':None,
             'generation_manifest_sha256':None,'code_serving_revision':None,'onsite_verified':False}
    (PATCH/'BUILD_RECEIPT.json').write_bytes(dump(receipt))
    print(json.dumps({'zip_sha256':zip_hash,'zip_members':len(rows)+1,'attachments':len(attachments),'report_programs':len(versions)},ensure_ascii=False))


if __name__=='__main__':main()
