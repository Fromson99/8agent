"""Prepare exact connector MIME tree from sealed files; does not send."""
import base64,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
OUT=Path(__file__).resolve().parent;NAME='GENOS_RAG_FOCUSED_RULES_20261013_R1'
TO='hyungjininfocz.son@partner.samsung.com'
SUBJECT='[GENOS 패치 R1] RAG 최적화 1~4 반영 · MAIN53 기반 · 기존 캐시 보존'
FILES=[NAME+'.zip',NAME+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','SHA256SUMS.txt']

def main():
 hand=json.loads((OUT/'HANDOFF.json').read_bytes());assert hand['validation']['patched_code_contracts']==204
 body='''<p>GENOS 적용용 RAG 최적화 패치 R1입니다. 로컬 MAIN53(focused-rules-20261013-r1)에서 검증한 변경을 기존 GENOS 인계 코드에 결합했습니다.</p>
<ul><li>탐색 입력 압축과 선택한 질문·검색 범위 유지</li><li>불필요한 재탐색·중복 읽기 감소 및 도구 실패 후 복구</li><li>문서 안의 제목 미발견과 문서 자체 부재 구분</li><li>원문에 연결한 조건·의무·허용 표현과 답변 구성 반복 감소</li></ul>
<p>기존 GENOS 캐시·CM·데이터 세대·모델 설정·진행 화면과 워크플로우 편집기는 보존합니다. 이번 ZIP/RUN으로 RAG 패치를 적용하고, 이전 캐시/CM/진행 화면 패키지는 다시 덮어쓰지 마세요.</p>
<p><b>빠른 적용:</b> 첨부 RUN.txt를 ~/DEV/TRANSFER에 올린 뒤 아래 한 줄을 실행합니다. TXT는 ZIP 없이도 독립 실행되며 원본 백업과 지속 로그를 남깁니다.</p>
<pre>bash ~/DEV/TRANSFER/GENOS_RAG_FOCUSED_RULES_20261013_R1_RUN.txt</pre>
<p>이후 같은 DEV에서 commit → 기존 generation으로 gate → push → 새 리비전 배포 순서입니다. 전체 명령, 재실행·원복 방법과 워크플로우 테스트 확인 사항은 GUIDE_UTF8.txt에 있습니다. 데이터 재구축은 필요하지 않습니다.</p>
<p>인계 조합의 모의 RAG 계약 204개, 8개 설치 상태의 적용·재실행·원복 등 72개 명령, 같은 committed checkout의 모의 generation gate 2개를 확인했습니다. 신규 외부 모델 호출은 없습니다.</p>
<p>조건 AND/OR 의미 판단, 의미상 반복 문장, 모델 형식 복구 지연은 후속 개선 사항입니다. 이번 검증은 WSL 로컬 결과이며 GENOS 현장 적용·배포·실제 질문 성공은 아직 확인하지 않았습니다.</p>'''
 parts=[{'mime_type':'text/html','charset':'utf-8','body':{'content':body}}];attachments=[]
 for name in FILES:
  raw=(OUT/name).read_bytes();pin=hashlib.sha256(raw).hexdigest()
  if name.endswith('.zip'):assert pin==hand['code_zip_sha256']
  parts.append({'mime_type':'application/zip' if name.endswith('.zip') else 'text/plain','filename':name,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode().rstrip('=')}})
  attachments.append({'filename':name,'size':len(raw),'sha256':pin})
 args={'to':TO,'subject':SUBJECT,'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
 path=Path('/tmp/genos-focused-rules-mail.json');path.write_text(json.dumps(args,ensure_ascii=True,separators=(',',':')))
 (OUT/'EMAIL_PREPARED.json').write_text(json.dumps({'status':'PREPARED_NOT_SENT','to':TO,'subject':SUBJECT,'prepared_at':datetime.now(timezone.utc).isoformat(),'attachments':attachments,'args_bytes':path.stat().st_size,'args_sha256':hashlib.sha256(path.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'attachments':attachments},ensure_ascii=False))
if __name__=='__main__':main()
