from pathlib import Path
import base64,hashlib,json
O=Path(__file__).resolve().parent;v=json.loads((O/'EMAIL_PREFLIGHT.json').read_text())
html='''<p>요청하신 수정 코드를 로컬 MAIN59에 반영하고 GENOS 인계본을 보냅니다.</p>
<ul><li>최종 답변 게시까지 정상 완료된 기록만 shortcut 목록과 위키 생성·재사용 대상으로 사용합니다. 중간 오류 후 복구 성공한 실행은 포함하고 실패 원장은 보존합니다.</li>
<li>AD shortcut / legal_wiki 목록의 다음·이전 페이지와 마지막 일부 페이지 이동을 수정했습니다.</li>
<li>정상 완료는 법률 의미 정답의 자동 인증이 아닙니다. 기존 원문·권한·현재 상태 검사를 유지합니다.</li></ul>
<p><b>로컬 MAIN:</b> successful-shortcut-20261013-r1, 포인터 generation59. 상태36조합, 후보/작업 각각169계약, 실제 서비스 HEALTH/RAG_SEARCH200 및 선택301파일을 확인했습니다. GENOS형 설치6상태, 서비스 시작12회, 동일 checkout/generation 게이트6회와 설치 코드278계약을 확인했습니다.</p>
<p><b>현장 적용:</b> 앞서 보낸 AD_REQUEST_LOGS R2가 적용된 기존 ~/DEV에 이번 SUCCESSFUL_SHORTCUT R1을 추가 적용하세요. R2를 아직 적용하지 않았다면 R2부터 적용해야 합니다. ZIP을 압축 해제한 후 GUIDE의 check → apply → 변경 검토·commit → gate → push/새 코드서빙 리비전/SSE 재시작 순서입니다. 원문 재구축이나 워크플로우 편집기 교체는 필요하지 않습니다.</p>
<p>기존 정상 기록은 게시 journal/최종 JSON/현재 route를 대조하는 backfill 절차로만 복원합니다. 경로나 증거가 불명확한 기록은 미확인으로 보존합니다.</p>
<p>ZIP 안에 수정 코드·전체 실행 TXT·가이드·검증/해시 자료를 넣었습니다. 실행 TXT도 별도로 첨부했습니다. GENOS 반입·배포·실제 워크플로우 화면은 현장 적용 후 확인해야 합니다.</p>'''
parts=[{'mime_type':'text/html','body':{'content':html}}]
for a in v['attachments']:
 data=(O/a['filename']).read_bytes();assert len(data)==a['bytes'] and hashlib.sha256(data).hexdigest()==a['sha256']
 parts.append({'mime_type':'application/zip' if a['filename'].endswith('.zip') else 'text/plain','filename':a['filename'],'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode(data).decode()}})
print(json.dumps({'to':v['to'],'subject':v['subject'],'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']},ensure_ascii=False))
