#!/usr/bin/env python3
"""Package only the R2 recovery runner, exact historical TXT and instructions."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r1'
STEM = 'GENOS_MEANING_RECOVERY_20261002_R1'
RUNNER = '06_TOOLS/OFFLINE/genos_meaning_recover_r1.py'
ORIGINAL = '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt'


def sha(value):
    return hashlib.sha256(value).hexdigest()


GUIDE = '''GENOS 의미 검토 R2 / 전문 색인 실패 복구 — 2026-10-02 R1

메일의 ZIP과 실행 TXT 두 파일을 기존 ~/DEV/TRANSFER에 함께 올립니다.
기존 GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt는 수정하거나 덮어쓰지 않습니다.
ZIP을 직접 덮어 풀지 말고 실행 TXT를 사용합니다.

1. 사진에서 실패한 OFF 구축 재개 (백그라운드):
   cd ~/DEV
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt
   기본 동작은 recover-off-background입니다. 실행 전 원본 해시, 기존 준비 입력,
   내부 모델 프로필, 실제 Python spawn/PeCab을 검사합니다. 생성된 PID/로그가 출력됩니다.
   이 시작 메시지는 구축 완료를 뜻하지 않습니다.

2. 상태와 로그:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt status
   표시된 worker 로그에 tail -f <출력된 로그 절대경로>를 실행합니다.
   모든 실행은 최초 부팅 로그와 01_DATA/LOGS/<run>/meaning-recovery-r1에 남습니다.
   meaning 검토 수/실패 및 OFF/ON ready, 보존된 색인 scratch가 함께 표시됩니다.

3. 이미 의미 검토가 끝난 ON 구축이 실패했다면:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt recover-on-background
   ON은 검토 완료 결과가 있어야 하며, 없으면 성공 처리하지 않고 중단합니다.

4. 의미 검토 자체에 남은 pending이 있다면:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt review-background
   완료/기존 실패 작업은 유지하고 남은 작업만 원래 R2 방식으로 진행합니다.
   기존 의미 검토 worker가 실행 중이면 중복 시작하지 않습니다. OFF는 별도 실행 가능.
   검토가 끝나면 ON을 자동 구축합니다. PARTIAL을 정본 승인/품질 인증으로 바꾸지 않습니다.

5. 중단 / 재개:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt stop-off
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt stop-on
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt stop-review
   필요한 대상만 중단합니다. 저장된 PID의 boot ID/시작시간을 검사한 뒤 SIGINT를 보냅니다.
   FINISHED 확인 후 위의 동일 백그라운드 명령으로 재개합니다.
   nohup은 터미널 연결 종료를 견디지만 서버/컨테이너 재시작 후에는 수동 재개가 필요합니다.

6. 완성된 OFF/ON 확인:
   bash TRANSFER/GENOS_MEANING_RECOVERY_20261002_R1.txt verify
   미완성 버전은 NOT READY / 종료 코드 3입니다. 양쪽 완성과 각각의 해시를 검증합니다.

복구 방식:
 - 사진의 /workspace/<stdin> 오류는 표준입력 TXT 실행과 multiprocessing spawn 충돌입니다.
   새 실행기는 실제 .py 파일로 실행하여 기존 PeCab 2프로세스 병렬 색인을 유지합니다.
 - 기존 .baseline-*에서 원문·선택 범위·용어집·컴파일러·색인·감사 증거를 모두 검증합니다.
   유효한 후보가 1개이면 원본을 보존한 새 사본으로 전문 색인부터 이어갑니다.
   유효한 후보가 여러 개이면 최신 파일을 임의 선택하지 않고 중단합니다.
 - 이전 실패 정리로 완성 색인이 없어졌다면 저장된 구조화 원문/용어 준비본을 사용해
   문서 연결·참조 색인부터 다시 만듭니다. RAW/문서 구조화/완료된 의미 검토를 다시 돌리지 않습니다.
 - 새 구축은 전문 색인 시작 전에 해시 결속 checkpoint를 기록합니다. 실패/인터럽트 때
   scratch를 지우지 않고 원래 traceback을 남깁니다. 불완전 전문 색인은 별도 폴더에 보존합니다.
   다음 실행은 checkpoint를 검증하고 전문 색인부터 재개합니다. payload 변조는 자동 통과하지 않습니다.
 - 사진의 이번 색인 생성은 34002.4초(9시간26분42초), 마지막 navigation은 3384.2초
   (56분24초)였습니다. 전체 작업 시간/복구 잔여 시간은 이 사진으로 확정할 수 없습니다.

기본 선택:
   코드 checkout: /home/genos/DEV (~/DEV의 실제 Git root)
   데이터: /workspace/01_DATA
   run: financial-risk-success-20261001-r3
   기존 bulk fork: 위 run 폴더 안의 <run>-bulk-r2
   공유 출력: /nfs-root/diamo/8-agent/term-releases
   현장 값이 다르면 GENOS_CODE_ROOT, GENOS_DATA_ROOT, GENOS_VARIANTS_RUN_ID,
   GENOS_VARIANTS_SHARED_ROOT를 실제 기존 값으로 지정합니다. 새 run ID를 임의로 만들지 않습니다.
   원본 TXT 경로는 기존 variant plan에서 찾습니다. 필요시 GENOS_VARIANTS_ORIGINAL에
   실제 기존 TXT 경로를 지정합니다. 경로/해시 불일치를 임의 rehash로 우회하지 않습니다.

적용/원복 범위:
   ~/DEV/06_TOOLS/OFFLINE/genos_meaning_recover_r1.py 한 파일만 추가합니다.
   이전 같은 경로 파일이 있다면 설치 영수증의 backup 경로에 보존합니다.
   기존 core checkout/원본 R2 TXT/계획/RAW/완료 세대/CURRENT는 덮어쓰지 않습니다.
   실행 방식 변경은 install 영수증과 baseline-recovery-r1.json에 별도로 결속합니다.
   Git push, 활성 세대 전환, 코드서빙 배포, 워크플로우 교체는 이 TXT가 수행하지 않습니다.
   구축 종료 후 출력되는 GENOS_GENERATION은 별도 서빙 선택값입니다. 현장 실제 구축 성공은 미확인입니다.
   원복은 worker 종료 확인 후 이 새 runner 사용을 중단하고, 필요한 경우 영수증의 이전 runner
   사본을 복원합니다. 원래 R2의 구축은 같은 stdin 오류가 있으므로 재사용하지 않습니다.
'''


SCRIPT = r'''#!/usr/bin/env bash
# ZIP and this TXT go together in ~/DEV/TRANSFER. Default: resume OFF in background.
set -Eeuo pipefail
umask 077
recovery_boot_log=$(mktemp /tmp/genos-meaning-recovery-r1-XXXXXX.log)
exec > >(tee -a "$recovery_boot_log") 2>&1
trap 'recovery_rc=$?; printf "RECOVERY HANDOFF FINISHED status=%s boot_log=%s\n" "$recovery_rc" "$recovery_boot_log"' EXIT
recovery_script=$(realpath "${BASH_SOURCE[0]}")
recovery_action="${1:-recover-off-background}"
recovery_internal=0
if [[ "$recovery_action" == __run ]]; then
  [[ "$#" == 2 ]] || exit 2
  recovery_internal=1
  recovery_action="$2"
  [[ "$recovery_action" == baseline || "$recovery_action" == review || "$recovery_action" == reviewed ]] || exit 2
elif [[ "$#" -gt 1 ]]; then
  printf 'Usage: bash <TXT> [recover-off-background|recover-on-background|review-background|status|check|verify|stop-off|stop-on|stop-review]\n'
  exit 2
fi
case "$recovery_action" in
  recover-off-background|recover-on-background|review-background|status|check|verify|stop-off|stop-on|stop-review|baseline|review|reviewed) ;;
  *) printf 'Unknown action\n'; exit 2 ;;
esac
recovery_root=$(realpath "${GENOS_CODE_ROOT:-/home/genos/DEV}")
cd "$recovery_root"
[[ "$(git rev-parse --show-toplevel)" == "$recovery_root" ]] || { printf 'Use the actual existing Git checkout root\n'; exit 2; }
export GENOS_CODE_ROOT="$recovery_root"
export GENOS_DATA_ROOT="${GENOS_DATA_ROOT:-/workspace/01_DATA}"
export GENOS_VARIANTS_RUN_ID="${GENOS_VARIANTS_RUN_ID:-financial-risk-success-20261001-r3}"
[[ "$GENOS_VARIANTS_RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$ ]] || exit 2
export PYTHONPATH="$recovery_root/02_BACKEND${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
recovery_logs="$GENOS_DATA_ROOT/LOGS/$GENOS_VARIANTS_RUN_ID/meaning-recovery-r1"
mkdir -p "$recovery_logs"
recovery_log=$(mktemp "$recovery_logs/$recovery_action-XXXXXX.log")
exec > >(tee -a "$recovery_log") 2>&1
printf 'RECOVERY START action=%s code_root=%s data_root=%s run=%s log=%s\n' "$recovery_action" "$recovery_root" "$GENOS_DATA_ROOT" "$GENOS_VARIANTS_RUN_ID" "$recovery_log"
recovery_zip="${GENOS_RECOVERY_ZIP:-$(dirname "$recovery_script")/__STEM__.zip}"
recovery_receipt="$recovery_log.install.json"
python3 -u - "$recovery_zip" "$recovery_root" "$recovery_receipt" <<'GENOS_RECOVERY_INSTALL_PY'
import hashlib,json,os,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
archive,root,receipt=Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])
print('PYTHON',sys.executable,sys.version.split()[0],flush=True)
if sys.version_info < (3,11): raise RuntimeError('Python 3.11 or later is required')
if sha_bytes(archive.read_bytes()) != '__ZIP_SHA__': raise ValueError('Recovery ZIP hash mismatch; no files applied')
with zipfile.ZipFile(archive) as z:
    manifest=json.loads(z.read('CODE_MANIFEST.json'))
    if len(z.namelist()) != len(set(z.namelist())): raise ValueError('Duplicate ZIP members')
    if set(z.namelist()) != {r['path'] for r in manifest['files']} | {'CODE_MANIFEST.json'}: raise ValueError('ZIP inventory differs')
    for row in manifest['files']:
        name=Path(row['path'])
        if name.is_absolute() or '..' in name.parts or name.suffix.lower() in {'.js','.jsx','.mjs','.cjs'}:
            raise ValueError('Forbidden ZIP path/type')
        if sha_bytes(z.read(row['path'])) != row['sha256']: raise ValueError('ZIP member hash mismatch')
    source=z.read('__RUNNER__')
    original_bytes=z.read('original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt')
    compile(source,'__RUNNER__','exec')
    if sha_bytes(original_bytes) != '__ORIGINAL_SHA__': raise ValueError('Original R2 payload mismatch')
    requested=os.environ.get('GENOS_VARIANTS_ORIGINAL')
    data=Path(os.environ['GENOS_DATA_ROOT']).resolve()
    run=os.environ['GENOS_VARIANTS_RUN_ID']
    parent=data/'TERM_RELEASES'/run/(run+'-bulk-r2')/'meaning-variants'
    pinned=set()
    for mode in ('off','on'):
        plan=parent/mode/'plan.json'
        if plan.is_file():
            for path,expected in json.loads(plan.read_text()).get('pins',{}).items():
                if Path(path).name=='GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt' and expected=='__ORIGINAL_SHA__':
                    pinned.add(str(Path(path).resolve()))
    if requested:
        original=Path(requested).resolve()
        if pinned and str(original) not in pinned: raise ValueError('Requested original TXT path differs from variant plan')
    elif len(pinned)==1:
        original=Path(next(iter(pinned)))
    elif len(pinned)>1:
        raise ValueError('Multiple pinned original TXT paths; set GENOS_VARIANTS_ORIGINAL to the actual existing one')
    else:
        original=root/'TRANSFER/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt'
    if original.exists():
        if sha_bytes(original.read_bytes())!='__ORIGINAL_SHA__': raise ValueError('Existing original TXT differs; preserved, no writes')
    else:
        # Restore exact historical bytes only to the path already selected above.
        original.parent.mkdir(parents=True,exist_ok=True)
        with original.open('xb') as out: out.write(original_bytes)
    target=root/'__RUNNER__'
    for item in [target,*target.parents]:
        if item==root: break
        if item.is_symlink(): raise ValueError('Runner target contains a symlink')
    backup=None
    if target.exists() and target.read_bytes()!=source:
        backup=receipt.parent/('runner-before-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid())+'.py')
        with backup.open('xb') as out: out.write(target.read_bytes())
    if not target.exists() or target.read_bytes()!=source:
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.recovery-install-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(source);out.flush();os.fsync(out.fileno())
            os.replace(temporary,target)
        finally:
            if Path(temporary).exists(): Path(temporary).unlink()
    if sha_bytes(target.read_bytes())!=sha_bytes(source): raise ValueError('Applied runner bytes differ')
    value={'schema_version':'genos-meaning-recovery-install-r1','zip_sha256':'__ZIP_SHA__',
        'code_manifest_sha256':sha_bytes(z.read('CODE_MANIFEST.json')),'checkout':str(root),
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        'tracked_dirty':bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True)),
        'runner':str(target),'runner_sha256':sha_bytes(source),'backup':None if backup is None else str(backup),
        'original_txt':str(original),'original_txt_sha256':'__ORIGINAL_SHA__',
        'python_executable':sys.executable,'python_version':sys.version,'activated':False,
        'data_root':str(data),'run_id':run,'serving_revision':None,'selected_serving_generation':None,
        'git_push':False,'core_modified':False,'workflow_modified':False}
    receipt.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print('PACKAGE_HASHES PASS; RUNNER APPLIED/VERIFIED '+str(target),flush=True)
    print('INSTALL_RECEIPT='+str(receipt)+' original_txt='+str(original),flush=True)
GENOS_RECOVERY_INSTALL_PY
export GENOS_VARIANTS_ORIGINAL
GENOS_VARIANTS_ORIGINAL=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["original_txt"])' "$recovery_receipt")
recovery_runner="$recovery_root/__RUNNER__"
recovery_args=(--original-txt "$GENOS_VARIANTS_ORIGINAL" --data-root "$GENOS_DATA_ROOT" --run-id "$GENOS_VARIANTS_RUN_ID" --batch "${GENOS_VARIANTS_BATCH:-32}" --workers "${GENOS_VARIANTS_WORKERS:-4}")
recovery_old_logs="$GENOS_DATA_ROOT/LOGS/$GENOS_VARIANTS_RUN_ID/meaning-variants"
mkdir -p "$recovery_old_logs"
case "$recovery_action" in
  recover-off-background|recover-on-background|review-background)
    case "$recovery_action" in
      recover-off-background) recovery_job=baseline; recovery_meta="$recovery_logs/off-worker.json"; recovery_lock="$recovery_logs/off-launcher.lock" ;;
      recover-on-background) recovery_job=reviewed; recovery_meta="$recovery_logs/on-worker.json"; recovery_lock="$recovery_logs/on-launcher.lock" ;;
      review-background) recovery_job=review; recovery_meta="$recovery_old_logs/worker.json"; recovery_lock="$recovery_old_logs/launcher.lock" ;;
    esac
    exec 8>"$recovery_lock"
    if ! flock -n 8; then printf 'A worker already holds this launcher lock; inspect status/log, not started again.\n'; exit 1; fi
    python3 -u "$recovery_runner" check "${recovery_args[@]}"
    recovery_worker_log=$(mktemp "$recovery_logs/$recovery_job-worker-XXXXXX.log")
    nohup bash "$recovery_script" __run "$recovery_job" >"$recovery_worker_log" 2>&1 < /dev/null &
    recovery_pid=$!
    python3 -u - "$recovery_pid" "$recovery_worker_log" "$recovery_script" "$recovery_meta" <<'GENOS_RECOVERY_PID_PY'
import json,os,sys
from pathlib import Path
pid=int(sys.argv[1]);proc=Path('/proc')/str(pid)
if not proc.exists(): raise RuntimeError('Worker exited during startup; inspect '+sys.argv[2])
stat=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()
record={'pid':pid,'start_time':stat[19],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'log':sys.argv[2],'script':sys.argv[3],'recovery_version':'20261002-r1'}
for path in (Path(sys.argv[2]+'.pid.json'),Path(sys.argv[4])):
    temporary=path.with_name('.'+path.name+'-'+str(os.getpid()))
    temporary.write_text(json.dumps(record,indent=2)+'\n');os.replace(temporary,path)
print('BACKGROUND STARTED pid='+str(pid)+' log='+sys.argv[2]+'; this is not a completion claim',flush=True)
print('Follow: tail -f '+sys.argv[2],flush=True)
GENOS_RECOVERY_PID_PY
    ;;
  stop-off|stop-on|stop-review|status)
    python3 -u - "$recovery_action" "$recovery_logs" "$recovery_old_logs" <<'GENOS_RECOVERY_STATUS_PY'
import json,os,signal,sys
from pathlib import Path
action=sys.argv[1]
paths={'off':Path(sys.argv[2])/'off-worker.json','on':Path(sys.argv[2])/'on-worker.json',
       'review':Path(sys.argv[3])/'worker.json'}
for name,path in paths.items():
    if action!='status' and action!='stop-'+name: continue
    if not path.is_file(): print(name+': no background PID record',flush=True);continue
    record=json.loads(path.read_text());proc=Path('/proc')/str(record['pid']);running=False
    if proc.exists() and record['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        fields=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()
        running=fields[19]==record['start_time'] and fields[0]!='Z'
    print(name+': running='+str(running)+' pid='+str(record['pid'])+' log='+record['log'],flush=True)
    if action=='stop-'+name and running:
        os.kill(record['pid'],signal.SIGINT)
        print('Interrupt sent only to recorded '+name+' worker; wait for FINISHED, artifacts preserved.',flush=True)
GENOS_RECOVERY_STATUS_PY
    if [[ "$recovery_action" == status ]]; then python3 -u "$recovery_runner" status "${recovery_args[@]}"; fi
    ;;
  baseline|review|reviewed)
    recovery_args+=(--shared-root "${GENOS_VARIANTS_SHARED_ROOT:-/nfs-root/diamo/8-agent/term-releases}")
    if [[ "$recovery_internal" == 1 ]]; then exec python3 -u "$recovery_runner" "$recovery_action" "${recovery_args[@]}"; fi
    python3 -u "$recovery_runner" "$recovery_action" "${recovery_args[@]}"
    ;;
  check|verify)
    python3 -u "$recovery_runner" "$recovery_action" "${recovery_args[@]}"
    ;;
esac
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original = (ROOT / ORIGINAL).read_bytes()
    runner = (ROOT / RUNNER).read_bytes()
    if sha(original).encode() not in runner:
        raise ValueError('Runner is not pinned to the exact original R2')
    compile(runner, RUNNER, 'exec')
    files = {RUNNER: runner, 'original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt':original,
             'GUIDE_UTF8.txt':GUIDE.encode()}
    manifest = {'schema_version':'genos-meaning-recovery-code-r1',
                'base_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'files':[{'path':name,'sha256':sha(body),'bytes':len(body)} for name,body in sorted(files.items())],
                'apply_paths':[RUNNER], 'original_preserved':True, 'activated':False}
    archive = OUT / (STEM + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name,body in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,2,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o600 << 16
            z.writestr(info,body)
        z.writestr('CODE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    zip_sha = sha(archive.read_bytes())
    script = SCRIPT.replace('__STEM__',STEM).replace('__ZIP_SHA__',zip_sha).replace('__RUNNER__',RUNNER).replace('__ORIGINAL_SHA__',sha(original))
    txt=OUT/(STEM+'.txt');txt.write_text(script)
    subprocess.run(['bash','-n',str(txt)],check=True)
    (OUT/(STEM+'_GUIDE_UTF8.txt')).write_text(GUIDE)
    handoff={'schema_version':'genos-meaning-recovery-handoff-r1',
             'local_validation_root':str(ROOT),'local_python':str(ROOT/'.venv/bin/python'),
             'base_git_head':manifest['base_git_head'],'original_txt':ORIGINAL,'original_txt_sha256':sha(original),
             'files':{p.name:sha(p.read_bytes()) for p in (archive,txt,OUT/(STEM+'_GUIDE_UTF8.txt'))},
             'runner_sha256':sha(runner),'field_build_verified':False,'field_python':None,
             'field_selected_generation':None,'field_serving_revision':None,'activated':False,
             'core_changes':False,'workflow_changes':False,'git_push':False}
    (OUT/'HANDOFF.json').write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'zip':str(archive),'zip_sha256':zip_sha,'txt':str(txt),'members':list(files)+['CODE_MANIFEST.json']},ensure_ascii=False))


if __name__ == '__main__':
    main()
