"""Seal exact verified attachments and prepare the explicitly requested Samsung mail."""
from pathlib import Path
import base64
import hashlib
import io
import json
import subprocess
import zipfile

H=Path(__file__).resolve().parent;R=H.parents[3]
N='GENOS_MAIN95_COMPARISON_SCOPE_20261020_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists() and not (H/'EMAIL_SENT.json').exists()
validation=json.loads((H/'VALIDATION.json').read_bytes())
final=json.loads((H/'FINAL_VERIFICATION.json').read_bytes())
assert validation['status']==final['status']=='PASS'
assert final['outer_zip_sha256']==sha((H/(N+'.zip')).read_bytes())
names=[N+'.zip',N+'_RUN.txt',N+'_WORKFLOW_PASTE_ALL.txt','GUIDE_UTF8.txt',
       'EXPERIMENT_RESULT.txt','VALIDATION.json','FINAL_VERIFICATION.json']
with zipfile.ZipFile(H/names[0]) as z:
    for name in names[1:-1]:assert z.read(name)==(H/name).read_bytes(),name
def scan(raw):
    count=0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        for member in z.infolist():
            assert Path(member.filename).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            count+=1
            if member.filename.lower().endswith(('.zip','.whl')):count+=scan(z.read(member.filename))
    return count
members=scan((H/names[0]).read_bytes())
subprocess.run(['bash','-n',str(H/names[1])],check=True)
(H/'SHA256SUMS.txt').write_text(''.join(sha((H/n).read_bytes())+'  '+n+'\n' for n in names))
names.append('SHA256SUMS.txt')
seal={'version':N,'files':{n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in names},
      'field_deployment':'NOT_VERIFIED'}
(H/'SEALED.json').write_bytes(enc(seal))
experiment=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0956-comparison-required-scope-retest/artifacts/run-001/result.json').read_text())
b=experiment['by_arm']['control'];s=experiment['by_arm']['scoped']
bc=experiment['cases']['control']['anchor-scope'];sc=experiment['cases']['scoped']['anchor-scope']
body=f"""<!doctype html><html lang="ko"><body>
<p>요청하신 <strong>4번 재실험을 완료하고, 3·4번 수정본을 로컬 MAIN95 / workflow1.20.2에 반영</strong>했습니다.</p>
<ol start="3"><li>같은 문서·세대·원문 위치·인용문을 대사표에서 하나로 표시합니다. 경로별 원래 근거 ID와 감사 기록은 보존합니다.</li>
<li>질문의 직접 요구나 답의 적용·조건·예외를 바꿀 수 있는 의존 조사만 추가하도록 지침을 구체화했습니다.
단순 배경·항목 채우기·숫자가 있다는 이유의 산식 확장을 줄이며, 필요한 외규 연속 참조와 명시적으로 요청한 산식 조사는 유지합니다.</li></ol>
<p><strong>합성4사례를 기존 MAIN94와 수정본에 각각 새로 실행했습니다.</strong>
전체 호출 {b['model_calls']}회 → {s['model_calls']}회, 공급자 보고 비용 ${b['cost_usd']:.6f} → ${s['cost_usd']:.6f}.
불필요한 산식 확장 사례는 {bc['model_calls']}회 → {sc['model_calls']}회였고 수정본의 추가 산식 과제는 0개였습니다.
예외 참조·누락 별표·산식 명시 요청은 고정 기준으로 검토했습니다. 세부 원문·결과·한계는 EXPERIMENT_RESULT.txt에 있습니다.</p>
<p>이 결과는 <strong>Qwen3.8/Parasail FP8 외부 모델과 합성 자료의 단회 비교</strong>입니다.
실제 Risk 자료나 GENOS 내부 모델의 성능 인증이 아닙니다. 조사 제한은 모델 지침이며 의미를 강제 판별해 미확인을 삭제하지 않습니다.
선택 개념 밖 승인 연결 조회와 더 엄격한 내규의 상충 오판은 별도 미해결 항목입니다. quality_certified=false입니다.</p>
<p>8개 응답 모두 미확인을 포함한 partial 상태였으며, 불필요한 미확인 문구도 남았습니다.
기준본의 출력 보정 실패도 호출 수에 포함하므로 호출 감소 전부를 범위 지시의 순수 효과로 단정하지 않습니다.</p>
<p><strong>이전 GENOS_MAIN94_INVESTIGATION_DEDUP_20261020_R1 대신 이번 {N}.zip을 사용하세요.</strong>
기존 MAIN94 기능을 포함한 누적 설치본이며 데이터·승인 관계·환경·실행 이력은 보존합니다.</p>
<p>ZIP을 업로드한 <strong>실제 TRANSFER 폴더에서</strong> 다음을 실행하세요. 코드 적용 대상은 기존 <code>~/DEV</code> Git checkout입니다.</p>
<pre>python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt check
bash ./{N}/{N}_RUN.txt apply
bash ./{N}/{N}_RUN.txt status</pre>
<p>첫 명령부터 지속 로그·종료 상태를 남기고 백업 후 적용합니다. Python3.11 이상과 기존 의존성을 사용합니다.
sqlglot30.23.0이 없을 때만 동봉 deps를 먼저 실행하세요. 실행·재실행·원복은 GUIDE_UTF8.txt에 있습니다.</p>
<p>코드 적용 후 기존 checkout의 변경 검토·commit → TRANSFER에서 gate-code
(현재 SQLite/NFS 현장은 같은 선택 세대의 gate-sqlite) → push → 같은 commit의 새 코드서빙 리비전 배포 순서입니다.
Oracle 조회 현장은 기존 조회 설정을 유지하며 전체 로컬 데이터 복원을 요구하지 않습니다.
워크플로우 편집기 전체본은 동봉 TXT에 있으며 MAIN94 편집기본을 이미 적용했다면 내용은 같습니다.
현장 질의는 <strong>워크플로우 테스트 화면의 새 채팅</strong>에서 확인하고 요청 ID와 원문·조사 기록을 보관하세요.</p>
<p>이전 코드에 결속된 중단/실패 요청·배치 PLAN·STATE는 보존하며 새 코드로 강제 재개하지 않습니다.
해시 검사를 끄거나 덮어쓰지 마세요. 이번 설치가 전체 배치나 자동 관계 승인을 실행하지 않습니다.</p>
<p><strong>검증:</strong> 작업·검증·선택·인계 runtime393파일 일치, 관련 계약59개 통과,
인계 코드 계약{validation['handoff_contracts']}개 통과, 설치2시나리오{validation['installation_commands']}명령,
최종 ZIP 재추출·적용·상태·원복5명령 통과.
로컬 MAIN95의 실제 서비스 선택·HEALTH·원문 읽기를 확인했습니다.
<strong>GENOS 반입·push·리비전·편집기·Oracle/NFS·내부 모델 현장 검증은 별도입니다.</strong></p>
<p>첨부8개: 코드 ZIP, 독립 실행 TXT, 편집기 전체본, 안내, 실험 결과, 인계 검증 JSON, 최종 ZIP 검증 JSON, SHA256 목록.
중첩 ZIP/wheel을 포함해 JavaScript 파일0개입니다.</p>
<p>ZIP SHA256: <code>{seal['files'][N+'.zip']['sha256']}</code></p>
</body></html>"""
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}];rows=[]
for name in names:
    raw=(H/name).read_bytes();mime={'.zip':'application/zip','.json':'application/json'}.get(Path(name).suffix,'text/plain')
    parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment',
        'body':{'base64_url_content':base64.urlsafe_b64encode(raw).decode()}})
    rows.append({'name':name,'bytes':len(raw),'sha256':sha(raw),'mime_type':mime})
args={'to':'hyungjininfocz.son@partner.samsung.com',
    'subject':'[GENOS] MAIN95 — 원문 표시 중복·조사 범위 수정 및 재실험 결과 (2026-10-20 R1)',
    'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']}
(H/'EMAIL_ARGS.json').write_bytes(json.dumps(args,ensure_ascii=True).encode())
(H/'EMAIL_BODY_UTF8.html').write_text(body)
(H/'EMAIL_ATTACHMENT_BINDING.json').write_bytes(enc(rows))
(H/'EMAIL_PRECHECK.json').write_bytes(enc({'status':'PASS','to':args['to'],'subject':args['subject'],
    'attachments':rows,'members_scanned':members,'javascript_exclusions':'PASS','bash_syntax':'PASS',
    'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size}))
print(json.dumps({'status':'PASS','to':args['to'],'attachments':len(rows),'args_bytes':(H/'EMAIL_ARGS.json').stat().st_size}))
