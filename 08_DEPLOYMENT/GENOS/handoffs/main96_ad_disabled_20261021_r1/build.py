"""Small MAIN95 -> MAIN96 patch; never replaces ignore or deployment settings."""
from pathlib import Path
import ast, hashlib, json, subprocess, zipfile

H=Path(__file__).resolve().parent;R=H.parents[3]
A=R/'09_ARTIFACTS/AUDITS/20261021-ad-disabled'
N='GENOS_MAIN96_AD_DISABLED_20261021_R1'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (H/'SEALED.json').exists()
before=read(A/'BEFORE.json')['files'];after=read(A/'frozen.json')['target_files'];stage=R/read(A/'frozen.json')['candidate_root']
patch=[n for n in after if before.get(n)!=after[n]]
assert len(patch)==34
base=H.with_name('basis_entry_fix_20261020_r1')
runner=(base/'runner.py').read_text().split('\ndef main():')[0]
runner+='''
def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['check','apply','gate','gate-code','gate-sqlite','rollback','status'])
    p.add_argument('--root',type=Path,default=Path.home()/'DEV')
    args=p.parse_args();root=checkout_root(args.root);spec=load()
    with plain(HERE/'installer.lock').open('a') as lock:
        fcntl.flock(lock, (fcntl.LOCK_EX if args.command in ('apply','rollback') else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        bind_root(root)
        if args.command=='check':check(root,spec);print('CHECK_PASS')
        elif args.command=='apply':apply(root,spec)
        elif args.command=='rollback':rollback(root,spec)
        elif args.command=='status':print(STATE.read_text() if STATE.exists() else 'NOT_INSTALLED')
        else:
            gate(root,spec)
            if args.command in ('gate-code','gate-sqlite'):
                command=[sys.executable,str(HERE/'genos_release_gate.py'),'--code-zip',str(HERE/'code.zip'),'--deploy-root',str(root)]
                if args.command=='gate-code':command+=['--code-only']
                return subprocess.call(command,cwd=root)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc:
        print('FAILED: '+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(2)
'''
(H/'runner.py').write_text(runner)
(H/'genos_release_gate.py').write_bytes((R/'06_TOOLS/COMMANDS/genos_release_gate.py').read_bytes())
run=(base/'GENOS_BASIS_ENTRY_FIX_20261020_R1_RUN.txt').read_text().replace('GENOS_BASIS_ENTRY_FIX_20261020_R1',N).replace('basis-entry-fix-r1-logs','main96-ad-disabled-r1-logs').replace('BASIS_BATCH_EXIT','MAIN96_AD_DISABLED_EXIT')
(H/(N+'_RUN.txt')).write_text(run)
for n in patch:
    assert sha(stage/n)==after[n]
    p=H/'payload'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((stage/n).read_bytes())
manifest={'format':'8agent-code/1','files':[{'path':n,'sha256':after[n],'bytes':(stage/n).stat().st_size} for n in patch],
          'required_files':[{'path':n,'sha256':h} for n,h in after.items() if n not in patch]}
put(H/'CODE_MANIFEST.json',manifest)
with zipfile.ZipFile(H/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    z.write(H/'CODE_MANIFEST.json','CODE_MANIFEST.json')
    for n in patch:z.write(stage/n,n)
(H/'COMMIT_PATHS.txt').write_text('\n'.join(patch)+'\n')
(H/'PATCH_NOTE.txt').write_text(f'''MAIN96 — 사용하지 않는 관리자 모드 차단

원인: 일반 질문에서 관리 세션을 먼저 검사해, 요청 team_id가 있어도 별도 서버 TEAM_ID를 요구했습니다.
수정: 기존 ad_management.enabled=false. 일반 질의의 관리 세션·workspace 검사, 관리 시작/종료, 자동 예약 복구를 차단합니다. 코드는 삭제하지 않습니다.
내규·외규 대사와 확정 연결, 팀·문서 범위, 기존 원문·관계·관리 이력은 유지합니다.
MAIN95 + ignore 추가 패치 위에 적용하는 작은 코드 패치입니다. ignore와 .env/현장 경로·데이터를 덮어쓰지 않습니다. MAIN95 누적 ZIP 재설치는 필요 없습니다.

실제 업로드한 TRANSFER 폴더를 현재 위치로 두고 실행하세요. 사진에서 확인한 기존 checkout은 /workspace입니다.
python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt check --root /workspace
bash ./{N}/{N}_RUN.txt apply --root /workspace
bash ./{N}/{N}_RUN.txt gate --root /workspace

위 apply는 코드만 적용합니다. 기존 관리 예약/세션을 삭제하거나 정상 법률 질문의 권한을 해제하지 않습니다. 옛 프로세스가 실행 중이면 새 코드서빙 리비전 배포 전까지 옛 코드가 동작합니다.
확인한 변경을 기존 checkout에서 commit한 뒤, TRANSFER에서 아래 검사를 실행하세요.
bash ./{N}/{N}_RUN.txt gate-code --root /workspace
현재 SQLite/NFS 운영이면 선택 세대까지 검사하세요. Oracle 운영에서는 이 명령을 쓰지 않습니다.
bash ./{N}/{N}_RUN.txt gate-sqlite --root /workspace
PASS 커밋을 push하고 같은 커밋으로 코드서빙 리비전을 배포한 다음, 워크플로우 테스트 화면에서 일반 질문/대사를 확인합니다. 워크플로우 편집기 변경은 없습니다.
기존 MAIN95/ignore 패치의 고정 코드 gate 대신 이번 gate를 사용합니다. ignore 규칙·로컬 exclude는 유지됩니다.

재실행: 같은 apply로 이어서 확인합니다. 로그/백업/INSTALL_STATE.json을 지우지 마세요.
원복: bash ./{N}/{N}_RUN.txt rollback --root /workspace
원복 코드는 관리 모드가 다시 켜진 MAIN95이며 이번 오류도 다시 발생할 수 있습니다. 원복 후에도 별도 commit/push/리비전 변경이 필요합니다.
GENOS 현장 적용·배포·내부 모델 결과는 아직 확인하지 않았습니다.
''')
files=['runner.py','genos_release_gate.py',N+'_RUN.txt','PATCH_NOTE.txt','CODE_MANIFEST.json','COMMIT_PATHS.txt','code.zip']+['payload/'+n for n in patch]
for n in files:
    if n.endswith('.py'):ast.parse((H/n).read_bytes(),filename=n,feature_version=(3,11))
subprocess.run(['bash','-n',str(H/(N+'_RUN.txt'))],check=True)
put(H/'PACKAGE.json',{'version':N,'base_release':'comparison-display-scope-20261020-r1','code':after,'patch':patch,
    'allowed_before':{n:list(dict.fromkeys([before.get(n),h])) for n,h in after.items()},
    'payload':{n:sha(H/n) for n in files},'management_enabled':False,'GENOS_field_verified':False})
with zipfile.ZipFile(H/(N+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n in sorted(files+['PACKAGE.json']):z.write(H/n,n)
put(H/'BUILD.json',{'archive':N+'.zip','sha256':sha(H/(N+'.zip')),'bytes':(H/(N+'.zip')).stat().st_size,'patch_files':len(patch),'required_code_files':len(after),
    'source_root':str(stage),'ignore_written':False,'data_written':False})
print((H/'BUILD.json').read_text())
