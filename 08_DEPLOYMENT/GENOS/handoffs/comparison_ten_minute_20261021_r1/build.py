"""Seal the verified comparison fix over MAIN96 without unrelated replacements."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_COMPARISON_TEN_MINUTE_20261021_R1'
BASE = HERE.with_name('main96_ad_disabled_20261021_r1')
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261021-comparison-ten-minute'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


assert not (HERE / 'SEALED.json').exists(), 'Already sealed; use a new revision'
before = read(BASE / 'PACKAGE.json')['code']
verified = {row['path']: row['after_sha256'] for row in read(AUDIT / 'CHANGES.json')['files']}
for name, expected in verified.items():
    assert sha(ROOT / name) == expected, name
after = {name: sha(ROOT / name) for name in before}
new = '02_BACKEND/workflow/risk_team_compare_workflow/finalize.py'
after[new] = sha(ROOT / new)
patch = [name for name in after if before.get(name) != after[name]]
assert set(patch) - set(verified) == {'02_BACKEND/workflow/risk_team_compare_workflow/concept_report.py'}
partial = read(ROOT / '09_ARTIFACTS/AUDITS/20261021-comparison-partial-items/CHANGES.json')
# The concept report is the preceding, already verified partial-items fix.
concept = next(row for row in partial['changed_files'] if row['path'].endswith('/concept_report.py'))
assert sha(ROOT / concept['path']) == concept['after']
for name in patch:
    target = HERE / 'payload' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT / name).read_bytes())
    if name.endswith('.py'):
        ast.parse(target.read_bytes(), filename=name, feature_version=(3, 11))

(HERE / 'runner.py').write_bytes((BASE / 'runner.py').read_bytes())
(HERE / 'genos_release_gate.py').write_bytes((BASE / 'genos_release_gate.py').read_bytes())
run = (BASE / 'GENOS_MAIN96_AD_DISABLED_20261021_R1_RUN.txt').read_text()
run = run.replace('GENOS_MAIN96_AD_DISABLED_20261021_R1', NAME)
run = run.replace('main96-ad-disabled-r1-logs', 'comparison-ten-minute-r1-logs')
run = run.replace('MAIN96_AD_DISABLED_EXIT', 'COMPARISON_TEN_MINUTE_EXIT')
(HERE / (NAME + '_RUN.txt')).write_text(run)
subprocess.run(['bash', '-n', str(HERE / (NAME + '_RUN.txt'))], check=True)

manifest = {'format': '8agent-code/1',
            'files': [{'path': n, 'sha256': after[n], 'bytes': (ROOT / n).stat().st_size} for n in patch],
            'required_files': [{'path': n, 'sha256': h} for n, h in after.items() if n not in patch]}
save(HERE / 'CODE_MANIFEST.json', manifest)
with zipfile.ZipFile(HERE / 'code.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    archive.write(HERE / 'CODE_MANIFEST.json', 'CODE_MANIFEST.json')
    for name in patch:
        archive.write(ROOT / name, name)
(HERE / 'COMMIT_PATHS.txt').write_text('\n'.join(patch) + '\n')

(HERE / 'PATCH_NOTE.txt').write_text(f'''대사 workflow 1.20.4 — 10분 제한과 확보 근거로 답변 마무리

변경
- 전체 600초 안에서 탐색·항목 검토는 480초까지, 나머지 120초는 답변 작성·발행에 사용합니다.
- 모델 전체 24회, 자식 조사당 6회, 추가 조사 1회, 쟁점 검토 2차로 제한합니다. 더 작은 운영 한도는 유지합니다.
- 한도에 도달하면 검색을 끝내고 저장된 원문으로 답변을 작성합니다. 마지막 작성도 실패하면 기존 의견·정확 원문·미확인을 부분 답변으로 표시합니다.
- 대사 항목 일부가 빠졌다는 이유만으로 전체 결과를 버리지 않습니다. 인용·권한·버전·해시 검사는 유지합니다.
- 재개해도 최초 기한과 사용량은 초기화하지 않습니다. 원문이 없거나 무결성 검사가 실패하면 근거 있는 답변을 꾸미지 않습니다.

적용 대상
MAIN96_AD_DISABLED 적용 checkout에 추가합니다. 기존 STABLE_COMMANDS / BASIS_FIXED_LOCAL 명령 패치와 함께 사용할 수 있습니다.
MAIN95 본체나 관리자 비활성화 패치를 재설치하지 마세요. 이 ZIP은 데이터·.env·ignore·현장 경로·기존 명령 도구를 덮어쓰지 않습니다.
로컬 MAIN 선택은 바꾸지 않았습니다. 일반 RAG의 시간 설정은 이번 대사 정책과 별도입니다.

실제 업로드한 TRANSFER 폴더를 현재 위치로 두고 다음 순서로 실행하세요.
기존 Git checkout 기본 대상은 ~/DEV이며, 실제 경로가 다르면 모든 명령에 --root /실제/checkout 을 동일하게 지정합니다.
python3 -m zipfile -e ./{NAME}.zip ./{NAME}
bash ./{NAME}/{NAME}_RUN.txt check
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt gate

apply는 백업 후 기존 checkout에 코드만 적용합니다. 모르는 기존 코드나 설치 후 변경은 덮어쓰지 않습니다.
기존 checkout에서 COMMIT_PATHS.txt의 변경과 git diff --check를 확인하고 commit한 뒤 TRANSFER에서 실행합니다.
bash ./{NAME}/{NAME}_RUN.txt gate-code
현재 SQLite/NFS 운영이면 같은 checkout과 선택 세대까지 검사합니다. Oracle 모드에는 이 명령을 사용하지 않습니다.
bash ./{NAME}/{NAME}_RUN.txt gate-sqlite

PASS한 커밋을 push하고 동일 커밋으로 코드서빙 리비전을 배포한 뒤 워크플로우 테스트 화면에서 대사를 확인하세요.
워크플로우 Python 편집기 변경은 없습니다. 이전 MAIN95/96의 고정 코드 gate 대신 이번 gate를 사용합니다.
새 리비전의 요청 로그에서 WORKFLOW_EXECUTION_POLICY의 600초·24회, 마무리 상태, 최종 답변·출처를 확인하세요.
기존에 실행 중인 프로세스에는 자동 적용되지 않습니다. 옛 코드에 결속된 요청은 원래 코드로 보존하고 새 질의로 확인합니다.

재실행·확인·원복 (TRANSFER에서)
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt status
bash ./{NAME}/{NAME}_RUN.txt rollback
백업·INSTALL_STATE.json·로그를 보존하세요. 원복은 적용 직전 코드로 되돌리며 이후 배포도 별도로 원복해야 합니다.

검증과 한계
작업 코드의 합성 계약/API/service 소비자 145검사 통과, 실제 모델 호출 0입니다.
전달 ZIP의 검증 결과와 지문은 HANDOFF_VALIDATION.txt / CODE_MANIFEST.json을 함께 확인하세요.
GENOS 반입·Git push·코드서빙 리비전·실제 모델 품질·현장 10분 실측은 미확인입니다.
플랫폼 강제 종료까지 정확히 600초를 보장하는 것은 아닙니다. 저장 결과 재발행에는 기존의 별도 읽기 전용 창이 사용될 수 있습니다.
전체 입력 중복·스키마 크기 감사의 나머지 개선은 별도이며, 이번 패치는 종료와 답변 확보에 집중합니다.
''')
files = ['runner.py', 'genos_release_gate.py', NAME + '_RUN.txt', 'PATCH_NOTE.txt',
         'CODE_MANIFEST.json', 'COMMIT_PATHS.txt', 'code.zip'] + ['payload/' + n for n in patch]
if (HERE / 'HANDOFF_VALIDATION.txt').exists():
    files.append('HANDOFF_VALIDATION.txt')
save(HERE / 'PACKAGE.json', {'version': NAME, 'base_release': 'ad-management-disabled-20261021-r1',
     'code': after, 'patch': patch,
     'allowed_before': {n: list(dict.fromkeys([before.get(n), h])) for n, h in after.items()},
     'payload': {n: sha(HERE / n) for n in files}, 'workflow_version': '1.20.4',
     'GENOS_field_verified': False, 'data_modified': False, 'selected_main_modified': False})
with zipfile.ZipFile(HERE / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name in sorted(files + ['PACKAGE.json']):
        assert Path(name).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs')
        archive.write(HERE / name, name)
for archive_path in (HERE / (NAME + '.zip'), HERE / 'code.zip'):
    with zipfile.ZipFile(archive_path) as archive:
        assert not archive.testzip()
        assert not any(Path(n).suffix.lower() in ('.js', '.jsx', '.mjs', '.cjs') for n in archive.namelist())
save(HERE / 'BUILD.json', {'archive': NAME + '.zip', 'sha256': sha(HERE / (NAME + '.zip')),
     'bytes': (HERE / (NAME + '.zip')).stat().st_size, 'patch_files': len(patch),
     'required_code_files': len(after), 'source_root': str(ROOT),
     'code_manifest_sha256': sha(HERE / 'CODE_MANIFEST.json'),
     'selected_release': read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
     'GENOS_checkout': '~/DEV (physical path recorded by check)', 'GENOS_commit': None,
     'GENOS_generation_path': None, 'GENOS_generation_manifest_sha256': None,
     'GENOS_serving_revision': None, 'GENOS_revision_generation_setting': None})
(HERE / 'SHA256SUMS.txt').write_text('\n'.join(sha(HERE / n) + '  ' + n for n in
    [NAME + '.zip', NAME + '_RUN.txt', 'PATCH_NOTE.txt']) + '\n')
print((HERE / 'BUILD.json').read_text())
