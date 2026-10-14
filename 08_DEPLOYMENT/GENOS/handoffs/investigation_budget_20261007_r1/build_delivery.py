"""Build a small exact-fragment ZIP and a complete independent Bash TXT."""
import ast
import base64
import hashlib
import html
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_INVESTIGATION_BUDGET_20261007_R1'
SETTINGS = ['GENOS_RAG_MAX_MODEL_ATTEMPTS', 'GENOS_RAG_MAX_TOOL_ACTIONS', 'GENOS_RAG_WALL_SECONDS',
            'GENOS_RAG_SEARCH_ROUNDS', 'GENOS_RAG_ASSESSMENT_REENTRY_LIMIT']
sha = lambda raw: hashlib.sha256(raw).hexdigest()
dump = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    archive = OUT / (NAME + '.zip')
    if archive.exists():
        raise FileExistsError('Preserve published ZIP; create a new revision')
    source = (ROOT / 'service.py').read_text()
    helpers = source[source.index('def _investigation_profile('):source.index('def _genos_v5_environment_binding(')]
    helper_anchor = 'def _genos_v5_environment_binding(request_profile=None):\n'
    app_before = '        _APP = create_app(\n'
    app_start = source.index("        if selected_implementation in ('legal-agent-tools-v5', 'legal-agent-unified-v6'):")
    app_after = source[app_start:source.index(app_before, app_start)] + app_before
    call_before = '''    configured_profile = profile(_genos_v5_wait_profile({**request_profile, "model_binding": model_binding,
                                  "max_output_tokens": output_tokens}), require_model=True)
'''
    call_after = '''    configured_profile = profile(_investigation_profile(_genos_v5_wait_profile(
        {**request_profile, "model_binding": model_binding, "max_output_tokens": output_tokens})),
        require_model=True)
'''
    operations = [
        {'name': 'operator helpers', 'before': helper_anchor, 'after': helpers + helper_anchor},
        {'name': 'GENOS environment profile', 'before': call_before, 'after': call_after},
        {'name': 'common local/GENOS application binding', 'before': app_before, 'after': app_after},
    ]
    assert all(source.count(op['after']) == 1 for op in operations)
    spec = {'revision': NAME, 'settings': SETTINGS, 'operations': operations,
            'source_service_sha256': sha(source.encode()), 'requires_rebuilt_generation': False,
            'modified_checkout_paths': ['service.py', 'CODE_MANIFEST.json']}
    (OUT / 'PATCH_SPEC.json').write_bytes(dump(spec))
    code = (OUT / 'install_budget.py').read_bytes()
    ast.parse(code, feature_version=(3, 11))
    packed = dump({'code': base64.b64encode(code).decode(), 'spec': spec})
    compressed = base64.b64encode(zlib.compress(packed, 9)).decode()
    runner = f'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BUDGET_LOG_ROOT="${{GENOS_BUDGET_LOG_ROOT:-${{TMPDIR:-/tmp}}/8-agent-investigation-budget}}"
BUDGET_RUN_DIR="$BUDGET_LOG_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BUDGET_RUN_DIR"
exec > >(tee -a "$BUDGET_RUN_DIR/RUN.log") 2>&1
budget_exit() {{
  BUDGET_EXIT=$?
  trap - EXIT
  printf '{{"exit_code":%s,"field_deployed":false}}\\n' "$BUDGET_EXIT" > "$BUDGET_RUN_DIR/EXIT_STATUS.json"
  printf 'EXIT=%s; RUN_DIR=%s\\n' "$BUDGET_EXIT" "$BUDGET_RUN_DIR"
  exit "$BUDGET_EXIT"
}}
trap budget_exit EXIT
printf 'RUN_DIR=%s\\n' "$BUDGET_RUN_DIR"
python3 - "$@" <<'BUDGET_PY'
import base64, hashlib, json, sys, types, zlib
raw = zlib.decompress(base64.b64decode({compressed!r}))
if hashlib.sha256(raw).hexdigest() != {sha(packed)!r}:
    raise ValueError('Embedded installer hash mismatch')
bundle = json.loads(raw)
code = base64.b64decode(bundle['code'])
if hashlib.sha256(code).hexdigest() != {sha(code)!r}:
    raise ValueError('Embedded Python hash mismatch')
module = types.ModuleType('budget_install')
module.__file__ = 'embedded-budget-install.py'
exec(compile(code, module.__file__, 'exec'), module.__dict__)
try:
    raise SystemExit(module.main(bundle['spec'], sys.argv[1:]))
except Exception as exc:
    print('BUDGET_INSTALL FAILED: ' + str(exc), file=sys.stderr, flush=True)
    raise SystemExit(1)
BUDGET_PY
'''.encode()
    run_name = NAME + '_RUN.txt'
    (OUT / run_name).write_bytes(runner)
    subprocess.run(['bash', '-n', str(OUT / run_name)], check=True)
    guide = f'''조사 한도 설정 R1 — 기존 DEV에 부분 적용

변경 직전 로컬 MAIN45: 모델 총 40회, 최종 판단 예약 3회, 조사 최대 37회.
이번 변경은 기본 횟수를 늘리지 않고 서비스 환경 설정으로 변경하도록 연결합니다.
더 이전 v5 초기 기본값은 총 14회였습니다. GENOS 현장 실제 적용값은 미확인입니다.
신규 설정 계약 27개와 실제 로컬 MAIN 서비스 HEALTH를 확인했습니다.

1. ZIP을 기존 ~/DEV/TRANSFER에 올리고 코드스페이스에서 해제합니다.
   ZIP 안의 실행 TXT와 별도 첨부 실행 TXT는 같은 바이트입니다.

cd ~/DEV
python3 -m zipfile -e TRANSFER/{NAME}.zip TRANSFER/{NAME}
(cd TRANSFER/{NAME} && sha256sum -c SHA256SUMS.txt)
bash TRANSFER/{NAME}/{run_name} check
bash TRANSFER/{NAME}/{run_name} apply
bash TRANSFER/{NAME}/{run_name} verify

기본 DEV 선택: GENOS_DEV_ROOT, GENOS_DEV, ~/DEV 순서. DEV 루트 링크는 실제 checkout으로
해결합니다. 기존 CODE_MANIFEST의 모든 코드와 엔진 등록/코드/포트/스키마 해시를 검사한
뒤 service.py의 세 변경 부분과 CODE_MANIFEST만 갱신합니다. 원문/색인/generation/CURRENT,
세션 DB, 기존 시스템 로그/캐시/데이터 경로/워크플로우 코드는 보존합니다.
변경 fragment가 다르거나 이미 다른 코드 수정이 있으면 그 상태를 덮어쓰지 않습니다.
같은 apply 재실행은 설치된 코드 해시를 확인하고 ALREADY_APPLIED로 끝납니다.
첫 단계부터 RUN_DIR/RUN.log와 EXIT_STATUS.json을 남깁니다.
apply가 출력한 BACKUP=... 경로를 보관합니다. 백업에는 두 변경 파일의 원본/결과 해시,
실제 Python/코드 루트/commit/선택 generation(확인 가능한 경우)/리비전 값을 기록합니다.

2. 출력한 BACKUP 경로를 아래 <BACKUP 경로>에 넣고 같은 checkout을 검토·commit·검증합니다.
   다른 작업의 변경을 함께 commit하지 않습니다. 새 Git remote를 임의로 만들지 않습니다.

cd ~/DEV
git diff --check
git diff -- service.py CODE_MANIFEST.json
git add -- service.py CODE_MANIFEST.json
git commit -m "Make investigation budgets configurable"
bash TRANSFER/{NAME}/{run_name} gate "<BACKUP 경로>"
git push

gate는 설치 결과 APPLIED_CODE.zip과 commit한 checkout을 전수 비교하고 같은 Python 및
checkout의 02_BACKEND로 기존 선택 generation E2E와 verify_assets를 실행합니다.
기존 경로 설정/환경/.env/CURRENT/검증 영수증을 재사용합니다. 선택 경로가 없으면
추정하지 않고 중단합니다. 실제 코드서빙이 사용 중인 generation 절대경로를 아는 경우:
bash TRANSFER/{NAME}/{run_name} gate "<BACKUP 경로>" --generation "<현재 generation 절대경로>"
stage/commit 전에 기존 staged 변경이 있는지도 확인하고, 현재 branch/upstream을 유지하세요.
코드 적용, commit, gate, push와 코드서빙 리비전/환경 저장/워크플로우 결과는 각각 별도입니다.

3. gate를 통과한 commit으로 새 코드서빙 리비전을 배포합니다. 기존 LLM/인증/문서 접근
   설정을 유지하며 리비전의 환경 설정에서 필요한 한도만 등록합니다. 다음은 현재 기본값:

GENOS_RAG_MAX_MODEL_ATTEMPTS=40
GENOS_RAG_MAX_TOOL_ACTIONS=1024
GENOS_RAG_WALL_SECONDS=1800
GENOS_RAG_SEARCH_ROUNDS=8
GENOS_RAG_ASSESSMENT_REENTRY_LIMIT=2

예: 모델 총량 60으로 설정하면 최종 판단 3회를 예약하고 조사 최대 57회입니다.
MAX_MODEL_ATTEMPTS는 검색만의 횟수가 아니라 INTENT/PLAN/조사/수정/재시도/최종 판단
전체 물리 모델 시도 총량입니다. 빈 설정은 선택 프로필 기본값을 유지합니다.
모델 총량은 finalization_reserve보다 크고, 도구 총량은 tool_finalization_reserve보다 커야
합니다. 재조사만 0을 허용하며 나머지 값은 양의 정수입니다.
service 환경 설정을 저장하고 재시작하면 새 요청부터 적용합니다. 이 TXT 실행은 리비전의
환경변수를 자동 저장하지 않습니다. .env.example도 서비스가 자동 읽는 파일이 아닙니다.
워크플로우는 이 조사 설정 변경으로 편집할 필요가 없습니다. 기존 Python 단계를 유지합니다.

4. 워크플로우 테스트 화면에서 HEALTH 요청을 통해 응답 release.investigation_budget과
   effective_profile_sha256/service_entry_sha256을 확인하고, 실제 근거 질문으로 요청 ID와
   결과를 보관합니다. 코드서빙 직접 테스트 화면/API로 질의를 실행하지 않습니다.
   JSON HEALTH 요청: {{"API_TYPE":"HEALTH"}}
기존 워크플로우 단계가 API_TYPE을 고정한다면 그 화면의 기존 제어 요청 전달 방법을 사용하거나
실제 질문 로그의 runtime.investigation_budget과 binding을 확인합니다.
같은 미완료 request ID의 재개는 이전 소비량·deadline·binding을 유지합니다.
설정을 바꾼 뒤 새 예산이 필요하면 새 요청 ID를 사용합니다.

5. 코드 원복은 apply에서 출력한 같은 BACKUP 경로를 사용합니다.
bash TRANSFER/{NAME}/{run_name} undo "<BACKUP 경로>"
이미 push/배포했다면 복구된 두 파일만 별도 commit·push하고 이전 검증 리비전과 원래 환경
설정으로 복귀합니다. 이후 다른 코드가 바뀌었으면 자동 원복은 보존을 위해 거절합니다.

신규 로컬 계약 27개는 PASS. 기존 전체 회귀의 workspace activation receipt hash 차이와
폐기된 입력 byte limit 기대값 실패는 LOCAL_VERIFICATION.json에 별도 보존했습니다.
이메일 발송과 GENOS apply/push/리비전/환경/실제 내부 질문 성공은 별도이며, 현장 성공은
사용자가 실행 결과를 확인하기 전 미확인입니다. 원문/질문/인증키는 ZIP에 포함하지 않습니다.
'''.encode()
    guide_name = NAME + '_GUIDE.txt'
    members = {'install_budget.py': code, 'PATCH_SPEC.json': dump(spec), run_name: runner,
        guide_name: guide, 'BUDGET_ENV.txt': (OUT / 'BUDGET_ENV.txt').read_bytes(),
        'LOCAL_VERIFICATION.json': (ROOT / '09_ARTIFACTS/VERIFICATION/investigation-budget-settings-20261007/VALIDATION.json').read_bytes()}
    manifest = {'format': '8agent-code/1', 'id': NAME,
        'scope': 'partial service installer; field applied-code ZIP generated from actual DEV inventory',
        'files': [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(members.items())],
        'field_commit': None, 'code_serving_revision': None, 'field_deployed': False}
    members['CODE_MANIFEST.json'] = dump(manifest)
    members['SHA256SUMS.txt'] = ''.join(f'{sha(raw)}  {name}\n' for name, raw in sorted(members.items())).encode()
    for name, raw in members.items():
        assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
        (OUT / name).write_bytes(raw)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for name, raw in sorted(members.items()):
            zipped.writestr(name, raw)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None and set(zipped.namelist()) == set(members)
        assert all(zipped.read(name) == raw for name, raw in members.items())
    attachments = [archive, OUT / run_name, OUT / guide_name]
    body = f'''<p>요청하신 조사 한도 설정 R1을 보냅니다.</p>
<p><b>변경 직전에도 모델 총 40회였습니다.</b> 최종 판단 3회를 남겨 조사에는 최대 37회를 씁니다.
이번에는 기본 횟수를 유지하고 환경 설정으로 바꿀 수 있게 연결했습니다. 더 이전 v5 초기 기본값은 총 14회였습니다.</p>
<p>첨부는 <b>패치 ZIP + 별도 전체 실행 TXT + 안내 TXT</b>입니다. 기존 DEV에서 service.py의 변경 부분과
CODE_MANIFEST만 반영하며 원문·세대·세션·기존 캐시/로그를 유지합니다.</p>
<pre>cd ~/DEV
python3 -m zipfile -e TRANSFER/{NAME}.zip TRANSFER/{NAME}
(cd TRANSFER/{NAME} &amp;&amp; sha256sum -c SHA256SUMS.txt)
bash TRANSFER/{NAME}/{run_name} check
bash TRANSFER/{NAME}/{run_name} apply
bash TRANSFER/{NAME}/{run_name} verify</pre>
<p>apply의 BACKUP 경로를 보관하세요. 안내 TXT에 같은 checkout의 commit → generation gate → 기존 remote push →
새 리비전 배포 → 환경 설정 → 워크플로우 테스트 → 원복 순서를 넣었습니다. 현장 실행은 python3입니다.</p>
<pre>GENOS_RAG_MAX_MODEL_ATTEMPTS=40
GENOS_RAG_MAX_TOOL_ACTIONS=1024
GENOS_RAG_WALL_SECONDS=1800
GENOS_RAG_SEARCH_ROUNDS=8
GENOS_RAG_ASSESSMENT_REENTRY_LIMIT=2</pre>
<p>예를 들어 모델 총량을 60으로 등록하면 조사 상한은 57회입니다. 서비스 환경 설정을 저장하고 재시작하면
새 요청부터 적용됩니다. HEALTH의 release.investigation_budget에서 실제 값을 확인합니다.</p>
<p>신규 설정 계약 27개와 실제 로컬 MAIN 서비스 확인을 완료했습니다. 기존 회귀 일부의 환경/폐기 설정 불일치는
ZIP 안 LOCAL_VERIFICATION.json에 별도로 남겼습니다. GENOS 현장 적용·리비전·내부 질문 성공은 미확인입니다.</p>'''
    request = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[8-AGENT] 조사 한도 설정 R1 — 기존 총 40회 유지, ZIP + 실행 TXT',
        'payload': {'mime_type': 'multipart/mixed', 'parts': [
            {'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}},
            *[{'mime_type': 'application/zip' if p.suffix == '.zip' else 'text/plain',
               'charset': None if p.suffix == '.zip' else 'UTF-8',
               'filename': p.name, 'content_disposition': 'attachment',
               'body': {'base64_url_content': base64.urlsafe_b64encode(p.read_bytes()).decode()}}
              for p in attachments]]}}
    (OUT / 'EMAIL_REQUEST.json').write_bytes(dump(request))
    handoff = {'version': NAME, 'zip_sha256': sha(archive.read_bytes()),
        'code_manifest_sha256': sha(members['CODE_MANIFEST.json']),
        'zip_members': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in members.items()},
        'attachments': [{'filename': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in attachments],
        'javascript_excluded': True, 'field_commit': None, 'code_serving_revision': None,
        'generation': None, 'generation_manifest_sha256': None,
        'default_model_attempts_changed': False, 'local_main_pointer_changed': False, 'genos_deployed': False}
    (OUT / 'HANDOFF.json').write_bytes(dump(handoff))
    print(json.dumps({'version': NAME, 'zip_bytes': archive.stat().st_size,
        'zip_sha256': handoff['zip_sha256'], 'attachment_names': [p.name for p in attachments]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
