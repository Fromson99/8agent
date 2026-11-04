import base64
import hashlib
import html
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
NAMES=['DATAIKU_GOLD_DEV_TEST_20261104_R1.zip','DATAIKU_GOLD_DEV_TEST_RUN_R1.txt',
       'DATAIKU_GOLD_DEV_TEST_WATCH_R1.txt','GUIDE.txt','VALIDATION.json']
with zipfile.ZipFile(HERE/NAMES[0]) as z:
    assert len([n for n in z.namelist() if '.part' in n])==2
    assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in z.namelist())
for name in NAMES[1:3]: compile((HERE/name).read_text(),name,'exec')
checks=json.loads((HERE/'VALIDATION.json').read_text())
assert checks['actual_oracle']['status']=='PASS' and checks['delivered_notebook_tests']['failed']==0
assert hashlib.sha256((HERE/NAMES[0]).read_bytes()).hexdigest()==checks['code_zip']['sha256']
(HERE/'EMAIL_SHA256SUMS.txt').write_text(''.join(hashlib.sha256((HERE/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in NAMES))
NAMES.append('EMAIL_SHA256SUMS.txt')
body='''<p>요청하신 개발계 테스트 전용 Flow입니다. <b>예시 데이터는 2조각</b>으로 줄였고 코드 ZIP 안에 함께 넣었습니다. 문서2개·원문3개·검색자료112행·벡터3개 규모입니다.</p>
<p><b>사용 순서</b></p><ol>
<li>개발계에 빈 프로젝트 <b>LEGAL_RAG_DEV_TEST</b>를 만들고, GOLD_TEST_CODE Managed Folder를 실제 개발계 S3 연결로 생성합니다. 연결의 기본 버킷/경로를 유지합니다.</li>
<li><b>DATAIKU_GOLD_DEV_TEST_20261104_R1.zip</b> 하나를 그 폴더에 그대로 업로드합니다.</li>
<li>같은 프로젝트의 Python 노트북에 <b>DATAIKU_GOLD_DEV_TEST_RUN_R1.txt</b> 전체를 붙이고 맨 위의 폴더ID·Oracle연결명·접속계정·대상스키마 네 값을 입력해 실행합니다. 모델ID/차원이나 공유 작업경로가 다른 환경이면 해당 설정도 맞춥니다.</li>
<li><b>TEST_FLOW_READY</b>가 나오면 Scenarios → <b>GTEST_RUN_ALL · 예시 2조각 전체 시험</b> → Run.</li></ol>
<p>설치 셀은 예시 파일과 Flow를 준비합니다. 시나리오를 실행하면 TST_B003_LGL_ 접두어의 테스트13테이블/인덱스를 만들고 적재합니다. 해당 스키마의 생성 권한과 native VECTOR 지원이 필요합니다. 기존 운영 테이블을 바꾸거나 서비스 연결을 전환하지 않습니다.</p>
<p>Flow는 <b>입력 → 복원·준비 → 원문·검색 → 게시 → 벡터 → 결과</b> 여섯 구역으로 구성했습니다. Zones를 켜고 모두 접으면 보기 편합니다. WATCH TXT는 같은 노트북의 새 셀에서 한 화면으로 단계 상태를 확인하는 용도입니다.</p>
<p>완료 시 report.json의 GOLD_LOADED와 문서2·원문단위3·블록3·검색자료112·벡터3을 확인합니다. 자세한 순서·설정·오류별 재개 방법은 GUIDE.txt에 있습니다.</p>
<p>로컬 실제 임시 Oracle에서 전체 적재·응답유실 후 재개·재실행·조회 검증을 통과했습니다. 로컬 검증의 Dataiku SDK와 임베딩은 대역이며, <b>현장 Dataiku/OBS/실제 내부 임베딩 성공은 아직 확인하지 않았습니다.</b> 기존34조각 운영용 패키지와 이번 DEV_TEST 파일은 서로 섞지 마세요.</p>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
records=[]
for name in NAMES:
    raw=(HERE/name).read_bytes()
    mime='application/zip' if name.endswith('.zip') else 'application/json' if name.endswith('.json') else 'text/plain'
    parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment',
                  'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    records.append({'filename':name,'bytes':len(raw),'mime_type':mime,'sha256':hashlib.sha256(raw).hexdigest()})
args={'to':'hyungjininfocz.son@partner.samsung.com',
      'subject':'[개발계 테스트 전용] Gold Flow 간소화 + 예시 데이터 2조각 + 실행 TXT',
      'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(HERE/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
(HERE/'EMAIL_PRECHECK.json').write_text(json.dumps({'to':args['to'],'subject':args['subject'],'attachments':records},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'args_chars':len((HERE/'EMAIL_ARGS.json').read_text()),'attachments':records},ensure_ascii=False))
