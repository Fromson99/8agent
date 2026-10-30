import base64,hashlib,html,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
names=['DATAIKU_FOUR_FORMAT_TEST_20261028_R1.zip','GENOS_R5_INSTALL.txt','DATAIKU_FOUR_FORMAT_TEST.txt','GUIDE.txt','PATCH_NOTES.txt']
body='''<p>기존 Dataiku 문서에서 DOC·DOCX·HWP·HWPX를 하나씩 골라 PDF 변환과 파싱을 확인하는 수정본입니다. 앞서 보낸 단일 파일 테스트 대신 이번 도구를 사용해 주세요.</p>
<p><b>파일 경로와 YAML은 노트북에 입력하지 않습니다.</b> 기존 LEGAL_RAG 02 레시피의 원문 폴더/RAW_INPUT 영수증을 재사용하고, GENOS 계산 Pod의 기존 파서 설정을 찾아 사용합니다. YAML은 문서가 아니라 layout/OCR 모델 등의 서버 설정입니다. 설정이 187번 Pod에만 있고 계산 Pod에는 없다면 복사/마운트 등 환경 준비가 필요하며 자동으로 있다고 가정하지 않습니다.</p>
<ol><li>전달 ZIP을 GENOS의 사용 중인 TRANSFER 폴더에서 풀고, 압축 해제한 폴더에서 <code>bash GENOS_R5_INSTALL.txt</code>를 실행합니다. 기존 ~/DEV legal_pipeline_serving 코드 검사·백업·적용·commit·검증·push 후 GENOS 화면에서 그 commit으로 새 리비전을 배포합니다.</li>
<li>동봉 <code>DATAIKU_COMPUTE_RECIPES_20261028_R5.zip</code>을 Dataiku <code>LEGAL_RAG/ehA8dpVm</code>에 업로드합니다.</li>
<li>LEGAL_RAG의 새 Python 노트북에 <code>DATAIKU_FOUR_FORMAT_TEST.txt</code> 전체를 붙여넣어 실행합니다. 원문 재업로드나 전체 02/03 실행은 필요 없습니다.</li></ol>
<p>확장자별 실제 원문을 최대 1개씩 선택합니다. PDF 변환과 파싱의 성공/실패를 구분하고 PDF·텍스트·JSON·오류 로그를 기존 Dataiku 결과 폴더에 보관합니다. 해당 형식이 없으면 NOT_FOUND로 표시합니다. 재실행/취소 시 같은 RUN_NAME을 유지합니다. 완료 후 재실행은 저장 결과만 표시합니다.</p>
<p>서버 R5는 기존 R4에 전용 테스트 분기를 추가했습니다. R4의 파서 의존성·변환기·실제 모델 구성은 계속 필요합니다. 전체 Flow를 다음에 사용할 때는 ZIP 안 DATAIKU_R5_INSTALL.txt로 클라이언트 해시를 함께 맞춰 주세요. 이번 테스트 자체는 RAG 검수·색인·SQL 적재를 실행하지 않습니다.</p>
<p><b>검증:</b> 최종 전달본 로컬 검사 46개 통과. 원문 선택/무결성, 4문서 처리, 변환·파싱 실패 분리, 부분 결과, 취소·재개·중복 실행 방지, 기존 R4 작업 예산 보존, 설치/복원, 노트북을 확인했습니다. 변환기와 파서 응답은 모의이고 실제 모델 호출은 0회입니다. 현장 문서의 변환/파싱 성공과 GENOS 리비전 배포는 아직 확인하지 않았습니다.</p>
<p>동봉 GUIDE와 PATCH_NOTES에 순서·설정 미발견 원인·결과 위치·복원 방법을 적었습니다. ZIP 안에 동일 실행 TXT와 전체 전달 파일이 들어 있습니다.</p>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];records=[]
for name in names:
    b=(HERE/name).read_bytes();mime='application/zip' if name.endswith('.zip') else 'text/plain'
    parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(b).decode()}})
    records.append({'filename':name,'mime_type':mime,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS/Dataiku] 기존 DOC·DOCX·HWP·HWPX 각 1개 자동 테스트 / YAML 입력 제거','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(HERE/'EMAIL_SEND_ARGS.json').write_text(json.dumps(args,ensure_ascii=False))
(HERE/'EMAIL_BODY.html').write_text(body)
(HERE/'EMAIL_ATTACHMENTS.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'bytes':(HERE/'EMAIL_SEND_ARGS.json').stat().st_size,'attachments':len(records)}))
