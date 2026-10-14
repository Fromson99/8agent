from pathlib import Path
import base64,hashlib,json,html,zipfile
O=Path(__file__).resolve().parent;N='GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1'
v=json.loads((O/'VALIDATION.json').read_bytes());assert v['status']=='PASS_DISPLAY_BOUNDARIES_AND_INSTALLER'
files=[N+'.zip',N+'_RUN.txt',N+'_PASTE_ALL.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','SHA256SUMS.txt']
with zipfile.ZipFile(O/files[0]) as z:
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
 assert z.read(files[1])==(O/files[1]).read_bytes() and z.read(files[2])==(O/files[2]).read_bytes()
body='''<p>요청하신 예외 안내 통합을 로컬 MAIN61에 반영하고 GENOS 인계본을 전달합니다.</p>
<p><b>검토 미완료</b><br>현재 충분한 법률 검토를 하지 못했습니다. 검토할 법률 쟁점이나 상황을 조금 더 구체적으로 질문해 주세요.</p>
<p><b>기술 예외</b><br>현재 충분한 법률 검토를 하지 못했습니다. 잠시 후 다시 요청해 주세요. (503)<br>시간 초과는 (timeout), 처리 한도는 (limit)으로 표시합니다. 401/403 권한, 409 처리 중·상태 충돌, 413 분량 초과, 429/500/502/504, 사전 점검·잘못된 응답·표시 예외도 같은 기준으로 처리합니다. 원시 오류는 내부 로그에 보존합니다.</p>
<p><b>GENOS 적용 순서</b></p><ol>
<li>기존 ASSESSMENT_GAP_ACTION R2 다음에 이 PUBLIC_FAILURE_GUIDANCE R1 ZIP을 적용합니다. 성공 shortcut도 함께 적용한다면 AD_REQUEST_LOGS R2 → SUCCESSFUL_SHORTCUT R1 → GAP_ACTION R2 → 이번 패치 순서입니다.</li>
<li>ZIP을 풀고 RUN.txt의 check/apply를 실행합니다. 기본 대상은 기존 ~/DEV이며 백업·지속 로그를 남깁니다. 별도 첨부 RUN.txt도 ZIP 안과 같은 완전한 실행 코드입니다.</li>
<li>같은 checkout에서 변경 검토·commit·현재 generation 배포 게이트 후 push하고 새 코드서빙 리비전을 배포합니다. 별도 SSE 서버도 재시작합니다.</li>
<li>PASTE_ALL.txt 전체를 기존 워크플로우 Python 편집기에 붙여 넣고 저장합니다. 기존 SOURCE_PROVIDER R2 편집기 코드를 이 버전으로 교체합니다. Git push만으로 편집기가 바뀌지는 않습니다.</li>
<li>워크플로우 테스트 화면에서 정상/기존 실패 질의를 실행하고 요청 ID와 결과를 확인합니다. 상세 명령과 원복은 GUIDE_UTF8.txt에 있습니다.</li></ol>
<p><b>확인 결과</b><br>합성 예외 조합 2,400개와 관련 계약 298개 통과. 실제 로컬 service.service 정상 조회와 503/timeout/limit, 선택 코드 301파일을 확인했습니다. GENOS 설치 코드 CONTRACT_COUNT개, 독립 편집기 15개, 설치/재실행/변조 거부/원복 6상태, 동일 checkout의 모의 generation 배포 게이트 6회가 통과했습니다. 신규 실제 모델 호출은 0회입니다.</p>
<p>이번 변경은 오류 안내와 실패 상태 보존입니다. 503/timeout 발생 원인 자체를 해결했다는 뜻은 아닙니다. GENOS 현장 반입·내부 모델·리비전 배포·편집기 저장·화면 확인은 현장에서 진행해야 합니다. 기존 미해결 회귀/계보 항목과 검증 한계는 첨부 검증요약에 남겼습니다.</p>
<p>로컬 활성 릴리스: <code>public-failure-guidance-20261014-r1</code>, generation 61.<br>코드 ZIP SHA-256: <code>ZIP_SHA</code></p>'''
body=body.replace('CONTRACT_COUNT',str(sum(v['installed_contracts'].values()))).replace('ZIP_SHA',hashlib.sha256((O/files[0]).read_bytes()).hexdigest())
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
for n in files:
 parts.append({'mime_type':'application/zip' if n.endswith('.zip') else 'text/plain','filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode((O/n).read_bytes()).decode()}})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS] 예외 안내 통합 R1 — 로컬 MAIN61 반영 / 설치 ZIP + 편집기 코드','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(O/'EMAIL_REQUEST.json').write_text(json.dumps(args,ensure_ascii=False));(O/'EMAIL_BODY.html').write_text(body)
(O/'EMAIL_ATTACHMENTS.json').write_text(json.dumps([{'filename':n,'bytes':(O/n).stat().st_size,'sha256':hashlib.sha256((O/n).read_bytes()).hexdigest()} for n in files],ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'request_bytes':(O/'EMAIL_REQUEST.json').stat().st_size,'attachments':len(files),'total_attachment_bytes':sum((O/n).stat().st_size for n in files)}))
