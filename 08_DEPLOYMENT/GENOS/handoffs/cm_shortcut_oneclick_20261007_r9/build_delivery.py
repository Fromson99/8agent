"""Extend sealed R8 recipes with explicit onsite document/article binding."""
import ast
import base64
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
R8 = OUT.with_name('cm_shortcut_oneclick_20261007_r8')
NAME = 'GENOS_CM_ONECLICK_20261007_R9'
PATHS = ('02_BACKEND/lawrag/pipeline/shortcut_package.py', '02_BACKEND/lawrag/pipeline/unified_memory.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    assert not (OUT/(NAME+'_RUN.txt')).exists(), 'Preserve sealed deliveries; use a new revision'
    builder = load(ROOT/'06_TOOLS/OFFLINE/cm_shortcut_package.py', 'cm_package_builder')
    builder.build(ROOT, ROOT/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation',
                  OUT/'CM51_SOURCE_PACKAGE.json', 'cm51-curated-common-20261007-r4-target-source',
                  common=True, target_selected=True)
    old = json.loads(gzip.decompress((R8/'PATCH_SPEC.json.gz').read_bytes()))
    spec = copy.deepcopy(old)
    spec.update(revision=NAME, recipes={}, states={}, r8_upgrades={}, r8_inventories={})
    changes = {p: (ROOT/p).read_bytes() for p in PATHS}
    # No unrelated latest code is copied over any prior field variant.
    prior = {}
    for path in PATHS:
        hashes = {old['inventories'][r['after']][path] for r in old['recipes'].values()}
        assert len(hashes) == 1
        prior[path] = next(iter(hashes))
    for path, raw in changes.items():
        ast.parse(raw, feature_version=(3, 11))
        spec['blobs'][sha(raw)] = base64.b64encode(raw).decode()
    for rid, recipe in old['recipes'].items():
        after = dict(old['inventories'][recipe['after']])
        patch = dict(old['patch_sets'][recipe['patches']])
        for path, raw in changes.items():
            after[path] = patch[path] = sha(raw)
        pipeline_path = '00_SYSTEM/PIPELINE.json'
        pipeline = json.loads(base64.b64decode(old['blobs'][after[pipeline_path]]))
        for entry in pipeline['engines'].values():
            path = entry['manifest']
            engine = json.loads(base64.b64decode(old['blobs'][after[path]]))
            for dependency, raw in changes.items():
                if dependency in engine['files']:
                    engine['files'][dependency] = sha(raw)
            raw = encoded(engine); pin = sha(raw)
            after[path] = patch[path] = entry['sha256'] = pin
            spec['blobs'][pin] = base64.b64encode(raw).decode()
        raw = encoded(pipeline); pin = sha(raw)
        after[pipeline_path] = patch[pipeline_path] = pin
        spec['blobs'][pin] = base64.b64encode(raw).decode()
        next_recipe = {**recipe, 'label': recipe['label']+'/onsite-source-r9', 'legacy_r8_recipe': rid}
        for key, value, group in [('after', after, 'inventories'), ('patches', patch, 'patch_sets')]:
            pin = sha(encoded(value)); spec[group][pin] = value; next_recipe[key] = pin
        next_recipe.pop('id'); next_recipe['id'] = sha(encoded(next_recipe))
        spec['recipes'][next_recipe['id']] = next_recipe
        spec['r8_upgrades'][rid] = next_recipe['id']
        spec['r8_inventories'][rid] = recipe['after']
    spec['states'] = {pin: [spec['r8_upgrades'][rid] for rid in recipes] for pin, recipes in old['states'].items()}
    raw = (OUT/'CM51_SOURCE_PACKAGE.json').read_bytes(); spec['package_sha256'] = sha(raw)
    spec['blobs'][sha(raw)] = base64.b64encode(raw).decode()
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec), mtime=0))
    code = (ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py').read_bytes()
    ast.parse(code, feature_version=(3, 11))
    bundle = encoded({'code': base64.b64encode(code).decode(), 'spec': spec})
    packed = base64.b64encode(zlib.compress(bundle, 9)).decode()
    script = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_transfer="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_logs="$task_transfer/cm-oneclick-r9/logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"' EXIT
printf 'CM 현장 문서명·조문 연결 수정 R9 시작 LOG=%s\\n' "$task_log"
if [[ -x /venv/bin/python3 ]]; then task_python=/venv/bin/python3; else task_python=python3; fi
"$task_python" - "$task_transfer" "$@" <<'CM_ONECLICK_PY'
'''+f'''import base64,hashlib,json,sys,types,zlib
raw=zlib.decompress(base64.b64decode({packed!r}))
assert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}
bundle=json.loads(raw);m=types.ModuleType('cm_oneclick')
exec(compile(base64.b64decode(bundle['code']),'genos_cm_oneclick.py','exec'),m.__dict__)
raise SystemExit(m.main(bundle['spec'],sys.argv[1:]))
CM_ONECLICK_PY
'''
    run = OUT/(NAME+'_RUN.txt'); run.write_text(script)
    subprocess.run(['bash', '-n', str(run)], check=True)
    guide = OUT/'GUIDE_UTF8.txt'
    guide.write_text('''CM 현장 이름·조문 연결 수정 R9 — 기존 R8 대신 실행

ZIP과 같은 이름의 RUN TXT를 모두 보냈습니다. ZIP 안에도 완전한 RUN TXT가 있습니다.
ZIP을 ~/DEV/TRANSFER에 올리고 아래 두 줄을 실행합니다.

unzip -n ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261007_R9.zip -d ~/DEV/TRANSFER
bash ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261007_R9_RUN.txt

R8이 package-check에서 중단한 현재 코드 위에 이어서 적용합니다. 이전 실패 로그와
원문은 보존합니다. 별도 사용자/팀/환경변수 입력이나 원문 재구축은 필요 없습니다.

정식 규정명과 폴더·파일 별칭으로 본문을 찾고, 전문·조문 형식은 기존 표현본 우선순위
XML→HTML→HWPX→DOCX→PDF→HWP를 따릅니다. 개정문·신구조문대비표는 본문으로
사용하지 않습니다. 같은 우선순위의 여러 판본이나 없는/중복 조문은 등록 전에 중단합니다.
로컬 해시와 현장 해시의 일치를 요구하지 않습니다. 등록한 근거는 현장 문서 ID,
실제 조문 본문, source/navigation/fulltext 해시에 결속하며 현재 적용은 다시 판단합니다.

코드 백업→적용→51건/98근거 확인→commit→같은 checkout/generation gate→공통 등록
검증→push를 실행합니다. 적용·등록·push·현장 배포는 각각 별도 상태입니다.
최종 화면에 나온 COMMIT으로 코드서빙 새 리비전을 배포하고 워크플로우 화면에서 확인합니다.
현재 모델·인증·원문·기존 숏컷 기록은 보존합니다. 새 로컬 MAIN 승격은 실행하지 않습니다.

결과: ~/DEV/TRANSFER/cm-oneclick-r9/STATUS.json
문서별 연결: ~/DEV/TRANSFER/cm-oneclick-r9/DATA_CHECKED.json
등록 영수증: ~/DEV/TRANSFER/cm-oneclick-r9/CM51_REGISTERED.json
실패 상세: ~/DEV/TRANSFER/cm-oneclick-r9/package-check.log 와 logs/<실행>.log
복구용 코드 백업/SQLite 백업도 같은 폴더에 보존합니다.
등록 원복은 같은 runtime에 package-retire --common --store-version 4 --source
CM51_REGISTERED.json으로 해당 import만 retire합니다. 원문 generation은 변경하지 않습니다.

외부 검증은 모의 현장 문서와 로컬 공개 원문을 사용합니다. 실제 GENOS 등록·배포·
워크플로우 성공은 현장 실행 전까지 미확인입니다. 모델 호출 없음.
''')
    archive = OUT/(NAME+'.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in (run, guide):
            z.write(path, path.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(Path(n).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
        assert z.read(run.name) == run.read_bytes()
    record = {'version': NAME, 'working_sources': {p: sha(raw) for p, raw in changes.items()},
              'prior_sources': prior, 'oneclick_source_sha256': sha(code), 'package_sha256': spec['package_sha256'],
              'package_policy': 'target-selected-document-article-v1', 'recipes': len(spec['recipes']),
              'input_inventories': len(spec['states']), 'supported_r8_recipes': len(spec['r8_upgrades']),
              'paths': spec['paths'], 'cases': 51, 'entries': 98, 'model_calls': 0,
              'GENOS_field_verified': False, 'code_serving_revision': None,
              'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in (archive, run, guide)]}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print('BUILT R9', len(spec['recipes']), 'recipes; ZIP', archive.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
