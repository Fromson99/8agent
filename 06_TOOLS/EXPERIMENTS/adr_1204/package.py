from common import *
import shutil,zipfile,tempfile,importlib.util
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/source_accordion_main118_20261029_r1'
H.mkdir(parents=True,exist_ok=False);P=H/'package';P.mkdir()
for n,h in f['files'].items():
 assert sha(C/n)==h
 p=P/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
manifest={'format':'8agent-code/1','release_id':RELEASE,'base_release_id':b['active']['release_id'],'base_main':117,'candidate':f['candidate_revision'],'files':[{'path':n,'sha256':h,'bytes':(C/n).stat().st_size} for n,h in sorted(f['files'].items())],'baseline_files':b['manifest']['files'],'field_deployed':False}
(P/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(Path(__file__).with_name('installer.py'),H/'apply_source_patch.py')
shutil.copyfile(C/PRODUCT,H/'GENOS_WORKFLOW_PASTE_ALL.txt')
archive=H/'GENOS_MAIN118_SOURCE_CODE.zip'
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(P.rglob('*')):
  if p.is_file():z.write(p,str(p.relative_to(P)))
checks={}
with zipfile.ZipFile(archive) as z:
 checks['zip_inventory_exact']=set(z.namelist())==set(f['files'])|{'CODE_MANIFEST.json'}
 checks['zip_all466_hashes']=all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in f['files'].items())
checks['paste_all_exact']=sha(H/'GENOS_WORKFLOW_PASTE_ALL.txt')==f['files'][PRODUCT]
spec=importlib.util.spec_from_file_location('source_installer',H/'apply_source_patch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='adr1204-install-') as td:
 T=Path(td)/'checkout';T.mkdir()
 for n in b['manifest']['files']:
  p=T/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/b['manifest']['code_root']/n,p)
 checks['check_one_change']=m.run(T,P)['changes']==[PRODUCT]
 r=m.run(T,P,'apply');checks['apply_one_change']=r['changes']==[PRODUCT] and sha(T/PRODUCT)==f['files'][PRODUCT]
 checks['verify_installed']=m.run(T,P,'verify')['status']=='INSTALLED_BYTES_VERIFIED'
 checks['idempotent']=m.run(T,P,'apply')['status']=='ALREADY_APPLIED'
 before=(T/PRODUCT).read_bytes();(T/PRODUCT).write_bytes(before+b'\n# changed\n')
 try:m.run(T,P,'rollback',r['receipt'])
 except ValueError:checks['reject_rollback_drift']=True
 else:checks['reject_rollback_drift']=False
 (T/PRODUCT).write_bytes(before)
 m.run(T,P,'rollback',r['receipt']);checks['rollback_exact']=all(sha(T/n)==h for n,h in b['manifest']['files'].items())
 (T/'service.py').write_text('unknown checkout\n')
 try:m.run(T,P,'apply')
 except ValueError:checks['reject_unknown_baseline_no_ui_write']=sha(T/PRODUCT)==b['manifest']['files'][PRODUCT]
 else:checks['reject_unknown_baseline_no_ui_write']=False
 checks['other_files_not_packaged']=not any(n.startswith(('01_DATA/','04_EXPERIMENTS/')) for n in f['files'])
assert all(checks.values()),checks
put(ART/'package-checks.json',{'checks':checks,'passed':True,'code_zip':bind(archive),'code_manifest':bind(P/'CODE_MANIFEST.json'),'files':466,'changed_files':1,'field_deployed':False})
put(H/'HANDOFF.json',{'release_id':RELEASE,'candidate_code_root':f['code_root'],'code_zip':bind(archive),'code_manifest':bind(P/'CODE_MANIFEST.json'),'source_renderer_sha256':f['files'][PRODUCT],'local_generation_path':str((ROOT/b['manifest']['data_path']).resolve()),'local_generation_manifest_sha256':b['manifest']['data_manifest_sha256'],'field_checkout':'~/DEV','field_commit':None,'field_generation_path':None,'field_generation_manifest_sha256':None,'field_code_serving_revision':None,'field_revision_generation_setting':None,'genos_deployed':False,'external_model_calls':0})
(H/'GUIDE.txt').write_text('''GENOS 출처 펼치기 — MAIN118 반입 안내

동작: [출처 · N건] → 출처별 네모 상자 → 상자를 누르면 확보한 원문 전체가 아래로 펼쳐집니다.
원문에 없는 내용을 추가하거나 출처를 클릭할 때 모델을 재호출하지 않습니다.

이 폴더는 검증한 MAIN118 코드 466파일, 전체 붙여넣기용 GENOS_WORKFLOW_PASTE_ALL.txt,
MAIN117에서 화면 파일 하나만 바꾸는 apply_source_patch.py를 포함합니다.
코드 ZIP에는 데이터·실험·비밀키가 없습니다. 현장 배포 완료를 뜻하지 않습니다.

실제 업로드한 TRANSFER 폴더에서 실행합니다. TRANSFER의 절대경로를 가정하지 마세요.
압축을 이 이름의 폴더로 푼 뒤 해당 폴더에 들어가 다음 명령을 실행합니다.

set -euo pipefail
mkdir -p logs
python3 apply_source_patch.py check --root "$HOME/DEV" 2>&1 | tee logs/01-check.txt
python3 apply_source_patch.py apply --root "$HOME/DEV" 2>&1 | tee logs/02-apply.txt
python3 apply_source_patch.py verify --root "$HOME/DEV" 2>&1 | tee logs/03-verify.txt
git -C "$HOME/DEV" diff --check
git -C "$HOME/DEV" diff --stat

check는 실제 ~/DEV의 466파일을 비교합니다. MAIN117/118과 다른 checkout은 아무 파일도
덮어쓰지 않고 중단합니다. 다른 버전이라면 그 결과로 기존 변경과 누적 MAIN 차이를 먼저
검토해야 합니다. ZIP을 기존 checkout 전체에 강제 덮어쓰지 마세요.
apply 영수증에 receipt 경로가 나옵니다. 이전 파일은 ~/DEV/.genos-source-backups 아래
보존됩니다. 재실행은 같은 파일이면 ALREADY_APPLIED입니다.

변경 내용을 검토해 현장의 커밋 절차를 마친 다음, 실제 push 대상 checkout에서 검사합니다.
아래 YOUR_SELECTED_GENERATION에는 현장에서 선택한 generation의 절대경로를 넣습니다.
로컬 개발 데이터 경로를 GENOS에 복사해 사용하지 마세요.

python3 "$HOME/DEV/06_TOOLS/run_tool.py" genos_release_gate.py --code-zip "$PWD/GENOS_MAIN118_SOURCE_CODE.zip" --deploy-root "$HOME/DEV" --generation /YOUR_SELECTED_GENERATION 2>&1 | tee logs/04-release-gate.txt

게이트 도구가 구 checkout에 없으면 현재 저장소의 genos_release_gate.py와
genos_generation_e2e.py를 현장 유지보수 경로로 반입한 뒤 같은 checkout을 대상으로 실행합니다.
PASS 이후 현장 Git push·코드서빙 리비전 배포 절차로 이어갑니다.
코드서빙과 워크플로우 편집기는 별개입니다. 편집기 Python Code 노드를 사용하는 경우
GENOS_WORKFLOW_PASTE_ALL.txt의 전체 내용을 반영하고 저장/배포합니다.

현장 확인: 새 리비전의 커밋·generation 경로/manifest 해시를 HANDOFF.json과 함께 기록하고,
원문 조회와 근거 질문의 요청 ID를 남깁니다. 화면에서 출처 버튼, 각 상자 펼침/접힘,
원문의 줄바꿈과 긴 본문을 확인합니다. 실제 GENOS의 HTML 렌더링 허용 여부는 현장 확인 사항입니다.
로컬 브라우저 및 JSON/SSE 검증을 현장 성공으로 간주하지 않습니다.

checkout 파일 되돌리기(리비전 배포 롤백과는 별도):
python3 apply_source_patch.py rollback --root "$HOME/DEV" --receipt /THE_RECEIPT_PATH_FROM_APPLY 2>&1 | tee logs/05-rollback.txt
적용 후 파일이 달라졌으면 되돌리기도 거절합니다. 이미 배포했다면 이전 코드서빙 리비전과
기존 generation, 워크플로우 편집기 이전 버전을 함께 복원해야 합니다.

로컬 MAIN 롤백은 저장소에서 .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main 입니다.
다른 작업의 PIPELINE 변경이 진행 중이면 백업 시점 이후 변경을 먼저 확인합니다.
''')
print('GENOS package verified:',len(checks),'conditions; field deployment pending')
