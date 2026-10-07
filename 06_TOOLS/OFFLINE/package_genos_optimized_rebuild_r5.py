"""Replace only the engine-report adapter in the immutable R4 handoff."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_optimized_rebuild_r4 as r4

ROOT = r4.ROOT
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r5'
STEM = 'GENOS_PIPELINE_OPTIMIZATION_20261002_R5'
PREVIOUS = r4.OUT / (r4.STEM + '.zip')
PREVIOUS_SHA = '57c7916b695cbfff38385b17f1415881f63b62908d894715a03d93eb843d5a4e'


def main():
    assert hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() == PREVIOUS_SHA
    with zipfile.ZipFile(PREVIOUS) as z:
        payload = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
    payload['APPLY_R2.py'] = (ROOT / '06_TOOLS/OFFLINE/genos_optimization_apply_r5.py').read_bytes()
    prior_guide = (r4.OUT / 'GENOS_PIPELINE_OPTIMIZATION_R4_GUIDE_UTF8.txt').read_text()
    guide = '''GENOS 최적화 재구축 R5 — 엔진 검사 실행·출력 처리 교체

R4 사진은 파일 적용 후 엔진 검사 출력의 JSON 파싱 실패와 ROLLBACK COMPLETE를 보입니다.
최적화 구축은 시작되지 않았습니다. 준비본은 유지하고 원복한 코드에서 다시 실행합니다.
사진만으로 빈 stdout인지 JSON이 아닌 출력인지 구분할 수 없습니다.
R5는 선택한 checkout의 control.rehash_engines를 명시적으로 호출하며 모듈 실행 진입점에 의존하지 않습니다.
검사 stdout/stderr/종료코드를 engine-command-*.json에 보존하고 잘못된 결과를 성공으로 처리하지 않습니다.
기존 파일·스키마·관련 없는 엔진 변경 거부와 적용 실패 시 원복 검사는 유지합니다.
최적화 코드·실행기·허용된 기존 코드 버전은 R4와 같습니다. 아래 R5 명령을 실행하세요.

''' + prior_guide.replace('R4', 'R5').replace('opt-r4', 'opt-r5').replace('optimized-rebuild-r4', 'optimized-rebuild-r5')
    payload['GUIDE_UTF8.txt'] = guide.encode()
    for row in manifest['files']:
        row['sha256'] = hashlib.sha256(payload[row['path']]).hexdigest()
    manifest.update(schema_version='genos-pipeline-optimization-r5', base_r4_zip_sha256=PREVIOUS_SHA)
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
        'financial-risk-success-20261002-opt-r4', 'financial-risk-success-20261002-opt-r5').replace('optimized-rebuild-r4', 'optimized-rebuild-r5')
    runnable = OUT / (STEM + '.txt'); runnable.write_text(script)
    subprocess.run(['bash', '-n', str(runnable)], check=True)
    instruction = OUT / 'GENOS_PIPELINE_OPTIMIZATION_R5_GUIDE_UTF8.txt'; instruction.write_text(guide)
    record = {'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, runnable, instruction)},
              'code_manifest_sha256': hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
              'field_applied': False, 'field_built': False, 'serving_verified': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
