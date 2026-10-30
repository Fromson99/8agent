from pathlib import Path
import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from materialize import materialize_code_zip

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
SOURCE = OUT.parent / 'main123_full_20261030_r1' / 'GENOS_MAIN123_FULL_20261030_R1.zip'
NAME = 'GENOS_MAIN123_FULL_OVERWRITE_20261030_R3'
RUN = NAME + '_RUN.txt'
FORBIDDEN = {'.js', '.jsx', '.mjs', '.cjs'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


assert sha(SOURCE.read_bytes()) == 'f6236b965ee5528e5130a79e277ec9b76e536be43bb8074ecaccceabd3d9f924'
with zipfile.ZipFile(SOURCE) as archive:
    selected_record = json.loads(archive.read('SELECTED_RELEASE_RECORD.json'))
    release = selected_record['release']
    prior_spec = json.loads(archive.read('PACKAGE.json'))
    binding = json.loads(archive.read('SOURCE_BINDING.json'))
    code = {name: archive.read('payload/' + name) for name in prior_spec['patch']}
    for name, expected in release['files'].items():
        raw = (ROOT / release['code_root'] / name).read_bytes()
        assert sha(raw) == expected, name
        if name in code:
            assert code[name] == raw, name
        code[name] = raw
    gate_raw = archive.read('genos_release_gate.py')
    results_raw = archive.read('MAIN123_RESULTS.txt')
assert len(code) == 492 and {p: sha(raw) for p, raw in code.items()} == prior_spec['code']
guide = f'''GENOS MAIN123 전체 덮어쓰기 R3

대상: GENOS 코드스페이스의 기존 ~/DEV. 이전 R1/R2 또는 과거 패치를 먼저 적용할 필요 없습니다.
첨부 {NAME}.zip, {RUN}, 이 GUIDE.txt를 실제 업로드 TRANSFER에 올립니다.
현재 작업 위치를 그 TRANSFER로 두고 터미널에서 아래 한 줄을 실행합니다.

bash ./{RUN}

사전 압축 해제와 폴더 이동 없이 ZIP 검증 → 준비 → 검사 → 원본 백업 → 492개 코드 덮어쓰기 → 전체 코드/엔진/워크플로우 해시 검증을 수행합니다.
선택 MAIN123의 489개 서빙 파일과 기존 인계 운영보조 3개를 포함합니다.
누락 파일, 옛 파일, 현장 수정본, 미추적 코드 대상까지 현재 상태를 백업한 뒤 교체합니다. 사진에서 불일치한 app.js도 포함됩니다.
메일 첨부 확장자 기준에 맞춰 app.js 본문은 ZIP 안에서 app.js.txt로 전달하고, 설치 시 원래 app.js 경로에 정확한 바이트로 복원합니다.
제품 코드 내용은 선택 MAIN123과 같습니다. DB/원문/세대/.env/가상환경/Git 이력/기존 반입 폴더와 대상 밖 파일은 덮어쓰지 않습니다.

완료 확인:
APPLIED MAIN123 FULL R3: all 492 code files verified; original files backed up
MAIN123_FULL_EXIT=0

백업/상태: 현재 TRANSFER/{NAME}/backup/ 및 INSTALL_STATE.json.
로그/종료코드: 현재 TRANSFER/main123-full-overwrite-r3-logs/.
이 폴더들은 원복에 필요하므로 보존합니다. 원래 R1/R2 폴더와 실패 로그도 그대로 남습니다.
중간에 끊겼으면 같은 명령을 다시 실행합니다. 기존 백업과 진행 상태를 읽어 before/after가 일치하는 파일만 이어갑니다.
설치 시작 이후 별도 수정, 패키지/백업 변조, 다른 DEV 대상은 자동 덮어쓰지 않고 중단합니다.
재실행 상태 조회: bash ./{RUN} status
검사만: bash ./{RUN} check
원복이 필요한 경우: bash ./{RUN} rollback
원복은 R3 실행 직전 코드 바이트를 복원합니다. 원복한 설치 상태를 새 설치로 초기화하지 않습니다.

Git commit/push, 코드서빙 리비전 배포, 워크플로우 편집기 반영은 별도입니다.
검토: git -C ~/DEV diff --check
검토: git -C ~/DEV diff --stat
{NAME}/COMMIT_PATHS.txt의 코드 파일 목록을 검토해 commit합니다. TRANSFER 전체를 git add하지 않습니다.
commit 후 게이트: bash ./{RUN} gate-code
NFS generation을 쓰는 환경에서만 기존 실제 선택 세대를 대상으로 별도 gate-sqlite 검증을 수행합니다.
해당 세대 경로/manifest 해시와 통과 commit을 기록한 뒤 push·새 코드서빙 리비전 배포를 수행합니다.
워크플로우 편집기는 패키지 안 GENOS_MAIN123_WORKFLOW_PASTE_ALL.txt 전체를 반영합니다.
실제 질문/웜업은 워크플로우 테스트 화면에서 수행하고 요청 ID/답변을 확인합니다.
현장 세대/리비전/실제 질문 성공은 여기서 확인한 것이 아닙니다.

필요할 때만 --root 실제_DEV경로를 명령 끝에 붙입니다. 기본값은 기존 ~/DEV이며 첫 검사 뒤 대상을 바꿀 수 없습니다.
이전 R1/R2 실행 안내 대신 이 R3 ZIP과 R3 실행 TXT를 함께 사용합니다.
MAIN123의 개발·실험 한계는 동봉 MAIN123_RESULTS.txt에 보존했습니다.
'''
with tempfile.TemporaryDirectory(prefix='main123-full-r3-build-') as temporary:
    package = Path(temporary)
    payload_paths = {}
    for name, raw in sorted(code.items()):
        if name.endswith('.py'):
            ast.parse(raw, filename=name, feature_version=(3, 11))
            compile(raw, name, 'exec')
        assert not {'.git', '.env', '.venv', '01_DATA', 'GENOS_DATA', 'TRANSFER'}.intersection(Path(name).parts)
        archive_path = 'payload/' + name + ('.txt' if Path(name).suffix.lower() in FORBIDDEN else '')
        payload_paths[name] = archive_path
        target = package / archive_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    manifest = {'format': '8agent-code/1', 'release_id': release['release_id'],
                'files': [{'path': p, 'sha256': sha(raw), 'bytes': len(raw)} for p, raw in sorted(code.items())],
                'required_files': []}
    (package / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    (package / 'COMMIT_PATHS.txt').write_text('\n'.join(sorted(code)) + '\n')
    (package / 'runner.py').write_bytes((OUT / 'runner.py').read_bytes())
    (package / 'genos_release_gate.py').write_bytes(gate_raw)
    (package / 'GENOS_MAIN123_WORKFLOW_PASTE_ALL.txt').write_bytes(code['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
    (package / 'SELECTED_RELEASE_RECORD.json').write_bytes(encoded(selected_record))
    (package / 'MAIN123_RESULTS.txt').write_bytes(results_raw)
    (package / 'GUIDE.txt').write_text(guide)
    binding['preserve_existing'] = {}
    binding['included_serving_files'] = len(release['files'])
    binding['source_r1_zip_sha256'] = sha(SOURCE.read_bytes())
    binding['overwrite_existing_authorized'] = True
    binding['transport_paths'] = {p: q for p, q in payload_paths.items() if q != 'payload/' + p}
    # The source binding records the immutable product; generated archive digest is separate.
    binding['previous_r1_code_zip_sha256'] = binding.pop('code_zip_sha256')
    (package / 'SOURCE_BINDING.json').write_bytes(encoded(binding))
    spec = {'version': NAME, 'code': {p: sha(raw) for p, raw in sorted(code.items())},
            'patch': sorted(code), 'payload_paths': payload_paths, 'overwrite_existing': True,
            'selected_release_id': release['release_id'], 'selected_main': 123,
            'field_deployment_verified': False}
    (package / 'PACKAGE.json').write_bytes(encoded(spec))
    materialize_code_zip(package)
    spec['payload'] = {p.relative_to(package).as_posix(): sha(p.read_bytes()) for p in sorted(package.rglob('*'))
                       if p.is_file() and p.name != 'PACKAGE.json'}
    spec_raw = encoded(spec)
    (package / 'PACKAGE.json').write_bytes(spec_raw)
    with zipfile.ZipFile(OUT / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sorted(package.rglob('*')):
            if p.is_file() and p.name != 'code.zip':
                relative = p.relative_to(package).as_posix()
                assert p.suffix.lower() not in FORBIDDEN and not relative.endswith('.zip')
                archive.write(p, relative)
    (OUT / 'EXPECTED_PACKAGE.json').write_bytes(spec_raw)
(OUT / 'GUIDE.txt').write_text(guide)
zip_sha = sha((OUT / (NAME + '.zip')).read_bytes())
bootstrap = (OUT / 'bootstrap.py').read_text().replace('__ZIP_SHA256__', zip_sha).replace('__SPEC_SHA256__', sha(spec_raw))
bootstrap = (OUT / 'materialize.py').read_text() + '\n' + bootstrap
compile(bootstrap, 'embedded_bootstrap.py', 'exec')
shell = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
TASK_LOG_DIR="$PWD/main123-full-overwrite-r3-logs"
if [[ -L "$TASK_LOG_DIR" ]]; then echo "Refuse symlink log folder" >&2; exit 2; fi
mkdir -p "$TASK_LOG_DIR"
TASK_LOG="$TASK_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$TASK_LOG") 2>&1
trap 'TASK_RC=$?; printf "%s\\n" "$TASK_RC" > "$TASK_LOG.exit"; echo "MAIN123_FULL_EXIT=$TASK_RC LOG=$TASK_LOG"' EXIT
python3 -u - "$@" <<'MAIN123_FULL_PY'
'''
(OUT / RUN).write_text(shell + bootstrap + '\nMAIN123_FULL_PY\n')
subprocess.run(['bash', '-n', str(OUT / RUN)], check=True)
record = {'main': 123, 'release_id': release['release_id'], 'serving_files': 489, 'code_files': len(code),
          'source_r1_zip_sha256': sha(SOURCE.read_bytes()), 'package_sha256': sha(spec_raw),
          'materialized_code_zip_sha256': spec['payload']['code.zip'],
          'product_changes_from_main123': 0, 'overwrite_authorized_by_user': True,
          'field_deployment_verified': False, 'attachments': []}
for name in [NAME + '.zip', RUN, 'GUIDE.txt']:
    p = OUT / name
    record['attachments'].append({'filename': name, 'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())})
(OUT / 'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps({'attachments': [{'filename': r['filename'], 'bytes': r['bytes']} for r in record['attachments']],
                  'code_files': len(code), 'no_prior_zip_required': True}))
