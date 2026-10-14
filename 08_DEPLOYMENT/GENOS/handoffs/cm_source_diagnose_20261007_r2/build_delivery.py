"""Seal MAIN-selected whole document identity inventory into an offline TXT."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_CM_SOURCE_DIAG_20261007_R2'
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from lawrag.platform.workspace import load_layout


def sha(path):
    fingerprint = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(4*1024*1024):
            fingerprint.update(chunk)
    return fingerprint.hexdigest()


def main():
    assert not (OUT/(NAME+'_RUN.txt')).exists(), 'Use a new revision after sealing'
    layout = load_layout(ROOT)
    # This creates an inspection inventory, not a runtime activation. Preserve
    # the existing activation receipt mismatch; inspect declared logical roots.
    active_path = layout.inspection_path('data', layout_version='v2')/'ACTIVE/local/ACTIVE_RELEASE.json'
    active = json.loads(active_path.read_bytes())
    release_path = ROOT/active['manifest_path']
    assert sha(release_path) == active['release_manifest_sha256']
    release = json.loads(release_path.read_bytes())
    generation = ROOT/release['data_path']
    manifest = json.loads((generation/'manifest.json').read_bytes())
    assert sha(generation/'manifest.json') == release['data_manifest_sha256']
    assert sha(generation/'store.sqlite') == manifest['store_sha256']
    db = sqlite3.connect((generation/'store.sqlite').resolve().as_uri()+'?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        documents = [dict(r) for r in db.execute(
            'SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY name,document_id')]
    finally:
        db.close()
    assert sorted(d['document_id'] for d in documents) == sorted(manifest['scope']['document_version_ids'])
    reference = {'schema_version': 'document-identity-inventory-v1',
                 'baseline': 'local MAIN-selected original source; no internal field-data assumption',
                 'active_release_id': active['release_id'], 'active_pointer_generation': active['generation'],
                 'active_pointer_sha256': sha(active_path), 'release_manifest_sha256': sha(release_path),
                 'generation_path': release['data_path'], 'generation_id': manifest['generation_id'],
                 'generation_manifest_sha256': sha(generation/'manifest.json'),
                 'store_sha256': manifest['store_sha256'], 'documents': documents}
    reference_text = json.dumps(reference, ensure_ascii=False, separators=(',', ':'))
    (OUT/'REFERENCE_INVENTORY.json').write_text(json.dumps(reference, ensure_ascii=False, indent=2)+'\n')
    code = (layout.inspection_path('tools', layout_version='v2')/'COMMANDS/genos_cm_source_diagnose.py').read_text()
    compile(code, 'genos_cm_source_diagnose.py', 'exec')
    script = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_transfer="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_reports="$task_transfer/cm-source-diag-r2"
mkdir -p -- "$task_reports"
task_output="$(mktemp -d "$task_reports/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
task_log="$task_output/DIAGNOSIS.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"' EXIT
printf '全 문서명·이름 무시 원본 SHA 읽기 전용 대조 시작 LOG=%s\\n' "$task_log"
python3 - "$task_transfer" "$task_output" <<'CM_SOURCE_DIAG_PY'
'''+f'import sys\nsys.argv.append({reference_text!r})\n'+code+'\nCM_SOURCE_DIAG_PY\n'
    run = OUT/(NAME+'_RUN.txt')
    run.write_text(script)
    subprocess.run(['bash', '-n', str(run)], check=True)
    guide = f'''전체 문서명·원본 SHA 대조 — 최종 진단 R2 (R1 대신 사용)

GENOS_CM_SOURCE_DIAG_20261007_R2_RUN.txt 하나를 기존 ~/DEV/TRANSFER에 올립니다.
아래 한 줄만 실행합니다. 별도 JSON·환경변수·팀·경로 입력은 없습니다.

bash ~/DEV/TRANSFER/GENOS_CM_SOURCE_DIAG_20261007_R2_RUN.txt

기준은 로컬 MAIN45가 선택한 전체 공개 원문 {len(documents)}개입니다.
GENOS에서는 R8과 같은 설정/manifest의 NFS 원문 전체를 읽어 양방향 비교합니다.
원문 DB 해시를 먼저 검증하며 진행 MiB와 실패 로그를 처음부터 남깁니다.

함께 확인하는 것:
1. 전체 문서명 일치 여부와 문서명+원본 SHA의 기존 엄격한 대조.
2. 문서명을 무시한 전체 원본 SHA 대조. 같은 원본인데 이름만 다르면 별도 표시.
3. 기준에 없는 현장 추가 문서, 기준 문서 누락, 해시 차이, 동일 원본 중복.
4. CM51 근거의21문서에 대해서도 이름 대조/이름 무시 SHA 대조를 각각 요약.

실행 마지막 요약을 보내주세요. 전수 상세 결과는 다음 폴더에 자동 저장합니다.
~/DEV/TRANSFER/cm-source-diag-r2/<실행별 폴더>/SOURCE_DIAGNOSIS.json
같은 폴더의 DIAGNOSIS.log에도 전체 차이 목록이 있습니다.

문서명은 표기 차이가 있을 수 있고, SHA가 다르면 같은 제목이어도 같은 원본으로
간주하지 않습니다. 이번 진단은 문서 정체성 대조이며 조문 본문/구조·판단 품질 전수 검사는 아닙니다.
로컬과 현장 선택 세대가 달라 현장에 추가 내부 문서가 있으면 그 차이를 따로 표시합니다.
코드·원문·기존 등록 DB·MAIN 포인터를 변경하지 않습니다. 모델 호출·등록·push·배포 없음.
앞서 준비한21문서 진단 R1 대신 이번 전체 진단 R2를 사용합니다.
'''
    guide_path = OUT/(NAME+'_GUIDE.txt')
    guide_path.write_text(guide)
    record = {'version': NAME, 'operation': 'READ_ONLY_WHOLE_DOCUMENT_IDENTITY_DIAGNOSIS',
              'reference_documents': len(documents), 'CM_documents': 21, 'CM_cases': 51,
              'reference_inventory_sha256': sha(OUT/'REFERENCE_INVENTORY.json'),
              'source_path': '06_TOOLS/COMMANDS/genos_cm_source_diagnose.py',
              'source_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'RUN_sha256': sha(run), 'model_calls': 0, 'GENOS_field_verified': False, 'email_sent': False,
              'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in (run, guide_path)]}
    (OUT/'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print('BUILT', len(documents), 'reference documents;', run.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
