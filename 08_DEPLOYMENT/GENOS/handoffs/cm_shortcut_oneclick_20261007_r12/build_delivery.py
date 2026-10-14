"""Extend sealed R11 recipes only with the requested XML body-name suffix."""
import ast
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PARENT=OUT.with_name('cm_shortcut_oneclick_20261007_r11')
NAME='GENOS_CM_ONECLICK_20261007_R12'
PATH='02_BACKEND/lawrag/pipeline/shortcut_package.py'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    assert not (OUT/(NAME+'_RUN.txt')).exists(),'Preserve sealed deliveries; use a new revision'
    old=json.loads(gzip.decompress((PARENT/'PATCH_SPEC.json.gz').read_bytes()))
    hand=json.loads((PARENT/'HANDOFF.json').read_bytes())
    baselines={old['inventories'][r['after']][PATH] for r in old['recipes'].values()}
    assert len(baselines)==1
    before=base64.b64decode(old['blobs'][next(iter(baselines))])
    # Exact Korean source edit; every other byte of the deployed module is retained.
    old_line="re.sub(r'[_\\-]*(?:전문|조문)$', '', key)".encode()
    new_line="re.sub(r'[_\\-]*(?:전문|조문|본문)$', '', key)".encode()
    assert before.count(old_line)==1
    changed=before.replace(old_line,new_line,1)
    assert (ROOT/PATH).read_bytes()==changed,'Preserve unrelated working changes'
    ast.parse(changed,feature_version=(3,11))
    spec=copy.deepcopy(old)
    spec.update(revision=NAME,recipes={},states={},r11_upgrades={},r11_inventories={})
    spec['blobs'][sha(changed)]=base64.b64encode(changed).decode()
    for rid,recipe in old['recipes'].items():
        after=dict(old['inventories'][recipe['after']])
        patch=dict(old['patch_sets'][recipe['patches']])
        after[PATH]=patch[PATH]=sha(changed)
        pipeline_path='00_SYSTEM/PIPELINE.json'
        pipeline=json.loads(base64.b64decode(old['blobs'][after[pipeline_path]]))
        for entry in pipeline['engines'].values():
            path=entry['manifest']
            engine=json.loads(base64.b64decode(old['blobs'][after[path]]))
            if PATH not in engine['files']:continue
            assert engine['files'][PATH]==sha(before)
            engine['files'][PATH]=sha(changed)
            raw=encoded(engine);pin=sha(raw)
            after[path]=patch[path]=entry['sha256']=pin
            spec['blobs'][pin]=base64.b64encode(raw).decode()
        raw=encoded(pipeline);pin=sha(raw)
        after[pipeline_path]=patch[pipeline_path]=pin
        spec['blobs'][pin]=base64.b64encode(raw).decode()
        successor={**recipe,'label':recipe['label']+'/xml-body-suffix-r12','legacy_r11_recipe':rid}
        for key,value,group in [('after',after,'inventories'),('patches',patch,'patch_sets')]:
            pin=sha(encoded(value));spec[group][pin]=value;successor[key]=pin
        successor.pop('id');successor['id']=sha(encoded(successor))
        spec['recipes'][successor['id']]=successor
        spec['r11_upgrades'][rid]=successor['id']
        spec['r11_inventories'][rid]=recipe['after']
    for version in ('r8','r10'):
        spec[version+'_upgrades']={rid:spec['r11_upgrades'][target] for rid,target in old[version+'_upgrades'].items()}
    spec['states']={pin:[spec['r11_upgrades'][rid] for rid in recipes] for pin,recipes in old['states'].items()}
    assert spec['package_sha256']==old['package_sha256']
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
    code=(ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py').read_bytes()
    ast.parse(code,feature_version=(3,11))
    assert ("VERSION='"+NAME+"'").encode() in code
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    script='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_transfer="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_logs="$task_transfer/cm-oneclick-r12/logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
cm_exit() {
    task_exit=$?
    python3 - "$task_log.EXIT_STATUS.json" "$task_exit" <<'EXIT_PY'
import json,os,sys
path=sys.argv[1];raw=(json.dumps({'exit_code':int(sys.argv[2])})+'\\n').encode()
with open(path+'.tmp','xb') as stream:
    stream.write(raw);stream.flush();os.fsync(stream.fileno())
os.replace(path+'.tmp',path)
EXIT_PY
    printf 'EXIT=%s LOG=%s\\n' "$task_exit" "$task_log"
}
trap cm_exit EXIT
printf 'CM R12 본문 이름 연결·조사 한도 보존 시작 LOG=%s\\n' "$task_log"
python3 - "$task_transfer" "$@" <<'CM_ONECLICK_PY'
'''+f'''import base64,hashlib,json,sys,types,zlib
raw=zlib.decompress(base64.b64decode({packed!r}))
if hashlib.sha256(raw).hexdigest()!={sha(bundle)!r}:raise ValueError('Embedded bundle hash mismatch')
bundle=json.loads(raw);m=types.ModuleType('cm_oneclick')
code=base64.b64decode(bundle['code'])
if hashlib.sha256(code).hexdigest()!={sha(code)!r}:raise ValueError('Embedded installer hash mismatch')
exec(compile(code,'genos_cm_oneclick.py','exec'),m.__dict__)
raise SystemExit(m.main(bundle['spec'],sys.argv[1:]))
CM_ONECLICK_PY
'''
    run=OUT/(NAME+'_RUN.txt');run.write_text(script)
    subprocess.run(['bash','-n',str(run)],check=True)
    guide_text='''CM R12 — 본문 이름 연결 추가, 이전 CM R11 대신 실행

정식명 뒤의 본문 접미어를 추가로 인식합니다. 예: 중소기업기본법 본문.xml.
공백/폴더/별칭/전문/조문 처리는 유지하고 시행령/시행규칙/개정문을 합치지 않습니다.
없는 문서, 중복 판본/조문, 권한과 source/nav/fulltext 해시 차이는 계속 중단합니다.
사진의 오류가 실제 문서 누락인 경우 이 이름 수정만으로 해결되지는 않습니다.

ZIP을 기존 ~/DEV/TRANSFER에 올린 다음 아래 세 줄을 실행합니다.
python3 -m zipfile -e ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261007_R12.zip ~/DEV/TRANSFER
(cd ~/DEV/TRANSFER && sha256sum -c GENOS_CM_ONECLICK_20261007_R12_SHA256SUMS.txt)
bash ~/DEV/TRANSFER/GENOS_CM_ONECLICK_20261007_R12_RUN.txt

별도 첨부 RUN TXT를 TRANSFER에 올렸다면 마지막 bash 한 줄로 실행할 수도 있습니다.
R11이 코드 적용 후 package-check에서 실패한 상태에 이어 적용합니다.
검증된 R8/R10/선행 코드 상태도 지원합니다. 조사 한도 코드/설정은 보존하고
R11에 남긴 백업과 원래 조사 한도 부모 inventory까지 대조합니다.
알 수 없는 코드 수정이나 선택 generation 변경은 덮어쓰지 않습니다.
원문 재구축, RAW 이름 변경, 조사 한도 재적용, 새 환경변수/사용자/팀 입력은 없습니다.

원문 51건/98근거 연결 확인 → commit → 같은 checkout/generation gate →
공통 등록/검증 → 기존 origin push를 수행합니다. EXIT=0과
READY_FOR_REVISION_DEPLOYMENT이면 출력한 COMMIT으로 새 코드서빙 리비전을
배포하고 워크플로우 테스트 화면에서 실제 질문을 확인합니다.
코드 적용/등록/Git push/리비전/워크플로우 성공은 각각 별도 상태입니다.

실행 상태/문서 연결/등록 영수증:
~/DEV/TRANSFER/cm-oneclick-r12/STATUS.json
~/DEV/TRANSFER/cm-oneclick-r12/DATA_CHECKED.json
~/DEV/TRANSFER/cm-oneclick-r12/CM51_REGISTERED.json
전체 실행 로그/종료 상태: 같은 폴더 logs/<실행>.log 및 .EXIT_STATUS.json
단계 실패 상세: 같은 폴더 package-check.log / package-import.log / package-verify.log
코드 백업: 같은 폴더 code-backup/receipt.json
등록 전 DB 백업: 같은 폴더 CASE_STATE_BEFORE.sqlite.gz
R8/R10/R11 실패 기록과 기존 조사 한도 백업, 원문 generation, 기존 DB를 보존합니다.

코드 원복: code-backup/receipt.json의 before/after SHA를 대조해 저장된 파일을
같은 DEV의 원래 위치에 복구하고 별도 commit/gate/push 후 이전 검증 리비전으로
복귀합니다. 현재 파일이 after SHA와 다르면 후속 변경을 보존하고 중단합니다.
등록 원복: 같은 runtime에서 package-retire --common --store-version 4 --source
CM51_REGISTERED.json으로 해당 import만 retire합니다. 원문 generation은 바꾸지 않습니다.
로컬 계약/모의 인계 검증과 실제 GENOS 적용/배포/질문 성공은 구분합니다.
'''
    guide=OUT/(NAME+'_GUIDE.txt');guide.write_text(guide_text)
    (OUT/'GUIDE_UTF8.txt').write_text(guide_text)
    sums=OUT/(NAME+'_SHA256SUMS.txt')
    sums.write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in (run,guide)))
    archive=OUT/(NAME+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in (run,guide,sums):z.write(path,path.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and z.read(run.name)==run.read_bytes()
        assert all(Path(p).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for p in z.namelist())
    record={'version':NAME,'oneclick_source_sha256':sha(code),'parent_r11_run_sha256':
        sha((PARENT/'GENOS_CM_ONECLICK_20261007_R11_RUN.txt').read_bytes()),
        'parent_r11_manifest':hand,'changed_module':PATH,'before_module_sha256':sha(before),
        'after_module_sha256':sha(changed),'package_sha256':spec['package_sha256'],
        'recipes':len(spec['recipes']),'r8_upgrades':len(spec['r8_upgrades']),
        'r10_upgrades':len(spec['r10_upgrades']),'r11_upgrades':len(spec['r11_upgrades']),
        'paths':spec['paths'],'GENOS_field_verified':False,'code_serving_revision':None,
        'model_calls':0,'local_main_pointer_changed':False,
        'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in (archive,run,guide,sums)]}
    (OUT/'HANDOFF.json').write_bytes(encoded(record))
    print('BUILT R12',len(spec['recipes']),'recipes; ZIP',archive.stat().st_size,'bytes')


if __name__=='__main__':main()
