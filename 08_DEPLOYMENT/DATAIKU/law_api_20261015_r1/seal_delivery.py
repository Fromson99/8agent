import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from dotenv import dotenv_values
from docx import Document

sys.path.insert(0,'02_BACKEND')
from lawrag.platform.paths import root_path, repository_root
OUT=root_path('deployment','DATAIKU','law_api_20261015_r1')
ROOT=repository_root()
NAME='DATAIKU_LAW_API_20261015_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
paths=['02_BACKEND/lawrag/sources/lawgo.py','02_BACKEND/lawrag/sources/base.py',
       '02_BACKEND/lawrag/sources/common.py','02_BACKEND/lawrag/sources/__init__.py',
       '02_BACKEND/lawrag/pipeline/collect.py','00_SYSTEM/WORKSPACE.json',
       '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
binding={'purpose':'Read-only source contract mapping; no collector or MAIN modifications',
         'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
         'files':[{'path':p,'sha256':sha((ROOT/p).read_bytes())} for p in paths],
         'helper_sha256':sha((OUT/'relay_check.py').read_bytes()),
         'public_call_count':{'initial_current_parser_check':4,'delivery_helper_check':5,'total':9},
         'samsung_internal_calls':0,'genos_calls':0,'model_calls':0,
         'screenshot_basis':['photo 1: curl and target_url; credentials omitted','photo 2: supported upstream URLs',
                             'photo 3: development relay and IP lookup','photo 4: intermediary network architecture']}
(OUT/'SOURCE_BINDING.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n')
v=json.loads((OUT/'VALIDATION.json').read_bytes())
assert v['status']=='PASS' and v['relay_helper_sha256']==binding['helper_sha256']
summary='''Dataiku 법령 API Notebook 검증 요약 / 2026-10-15 R1

확인됨
- 외부 법제처 공개 API 실수신: 최초 4회, 인계 공통 코드 5회, 총 9회.
- 같은 인계 코드의 5개 확인 모두 성공: 법령 공포일 본문, 법령 목록, 행정규칙 목록/본문, 법령 시행일 본문.
- 오류/무결성 계약 검사 22개 통과, 실패/오류 0.
- 실제 첨부 Notebook 8개 코드 셀과 전체 RUN.txt를 모의 중계에서 각각 실행.
- 각각 5회 호출, 재실행 시 추가 호출 0회, Managed Folder 저장/재읽기 12파일 검증.
- curl 재현용 Python TXT를 모의 프로세스로 실행하고 키가 명령행 인자에 노출되지 않는지 확인.
- Python 3.9 구문 검사, Notebook 저장 출력 없음, 등록 OC 미포함 확인.

현장 확인 필요
- 사내 Dataiku/삼성 중계/GENOS 접속 0회. 네트워크/CA/인증/등록 API 범위/실제 UI 미확인.
- 사진의 명시 지원 목록에 eflaw와 법령/행정규칙 일반 검색, 별표 다운로드가 전부 보이지 않음.
- law 본문 성공만으로 eflaw/별표/모든 법령 API 지원을 판정하지 않음.
- 예고/운영 IP는 형식 수신 뒤 현장 명세 검토가 필요. 임의 필드/주소를 추정하지 않음.
- 수집 원문은 자동 RAW 반입/MAIN 승격/GENOS 배포되지 않음.

자세한 결과: VALIDATION.json, SAME_CODE_EXTERNAL_CHECK.json, SOURCE_BINDING.json.
'''
(OUT/'VALIDATION_SUMMARY.txt').write_text(summary)
files=[NAME+'.ipynb',NAME+'_RUN.txt','relay_check.py',NAME+'_GUIDE.docx','GUIDE_UTF8.txt','CURL_EQUIVALENT.txt',
       'VALIDATION_SUMMARY.txt','VALIDATION.json','SAME_CODE_EXTERNAL_CHECK.json','EXTERNAL_CHECK.json','SOURCE_BINDING.json']
(OUT/'SHA256SUMS.txt').write_text(''.join(f'{sha((OUT/f).read_bytes())}  {f}\n' for f in files))
files.append('SHA256SUMS.txt')
oc=dotenv_values(ROOT/'.env').get('LAW_OC')
for f in files:
    raw=(OUT/f).read_bytes()
    assert not oc or oc.encode() not in raw, f
    assert Path(f).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
    if f.endswith('.docx'):
        with zipfile.ZipFile(OUT/f) as doc:
            assert doc.testzip() is None
            assert not oc or oc.encode() not in doc.read('word/document.xml')
        texts='\n'.join(p.text for p in Document(OUT/f).paragraphs)
        assert '13. 근거와 검증 기록' in texts and 'Managed Folder' in texts
with zipfile.ZipFile(OUT/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for f in files:archive.write(OUT/f,f)
with zipfile.ZipFile(OUT/(NAME+'.zip')) as archive:
    assert archive.testzip() is None
    assert archive.namelist()==files
    assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in archive.namelist())
    for f in files:assert archive.read(f)==(OUT/f).read_bytes()
check={'archive':NAME+'.zip','sha256':sha((OUT/(NAME+'.zip')).read_bytes()),'files':files,
       'crc_ok':True,'standalone_txt_identical':True,'all_member_bytes_match':True,'no_javascript':True,
       'no_real_law_oc':True,'docx_text_structure_verified':True}
(OUT/'SEALED_CHECK.json').write_text(json.dumps(check,ensure_ascii=False,indent=2)+'\n')
body='''<p>Dataiku에서 법제처 API를 확인할 <b>Jupyter Notebook과 클릭 순서별 실행 가이드</b>를 보냅니다.</p>
<p>외부에서 실제 자본시장법·금융투자업규정 XML 본문을 받았고, 인계 코드의 법령/행정규칙 확인 5개도 모두 성공했습니다. 사내 Dataiku와 삼성 중계 연결은 첨부 Notebook을 사내에서 실행해 확인해야 합니다.</p>
<p><b>실행 순서</b><br>1. ZIP 압축 해제<br>2. Dataiku 프로젝트 Flow → New dataset → Folder에서 결과 폴더 생성<br>3. Code → Notebooks에서 ZIP 안 .ipynb 가져오기<br>4. 셀 1의 중계 주소·Managed Folder ID 확인<br>5. 셀 1~8 실행, 등록 OC는 입력창에 입력<br>6. 결과표와 폴더 저장 완료 확인</p>
<p>가져오기 버튼이 없으면 New Notebook → Python으로 빈 Notebook을 만들고, 별도 첨부 RUN.txt 전체를 첫 코드 셀에 붙여 넣으면 됩니다. RUN.txt는 <b>Python 코드</b>이며 bash 파일이 아닙니다. Word/TXT 가이드 4~8절에 상세 버튼 순서를 적었습니다.</p>
<p><b>확인할 차이:</b> 사진의 “현행법령” curl 샘플은 실제로 행정예고 주소입니다. 현재 수집 코드가 쓰는 시행일 기준 <code>target=eflaw</code>는 사진의 명시 지원 목록에 보이지 않아 별도 확인하도록 했습니다. 법령 <code>law</code> 본문 성공과 <code>eflaw</code> 성공은 결과표에서 구분됩니다.</p>
<p>기본은 Python requests로 curl과 같은 HTTP 요청을 보냅니다. curl 자체 재현이 필요하면 ZIP의 CURL_EQUIVALENT.txt를 별도 셀에서 추가 1회 실행할 수 있습니다. 개발계/운영 주소, CA, 인증, 예고 확인, 오류별 조치도 가이드에 포함했습니다.</p>
<p>사진의 OC·세션 쿠키는 복사하지 않았습니다. 본인/과제에 등록된 인증값을 입력하세요. 내부 LLM 호출, GENOS 코드 교체, MAIN 변경은 없습니다.</p>
<p>첨부: ZIP(Notebook 포함), 완전 실행 Python TXT, Word 가이드, 동일 내용 TXT 가이드, 검증 요약, SHA-256 목록.</p>'''
(OUT/'EMAIL_BODY.html').write_text(body)
attachments=[NAME+'.zip',NAME+'_RUN.txt',NAME+'_GUIDE.docx','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','SHA256SUMS.txt']
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
metadata=[]
for f in attachments:
    raw=(OUT/f).read_bytes()
    mime='application/zip' if f.endswith('.zip') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if f.endswith('.docx') else 'text/plain'
    parts.append({'mime_type':mime,'content_disposition':'attachment','filename':f,'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    metadata.append({'name':f,'bytes':len(raw),'mime_type':mime,'sha256':sha(raw)})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[Dataiku 법제처 API 확인] Jupyter Notebook + 클릭별 실행 가이드 (실제 공개 본문 수신 확인)',
      'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(OUT/'EMAIL_ARGS.json').write_text(json.dumps(args,ensure_ascii=True))
(OUT/'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'to':args['to'],'subject':args['subject'],'attachments':metadata,'zip_members':files,'args_bytes':(OUT/'EMAIL_ARGS.json').stat().st_size},ensure_ascii=False,indent=2))
