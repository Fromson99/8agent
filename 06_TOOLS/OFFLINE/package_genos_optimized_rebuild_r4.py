"""Bind the photographed field predecessors to retained patch bytes; preserve R3."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_optimized_rebuild_r3 as r3

ROOT = r3.ROOT
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/pipeline_optimization_20261002_r4'
STEM = 'GENOS_PIPELINE_OPTIMIZATION_20261002_R4'
PREVIOUS = r3.OUT / (r3.STEM + '.zip')
PREVIOUS_SHA = '1a26b133cc3a5ec419172499c9d79a5a0016cd76939d53216c9590ffdabff438'
FIELD_FILES = {
    '02_BACKEND/semantic_runtime/term_index.py': ('response_overhead_20260928_r3', 'e1557537ec5409c6993aef6d6f064cce212c0fa2f301b49e130848d22ca16ffd'),
    '02_BACKEND/semantic_runtime/fulltext.py': ('fulltext_diagnostics_20260928_r1', '02aa242f86e34f687b9b5077d5bc86fe7381ad1682386757343f04b42f3a62a8'),
}
INTRO = '''GENOS 최적화 재구축 R4 — 사진에서 확인한 기존 패치 코드 이행

R3 현장 사진의 term_index.py/fulltext.py 실제 해시는 기존 반입 패치의 코드와 일치합니다.
R4는 해당 두 파일의 검증된 해시만 추가로 허용합니다. 최적화 코드와 실행기는 R3와 같습니다.
R3는 적용 전에 종료했으므로 준비본·코드는 유지됐습니다. 해시를 임의로 고쳐 통과시키지 않습니다.
R4 ZIP과 실행 TXT를 함께 ~/DEV/TRANSFER에 올린 뒤 실행하세요.
  cd ~/DEV
  export GENOS_PREPARED_RUN=financial-risk-success-20261001-r3
  export GENOS_OPTIMIZED_RUN=financial-risk-success-20261002-opt-r4
  bash TRANSFER/GENOS_PIPELINE_OPTIMIZATION_20261002_R4.txt

현장 전체 적용·구축·서빙 완료는 아직 미확인입니다. 아래 기존 재사용·로그·재개·롤백 안내를 따릅니다.

'''


def main():
    assert hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() == PREVIOUS_SHA
    with zipfile.ZipFile(PREVIOUS) as z:
        payload = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
    evidence = {'photograph_hash_match': True, 'field_applied': False, 'files': {}}
    for path, (patch, expected) in FIELD_FILES.items():
        folder = ROOT / '08_DEPLOYMENT/GENOS/patches' / patch
        content = (folder / 'payload' / path).read_bytes()
        patch_bytes = (folder / 'PATCH_MANIFEST.json').read_bytes()
        record = json.loads(patch_bytes)['files'][path]
        assert hashlib.sha256(content).hexdigest() == expected == record['new_sha256']
        payload['field-predecessors/' + path] = content
        evidence['files'][path] = {'sha256': expected, 'source_patch': str(folder.relative_to(ROOT)),
                                  'patch_manifest_sha256': hashlib.sha256(patch_bytes).hexdigest()}
    payload['FIELD_PREDECESSOR_EVIDENCE.json'] = (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()
    guide = INTRO + r3.r2.GUIDE.replace('재구축 R2 /', '재구축 R4 /').replace('이 R2 ZIP/TXT', '이 R4 ZIP/TXT').replace(
        'GENOS_PIPELINE_OPTIMIZATION_20261002_R2', STEM).replace('financial-risk-success-20261002-opt-r2',
        'financial-risk-success-20261002-opt-r4').replace('optimized-rebuild-r2', 'optimized-rebuild-r4').replace(
        '순서: 지속 로그 시작 → 기록된 이전 worker만 SIGINT·종료 확인 → checkout hash 검사 →',
        '순서: 지속 로그 시작 → checkout hash 검사 → 기록된 이전 worker만 SIGINT·종료 확인 →')
    payload['GUIDE_UTF8.txt'] = guide.encode()
    old_rows = {r['path']: r for r in manifest['files']}
    rows = []
    for path, content in payload.items():
        row = {**old_rows.get(path, {'path': path, 'role': 'handoff'}), 'sha256': hashlib.sha256(content).hexdigest()}
        if path in FIELD_FILES:
            row['allowed_predecessors'] = list(dict.fromkeys(row['allowed_predecessors'] + [FIELD_FILES[path][1]]))
            row['field_predecessor_evidence'] = 'FIELD_PREDECESSOR_EVIDENCE.json'
        rows.append(row)
    manifest.update(schema_version='genos-pipeline-optimization-r4', files=rows, base_r3_zip_sha256=PREVIOUS_SHA)
    payload['CODE_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path, content in payload.items():
            assert Path(path).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            z.writestr(path, content)
    zip_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    script = r3.script(zip_sha).replace(r3.STEM, STEM).replace('financial-risk-success-20261002-opt-r3',
        'financial-risk-success-20261002-opt-r4').replace('optimized-rebuild-r3', 'optimized-rebuild-r4')
    runnable = OUT / (STEM + '.txt'); runnable.write_text(script)
    subprocess.run(['bash', '-n', str(runnable)], check=True)
    instruction = OUT / 'GENOS_PIPELINE_OPTIMIZATION_R4_GUIDE_UTF8.txt'; instruction.write_text(guide)
    record = {'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, runnable, instruction)},
              'code_manifest_sha256': hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
              'field_predecessor_hashes_match_photo': True, 'field_applied': False, 'field_built': False,
              'serving_verified': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
