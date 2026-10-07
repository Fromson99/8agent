"""Build the final-review OFF handoff from the tested MAIN working bytes."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
PATCH = Path(__file__).resolve().parent
ID = 'final-review-disabled-20260928-r1'
STEM = 'GENOS_FINAL_REVIEW_OFF_20260928_R1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def undo(raw, pairs):
    for after, before in pairs:
        assert raw.count(after.encode()) == 1, after
        raw = raw.replace(after.encode(), before.encode(), 1)
    return raw


def build():
    bases = {}
    name = '02_BACKEND/semantic_runtime/legal_agent/workflow_tiers_policy.py'
    bases[name] = undo((ROOT/name).read_bytes(), [
        ("'bounded_source_selection_enabled':False, 'final_review_enabled':False}", "'bounded_source_selection_enabled':False}"),
        ("    if type(p['final_review_enabled']) is not bool: raise ContractError('final_review_enabled must be bool')\n", ''),
        ("'bounded_source_selection_enabled', 'final_review_enabled'}:", "'bounded_source_selection_enabled'}:")])
    name = '00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json'
    bases[name] = undo((ROOT/name).read_bytes(), [
        ('"bounded_source_selection_enabled": true,\n  "final_review_enabled": false', '"bounded_source_selection_enabled": true')])
    name = '02_BACKEND/semantic_runtime/legal_agent/tools_session.py'
    bases[name] = undo((ROOT/name).read_bytes(), [
        ("if claims and self.profile.get('final_review_enabled', True):", 'if claims:'),
        ("                elif claims:\n                    with self.work.transaction():\n                        self.work.event('FINAL_REVIEW_SKIPPED', {\n                            'reason': 'disabled_by_profile',\n                            'claim_versions': {h['entity_id']: h['version'] for h in claims}})\n", ''),
        ("            stage = '작성·검토' if self.profile.get('final_review_enabled', True) else '답변 작성'\n            self.limitations.append(stage+'을 완료하지 못했습니다: '+str(exc))", "            self.limitations.append('작성·검토를 완료하지 못했습니다: '+str(exc))"),
        ("        reason = ('주장별 원문·질문 검토와 실행 한도' if self.profile.get('final_review_enabled', True)\n                  else '선택 원문 기반 답변 작성과 실행 한도')\n        control = {'decision': self.next_mode, 'gate': gate, 'reason': reason,", "        control = {'decision': self.next_mode, 'gate': gate, 'reason': '주장별 원문·질문 검토와 실행 한도',")])
    assert sha(bases[name]) == 'c65438d124a6d26f422d2b6bc776d922683b95d02909249a3ab89f0682d459f5'
    name = '02_BACKEND/semantic_runtime/legal_agent/question_obligations.py'
    bases[name] = undo((ROOT/name).read_bytes(), [
        ('exact evidence/claim -> optional review, MAIN', 'exact evidence/claim -> review, MAIN'),
        ("'reason':review['reason'] if review else (\n                             '이 요구에 대한 답변 검토가 완료되지 않았습니다.' if self.profile['final_review_enabled']\n                             else '최종 답변 검토는 비활성화되어 있습니다.')", "'reason':review['reason'] if review else '이 요구에 대한 답변 검토가 완료되지 않았습니다.'")])
    name = '02_BACKEND/semantic_runtime/legal_agent/final_review_notes.py'
    bases[name] = undo((ROOT/name).read_bytes(), [
        ('Publish the chosen v5 draft; report review gaps only when review is enabled.', 'Publish the chosen v5 draft; translate review gaps into legal review notes.'),
        ("    review_enabled = session.profile.get('final_review_enabled', True)\n", ''),
        ('        if review_enabled:\n            notes.collect(claims, observation)', '        notes.collect(claims, observation)'),
        ('if review_enabled and claims and any(', 'if claims and any('),
        ("        heading = '**법률 검토 필요사항**' if review_enabled else '확인 한계'\n        result['answer']['text'] += ('\\n\\n' if result['answer']['text'] else '') + heading + '\\n'", "        result['answer']['text'] += ('\\n\\n' if result['answer']['text'] else '') + '**법률 검토 필요사항**\\n'"),
        ("    review_states = ({h['entity_id']: h['payload']['verdict'] for h in session.work.heads('review', current=True)}\n                     if review_enabled else {})", "    review_states = {h['entity_id']: h['payload']['verdict'] for h in session.work.heads('review', current=True)}"),
        ("final_review_policy='advisory' if review_enabled else 'disabled'", "final_review_policy='advisory'"),
        ("    if not review_enabled:\n        receipt['final_review_status'] = 'SKIPPED'\n", '')])
    spec = {'format': '8agent-final-review-off-patch/1', 'patch': ID, 'files': {},
            'generation_change': False, 'code_serving_revision': None, 'onsite_verified': False}
    preimage = ROOT/'90_RUNTIME/handoffs'/ID/'preimage'
    for name, before in bases.items():
        current = (ROOT/name).read_bytes()
        for data, folder in ((before, preimage), (current, PATCH/'payload')):
            path = folder/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if name.endswith('.py'):
            ast.parse(before, feature_version=(3, 11))
            ast.parse(current, feature_version=(3, 11))
        else:
            json.loads(before); json.loads(current)
        spec['files'][name] = {'base_sha256': sha(before), 'new_sha256': sha(current)}
    (PATCH/'PATCH_MANIFEST.json').write_bytes(dump(spec))
    source = (PATCH.parent/'request_unlimited_20260928_r1/apply.py').read_text()
    source = source.replace("PATCH_ID = 'request-unlimited-20260928-r1'", "PATCH_ID = '"+ID+"'")
    source = source.replace('import argparse\n', 'import argparse\nimport ast\n')
    source = source.replace("        compile(payload, name, 'exec')", "        if name.endswith('.py'):\n            ast.parse(payload, feature_version=(3, 11))\n            compile(payload, name, 'exec')\n        else:\n            json.loads(payload)")
    source = source.replace("            if file not in spec['files'] and actual != expected:", "            if actual != expected:")
    insertion = '''    # Rebind explicit profile consumers without rewriting any data bindings.
    def profile_bindings(node):
        if isinstance(node, dict):
            name = node.get('path')
            if name in changes and 'sha256' in node:
                if node['sha256'] != sha(safe_path(root, name).read_bytes()):
                    raise ValueError('profile pin mismatch: ' + name)
                replacements[node['sha256']] = sha(changes[name])
            for child in node.values():
                profile_bindings(child)
        elif isinstance(node, list):
            for child in node:
                profile_bindings(child)
    profile_bindings(config)
'''
    source = source.replace('    for old, new in replacements.items():\n', insertion+'    for old, new in replacements.items():\n')
    source = source.replace("    parser.add_argument('--rollback-from', type=Path)\n", "    parser.add_argument('--rollback-from', type=Path)\n    parser.add_argument('--check-only', action='store_true')\n")
    source = source.replace("        changes = prepare(root, spec)\n", "        if spec.get('patch') != PATCH_ID: raise ValueError('patch ID mismatch')\n        changes = prepare(root, spec)\n")
    source = source.replace('        backup = None\n', "        if args.check_only:\n            output({'status': 'CHECK_PASS', 'changed_files': sorted(different), 'deploy_root': str(root)})\n            return\n        backup = None\n")
    (PATCH/'apply.py').write_text(source)
    (PATCH/'gate.py').write_bytes((ROOT/'06_TOOLS/COMMANDS/genos_release_gate.py').read_bytes())
    (PATCH/'README.txt').write_text('''GENOS 최종 답변 검토 OFF R1 (2026-09-28)
이 메일의 GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt를 사용하세요.
기존 ~/DEV Git checkout에 변경 파일 5개만 백업 후 적용하며 엔진/프로필 pin을 함께 갱신합니다.
현장에 이미 적용한 시간 설정·팀 로그·thinking·fulltext 진단 파일은 교체하지 않습니다.
메일 ZIP과 TXT를 같은 폴더에 저장하고 아래를 실행합니다.

bash GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt

기본 대상: ~/DEV. 다른 checkout이면 DEPLOY_ROOT=/실제/checkout 을 앞에 붙입니다.
로그의 BACKUP_READY 경로와 TRANSFER/final-review-disabled-20260928-r1/ 영수증을 보존하세요.
CHECK_PASS/APPLIED는 코드 적용 상태이며 배포 성공이 아닙니다.
지원된 변경 전/후 파일 해시만 허용합니다. 미지원 파일이나 기존 pin 불일치는 쓰기 전에 중단합니다.
중단한 경우 강제 덮어쓰지 말고 로그를 전달하세요.

적용 후 git diff와 changed_files를 확인해 해당 코드와 엔진/프로필/PIPELINE 파일만 commit합니다.
이 TXT는 자동 git add, commit, push, 플랫폼 배포를 하지 않습니다.
commit 후 MODE=verify bash GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt 를 실행합니다.
기존 설정/CURRENT에서 선택 generation을 확인해 같은 checkout에서 generation E2E/verify_assets를 실행합니다.
기존 설정을 찾지 못하면 GENOS_GENERATION=/실제/선택/generation 을 명시합니다. 새 generation 생성은 없습니다.
그 commit을 push하고 코드서빙 새 리비전이 같은 commit/generation을 선택하게 합니다.
워크플로우 Python 교체는 필요 없습니다. 확인은 워크플로우 테스트 화면의 새 질문으로 합니다.
응답 기록: final_review_policy=disabled, final_review_status=SKIPPED, claim_review_status=UNREVIEWED.
source-omission-review는 원문 선별 단계로 유지되며 최종 답변 검토만 꺼집니다.

원복: MODE=rollback ROLLBACK_FROM=/BACKUP_READY의/실제/경로 bash GENOS_FINAL_REVIEW_OFF_20260928_R1_APPLY.txt
원복 후 이전 commit/코드서빙 리비전 선택도 별도로 처리합니다.
로컬 MAIN 계약·회귀 312개 통과. 현장 적용/배포/실제 속도는 미확인입니다.
''')
    rows = []
    archive = PATCH.parent/(STEM+'.zip')
    assert not archive.exists(), archive
    paths = [PATCH/'apply.py', PATCH/'gate.py', PATCH/'PATCH_MANIFEST.json', PATCH/'README.txt']
    paths += sorted((PATCH/'payload').rglob('*'))
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            if not path.is_file(): continue
            name = path.relative_to(PATCH).as_posix()
            assert path.suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            raw = path.read_bytes()
            rows.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
            z.writestr(name, raw)
        z.writestr('CODE_MANIFEST.json', dump({'format': '8agent-code/1', 'patch': ID, 'files': rows}))
    shell = '''#!/usr/bin/env bash
set -Eeuo pipefail
RUN_LOG="$(mktemp "${TMPDIR:-/tmp}/genos-review-off-r1-XXXXXXXX.log")"
exec > >(tee -a "$RUN_LOG") 2>&1
trap 'result=$?; printf "FINISHED status=%s log=%s\\n" "$result" "$RUN_LOG"' EXIT
printf 'START patch=final-review-disabled-20260928-r1 log=%s\\n' "$RUN_LOG"
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/DEV}"
MODE="${MODE:-apply}"
[[ -d "$DEPLOY_ROOT/.git" || -f "$DEPLOY_ROOT/.git" ]] || { printf 'ERROR existing Git checkout required\\n'; exit 2; }
if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$DEPLOY_ROOT/.venv/bin/python" ]]; then PYTHON_BIN="$DEPLOY_ROOT/.venv/bin/python";
    else PYTHON_BIN="$(command -v python3 || true)"; fi
fi
[[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]] || { printf 'ERROR existing Python required\\n'; exit 2; }
mkdir -p "$DEPLOY_ROOT/TRANSFER"
PATCH_DIR="$(mktemp -d "$DEPLOY_ROOT/TRANSFER/final-review-off-r1-unpack-XXXXXXXX")"
PATCH_ZIP="$PATCH_DIR/package.zip"
base64 --decode > "$PATCH_ZIP" <<'REVIEW_OFF_PAYLOAD'
'''+base64.encodebytes(archive.read_bytes()).decode()+'''REVIEW_OFF_PAYLOAD
"$PYTHON_BIN" - "$PATCH_ZIP" "$PATCH_DIR" "'''+sha(archive.read_bytes())+'''" <<'VERIFY_REVIEW_OFF_PACKAGE'
import hashlib,json,sys,zipfile
from pathlib import Path,PurePosixPath
raw=Path(sys.argv[1]).read_bytes()
if hashlib.sha256(raw).hexdigest()!=sys.argv[3]:raise ValueError('ZIP SHA-256 mismatch')
with zipfile.ZipFile(sys.argv[1]) as z:
    names=z.namelist()
    if len(names)!=len(set(names)):raise ValueError('duplicate ZIP paths')
    manifest=json.loads(z.read('CODE_MANIFEST.json'))
    if manifest['format']!='8agent-code/1':raise ValueError('invalid manifest format')
    rows={r['path']:r for r in manifest['files']}
    if len(rows)!=len(manifest['files']) or set(names)!=set(rows)|{'CODE_MANIFEST.json'}:raise ValueError('ZIP inventory mismatch')
    for name,row in rows.items():
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\\\' in name or str(p)!=name:raise ValueError('unsafe ZIP path')
        if p.suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:raise ValueError('excluded JavaScript')
        data=z.read(name)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('ZIP member hash mismatch')
        target=Path(sys.argv[2])/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
print('PACKAGE_HASHES PASS')
VERIFY_REVIEW_OFF_PACKAGE
printf 'MODE=%s CHECKOUT=%s PYTHON=%s\\n' "$MODE" "$DEPLOY_ROOT" "$PYTHON_BIN"
case "$MODE" in
 check) "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT" --check-only ;;
 apply)
    "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT"
    git -C "$DEPLOY_ROOT" diff --check
    printf 'Review changed_files and commit them, then run MODE=verify with this TXT.\\n'
    ;;
 verify|code-only)
    GATE_ARGS=()
    [[ "$MODE" != code-only ]] || GATE_ARGS+=(--code-only)
    "$PYTHON_BIN" "$PATCH_DIR/gate.py" --code-zip "$DEPLOY_ROOT/TRANSFER/final-review-disabled-20260928-r1/applied-code.zip" --deploy-root "$DEPLOY_ROOT" "${GATE_ARGS[@]}"
    ;;
 rollback)
    : "${ROLLBACK_FROM:?Set ROLLBACK_FROM to the actual BACKUP_READY path}"
    "$PYTHON_BIN" "$PATCH_DIR/apply.py" --deploy-root "$DEPLOY_ROOT" --rollback-from "$ROLLBACK_FROM"
    git -C "$DEPLOY_ROOT" diff --check
    ;;
 *) printf 'ERROR MODE must be apply, check, verify, code-only or rollback\\n'; exit 2 ;;
esac
'''
    txt = PATCH.parent/(STEM+'_APPLY.txt')
    txt.write_text(shell)
    guide = PATCH.parent/(STEM+'_GUIDE.txt')
    guide.write_bytes((PATCH/'README.txt').read_bytes())
    files = [archive, txt, guide]
    sums = PATCH.parent/(STEM+'_SHA256SUMS.txt')
    sums.write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in files))
    files.append(sums)
    receipt = {'patch': ID, 'tested_code_root': str(ROOT), 'push_checkout': None, 'commit': None,
               'generation': None, 'generation_manifest_sha256': None, 'code_serving_revision': None,
               'onsite_verified': False, 'files': [{'name':p.name,'path':str(p),'bytes':p.stat().st_size,
                                                   'sha256':sha(p.read_bytes())} for p in files]}
    (PATCH/'BUILD_RECEIPT.json').write_bytes(dump(receipt))
    print(json.dumps({'zip_bytes': archive.stat().st_size, 'members': len(rows)+1,
                      'attachments': len(files), 'zip_sha256': sha(archive.read_bytes())}))


if __name__ == '__main__':
    build()
