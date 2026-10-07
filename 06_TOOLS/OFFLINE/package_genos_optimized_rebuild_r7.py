"""Replace only the engine-report adapter in the immutable R4 handoff."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_optimized_rebuild_r6 as r4
import package_genos_optimized_rebuild_r2 as base_guide

ROOT = r4.ROOT
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r7'
STEM = 'GENOS_PIPELINE_OPTIMIZATION_20261002_R7'
PREVIOUS = r4.OUT / (r4.STEM + '.zip')
PREVIOUS_SHA = '87fca6c1ac84d9f7e56e88bebb8dbbbb0b790553125b6716b69e32793b7158f5'


def main():
    assert hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() == PREVIOUS_SHA
    with zipfile.ZipFile(PREVIOUS) as z:
        payload = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
    payload['APPLY_R2.py'] = (ROOT / '06_TOOLS/OFFLINE/genos_optimization_apply_r7.py').read_bytes()
    guide = """GENOS 최적화 OFF 재구축 R7 — 패키지 범위 적용 / 파일 반출 불필요

R2~R6의 반복 실패는 현장 전체의 누적 코드·엔진 pin·과거 데이터 상태를
이번 최적화 패키지의 적용 조건과 함께 검사한 문제였습니다.
R7는 전체 rehash-engines를 호출하지 않고 패키지에 들어 있는 코드 pin만 변경합니다.
1. 패키지 파일의 기존 버전·배포 바이트·문법을 먼저 검사합니다.
2. 코드 적용 전에 엔진/스키마/기존 pin 불일치를 한 번에 기록합니다.
3. 패키지 밖 코드 pin·미등록 파일·스키마 pin은 그대로 보존합니다. 정상이라고 인증하지 않습니다.
4. 기존 profiles·데이터 경로·데이터 해시는 변경하지 않습니다. 과거 서빙 데이터 파일이 없어도 복구를 요구하지 않습니다.
5. 백업 후 알려진 패키지 파일과 해당 엔진 코드 pin만 적용합니다.
6. 실행 중 새로 생긴 외부 파일/메타데이터 변경은 중단합니다.
7. 기존 준비본으로 새 OFF 구축을 실행하고 입력·출력·감사·전문색인 검증을 수행합니다.
8. CURRENT·Git push·서빙 리비전·workflow는 활성화하지 않습니다.

R7 ZIP·TXT를 함께 ~/DEV/TRANSFER에 올리고 실행하세요:
  cd ~/DEV
  export GENOS_PREPARED_RUN=financial-risk-success-20261001-r3
  export GENOS_OPTIMIZED_RUN=financial-risk-success-20261002-opt-r7
  bash TRANSFER/GENOS_PIPELINE_OPTIMIZATION_20261002_R7.txt

EXISTING STATE PRESERVED는 이전 상태를 바꾸지 않고 기록했다는 뜻입니다.
그 목록은 현장 로그와 package-engine-plan-*.json에 남습니다. 파일 반출을 요구하지 않습니다.
기존 코드/준비본/원문/구조화/검토 원장/실패 scratch는 삭제하지 않습니다.
패키지 파일 자체가 알 수 없는 버전이면 덮어쓰지 않고 정확한 파일·해시를 출력합니다.

""" + base_guide.GUIDE.replace('재구축 R2 /', '재구축 R7 /').replace('이 R2 ZIP/TXT', '이 R7 ZIP/TXT').replace(
        'GENOS_PIPELINE_OPTIMIZATION_20261002_R2', STEM).replace('financial-risk-success-20261002-opt-r2',
        'financial-risk-success-20261002-opt-r7').replace('optimized-rebuild-r2', 'optimized-rebuild-r7').replace(
        '순서: 지속 로그 시작 → 기록된 이전 worker만 SIGINT·종료 확인 → checkout hash 검사 →',
        '순서: 지속 로그 시작 → checkout hash 검사 → 기록된 이전 worker만 SIGINT·종료 확인 →')
    payload['GUIDE_UTF8.txt'] = guide.encode()
    for row in manifest['files']:
        row['sha256'] = hashlib.sha256(payload[row['path']]).hexdigest()
    manifest.update(schema_version='genos-pipeline-optimization-r7', base_r6_zip_sha256=PREVIOUS_SHA)
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
        'financial-risk-success-20261002-opt-r6', 'financial-risk-success-20261002-opt-r7').replace('optimized-rebuild-r6', 'optimized-rebuild-r7')
    runnable = OUT / (STEM + '.txt'); runnable.write_text(script)
    subprocess.run(['bash', '-n', str(runnable)], check=True)
    instruction = OUT / 'GENOS_PIPELINE_OPTIMIZATION_R7_GUIDE_UTF8.txt'; instruction.write_text(guide)
    record = {'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, runnable, instruction)},
              'code_manifest_sha256': hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
              'field_applied': False, 'field_built': False, 'serving_verified': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
