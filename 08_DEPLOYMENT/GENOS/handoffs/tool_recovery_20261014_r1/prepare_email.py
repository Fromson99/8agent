import base64,hashlib,json,zipfile
from pathlib import Path
O=Path(__file__).resolve().parent;N='GENOS_TOOL_RECOVERY_20261014_R1';sha=lambda b:hashlib.sha256(b).hexdigest()
sealed=json.loads((O/'SEALED_UNPACK_CHECK.json').read_bytes());v=json.loads((O/'VALIDATION.json').read_bytes())
assert sealed['sha256']==sha((O/(N+'.zip')).read_bytes()) and sealed['standalone_run_matches'] and sealed['no_javascript']
assert v['qualification']['strict_success'] and all(x['failures']==1 and x['errors']==x['skipped']==0 for x in v['installed_contracts'].values())
with zipfile.ZipFile(O/(N+'.zip')) as z:
 assert z.testzip() is None and z.read(N+'_RUN.txt')==(O/(N+'_RUN.txt')).read_bytes()
 assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
body=(O/'EMAIL_BODY_UTF8.html').read_text();assert body.count('<!-- INSTALLED_VALIDATION -->')==1
body=body.replace('<!-- INSTALLED_VALIDATION -->',f"<p><b>GENOS 설치본 모의 검증:</b> 두 현장 구성에서 계약/API 합계 {v['installed_total']}개 통과(각 구성의 기존 표시 정책 기대 차이 1건은 패치 전 동일 재현, 새 회귀/skip 0), 실제 실행 TXT 32명령, 서비스 부팅 2회, 같은 committed checkout의 generation gate 2회와 원복·변조 거부를 확인했습니다. 알려진 코드 inventory {v['known_predecessors']}개를 지원합니다. 실제 모델 추론은 0회입니다.</p>")
(O/'EMAIL_BODY_FINAL_UTF8.html').write_text(body)
files=[N+'.zip',N+'_RUN.txt','GUIDE_UTF8.txt','FIX_REPORT_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json','SHA256SUMS.txt'];parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];meta=[]
for n in files:
 raw=(O/n).read_bytes();mime='application/zip' if n.endswith('.zip') else 'application/json' if n.endswith('.json') else 'text/plain'
 parts.append({'mime_type':mime,'content_disposition':'attachment','filename':n,'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
 meta.append({'name':n,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[MAIN63·GENOS 누적 수정] 도구 실패 복구·최근 원문 오류 수정 R1 — ZIP/실행 TXT','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
raw=json.dumps(args,ensure_ascii=True);(O/'EMAIL_ARGS.json').write_text(raw)
(O/'EMAIL_ATTACHMENT_BINDING.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'args_characters':len(raw),'args_sha256':sha(raw.encode()),'attachments':meta,'to':args['to'],'subject':args['subject']},ensure_ascii=False))
