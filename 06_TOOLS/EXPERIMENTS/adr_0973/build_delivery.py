"""Package exact activated MAIN bytes for the existing DEV checkout."""
from common import *
import shutil,subprocess,zipfile,ast
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs';P=H/'structured_selection_20261021_r1';P.mkdir(exist_ok=False)
OLD=H/'natural_language_routing_20261021_r1';NAME='GENOS_STRUCTURED_SELECTION_20261021_R1'
s=read(ART/'stage.json');pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path']);C=ROOT/release['code_root']
assert pointer['generation']==s['base_pointer']['generation']+1 and release['files']==s['files']['candidate']
assert read(ART/'consumer-active.json')['status']=='PASS' and read(ART/'result.json')['strict_success']
files=s['files']['candidate'];assert all(sha(C/n)==h and sha(ROOT/n)==h for n,h in files.items())
old=read(OLD/'PACKAGE.json');base=read(ROOT/'09_ARTIFACTS/AUDITS/20261021-natural-language-routing/GENOS_CODE.json')['base_code']
for n in sorted(files):
 dst=P/'payload'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,dst)
 if n.endswith('.py'):ast.parse(dst.read_bytes(),filename=n,feature_version=(3,11))
for n in ('runner.py','genos_release_gate.py'):shutil.copyfile(OLD/n,P/n)
run=(OLD/'GENOS_NATURAL_LANGUAGE_ROUTING_20261021_R1_RUN.txt').read_text().replace('GENOS_NATURAL_LANGUAGE_ROUTING_20261021_R1',NAME).replace('natural-language-routing-r1-logs','structured-selection-r1-logs').replace('NATURAL_LANGUAGE_ROUTING_EXIT','STRUCTURED_SELECTION_EXIT')
(P/(NAME+'_RUN.txt')).write_text(run);subprocess.run(['bash','-n',str(P/(NAME+'_RUN.txt'))],check=True)
manifest={'format':'8agent-code/1','files':[{'path':n,'sha256':h,'bytes':(C/n).stat().st_size} for n,h in sorted(files.items())],'required_files':[]}
save(P/'CODE_MANIFEST.json',manifest)
with zipfile.ZipFile(P/'code.zip','x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 z.write(P/'CODE_MANIFEST.json','CODE_MANIFEST.json')
 for n in sorted(files):z.write(C/n,n)
(P/'COMMIT_PATHS.txt').write_text('\n'.join(sorted(files))+'\n')
shutil.copyfile(C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',P/'GENOS_WORKFLOW_PYTHON.txt')
analysis=read(ART/'analysis.json');counts={a:sum(r['pass'] for r in ts) for a,ts in analysis['by_arm'].items()}
workflow=read(ART/'consumer-active.json')['workflow_version']
(P/'GUIDE.txt').write_text(f'''GENOS 구조화 범위·복수·제외 선택 R1

검증한 로컬 MAIN {pointer['generation']} / workflow {workflow}의 서빙419파일을 그대로 담았다.
범위·복수·제외의 의미는 LLM이 판단하고 실제 저장 조·항·호·목 집합을 조회·읽는다.
초기·후속 질문의 범위 판단 필드를 필수 출력으로 바꾸고 이상·초과·이하·미만 비교 연산을 명시했다.
질문을 문서 목록으로 보내던 자연어 어미 분기 제거, 기존 멀티턴 범위와 법령명 복구도 포함한다.

적용 가능한 기존 코드: RAG_RECOVERY_ALL_20261021_R2 + DEV_SEARCH_SELECTION_20261021_R1,
그 위의 NATURAL_LANGUAGE_ROUTING_20261021_R1, 또는 MAIN98의 확인된 바이트.
서로 다른 사용자 변경은 check에서 거부하며 자동 덮어쓰기하지 않는다.
환경설정·00_SYSTEM/GENOS_SERVING_PATHS.json·00_SYSTEM/SEARCH_SELECTION·데이터·원문·색인은 변경하지 않는다.
이 패키지는 데이터 저장 구조를 전환하는 작업이 아니다. Oracle/조회 API 설정과 실제 사용하는 데이터 버전을 유지한다.

실제 업로드한 TRANSFER 폴더에서 아래 명령을 실행한다. TRANSFER의 절대 위치를 가정하지 않는다.
처음 압축 해제부터 로그를 남기려면 아래 블록을 그대로 실행한다.

mkdir -p ./structured-selection-r1-logs
python3 -m zipfile -e ./{NAME}.zip ./{NAME} > ./structured-selection-r1-logs/extract.log 2>&1
TASK_EXTRACT_RC=$?
printf '%s\\n' "$TASK_EXTRACT_RC" > ./structured-selection-r1-logs/extract.exit
if [ "$TASK_EXTRACT_RC" -ne 0 ]; then cat ./structured-selection-r1-logs/extract.log; else
  bash ./{NAME}/{NAME}_RUN.txt check
fi

check 성공 후:
bash ./{NAME}/{NAME}_RUN.txt apply
bash ./{NAME}/{NAME}_RUN.txt gate

기본 적용 대상은 기존 ~/DEV Git checkout이다. 실제 경로를 해석해 ROOT_BINDING.json에 결속한다.
별도 후보 폴더에만 설치하지 않는다. check/apply/gate는 TRANSFER 위치에서 실행한다.
적용 전 파일은 패키지 backup에 보존하고 INSTALL_STATE.json에 파일별 이전/이후 SHA를 기록한다.
중단 뒤 같은 apply를 재실행하면 이미 적용된 파일을 확인하고 남은 파일만 이어 적용한다.
확인할 수 없는 변경·권한·해시 불일치가 있으면 로그와 실패 상태를 남긴다.

워크플로우 편집기
코드 ZIP 적용과 GENOS 워크플로우 Python 편집기 반영은 별도다.
현재 편집기 내용을 백업한 뒤 동봉 GENOS_WORKFLOW_PYTHON.txt를 Python 단계에 반영한다.
이는 위 코드의 08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py와 정확히 같은 내용이다.
동일 파일이 이미 반영된 경우 해시를 확인한다. 편집기 반영 성공을 ZIP 적용 성공으로 대신하지 않는다.

Git 및 코드서빙 리비전
~/DEV에서 변경을 검토하고 git diff --check를 수행한다. COMMIT_PATHS.txt에 이번 서빙파일 목록이 있다.
기존 환경설정·선택 JSON은 원래의 검증·추적 상태를 보존한다. 다른 staged 작업을 섞지 않는다.
커밋한 실제 checkout을 아래 명령으로 검사한다(TRANSFER에서 실행).
bash ./{NAME}/{NAME}_RUN.txt gate-code
코드가 다시 바뀌면 새 커밋으로 게이트를 다시 실행한다. 확인한 커밋을 push한 후 같은 커밋으로 서빙 리비전을 배포한다.
코드 적용·커밋·push·리비전 배포·워크플로우 편집기 반영·질의 성공은 각각 별도 상태다.
기존 generation을 사용하는 환경은 기존 checkout 도구로 다음 검사를 순차 실행한다.
bash ./{NAME}/{NAME}_RUN.txt gate-sqlite
실제 선택 generation 경로·manifest SHA를 기록한다. 이 검사는 데이터 생성/복원 명령이 아니다.
Oracle 조회 환경은 위 SQLite 검사를 대신 실행한 것으로 보고하지 말고 실제 조회 API의 데이터 버전·권한·응답 원문을 확인한다.

현장 질의는 워크플로우 테스트 화면에서만 실행한다. 코드서빙 직접 테스트 UI/API는 요구하지 않는다.
- 실제 존재하는 규정·부모 조항으로 1호~3호 / 1호에서 3호까지 / 1호부터 3호까지.
- 1~3호와 7호, 5호 빼고 전부, 2~8호 중 4~6호 제외.
- 번호가 4 이하/미만/이상/초과, 다른 항의 호들, 가목~다목, 여러 문서.
- '5호에는 해당하지 않는다고 가정'을 원문 읽기 제외로 바꾸지 않는지 확인.
- 전부 제외한 요청, 없는 끝 번호, 후속 질문·동일 요청 재실행을 확인.
요청 ID·코드 커밋·리비전·데이터 버전·실제 내부 모델 ID·구조화 판단·선택 원문·답변을 함께 기록한다.

외부 검증: 새 합성32질문, Qwen3.8 / Parasail FP8 / reasoning none / no fallback.
기존 {counts['baseline']}/32, 후보 {counts['candidate']}/32의 정확한 범위 원문 읽기(또는 안전한 빈 선택).
전체 법률 답변 품질이나 GENOS 내부 모델의 현장 성능을 인증한 결과는 아니다.
최종 계약 {read(ART/'contracts-final.json')['tests']}개, 로컬 선택 서비스 HEALTH/코드·데이터·모델 설정 검사와 ZIP 설치 모의 검사를 별도 기록한다.
현장 코드 반입·push·리비전 배포·내부 모델 질의 성공은 현재 미확인이다.

복원(TRANSFER에서):
bash ./{NAME}/{NAME}_RUN.txt rollback
새 사용자 수정이 있으면 복원을 거부해 보존한다. 코드 복원 뒤 Git 커밋/이전 리비전 선택은 별도다.
워크플로우 편집기도 백업한 버전으로 별도 복원한다. 데이터는 이 설치기가 변경하지 않는다.
''')
pack=['runner.py','genos_release_gate.py',NAME+'_RUN.txt','CODE_MANIFEST.json','COMMIT_PATHS.txt','code.zip','GUIDE.txt','GENOS_WORKFLOW_PYTHON.txt']+['payload/'+n for n in sorted(files)]
allowed={n:list(dict.fromkeys(([base[n]] if n in base else [None])+([old['code'][n]] if n in old['code'] else [])+([s['files']['baseline'][n]] if n in s['files']['baseline'] else [])+[h])) for n,h in files.items()}
save(P/'PACKAGE.json',{'version':NAME,'base_release':'R2+DEV_SELECTION, NATURAL_LANGUAGE_ROUTING_R1, or exact MAIN98','code':files,'patch':sorted(files),'allowed_before':allowed,'payload':{n:sha(P/n) for n in pack},'workflow_version':workflow,'GENOS_field_verified':False,'data_modified':False,'local_release':pointer})
with zipfile.ZipFile(P/(NAME+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in sorted(pack+['PACKAGE.json']):z.write(P/n,n)
with zipfile.ZipFile(P/(NAME+'.zip')) as z:assert z.testzip() is None
save(P/'BUILD.json',{'archive':NAME+'.zip','sha256':sha(P/(NAME+'.zip')),'bytes':(P/(NAME+'.zip')).stat().st_size,'code_files':len(files),'verified_code_root':str(C),'local_active_release':pointer,'qualification':{'path':str((ART/'result.json').relative_to(ROOT)),'sha256':sha(ART/'result.json')},'GENOS_checkout':'~/DEV, resolved and recorded on site','GENOS_commit':None,'GENOS_generation_path':None,'GENOS_generation_manifest_sha256':None,'GENOS_serving_revision':None,'GENOS_revision_generation_setting':None,'GENOS_field_verified':False})
print('Built',P/(NAME+'.zip'))
