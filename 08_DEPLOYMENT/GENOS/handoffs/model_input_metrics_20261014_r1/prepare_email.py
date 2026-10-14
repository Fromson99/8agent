from pathlib import Path
import base64, hashlib, json, subprocess, zipfile
O = Path(__file__).resolve().parent
N = 'GENOS_MODEL_INPUT_METRICS_20261014_R1'
files = [N+'.zip', N+'_RUN.txt', 'FINDINGS_UTF8.txt', 'GUIDE_UTF8.txt', 'VALIDATION.json', 'SHA256SUMS.txt']
for line in (O/'SHA256SUMS.txt').read_text().splitlines():
    digest, name = line.split(maxsplit=1)
    assert hashlib.sha256((O/name.strip()).read_bytes()).hexdigest() == digest, name
with zipfile.ZipFile(O/files[0]) as z:
    assert z.testzip() is None
    assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
    manifest=json.loads(z.read('CODE_MANIFEST.json'))
    for f in manifest['files']:
        b=z.read(f['path'])
        assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256'], f['path']
    for name in files[1:-1]:
        assert z.read(name)==(O/name).read_bytes(),name
subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
v=json.loads((O/'VALIDATION.json').read_bytes())
assert v['installed_contract_tests']==80 and v['delivery_tests']['failures']==0
attachments=[{'filename':n,'bytes':(O/n).stat().st_size,'sha256':hashlib.sha256((O/n).read_bytes()).hexdigest()} for n in files]
body='''<p>요청하신 입력 길이 계측 및 최종 실패 로그 복구 패치노트와 적용 파일을 전달합니다.</p>
<p><b>이번 수정</b></p><ul>
<li>각 모델 호출마다 입력 메시지 문자 수·UTF-8 바이트·시스템/사용자 길이·응답 스키마 크기를 기록합니다. 실제 prompt_tokens/completion_tokens, max_tokens, finish_reason을 같은 호출에 연결해 출력 상한 도달 여부를 확인할 수 있게 했습니다.</li>
<li>공개 실패 응답의 message/answer_status/failure_reason/error_code가 FINAL RESPONSE / ANSWER 및 최종 TXT에서 빠지던 문제를 수정했습니다. 서비스 종료 시 SERVICE OUTCOME과 request.outcome도 기록합니다.</li>
<li>공개 응답에 run_id가 없더라도 같은 request_id의 수집 이벤트로 실행 원장을 찾아 상세 JSON에 연결합니다. 실패 안내와 정상 법률 답변을 구분해 보존합니다.</li></ul>
<p><b>사진에서 확인한 원인과 남은 확인</b><br>
source-law-navigation-2의 HTTP 200과 finish_reason=length는 확인됩니다. ADOPT/FINISH는 조사 단계의 모델 제안으로, 검증된 최종 답변이 게시됐다는 뜻은 아닙니다. length 응답이 거부되고 수정 요청이 시작된 기록은 있지만 그 이후 최종 중단 위치는 사진만으로 확인되지 않았습니다.<br>
입력 컨텍스트 초과인지 출력 토큰 상한 도달인지는 실제 usage와 내부 모델의 컨텍스트 설정을 대조해야 합니다. 이번 패치는 그 진단과 로그 누락을 보완하며, 모델·프롬프트·출력 한도·재시도 및 근거 검증 정책은 유지합니다.</p>
<p><b>GENOS 적용 순서</b></p><ol>
<li>AD_REQUEST_LOGS R2와 ASSESSMENT_GAP_ACTION R2가 적용된 기존 ~/DEV에 추가 적용합니다. PUBLIC_FAILURE_GUIDANCE R1도 설치할 예정이면 그 패치를 먼저 적용하고 이번 MODEL_INPUT_METRICS R1을 마지막에 적용하세요. 기존 성공 shortcut 및 조사 예산 설정을 보존합니다.</li>
<li>아래 명령으로 ZIP을 풀고 check/apply를 실행합니다. ZIP 업로드 위치는 실제 경로로 바꾸세요. 별도 첨부 RUN.txt는 ZIP 안과 동일한 완전한 실행 코드입니다.</li></ol>
<pre>python3 -m zipfile -e ~/TRANSFER/GENOS_MODEL_INPUT_METRICS_20261014_R1.zip ~/DEV/TRANSFER/model-input-metrics-r1-package
bash ~/DEV/TRANSFER/model-input-metrics-r1-package/GENOS_MODEL_INPUT_METRICS_20261014_R1_RUN.txt check
bash ~/DEV/TRANSFER/model-input-metrics-r1-package/GENOS_MODEL_INPUT_METRICS_20261014_R1_RUN.txt apply</pre>
<p>적용 후 GUIDE_UTF8.txt에 따라 같은 ~/DEV에서 변경 검토·commit·선택 generation 배포 게이트·push를 진행하고 <b>새 코드서빙 리비전 배포와 별도 SSE 서버 재시작</b>을 수행합니다. 원문 재구축이나 이번 패치를 위한 워크플로우 편집기 교체는 없습니다. 적용 로그와 백업 경로를 보관하고, 워크플로우 테스트 화면에서 같은 요청 ID의 입력 계측·SERVICE OUTCOME·최종 로그를 확인하세요. 원복 절차도 안내에 포함했습니다.</p>
<p><b>검증 결과와 반영 상태</b><br>
설치본 계약 80개, 설치·재실행·변조 거부·원복 4조합, 서비스 부팅 8회, 같은 committed checkout의 모의 generation 게이트 4회가 통과했습니다. 확대 검사 166개 중 157개 통과, 9개 실패이며 수정 전 격리 코드에서도 같은 9개 실패를 재현했습니다. 기존 실패 항목과 한계는 첨부에 기록했습니다. 실제 모델 호출은 0회입니다.<br>
현재 작업 코드와 인계본까지 준비된 상태입니다. 로컬 선택 MAIN61은 유지했고 GENOS 현장 반입·배포·내부 모델 재질의 결과는 아직 확인하지 않았습니다.</p>
<p><b>첨부 6개</b>: 수정 ZIP, 독립 실행 RUN.txt, 패치노트 FINDINGS_UTF8.txt, 적용·원복 안내 GUIDE_UTF8.txt, VALIDATION.json, SHA256SUMS.txt.<br>
ZIP SHA-256: <code>ZIP_SHA</code></p>'''
body=body.replace('ZIP_SHA',attachments[0]['sha256'])
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
for n in files:
    parts.append({'mime_type':'application/zip' if n.endswith('.zip') else 'application/json' if n.endswith('.json') else 'text/plain','filename':n,'content_disposition':'attachment','body':{'base64_url_content':base64.urlsafe_b64encode((O/n).read_bytes()).decode()}})
args={'to':'hyungjininfocz.son@partner.samsung.com','subject':'[GENOS 패치노트] 입력 길이 계측·최종 실패 로그 복구 R1 (2026-10-14)','payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(O/'EMAIL_REQUEST.json').write_text(json.dumps(args,ensure_ascii=False))
(O/'EMAIL_BODY.html').write_text(body)
(O/'EMAIL_ATTACHMENTS.json').write_text(json.dumps(attachments,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'integrity':'PASS','bash_syntax':'PASS','javascript_members':0,'attachments':attachments,'request_bytes':(O/'EMAIL_REQUEST.json').stat().st_size}))
