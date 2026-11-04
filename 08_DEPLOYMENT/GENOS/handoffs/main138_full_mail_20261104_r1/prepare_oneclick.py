"""Simplify the already verified installer; preserve the exact validated code ZIP."""
from pathlib import Path
import ast,hashlib,json,shutil,subprocess
OLD=Path(__file__).resolve().parent;R=OLD.parents[3]
H=OLD.with_name('main138_oneclick_mail_20261104_r2');H.mkdir(exist_ok=False)
ZIP='MAIN138_FULL_ORACLE_20261104_R1.zip';RUN='MAIN138_ONECLICK_R2.txt'
shutil.copyfile(OLD/ZIP,H/ZIP)
assert hashlib.sha256((H/ZIP).read_bytes()).hexdigest()=='9eb7075eb2bce51ae94e62f5372b1971538b9b363cbafa5c6c969190e92dca48'
s=(OLD/'MAIN138_FULL_ORACLE_20261104_R1_RUN.txt').read_text()
s=s.replace('export MAIN138_RUN_PATH="$task_dir/MAIN138_FULL_ORACLE_20261104_R1_RUN.txt"',
            'export MAIN138_RUN_PATH="$task_dir/$(basename -- "${BASH_SOURCE[0]}")"')
s=s.replace("parser.add_argument('action',choices=['check','apply','status','stage','gate-code','undo'])",
            "parser.add_argument('action',choices=['check','apply','status','stage','gate-code','undo'],nargs='?',default='apply')")
s=s.replace("parser.add_argument('--root',type=Path,required=True,help='Actual existing Git checkout to overwrite')",
            "parser.add_argument('--root',type=Path,default=Path.home()/'DEV',help='Optional existing checkout; default ~/DEV, resolving links')")
s=s.replace('root=plain(args.root).resolve(strict=True)',
            "root=plain(args.root.expanduser().resolve(strict=True))\n    print('MAIN138_TARGET='+str(root),flush=True)")
s=s.replace("print('MAIN138_CODE_APPLIED BACKUP='+str(backup))",
            "print('MAIN138_CODE_APPLIED BACKUP='+str(backup))\n            print('MAIN138_ONECLICK_DONE: backup, code replacement and engine verification completed')")
assert s!=(OLD/'MAIN138_FULL_ORACLE_20261104_R1_RUN.txt').read_text()
(H/RUN).write_text(s)
subprocess.run(['bash','-n',str(H/RUN)],check=True)
python=s.split("<<'MAIN138_INSTALL_PY'\n",1)[1].rsplit('\nMAIN138_INSTALL_PY',1)[0]
ast.parse(python,feature_version=(3,11))
shutil.copyfile(OLD/'ENVIRONMENT.txt',H/'ENVIRONMENT.txt')
(H/'GUIDE.txt').write_text('''MAIN138 딸깍 적용 — R2

실행 위치: GENOS 코드스페이스의 TRANSFER 폴더.
같은 TRANSFER 폴더에 아래 두 첨부를 그대로 둡니다. 압축은 풀지 않습니다.
  MAIN138_FULL_ORACLE_20261104_R1.zip
  MAIN138_ONECLICK_R2.txt

터미널에서 이것만 실행합니다.

bash MAIN138_ONECLICK_R2.txt

별도 export, --root, check/apply/status 입력이 필요 없습니다.
~/DEV의 실제 경로를 자동으로 찾으므로 /home/genos/DEV가 링크여도 실행됩니다.
출력 MAIN138_TARGET으로 적용 대상을 표시한 뒤 ZIP/기존 필수파일 확인 → 기존 코드 백업 → 전체 목록 덮어쓰기 → 엔진 해시검증을 수행합니다.
완료 표시는 MAIN138_ONECLICK_DONE입니다. 정상 적용 후 같은 명령을 다시 실행해도 중복 백업/덮어쓰기 없이 같은 코드를 검증합니다.

이전 메일의 긴 MAIN138_FULL_ORACLE_20261104_R1_RUN.txt 대신 이번 MAIN138_ONECLICK_R2.txt를 사용합니다.
ZIP은 이전에 보낸 R1과 SHA-256까지 같은 검증본이며 코드내용 변경은 없습니다. 새 메일에도 그대로 첨부했습니다.
ZIP SHA256: 9eb7075eb2bce51ae94e62f5372b1971538b9b363cbafa5c6c969190e92dca48

기존 데이터·.env·Git 이력·PeCab/pyarrow는 유지합니다. 기존 app.js 1개는 메일 첨부제외 규칙에 따라 유지하고 먼저 해시를 검사합니다.
실행 로그는 TRANSFER/main138-install-logs, 원래 코드 백업은 DEV/09_ARTIFACTS/BACKUPS/code-replacement에 남습니다.
스크립트 파일명이 다운로드 때 바뀌어도 자신의 위치를 찾아 실행하지만, 함께 둔 ZIP 이름은 위 이름을 유지해야 합니다.

코드 적용 이후
이 명령이 완료하는 범위는 checkout 코드 적용/검증입니다. 원격 Git push나 코드서빙 배포, 비밀 환경변수 입력은 자동 실행하지 않습니다.
필요하면 다음 명령으로 전달본 파일만 stage하고, 현장의 기존 commit/push/새 리비전 배포 절차를 진행합니다.
bash MAIN138_ONECLICK_R2.txt stage
commit 후 코드와 첨부 ZIP이 같은지 확인:
bash MAIN138_ONECLICK_R2.txt gate-code
ENVIRONMENT.txt의 Oracle 매핑·벡터 모드·임베딩 MODEL/PROFILE_SHA256을 실제 코드서빙 환경에 설정합니다.
실제 질문은 새 리비전의 워크플로우 테스트 화면에서 확인합니다. 현장 실제 임베딩/답변 완료는 아직 미확인입니다.

오류/복구
~/DEV 또는 ZIP이 없으면 시작 단계에서 중단합니다. 적용 대상이 DEV가 아닌 특수환경만 --root 실제경로를 선택적으로 사용할 수 있습니다.
파일/백업이 다른 작업으로 바뀐 경우 해당 변경을 덮어쓰지 않고 중단합니다.
강제중단 후 복구 요청이 나오면 로그에 출력된 백업경로로 다음을 실행하고 같은 한 줄을 다시 실행합니다.
bash MAIN138_ONECLICK_R2.txt undo --backup '로그에 나온 백업 폴더 절대경로'
''')
(H/'HANDOFF.json').write_text(json.dumps({'revision':'oneclick-r2','zip_preserved':True,'zip_sha256':hashlib.sha256((H/ZIP).read_bytes()).hexdigest(),
 'run':RUN,'default_action':'apply','default_root':'~/DEV resolved to physical path','original_main':138,'field_deployed':False},ensure_ascii=False,indent=2)+'\n')
print(str(H))
