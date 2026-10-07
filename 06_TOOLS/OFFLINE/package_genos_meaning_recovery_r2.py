#!/usr/bin/env python3
"""New R2 handoff; the mailed R1 and original bulk artifacts stay byte-exact."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('recovery_r1_packager', Path(__file__).with_name('package_genos_meaning_recovery.py'))
r1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r1)
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r2'
STEM = 'GENOS_MEANING_RECOVERY_20261002_R2'
RUNNER = '06_TOOLS/OFFLINE/genos_meaning_recover_r2.py'
BASE = r1.RUNNER
GUIDE = '''GENOS 의미 구축 복구 R2 — 기존 OFF plan.json 결속 충돌 보완

이번 사진에서 복구 R1 worker는 Immutable receipt differs: .../off/plan.json으로
종료 코드 1로 중단했습니다. R1 사전 검사는 기존 variant plan 비교를 하지 않았습니다.
체크아웃 경로 별칭으로 pins의 키가 달라지는 경우를 새 R2가 검증합니다.
같은 실제 파일(dev/inode)이고 SHA-256도 같을 때에만 기존 키를 재사용합니다.
같은 바이트의 별도 사본, 변경된 파일, 설정 변경, 추가/누락 파일은 중단합니다.
사진만으로 기존 plan의 실제 차이 항목까지 확인된 것은 아닙니다.

1. 이 R2 ZIP과 TXT를 함께 ~/DEV/TRANSFER에 올립니다.
   기존 bulk R2 TXT와 복구 R1 ZIP/TXT는 그대로 둡니다. ZIP을 직접 덮어 풀지 않습니다.

2. 실행:
   cd ~/DEV
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt
   기존 OFF를 백그라운드로 재개합니다. 내부 입력·프로필·spawn/PeCab과 기존
   OFF/ON plan까지 검사한 다음 시작합니다. BACKGROUND STARTED는 구축 완료가 아닙니다.
   차이가 경로 별칭이면 PLAN ALIASES verified same inode + SHA-256이 나옵니다.
   파일/설정 차이이면 기존 plan을 보존하고 중단합니다. plan 삭제·수동 rehash를 하지 않습니다.

3. 실제 작업 로그를 이 터미널에서 보기:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt log-off
   기록된 OFF worker의 마지막 100줄과 이후 로그가 표시됩니다.
   Ctrl+C는 로그 보기만 종료하며 worker는 계속 실행됩니다.
   log-on / log-review로 해당 worker의 기록도 열 수 있습니다.
   status는 상태를 한 번 출력하고 종료합니다.
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt status

4. 종료/재개:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt stop-off
   실제 worker FINISHED 확인 후 같은 기본 명령을 다시 실행합니다.
   R1과 R2는 meaning-recovery-r1의 PID/잠금을 공유하므로 중복 worker를 시작하지 않습니다.
   새 worker는 baseline-worker-r2-*.log, 실행 기록은 /tmp/genos-meaning-recovery-r2-*.log와
   01_DATA/LOGS/<run>/meaning-recovery-r1에 남습니다. 상태 끝의 status=0은 작업 성공이 아닙니다.

5. 의미 검토 / ON (필요한 단계만 별도로 실행):
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt review-background
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt recover-on-background
   완료/실패한 의미 작업은 보존하고 pending만 원래 bulk 방식으로 진행합니다.
   ON은 의미 검토 완료 결과가 필요합니다. 두 경로 모두 명시 참조 LLM을 유지합니다.
   이번 OFF 기본 명령이 의미 검토 pending을 자동 시작하는 것은 아닙니다.

6. 완성된 양쪽 결과 확인:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R2.txt verify
   미완성은 종료 코드 3이며 각 variant의 원래 해시·참조·감사 검증을 유지합니다.

보존과 적용:
 - 기존 ~/DEV에 R2 runner 한 파일을 추가하고 정확한 R1 runner를 의존성으로 사용합니다.
   R1 파일이 이미 있으면 동일 해시여야 하며, 다른 바이트이면 덮어쓰지 않고 중단합니다.
   R2 파일의 기존 버전이 있으면 백업 후 적용합니다. 설치 영수증은 두 파일을 함께 기록합니다.
 - original bulk TXT·plan.json·origin.json·준비본·완료/실패 검토 원장은 보존합니다.
   별칭 검증 기록은 variant의 plan-alias-recovery-r2.jsonl에 append-only로 남깁니다.
 - R1의 navigation-complete checkpoint와 실제 runner 해시를 그대로 검증하여 재사용합니다.
   완전한 scratch가 없으면 저장된 준비본에서 문서 연결/navigation을 재구축합니다.
   RAW·문서 구조화·완료한 의미 검토를 다시 실행하지 않습니다.
 - 기본 run financial-risk-success-20261001-r3, 공유 출력
   /nfs-root/diamo/8-agent/term-releases를 유지합니다. 데이터와 원본 TXT 경로는
   기존 GENOS_DATA_ROOT / GENOS_VARIANTS_ORIGINAL 또는 기존 계획에서 확인합니다.
 - 현장 명령은 python3입니다. 실제 실행 파일·버전과 checkout·ZIP/파일 해시를 기록합니다.
 - CURRENT·Git push·코드서빙 리비전·워크플로우는 변경하지 않습니다.
   현장 실제 재구축·NFS 발행·서빙 성공은 사용자 로그로 별도 확인해야 합니다.
 - 원복은 R2 worker 종료를 확인하고 R2 runner 사용을 중단합니다.
   R1 재실행에는 기존 plan 충돌이 남을 수 있습니다. 기존 계획을 변경해서 우회하지 않습니다.
'''


def script(zip_sha):
    value = r1.SCRIPT
    value = value.replace('/tmp/genos-meaning-recovery-r1-', '/tmp/genos-meaning-recovery-r2-')
    value = value.replace('stop-off|stop-on|stop-review|baseline|review|reviewed)',
                          'stop-off|stop-on|stop-review|log-off|log-on|log-review|baseline|review|reviewed)')
    value = value.replace('|stop-review]', '|stop-review|log-off|log-on|log-review]')
    marker = 'recovery_zip="${GENOS_RECOVERY_ZIP:'
    position = value.index(marker)
    logs = r'''case "$recovery_action" in
  log-off|log-on|log-review)
    case "$recovery_action" in
      log-off) recovery_meta="$recovery_logs/off-worker.json" ;;
      log-on) recovery_meta="$recovery_logs/on-worker.json" ;;
      log-review) recovery_meta="$GENOS_DATA_ROOT/LOGS/$GENOS_VARIANTS_RUN_ID/meaning-variants/worker.json" ;;
    esac
    python3 -u - "$recovery_meta" <<'GENOS_RECOVERY_LOG_PY'
import json,os,sys
from pathlib import Path
meta=Path(sys.argv[1])
if not meta.is_file(): raise ValueError('No recorded worker: '+str(meta))
log=Path(json.loads(meta.read_text())['log'])
if not log.is_file(): raise ValueError('Recorded log is missing: '+str(log))
print('WORKER LOG '+str(log)+'; Ctrl+C closes log viewing only',flush=True)
os.execvp('tail',['tail','-n','100','-f',str(log)])
GENOS_RECOVERY_LOG_PY
    exit 0 ;;
esac
'''
    value = value[:position] + logs + value[position:]
    start = value.index("    target=root/'__RUNNER__'")
    end = value.index("    value={'schema_version':", start)
    install = '''    applied=[]
    for relative in ('__BASE__','__RUNNER__'):
        payload=z.read(relative)
        compile(payload,relative,'exec')
        target=root/relative
        for item in [target,*target.parents]:
            if item==root: break
            if item.is_symlink(): raise ValueError('Runner target contains a symlink')
        backup=None
        if target.exists() and target.read_bytes()!=payload:
            if relative=='__BASE__': raise ValueError('Existing R1 runner differs; preserved, no overwrite')
            backup=receipt.parent/('runner-r2-before-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid())+'.py')
            with backup.open('xb') as out: out.write(target.read_bytes())
        if not target.exists() or target.read_bytes()!=payload:
            target.parent.mkdir(parents=True,exist_ok=True)
            fd,temporary=tempfile.mkstemp(prefix='.recovery-install-',dir=target.parent)
            try:
                with os.fdopen(fd,'wb') as out:
                    out.write(payload);out.flush();os.fsync(out.fileno())
                os.replace(temporary,target)
            finally:
                if Path(temporary).exists(): Path(temporary).unlink()
        if sha_bytes(target.read_bytes())!=sha_bytes(payload): raise ValueError('Applied runner bytes differ')
        applied.append({'path':str(target),'sha256':sha_bytes(payload),'backup':None if backup is None else str(backup)})
'''
    value = value[:start] + install + value[end:]
    value = value.replace("'schema_version':'genos-meaning-recovery-install-r1'", "'schema_version':'genos-meaning-recovery-install-r2'")
    value = value.replace("'runner':str(target)", "'applied_files':applied,'runner':str(target)")
    value = value.replace("'recovery_version':'20261002-r1'", "'recovery_version':'20261002-r2'")
    value = value.replace('$recovery_job-worker-XXXXXX.log', '$recovery_job-worker-r2-XXXXXX.log')
    return value.replace('__STEM__', STEM).replace('__ZIP_SHA__', zip_sha).replace('__BASE__', BASE).replace('__RUNNER__', RUNNER).replace('__ORIGINAL_SHA__', r1.sha((ROOT / r1.ORIGINAL).read_bytes()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original = (ROOT / r1.ORIGINAL).read_bytes()
    base = (ROOT / BASE).read_bytes()
    runner = (ROOT / RUNNER).read_bytes()
    if r1.sha(original).encode() not in base:
        raise ValueError('R1 original fingerprint mismatch')
    compile(base, BASE, 'exec')
    compile(runner, RUNNER, 'exec')
    files = {BASE: base, RUNNER: runner, 'original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt': original,
             'GUIDE_UTF8.txt': GUIDE.encode()}
    manifest = {'schema_version': 'genos-meaning-recovery-code-r2',
                'base_git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'files': [{'path': name, 'sha256': r1.sha(body), 'bytes': len(body)} for name, body in sorted(files.items())],
                'apply_paths': [BASE, RUNNER], 'original_preserved': True, 'activated': False}
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, body)
        z.writestr('CODE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    zip_sha = r1.sha(archive.read_bytes())
    txt = OUT / (STEM + '.txt')
    txt.write_text(script(zip_sha))
    subprocess.run(['bash', '-n', str(txt)], check=True)
    guide = OUT / (STEM + '_GUIDE_UTF8.txt')
    guide.write_text(GUIDE)
    handoff = {'schema_version': 'genos-meaning-recovery-handoff-r2', 'local_validation_root': str(ROOT),
               'local_python': str(ROOT / '.venv/bin/python'), 'base_git_head': manifest['base_git_head'],
               'original_txt': r1.ORIGINAL, 'original_txt_sha256': r1.sha(original),
               'files': {path.name: r1.sha(path.read_bytes()) for path in (archive, txt, guide)},
               'runner_sha256': r1.sha(runner), 'base_runner_sha256': r1.sha(base),
               'field_build_verified': False, 'field_python': None, 'field_selected_generation': None,
               'field_serving_revision': None, 'activated': False, 'core_changes': False,
               'workflow_changes': False, 'git_push': False}
    (OUT / 'HANDOFF.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'zip': str(archive), 'zip_sha256': zip_sha, 'txt': str(txt)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
