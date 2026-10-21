import base64,hashlib,json,zipfile
from pathlib import Path
O=Path(__file__).resolve().parent;N='GENOS_TOOL_AVAILABILITY_20261014_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
sealed=json.loads((O/'SEALED_UNPACK_CHECK.json').read_bytes());v=json.loads((O/'VALIDATION.json').read_bytes())
assert sealed['sha256']==sha((O/(N+'.zip')).read_bytes()) and sealed['standalone_run_matches'] and sealed['no_javascript']
assert v['working_regressions']['failures']==v['working_regressions']['errors']==0
assert all(x['failures']==x['errors']==x['skipped']==0 for x in v['installed_contracts'].values())
with zipfile.ZipFile(O/(N+'.zip')) as z:
 assert z.testzip() is None and z.read(N+'_RUN.txt')==(O/(N+'_RUN.txt')).read_bytes()
 assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
body=(O/'EMAIL_BODY_UTF8.html').read_text()
summary=f"<p><b>최종 검증:</b> 작업 코드 {v['working_regressions']['tests']-v['working_regressions']['skipped']}개 통과, {v['working_regressions']['skipped']}개 skip. 수정 전에도 실패하는 구형 검사 4건은 재현 기록과 함께 제외했습니다. 설치한 두 현장 구성은 합계 {v['installed_total']}개 통과(실패/면제 0), 실제 실행 TXT 32명령, 서비스 부팅 2회와 동일 committed checkout generation gate 2회를 확인했습니다.</p>\n"
assert '<b>최종 검증:</b>' not in body
body=body.replace('<p><b>ZIP을 실제',summary+'<p><b>ZIP을 실제');(O/'EMAIL_BODY_UTF8.html').write_text(body)
files=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SHA256SUMS.txt']
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];meta=[]
for n in files:
 raw=(O/n).read_bytes();mime='application/zip' if n.endswith('.zip') else 'application/json' if n.endswith('.json') else 'text/plain'
 parts.append({'mime_type':mime,'content_disposition':'attachment','filename':n,'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
 meta.append({'name':n,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS 수정] 상황별 도구 전수 점검·부모 원문 읽기 R1 — ZIP 및 실행 TXT (2026-10-14)','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
raw=json.dumps(args,ensure_ascii=True);(O/'EMAIL_ARGS.json').write_text(raw)
(O/'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'args_characters':len(raw),'args_sha256':sha(raw.encode()),'attachments':meta,'to':args['to'],'subject':args['subject']},ensure_ascii=False))
