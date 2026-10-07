"""Replace only the engine-report adapter in the immutable R4 handoff."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_optimized_rebuild_r5 as r4

ROOT = r4.ROOT
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r6'
STEM = 'GENOS_PIPELINE_OPTIMIZATION_20261002_R6'
PREVIOUS = r4.OUT / (r4.STEM + '.zip')
PREVIOUS_SHA = '98a34881fe04ee7fb8e3674bf8b97c71a2b4bb4b1f4df6ece6694aa6dcb52c10'


def main():
    assert hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() == PREVIOUS_SHA
    with zipfile.ZipFile(PREVIOUS) as z:
        payload = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
    payload['APPLY_R2.py'] = (ROOT / '06_TOOLS/OFFLINE/genos_optimization_apply_r6.py').read_bytes()
    prior_guide = (r4.OUT / 'GENOS_PIPELINE_OPTIMIZATION_R5_GUIDE_UTF8.txt').read_text()
    guide = '''GENOS 최적화 재구축 R6 — 과거 서빙 데이터 선택과 코드 엔진 pin 갱신 분리

R5는 과거 relation-subtree-main-serving-20260920-v1의 navigation/manifest.json이 없어 실패했습니다.
ROLLBACK COMPLETE가 출력됐으며 이번 준비본의 구축은 시작되지 않았습니다.
R6는 엔진 검사 입력 메타데이터를 임시 복사해 코드/스키마 검사만 수행합니다.
원본 PIPELINE.json의 profiles·데이터 선택·데이터 pin은 그대로 보존하며 엔진 sha만 반영합니다.
과거 데이터는 검증한 것으로 처리하지 않습니다. 관련 없는 코드·스키마 변경은 계속 거부합니다.
새 prepared 입력과 새 출력의 검증은 기존 구축 실행기의 검증 경로로 수행합니다.
현재 서빙/CURRENT/Git/workflow는 활성화하지 않습니다. 기존 결과는 삭제하지 않습니다.

''' + prior_guide.replace('R5', 'R6').replace('opt-r5', 'opt-r6').replace('optimized-rebuild-r5', 'optimized-rebuild-r6')
    payload['GUIDE_UTF8.txt'] = guide.encode()
    for row in manifest['files']:
        row['sha256'] = hashlib.sha256(payload[row['path']]).hexdigest()
    manifest.update(schema_version='genos-pipeline-optimization-r6', base_r5_zip_sha256=PREVIOUS_SHA)
    payload['CODE_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path, content in payload.items():
            assert Path(path).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            z.writestr(path, content)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    script = (r4.OUT / (r4.STEM + '.txt')).read_text().replace(r4.STEM, STEM).replace(
        r4.json.loads((r4.OUT / 'HANDOFF.json').read_text())['files'][r4.STEM + '.zip'], sha).replace(
        'financial-risk-success-20261002-opt-r5', 'financial-risk-success-20261002-opt-r6').replace('optimized-rebuild-r5', 'optimized-rebuild-r6')
    runnable = OUT / (STEM + '.txt'); runnable.write_text(script)
    subprocess.run(['bash', '-n', str(runnable)], check=True)
    instruction = OUT / 'GENOS_PIPELINE_OPTIMIZATION_R6_GUIDE_UTF8.txt'; instruction.write_text(guide)
    record = {'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, runnable, instruction)},
              'code_manifest_sha256': hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
              'field_applied': False, 'field_built': False, 'serving_verified': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
