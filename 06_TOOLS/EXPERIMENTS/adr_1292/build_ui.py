from common import *
import shutil,zipfile,subprocess
RELEASE='ontology-console-20261103-r1'
release=read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json')
C=ROOT/release['code_root'];F=read(DES/'freeze.json');S=ROOT/F['code_root']
P=ROOT/'08_DEPLOYMENT/DATAIKU/ontology_console_20261103_r1';P.mkdir(exist_ok=False)
for n,h in release['files'].items():
 assert sha(C/n)==h
 dst=P/'code'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(C/n,dst)
front='03_FRONTEND/APPS/legal-knowledge-streamlit'
names=['ontology_app.py','ontology_private_app.py','ontology_console.py','ontology_dashboard.py','ontology_dashboard_model.py','ontology_dashboard_demo.py','app.py']
for n in names:
 assert sha(S/front/n)==sha(ROOT/front/n)
 shutil.copy2(S/front/n,P/n)
(P/'streamlit_app.py').write_text('''"""Verified standalone package entry; configure the existing authenticated host."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
binding=json.loads((ROOT/'package-binding.json').read_text())
for name,expected in binding['files'].items():
    path=ROOT/name
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Ontology UI package changed: '+name)
configured=os.environ.get('GENOS_ONTOLOGY_CODE_ROOT')
if configured and Path(configured).resolve()!=(ROOT/'code').resolve():
    raise RuntimeError('Package backend root mismatch; use this package code or rebuild the binding')
os.environ['GENOS_ONTOLOGY_CODE_ROOT']=str(ROOT/'code')
sys.path.insert(0,str(ROOT))
from ontology_console import main
main()
''')
(P/'GUIDE.txt').write_text(f'''온톨로지 공통 관리 화면 / 2026-11-03 r1

연결 대상: 로컬 {RELEASE}. quality_certified=false.
기존 R4 대시보드의 승인 전용 기능과 자유 작업공간·도메인·시나리오 화면을 함께 제공한다.
이 묶음은 현장 배포 완료 기록이 아니다. 인증·자료·모델 연결은 현장의 기존 설정을 사용한다.

실행: streamlit run streamlit_app.py
필요 패키지는 기존 Streamlit 운영 환경과 해당 Oracle/Dataiku 어댑터 의존성을 사용한다.
code/는 이번에 검증한 전체 서빙 코드다. 기존 라이브러리와 혼합하지 않고 새 프로세스로 시작한다.
package-binding.json은 화면·backend 전체 해시를 검사한다. 원문·DB·비밀번호는 들어 있지 않다.

GENOS_RAG_ONTOLOGY_CONFIG: 운영자가 관리하는 ontology-connection-v1 설정 파일.
로컬은 GENOS_ONTOLOGY_OPERATOR, 원격은 Dataiku 브라우저 인증 사용자로 권한을 확인한다.
operators[사용자].document_ids는 원문 범위, workspace_publish=true는 별도 게시 관리 권한이다.
도메인/작업공간 namespace·source_snapshot·acl_ref가 일치해야 한다.
work_store는 로컬 개발에서만 local, 원격에서는 기존 Dataiku managed folder다.

원격 mapped Gold 호스트:
GENOS_ONTOLOGY_HOST_FACTORY를 운영자가 설치한 모듈:context 함수로 지정한다.
함수는 인증된 요청의 기존 Gold store/request와 별도 관리자 writer_connect를 열고,
semantic_runtime.ontology_work.mapped_authoring.context(actor=인증사용자, store=store,
 request=request, writer_connect=별도관리연결, agent_owner=기존작업표소유자,
 config=설정)를 yield하는 context manager여야 한다. 연결은 렌더 종료 시 닫는다.
호스트는 원래의 문서 권한과 소스 snapshot을 좁히며 DB/자격증명을 브라우저 입력에서 받지 않는다.
로컬 connect.open_store는 새 전용 프로세스 계약을 갖는다. 이를 Streamlit rerun의 공유 전역 연결로
캐시하지 않는다. 현장 호스트의 요청별 어댑터 수명/동시성 검증은 현장 반영 시 별도로 수행한다.
호스트 포트가 없으면 관리 연결만 설정됨/읽기 확인 전으로 표시하고, 원격 용어집 작업은 차단된다.

RAG reader의 workspace_runtime_scopes는 관리자의 쓰기 권한과 별도로 등록한다.
readiness_anchors에는 운영자가 선택한 현재 원문 앵커를 최대16개 지정한다.
미사용/읽기범위없음/게시본없음/읽기확인 상태를 구분하며 오류를 빈 자료로 바꾸지 않는다.
READY는 이 앵커·범위의 게시본과 원문 대조 결과이며 법률 의미 품질 인증이 아니다.
기존 승인 대시보드는 자동 게시하지 않는다. 자유 작업공간은 명시적 승인·소비검증·활성화를 따른다.

검증: 두 실제 앱의 저장·왕복과 공통 화면의 컴파일·승인·활성화, 로컬 Oracle 격리 게시본
새 프로세스 읽기와 철회 차단. 실모델 개선효과·현장 GENOS/Dataiku는 별도 미검증.
원복: MAIN133 포인터/Gold 이전 binding/이전 UI 묶음을 함께 복구한다.
새 계산 답변은 이번 application-v4 reader가 필요하므로 새 저장 namespace를 구 reader로 읽지 않는다.
Oracle layout4 reader를 유지하고 원문/이력/실패 기록은 삭제하지 않는다.
''')
files={str(p.relative_to(P)):sha(p) for p in P.rglob('*') if p.is_file()}
put(P/'package-binding.json',{'schema_version':'ontology-console-package-v1','backend_release_id':RELEASE,
 'backend_release_manifest_sha256':sha(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json'),
 'backend_files':len(release['files']),'candidate_revision':F['candidate_revision'],'files':files,
 'quality_certified':False,'field_deployed':False})
archive=P.with_suffix('.zip')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(P.rglob('*')):
  if p.is_file():z.write(p,p.relative_to(P))
with zipfile.ZipFile(archive) as z:
 for n,h in files.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
 assert json.loads(z.read('package-binding.json'))==read(P/'package-binding.json')
put(OUT/'ui-package.json',{'path':str(P.relative_to(ROOT)),'binding':bind(P/'package-binding.json'),'archive':bind(archive),
 'files':len(files)+1,'backend_files':len(release['files']),'zip_bytes_verified':True,'field_deployed':False})
print('UI package bound',len(files)+1,'files',archive.stat().st_size,'bytes')
