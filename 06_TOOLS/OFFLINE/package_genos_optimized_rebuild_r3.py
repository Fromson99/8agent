"""Strict, documented migration from a retained pre-audit GENOS code delivery."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
R2_OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r2'
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r3'
STEM = 'GENOS_PIPELINE_OPTIMIZATION_20261002_R3'
PREVIOUS = R2_OUT / 'GENOS_PIPELINE_OPTIMIZATION_20261002_R2.zip'
PREVIOUS_SHA = '9d9e2cfc9aa66632aee8167b9048764861b08287dd547647d8c6bb3b5e128509'
LEGACY = ROOT / '90_RUNTIME/OUT/ship/timeout-20260928-r2/8agent-genos-timeout-sync-20260928-r2.zip'
LEGACY_FILES = {
    '02_BACKEND/lawrag/pipeline/term_generation.py': 'ceab4c33a2b8acde9b38d1a119f7040f75132639e63b910a178ab0ee1d23b885',
    '02_BACKEND/semantic_runtime/term_index.py': '59a198b619c743c0f0ec2ee8150d319ce8e291c27cf7f99791963bd52df1c5b3',
    '02_BACKEND/semantic_runtime/fulltext.py': '8c812c64a39462fccb4628a079963606047d603964654f1f42931df130a5ee26',
}

spec = importlib.util.spec_from_file_location('optimization_r2_packager', Path(__file__).with_name('package_genos_optimized_rebuild_r2.py'))
r2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r2)
INTRO = '''GENOS 최적화 OFF 재구축 R3 — 알려진 감사 분리 전 코드의 이행

사진의 R2는 기존 worker 중단 뒤 code-preflight에서 term_generation.py FILE_DRIFT로 종료했습니다.
코드·준비본에 파일 적용은 없었습니다. 예전 worker는 종료됐으므로 자동 재개되지는 않습니다.
R2의 허용 predecessor는 감사 DB 분리 후 버전만 포함했습니다. 이전 전달 ZIP에서 그 전 버전의
term_generation.py/term_index.py/fulltext.py를 확인했으며 R3는 검증한 세 해시만 추가로 허용합니다.
현장 파일의 실제 해시는 사진에 없어 동일 버전이라고 확정하지 않습니다. 실제 일치는 현장 검사로 결정합니다.
기존 해시를 새 값으로 고쳐 통과시키거나 임의 다른 코드 버전을 허용하지 않습니다.

이번에는 새 R3 ZIP/TXT를 함께 ~/DEV/TRANSFER에 올리고 다음을 실행하세요:
  cd ~/DEV
  export GENOS_PREPARED_RUN=financial-risk-success-20261001-r3
  export GENOS_OPTIMIZED_RUN=financial-risk-success-20261002-opt-r3
  bash TRANSFER/GENOS_PIPELINE_OPTIMIZATION_20261002_R3.txt

R3는 코드 사전 검사를 worker 중단보다 먼저 합니다. 알 수 없는 버전이면 코드/worker를 바꾸지 않습니다.
실제 파일 해시를 모두 출력하고 field-code-preflight.json에 기록합니다.
여전히 FILE_DRIFT면 로그의 FIELD DRIFT DIAGNOSTIC ZIP 경로에 있는 ZIP을 이 대화에 첨부하세요.
그 ZIP에는 불일치한 코드 파일과 차이만 들어 있으며 RAW/구조화 DB/용어집/검토 원장/.env는 포함하지 않습니다.
검토할 현장 코드가 없으면 예외를 넓혀 강제로 덮어쓰지 않습니다.
R1/R2 ZIP/TXT와 원래 준비본·계획·검토 원장·실패 scratch는 보관합니다.

아래는 기존 준비본 재사용/OFF/지속 로그/공유 발행 안내입니다. 이번 실행은 R3 기본 새 run을 사용하세요.

'''
GUIDE = INTRO + r2.GUIDE.replace('재구축 R2 /', '재구축 R3 /').replace('이 R2 ZIP/TXT', '이 R3 ZIP/TXT').replace(
    'GENOS_PIPELINE_OPTIMIZATION_20261002_R2', STEM).replace('financial-risk-success-20261002-opt-r2',
    'financial-risk-success-20261002-opt-r3').replace('optimized-rebuild-r2', 'optimized-rebuild-r3').replace(
    '순서: 지속 로그 시작 → 기록된 이전 worker만 SIGINT·종료 확인 → checkout hash 검사 →',
    '순서: 지속 로그 시작 → checkout hash 검사 → 기록된 이전 worker만 SIGINT·종료 확인 →')


def script(zip_sha):
    value = r2.SCRIPT.replace('__STEM__', STEM).replace('__ZIP_SHA__', zip_sha)
    value = value.replace('financial-risk-success-20261002-opt-r2', 'financial-risk-success-20261002-opt-r3')
    value = value.replace('optimized-rebuild-r2', 'optimized-rebuild-r3')
    command = 'run_stage code-preflight python3 -u "$TASK_LOG_DIR/payload/APPLY.py" --dev "$TASK_DEV" --check\n'
    assert value.count(command) == 1
    value = value.replace(command, '')
    marker = 'if [[ "$task_action" == stop-old || "$task_action" == build ]]; then\n'
    assert value.count(marker) == 1
    value = value.replace(marker, 'if [[ "$task_action" != stop-old ]]; then\n  ' + command + 'fi\n' + marker)
    return value


def main():
    assert hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() == PREVIOUS_SHA
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PREVIOUS) as z:
        payload = {name: z.read(name) for name in z.namelist()}
    manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
    original_apply = payload['APPLY.py']
    payload['APPLY_R2.py'] = original_apply
    payload['APPLY.py'] = (ROOT / '06_TOOLS/OFFLINE/genos_optimization_apply_r3.py').read_bytes()
    payload['GUIDE_UTF8.txt'] = GUIDE.encode()
    evidence = {'source_archive': str(LEGACY.relative_to(ROOT)),
                'archive_sha256': hashlib.sha256(LEGACY.read_bytes()).hexdigest(),
                'files': {}, 'field_match_confirmed': False}
    with zipfile.ZipFile(LEGACY) as z:
        source_manifest = json.loads(z.read('CODE_MANIFEST.json'))
        source_rows = {r['path']: r for r in source_manifest['files']}
        for name, expected in LEGACY_FILES.items():
            content = z.read(name)
            assert hashlib.sha256(content).hexdigest() == expected
            assert source_rows[name]['sha256'] == expected and source_rows[name]['bytes'] == len(content)
            payload['predecessors/' + name] = content
            evidence['files'][name] = {'sha256': expected, 'bytes': len(content)}
    payload['PREDECESSOR_EVIDENCE.json'] = (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()
    rows = []
    old_rows = {r['path']: r for r in manifest['files']}
    for name, content in payload.items():
        row = {**old_rows.get(name, {'path': name, 'role': 'handoff'}),
               'sha256': hashlib.sha256(content).hexdigest()}
        if name in LEGACY_FILES:
            row['allowed_predecessors'] = list(dict.fromkeys(row['allowed_predecessors'] + [LEGACY_FILES[name]]))
            row['predecessor_evidence'] = 'PREDECESSOR_EVIDENCE.json'
        rows.append(row)
    manifest.update(schema_version='genos-pipeline-optimization-r3', files=rows,
                    base_r2_zip_sha256=PREVIOUS_SHA, strict_legacy_migration=True)
    payload['CODE_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in payload.items():
            assert Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            z.writestr(name, content)
    zip_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    runnable = OUT / (STEM + '.txt'); runnable.write_text(script(zip_sha))
    subprocess.run(['bash', '-n', str(runnable)], check=True)
    guide = OUT / 'GENOS_PIPELINE_OPTIMIZATION_R3_GUIDE_UTF8.txt'; guide.write_text(GUIDE)
    receipt = {'zip_sha256': zip_sha, 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (archive, runnable, guide)}, 'code_manifest_sha256': hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
        'legacy_source_archive_sha256': evidence['archive_sha256'],
        'field_applied': False, 'field_match_confirmed': False, 'field_built': False, 'serving_verified': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
