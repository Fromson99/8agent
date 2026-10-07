#!/usr/bin/env python3
"""Package R3 with exact R1/R2 dependencies and no changes to frozen handoffs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('recovery_r2_packager', Path(__file__).with_name('package_genos_meaning_recovery_r2.py'))
r2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r2)
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r3'
STEM = 'GENOS_MEANING_RECOVERY_20261002_R3'
RUNNER = '06_TOOLS/OFFLINE/genos_meaning_recover_r3.py'
GUIDE = '''GENOS 의미 구축 복구 R3 — 현장 구버전 navigation 검증 호환

2026-10-02 09:48 사진의 R2 worker는 기존 scratch를 검증하면서
ImportError: cannot import name navigation_storage from semantic_runtime로
종료 코드 1로 중단했습니다. plan 경로 별칭 충돌은 앞선 사진에서 해결 확인됐습니다.
로컬의 선택 기능을 현장에서도 필수로 가정했던 복구기 검증 import가 직접 원인입니다.

이번에는 이 R3 ZIP과 실행 TXT를 사용합니다. 이전 복구 R1/R2 ZIP/TXT,
원래 bulk R2 TXT, plan.json, RAW, 완료/실패 검토 원장, 기존 scratch는 보존합니다.
ZIP을 직접 덮어 풀지 말고 기존 ~/DEV/TRANSFER에 ZIP과 TXT를 함께 올립니다.

실행과 로그:
   cd ~/DEV
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt &&
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt log-off

기본은 기존 OFF 백그라운드 재개입니다. 사전 검사에 모든 필수 검증 함수의 실제
import와 기존 색인 형식별 의존성을 추가했습니다. 현장 모듈이 없고 통합 색인이면
CAPABILITIES ... navigation audit module=absent; monolithic native verification supported
가 나옵니다. 이는 형식/실행 호환 확인이며 전체 scratch 검증이나 구축 완료는 아닙니다.
실제 scratch 검증은 별도 START/RUNNING/END 로그로 이어집니다.
BACKGROUND STARTED와 상태 명령의 status=0은 구축 완료를 뜻하지 않습니다.
log-off는 기록된 OFF worker 마지막 100줄과 이후 로그를 이 터미널에서 보여줍니다.
Ctrl+C는 로그 보기만 종료합니다. log-on / log-review도 제공합니다.

상태 / 양쪽 완료 검증:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt status
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt verify
미완성은 verify 종료 코드 3입니다. 완료와 NFS 발행은 실제 worker 로그/검증으로 확인합니다.

선택 단계:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt recover-on-background
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt review-background
ON은 의미 검토 완료 결과가 필요합니다. pending 의미 검토는 별도 review-background로
진행하며 완료/실패한 의미 작업은 유지합니다. 기존 bulk 방식과 내부 GENOS 모델만 씁니다.
OFF/ON 모두 문서–용어 연결과 명시 참조 LLM을 유지합니다.

중단과 재개:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt stop-off
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt stop-on
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R3.txt stop-review
원래 PID/boot ID/시작시간 확인 후 해당 worker만 SIGINT합니다. FINISHED 확인 후
같은 기본 명령으로 재개합니다. R1/R2/R3는 meaning-recovery-r1의 PID/잠금을 공유합니다.
nohup은 터미널 종료를 견디지만 서버/컨테이너 재시작 후에는 수동 재개가 필요합니다.

검증과 보존:
 - R1의 검증식은 유지하고 navigation_storage import만 기존 storage 분기에 둡니다.
   storage 없는 통합 색인은 현장 원래 Store/TermIndex와 원문·범위·용어집·연결·컴파일러
   해시 검사로 검증합니다. 근거 부족/불완전 scratch는 보존하고 준비본에서 재구축합니다.
 - storage가 있는 감사 분리 색인은 navigation_storage의 verify_audit/verify_build가
   필수입니다. 모듈이 없으면 백그라운드 시작 전에 중단합니다. 감사 검증을 생략하지 않습니다.
 - 기존 plan은 같은 실제 파일과 SHA-256의 경로 별칭만 재사용합니다. 별도 사본,
   설정·파일 변경, pin 추가/누락은 중단하며 plan 삭제/rehash로 우회하지 않습니다.
 - R1/R2 runner는 ZIP에 정확한 기존 바이트로 포함하며 이미 있으면 동일 해시를 요구합니다.
   R3 runner만 추가합니다. 기존 R3가 다르면 백업 후 적용하고 설치 영수증에 세 파일을 기록합니다.
 - R1 checkpoint는 원래 해시/계약으로 유지합니다. runtime 검증 호환의 코드 해시는
   설치 영수증과 recovery-field-capabilities-r3.jsonl에 별도 append-only로 기록합니다.
 - 유효한 navigation scratch가 1개면 원본을 보존한 사본으로 전문 색인부터 재개합니다.
   여러 유효 후보는 임의 선택하지 않고 중단합니다. 없으면 준비본에서 연결/navigation을
   재구축합니다. RAW·문서 구조화·완료한 의미 검토는 다시 돌리지 않습니다.

기본 환경:
   실제 기존 Git checkout ~/DEV, 명시 실행 명령 python3 (실제 경로/버전은 로그)
   GENOS_DATA_ROOT 기존 데이터 경로 (기본 /workspace/01_DATA)
   GENOS_VARIANTS_RUN_ID=financial-risk-success-20261001-r3
   GENOS_VARIANTS_SHARED_ROOT 기본 /nfs-root/diamo/8-agent/term-releases
   GENOS_VARIANTS_ORIGINAL은 기존 원래 TXT를 plan에서 찾으며 필요 시 기존 실제 경로 지정
입력은 기존 bulk fork의 준비 원문·용어집·내부 모델 프로필·검토 원장입니다.
출력은 기존 meaning-variants/off/on, 검증된 별도 NFS 세대와 그 서빙 선택 파일입니다.
NFS 발행과 CURRENT 활성화는 별도이며 CURRENT·Git push·코드서빙·워크플로우는 바꾸지 않습니다.
새 worker 로그는 baseline-worker-r3-*.log와 01_DATA/LOGS/<run>/meaning-recovery-r1에 남고
최초 로그는 /tmp/genos-meaning-recovery-r3-*.log입니다.
원복은 R3 worker 종료 확인 후 새 runner 사용을 중단합니다. 이전 R2에는 같은 import 오류가
남습니다. 현장 실제 재개·NFS 발행·서빙 성공은 로컬 검사와 구분하여 확인해야 합니다.
'''


def script(zip_sha):
    value = r2.script(zip_sha)
    value = value.replace(r2.STEM, STEM).replace(r2.RUNNER, RUNNER)
    value = value.replace("for relative in ('" + r2.BASE + "','" + RUNNER + "'):",
                          "for relative in ('" + r2.BASE + "','" + r2.RUNNER + "','" + RUNNER + "'):")
    value = value.replace("if relative=='" + r2.BASE + "': raise ValueError('Existing R1 runner differs; preserved, no overwrite')",
                          "if relative in ('" + r2.BASE + "','" + r2.RUNNER + "'): raise ValueError('Existing R1/R2 runner differs; preserved, no overwrite')")
    value = value.replace('/tmp/genos-meaning-recovery-r2-', '/tmp/genos-meaning-recovery-r3-')
    value = value.replace('genos-meaning-recovery-install-r2', 'genos-meaning-recovery-install-r3')
    value = value.replace("'recovery_version':'20261002-r2'", "'recovery_version':'20261002-r3'")
    value = value.replace('runner-r2-before-', 'runner-r3-before-')
    value = value.replace('$recovery_job-worker-r2-XXXXXX.log', '$recovery_job-worker-r3-XXXXXX.log')
    return value


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original = (ROOT / r2.r1.ORIGINAL).read_bytes()
    files = {name: (ROOT / name).read_bytes() for name in (r2.BASE, r2.RUNNER, RUNNER)}
    for name, body in files.items():
        compile(body, name, 'exec')
    if r2.r1.sha(original).encode() not in files[r2.BASE]:
        raise ValueError('R1 original fingerprint mismatch')
    files.update({'original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt': original, 'GUIDE_UTF8.txt': GUIDE.encode()})
    manifest = {'schema_version': 'genos-meaning-recovery-code-r3',
                'base_git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'files': [{'path': name, 'sha256': r2.r1.sha(body), 'bytes': len(body)} for name, body in sorted(files.items())],
                'apply_paths': [r2.BASE, r2.RUNNER, RUNNER], 'original_preserved': True, 'activated': False}
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, body)
        z.writestr('CODE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    zip_sha = r2.r1.sha(archive.read_bytes())
    txt = OUT / (STEM + '.txt'); txt.write_text(script(zip_sha))
    subprocess.run(['bash', '-n', str(txt)], check=True)
    guide = OUT / (STEM + '_GUIDE_UTF8.txt'); guide.write_text(GUIDE)
    handoff = {'schema_version': 'genos-meaning-recovery-handoff-r3', 'local_validation_root': str(ROOT),
               'local_python': str(ROOT / '.venv/bin/python'), 'base_git_head': manifest['base_git_head'],
               'original_txt': r2.r1.ORIGINAL, 'original_txt_sha256': r2.r1.sha(original),
               'files': {path.name: r2.r1.sha(path.read_bytes()) for path in (archive, txt, guide)},
               'runners': {name: r2.r1.sha(files[name]) for name in (r2.BASE, r2.RUNNER, RUNNER)},
               'field_build_verified': False, 'field_python': None, 'field_selected_generation': None,
               'field_serving_revision': None, 'activated': False, 'core_changes': False,
               'workflow_changes': False, 'git_push': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'zip': str(archive), 'zip_sha256': zip_sha, 'txt': str(txt)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
