from pathlib import Path
import hashlib,json
out=Path(__file__).resolve().parent
archive=out/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip'
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
script=r'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
handoff_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
handoff_mode="${1:-check}"
handoff_root="${MAIN_DEV_ROOT:-$HOME/DEV}"
handoff_logs="${GENOS_HANDOFF_LOG_DIR:-$handoff_dir/v6-r4-logs}"
mkdir -p "$handoff_logs"
handoff_log="$handoff_logs/$(date -u +%Y%m%dT%H%M%SZ)-${handoff_mode}-$$.log"
exec > >(tee -a "$handoff_log") 2>&1
trap 'handoff_exit=$?; trap - EXIT; printf "HANDOFF_EXIT=%s MODE=%s LOG=%s\n" "$handoff_exit" "$handoff_mode" "$handoff_log"; exit "$handoff_exit"' EXIT
printf 'HANDOFF_START ROOT=%s MODE=%s LOG=%s\n' "$handoff_root" "$handoff_mode" "$handoff_log"
python3 - "$handoff_dir/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip" "$handoff_root" "$handoff_mode" "${2:-}" <<'GENOS_V6_PY'
import hashlib,json,os,subprocess,sys,types,zipfile
from pathlib import Path
print('PYTHON',sys.executable,sys.version.replace('\n',' '),flush=True)
if sys.version_info < (3,11): raise ValueError('Python 3.11+ required')
archive=Path(sys.argv[1]).resolve(strict=True);root=Path(sys.argv[2]).resolve(strict=True)
mode=sys.argv[3];argument=sys.argv[4]
expected='__ZIP_SHA256__'
actual=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
if actual!=expected:raise ValueError('R4 code ZIP SHA256 mismatch')
print('CODE_ZIP_SHA256',actual,flush=True)
with zipfile.ZipFile(archive) as z:
 raw=z.read('06_TOOLS/OFFLINE/genos_code_replace.py')
 manifest=json.loads(z.read('CODE_MANIFEST.json'))
 names={r['path']:r for r in manifest['files']}
 if hashlib.sha256(raw).hexdigest()!=names['06_TOOLS/OFFLINE/genos_code_replace.py']['sha256']:raise ValueError('Installer manifest mismatch')
 installer=types.ModuleType('r4_checked_installer')
 installer.__file__=str(archive.parent/'checked-installer.py')
 exec(compile(raw,'checked-installer.py','exec'),installer.__dict__)
if mode in ('check','apply'):
 with installer.plain(root/'.genos-code-replacement.lock').open('a') as stream:
  import fcntl
  fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
  installer.install(root,archive.parent,apply=mode=='apply',archive=archive)
elif mode=='verify':
 content,units,delivery=installer.full_payload(archive)
 for name,(raw,permissions) in content.items():
  target=installer.plain(root/name)
  if not target.is_file() or installer.sha(target.read_bytes())!=installer.sha(raw):raise ValueError('Installed file differs: '+name)
 print('INSTALLED_BYTES_VERIFIED',len(content),flush=True)
elif mode=='gate':
 command=[sys.executable,str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),'--code-zip',str(archive),'--deploy-root',str(root)]
 generation=os.environ.get('GENOS_GENERATION')
 if generation:
  selected=Path(generation).resolve(strict=True)
  print('SELECTED_GENERATION',selected,'MANIFEST_SHA256',installer.sha((selected/'manifest.json').read_bytes()),flush=True)
  command+=['--generation',str(selected)]
 subprocess.run(command,cwd=root,check=True)
elif mode=='rollback':
 if not argument:raise ValueError('Supply exact BACKUP/RECOVERY path printed by apply')
 backup=Path(argument).resolve(strict=True)
 receipt=json.loads((backup/'receipt.json').read_text())
 if Path(receipt['root']).resolve()!=root:raise ValueError('Rollback root mismatch')
 with installer.plain(root/'.genos-code-replacement.lock').open('a') as stream:
  import fcntl
  fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
  installer.rollback(backup)
else:raise ValueError('Modes: check apply verify gate rollback')
print('HANDOFF_MODE_COMPLETE',mode,'GENOS_DEPLOYMENT=NOT_VERIFIED',flush=True)
GENOS_V6_PY
'''.replace('__ZIP_SHA256__',digest)
(out/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt').write_text(script)
guide='''GENOS 누적 v6 R4 — R2 이후 개발분 통합 / 판단·답변 검증 LLM 제거

사용 버전: 이 R4 ZIP과 R4 실행 TXT를 같이 사용합니다. service/service.py는 이미 반영하신
R3 어댑터와 같은 바이트입니다. 이 인계로 워크플로우 편집기를 바꾸거나 main.py를 삭제하지 않습니다.
이전 R2 전체 ZIP 재적용 및 잘못된 진입 파일 롤백 R1/R2 대신 R4를 사용합니다.

추가 반영:
1) 검색된 항·호·목 직접 원문 + 해당 단위/항/조 subtree 펼치기 선택.
2) 정참조·역참조 후보 묶음 탐색과 실제 FOLLOW된 원문의 후속 판단/출력/경험 소비.
3) 압축 연결 메뉴, 생략 묶음 표시, 잘못된 ID/READ scope 쌍의 1회 재선택.
4) 판단 후 memory-assess-check, 답변 후 memory-compose-check LLM 호출 제거.
5) 최근 fulltext builder/manifest dispatch/정확 위치, NFS DELETE 저널, 후속 fulltext 실행기 보존.

코드 ZIP과 실행 TXT를 기존 ~/DEV/TRANSFER에 올린 뒤 실행:
cd -P ~/DEV
bash TRANSFER/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt check
bash TRANSFER/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt apply
bash TRANSFER/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt verify

전체 stdout/stderr·종료코드는 실행 TXT 옆 v6-r4-logs에 처음부터 기록합니다.
기존 ~/DEV의 ZIP manifest 파일만 파일별 백업 후 적용하며 실제 .env/.git/데이터/경험 DB는 보존합니다.
재실행은 동일 설치 상태를 확인합니다. 별도 후보 폴더만 풀고 끝나는 방식이 아닙니다.
새 의존성은 추가하지 않았습니다. 현장 실행 명령은 python3이며 실제 경로·버전을 기록합니다.

핵심 조건:
단위 탐색은 실제 선택 generation의 fulltext manifest가 semantic-unit-fulltext-v1일 때 v6에 자동
결속합니다. 조 단위 색인을 선택하면 기존 조 단위 회수 경로입니다. 코드 적용만으로 현재 색인이
단위 색인으로 바뀌지는 않습니다. 완료 navigation에서 fulltext만 새로 만들려면:
python3 06_TOOLS/pipeline.py fulltext --generation /정확한/완료/generation --output /별도/새/generation --granularity unit --workers 2
위 두 경로는 현장에서 확인한 절대경로로 지정합니다. 원래 generation을 덮어쓰지 않습니다.
미완료 reindex를 서빙 세대로 선택하지 마세요. 단위 fulltext 산출물의 전체 서빙 검증은 별도입니다.

기존 코드서빙 설정은 유지합니다:
GENOS_RAG_IMPLEMENTATION=legal-agent-unified-v6
GENOS_RUNTIME_DIR=/nfs-root/diamo/8-agent/runtime
GENOS_MEMORY_JOURNAL_MODE=DELETE
기존 내부 모델 ID/endpoint/서명키/TEAM_ID와 선택된 generation은 그대로 확인합니다. 키를 로그로 출력하지 않습니다.
기존 경험은 실행 코드 binding이 달라진 뒤 자동 승인/재사용하지 않고 재조사 대상으로 남을 수 있습니다.
사용자 확정 경험을 법률 품질 인증으로 해석하지 않습니다.

Git commit/push, 새 코드서빙 리비전 배포, generation 선택, 워크플로우 확인은 각각 별도입니다.
ZIP manifest 파일을 검토 후 해당 Git checkout에서 commit하고:
bash TRANSFER/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt gate
정확한 generation을 명시하려면 GENOS_GENERATION=/실제/선택/generation을 명령 앞에 지정합니다.
생략하면 기존 설정/CURRENT에서 선택하는 현행 gate를 사용하며 실제 선택을 로그에 남깁니다.
gate는 동일 commit+ZIP+generation 검사이며 push/배포/품질 인증을 수행하지 않습니다.
검사한 commit을 push하고 새 코드서빙 리비전에서 기존 Python 워크플로우 연결을 유지합니다.
최종 질문·warmup은 워크플로우 테스트 화면에서만 수행합니다. 코드서빙 직접 테스트 UI/API 실행은 요구하지 않습니다.

현장 확인:
질문 반환·출처, 항/호/목 정확 READ, FOLLOW된 참조 본문, 원장 모델 phase를 확인합니다.
memory-assess-check 및 memory-compose-check 호출이 없어야 합니다. 검토 상태는 SKIPPED/UNREVIEWED이며
quality_certified=false입니다. 인용·해시·권한·현재 revision·형식 검사는 유지합니다.
정정→재검색→확정→두 위키→새 대화 재사용은 실제 내부 모델과 NFS에서 확인해야 합니다.
현재 연결 수집의 조 단위 범위, CM003 예외 미열람, CM051 ID/scope 실패는 미해결입니다.
현재 항·호·목에 연결된 후보만 우선 제시하는 요구를 구현 완료로 보고하지 않습니다.

복구:
bash TRANSFER/GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.txt rollback /apply가_출력한_정확한_BACKUP_RECOVERY_폴더
동시 변경 파일은 덮어쓰지 않고 중단합니다. 데이터/경험 DB는 삭제하지 않습니다.
배포 후에는 이전 검증 코드서빙 리비전과 이전 generation 선택도 별도로 되돌립니다.

로컬 모의 계약/인계 검증 기록은 VALIDATION.json입니다. 실제 GENOS 반입/배포/내부 모델 품질은 미확인입니다.
소스 SHA256: '''+digest+'\n'
(out/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4_GUIDE_UTF8.txt').write_text(guide)
