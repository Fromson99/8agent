"""Build one self-contained Samsung TXT with only reference-stage code."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import textwrap
import zlib


ROOT = Path(__file__).resolve().parents[2]
STEM = 'GENOS_REFERENCE_MAIN_AUTO_20260929_R1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def functions(path, names):
    text = path.read_text()
    nodes = {node.name: node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}
    return {name: ast.get_source_segment(text, nodes[name]) for name in names}


def build():
    from lawrag.platform.workspace import load_layout
    layout = load_layout(ROOT)
    folder = layout.path('deployment') / 'GENOS/patches/reference_main_20260929_r1'
    folder.mkdir(parents=True, exist_ok=True)
    files = [
        '02_BACKEND/lawrag/pipeline/reference_resolution.py',
        '02_BACKEND/semantic_runtime/reference_resolution_repository.py',
        '02_BACKEND/semantic_runtime/reference_resolution_protocol.py',
        '00_SYSTEM/SCHEMAS/reference-resolution-v1.schema.json',
        '06_TOOLS/COMMANDS/composed_build.py',
    ]
    spec = {'patch': 'reference-main-20260929-r1', 'files': {}, 'functions': {}}
    for name in files:
        raw = (ROOT / name).read_bytes()
        spec['files'][name] = {'text': raw.decode(), 'sha256': sha(raw)}
    name = '02_BACKEND/lawrag/pipeline/document_release.py'
    spec['functions'][name] = functions(ROOT / name, ['build', 'main', 'recorded_status',
                                                     'verify_release', '_copy_reference_audit', '_verify_navigation_audit'])
    spec['reference_targets'] = functions(ROOT / '02_BACKEND/semantic_runtime/term_references.py', ['reference_targets'])['reference_targets']
    spec['pipeline_route'] = '''if __name__ == '__main__' and sys.argv[1:2] == ['reference-resolution']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.reference_resolution import main
    raise SystemExit(main(sys.argv[2:]))'''
    payload = base64.b64encode(zlib.compress(json.dumps(spec, ensure_ascii=False).encode(), 9)).decode()
    installer = (ROOT / '06_TOOLS/OFFLINE/reference_genos_handoff.py').read_text()
    payload_hash = sha(payload.encode())
    installer_hash = sha(installer.encode())
    header = '''#!/usr/bin/env bash
# GENOS 참조 LLM 자동 승인 MAIN 배선 — 2026-09-29 R1
# 이 TXT 하나만 TRANSFER에 저장합니다. 별도 ZIP/Python 파일은 필요 없습니다.
# 코드 적용(기본): bash TRANSFER/GENOS_REFERENCE_MAIN_AUTO_20260929_R1.txt
# 기존 세대의 모호한 참조 처리/새 후보 생성:
#   bash TRANSFER/GENOS_REFERENCE_MAIN_AUTO_20260929_R1.txt run /실제/generation
# GENOS_GENERATION 또는 GENOS_DATA_ROOT/CURRENT가 있으면 run 뒤 경로 생략 가능.
# 이미 구조화한 범위의 통합 구축:
#   bash TRANSFER/GENOS_REFERENCE_MAIN_AUTO_20260929_R1.txt build 실제_RUN_ID [기존 build 옵션]
# RAW부터 전체 구축:
#   bash TRANSFER/GENOS_REFERENCE_MAIN_AUTO_20260929_R1.txt all 새로운_RUN_ID [기존 build-all 옵션]
# 상태: bash 같은TXT status /실제/generation
# 코드 원복: bash 같은TXT rollback /실제/백업/receipt.json
# 현장 입력: 기존 GENOS_LLM_URL 또는 GENOS_BASE_URL+GENOS_LLM_SERVING_ID, GENOS_LLM_KEY.
# 내부 모델이 복수이면 GENOS_LLM_MODEL에 현장의 실제 모델 ID를 지정합니다.
# 현장 .env와 기존 설정을 읽으며 인증키/내부 데이터는 첨부에 포함되지 않습니다.
# 내부 LLM을 사용합니다. 외부 Qwen3.8 시험 모델이 GENOS에 설치되었다고 가정하지 않습니다.
# 모든 유효한 모델 선택 자동 승인, 기권 UNKNOWN. 실패 사례 차단 규칙 추가 없음.
# apply는 코드 적용/문법/import 검증만 수행합니다. run/build/all에서 실제 모델을 호출합니다.
# build/all의 기존 용어집 검토 절차는 유지하고, 이번 참조 단계는 사람 승인을 기다리지 않습니다.
# exit 3이면 실행량 제한/보류 상태입니다. 같은 입력/코드/run ID로 재개합니다.
# 원문/완료 generation/CURRENT/워크플로우/코드서빙 리비전/Git push는 자동 변경하지 않습니다.
# 새 서빙 후보를 사용하려면 공유 NFS 발행과 해당 리비전의 GENOS_GENERATION 변경이 별도입니다.
# 최종 현장 질의는 워크플로우 테스트 화면에서 확인합니다.
set -Eeuo pipefail
REFERENCE_LOG="$(mktemp /tmp/genos-reference-main-r1-XXXXXX.log)"
exec > >(tee -a "$REFERENCE_LOG") 2>&1
trap 'REFERENCE_EXIT=$?; trap - EXIT; printf "GENOS_REFERENCE_EXIT=%s LOG=%s\\n" "$REFERENCE_EXIT" "$REFERENCE_LOG"; exit "$REFERENCE_EXIT"' EXIT
printf 'GENOS_REFERENCE_START LOG=%s\\n' "$REFERENCE_LOG"
REFERENCE_ROOT="${DEPLOY_ROOT:-}"
if [[ -z "$REFERENCE_ROOT" ]]; then
  REFERENCE_ROOT="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -z "$REFERENCE_ROOT" ]]; then REFERENCE_ROOT="$HOME/DEV"; fi
fi
REFERENCE_ROOT="$(git -C "$REFERENCE_ROOT" rev-parse --show-toplevel)"
REFERENCE_ROOT="$(cd -P "$REFERENCE_ROOT" && pwd -P)"
REFERENCE_PYTHON="${GENOS_PYTHON:-}"
if [[ -z "$REFERENCE_PYTHON" ]]; then
  if [[ -x "$REFERENCE_ROOT/.venv/bin/python" ]]; then REFERENCE_PYTHON="$REFERENCE_ROOT/.venv/bin/python";
  else REFERENCE_PYTHON="$(command -v python3)"; fi
fi
REFERENCE_TEMP="$(mktemp -d /tmp/genos-reference-main-payload-XXXXXX)"
cat > "$REFERENCE_TEMP/payload.b64" <<'REFERENCE_CODE_PAYLOAD'
'''
    tail = "\nREFERENCE_CODE_PAYLOAD\ncat > \"$REFERENCE_TEMP/apply.py\" <<'REFERENCE_INSTALLER'\n" + installer + "\nREFERENCE_INSTALLER\n"
    tail += '''"$REFERENCE_PYTHON" - "$REFERENCE_TEMP" <<'REFERENCE_VERIFY'
import hashlib,sys
from pathlib import Path
folder=Path(sys.argv[1])
for name,expected in [('payload.b64','PAYLOAD_HASH'),('apply.py','INSTALLER_HASH')]:
    raw=(folder/name).read_bytes().rstrip(b'\\n') if name=='payload.b64' else (folder/name).read_bytes()
    if name=='apply.py': raw=raw.rstrip(b'\\n')+b'\\n'
    if hashlib.sha256(raw).hexdigest()!=expected: raise SystemExit('Embedded TXT hash mismatch: '+name)
print('EMBEDDED_CODE_HASH_PASS')
REFERENCE_VERIFY
REFERENCE_MODE="${1:-apply}"
if [[ $# -gt 0 ]]; then shift; fi
"$REFERENCE_PYTHON" -B "$REFERENCE_TEMP/apply.py" --root "$REFERENCE_ROOT" --payload "$REFERENCE_TEMP/payload.b64" "$REFERENCE_MODE" "$@"
'''.replace('PAYLOAD_HASH', payload_hash).replace('INSTALLER_HASH', installer_hash)
    script = header + '\n'.join(textwrap.wrap(payload, 96)) + tail
    # Payload hash covers the folded text exactly as stored in the heredoc.
    folded = '\n'.join(textwrap.wrap(payload, 96))
    script = script.replace(payload_hash, sha(folded.encode()))
    target = folder.parent / (STEM + '.txt')
    if target.exists() and target.read_text() != script:
        raise ValueError('Preserve an existing delivery revision; use a new version')
    target.write_text(script)
    (folder / 'PAYLOAD_MANIFEST.json').write_text(json.dumps({**spec, 'files': {p: {'sha256':v['sha256'],'bytes':len(v['text'].encode())} for p,v in spec['files'].items()},
                                                            'functions': {p:list(v) for p,v in spec['functions'].items()}}, ensure_ascii=False, indent=2)+'\n')
    receipt = {'patch': spec['patch'], 'attachment': str(target), 'txt_sha256': sha(target.read_bytes()),
               'bytes': target.stat().st_size, 'installer_sha256': installer_hash,
               'code_root':str(ROOT), 'git_commit':None, 'code_serving_revision':None,
               'selected_generation':None, 'onsite_verified':False, 'live_model_calls_local':0,
               'javascript_members':[], 'credential_files':[], 'openrouter_configuration_included':False}
    (folder / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    build()
