"""Seal verified artifacts and prepare the explicitly requested Samsung handoff."""
from pathlib import Path
import base64, hashlib, io, json, subprocess, zipfile

H = Path(__file__).resolve().parent
N = 'GENOS_MAIN92_CUMULATIVE_20261020_R1'
sha = lambda b: hashlib.sha256(b).hexdigest()
enc = lambda v: (json.dumps(v, ensure_ascii=False, indent=2) + '\n').encode()
assert not (H / 'EMAIL_SENT.json').exists(), 'Inspect existing receipt before retrying'
final = json.loads((H / 'FINAL_VERIFICATION.json').read_bytes())
assert final['status'] == 'PASS'
assert final['outer_zip_sha256'] == sha((H / (N + '.zip')).read_bytes())
names = [N + '.zip', N + '_RUN.txt', N + '_WORKFLOW_PASTE_ALL.txt',
         'GUIDE_UTF8.txt', 'VALIDATION.json', 'FINAL_VERIFICATION.json']
with zipfile.ZipFile(H / names[0]) as z:
    for n in names[1:-1]:
        assert z.read(n) == (H / n).read_bytes(), n
count = 0


def scan(raw):
    global count
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        for i in z.infolist():
            assert Path(i.filename).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            count += 1
            if i.filename.lower().endswith(('.zip', '.whl')):
                scan(z.read(i.filename))


scan((H / names[0]).read_bytes())
subprocess.run(['bash', '-n', str(H / names[1])], check=True)
(H / 'SHA256SUMS.txt').write_text(''.join(sha((H / n).read_bytes()) + '  ' + n + '\n' for n in names))
names += ['SHA256SUMS.txt']
seal = {'version': N, 'files': {n: {'sha256': sha((H / n).read_bytes()),
                                 'bytes': (H / n).stat().st_size} for n in names},
        'field_deployment': 'NOT_VERIFIED'}
if (H / 'SEALED.json').exists():
    assert json.loads((H / 'SEALED.json').read_bytes()) == seal
else:
    (H / 'SEALED.json').write_bytes(enc(seal))

body = f'''<!doctype html><html lang="ko"><body>
<p>요청하신 <strong>지금까지의 MAIN92 최신 누적 코드</strong>를 보내드립니다.</p>
<p><strong>앞서 보낸 GENOS_MAIN90_RESEARCH_20261020_R1 대신 이번 {N}.zip을 사용하세요.</strong>
기존 Oracle 직접 조회·세션·로그를 유지하면서 MAIN91/92의 변경을 합쳤습니다.</p>
<ul>
<li>조사 상태·부모/자식 이력 전달, 상태 변화 재검토, 부족 해소와 최대3회 탐색→읽기 복구.</li>
<li>전송 실패 시 확보 원문 전달, 중단·재개·중복 방지, 최신 대사 보고서·화면 표시.</li>
<li>승호님 코드처럼 응답 모델명이 요청 ID와 다르거나 없어도 중단하지 않는 수정. 자동 ID 조회 및 요청/응답 ID 기록은 유지하며 일반·스트림·재개·AD에 적용.</li>
</ul>
<p>본문·권한·해시·호출 예산 검사는 유지합니다. 전체1306파일 중 직전 누적본 대비53파일 변경,
1253파일 동일이며 MAIN92 선택389파일 중388파일이 같습니다. PIPELINE의 Oracle 안내 경로만 동봉 문서로 바꿨습니다.</p>
<p>ZIP을 실제 업로드한 <strong>TRANSFER 폴더에서</strong> 다음을 실행하세요.
적용 대상은 기존 <code>~/DEV</code> Git checkout입니다. 다른 위치를 쓰고 있다면 안내의 <code>--root</code>에 확인한 실제 경로를 지정하세요.</p>
<pre>python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt check
bash ./{N}/{N}_RUN.txt apply
bash ./{N}/{N}_RUN.txt status</pre>
<p>실행 시작부터 <code>main92-cumulative-r1-logs</code>에 로그와 종료 코드를 남깁니다.
기존 checkout을 백업 후 적용하며 재실행·원복은 GUIDE를 따릅니다.
Python3.11 이상이 필요하고 sqlglot30.23.0이 없을 때만 동봉 wheel의 <code>deps</code> 명령을 먼저 실행합니다.</p>
<p>적용 후 기존 checkout의 변경 검토·commit → 같은 RUN.txt의 <code>gate-code</code> → push → 같은 commit의 새 코드서빙 리비전 순서로 진행합니다.
데이터 재구축·Oracle 조회 채널 변경·리비전 배포는 설치기가 실행하지 않습니다.</p>
<p><strong>이번 WORKFLOW_PASTE_ALL.txt는 직전 MAIN90 편집기본과 다릅니다.</strong>
워크플로우 Python 단계에 이번 전체본을 반영하고 저장하세요. Git push와 편집기 저장은 별도입니다.</p>
<p>현장 확인은 <strong>워크플로우 테스트 화면의 새 채팅</strong>에서 사진에 나온 동일 질의부터 진행하세요.
모델명 차이로 중단되지 않는지, 내규/외규 원문·미확인 사항·진행 및 최종 답변을 확인합니다.
기존 실패 실행은 원장을 보존하고 코드 binding을 무시해 강제 재개하지 않습니다.</p>
<p><strong>검증:</strong> 실제 반입 코드204개 계약/API/화면 검사,
ZIP/TXT 설치2시나리오·43명령(중단 복구·재적용·committed checkout 게이트·변조 거부·정확한 원복),
Python3.11의757모듈 컴파일, 최종 ZIP 재추출·적용·상태·원복5명령 통과.
새 외부/내부 모델 호출은 없습니다.</p>
<p>로컬 MAIN92 선택과 실제 로컬 서비스 연결은 확인했습니다. GENOS 실제 반입·리비전·Oracle/NFS·편집기 저장·내부 모델 결과는 미확인입니다.
기존 근거 충분성·직접 인용 및 최종 품질/비용의 한계는 남아 있고 <code>quality_certified=false</code>입니다.
Dataiku Oracle 이관용 CLEAN R1은 별도 발송본이며 이 ZIP은 서빙 코드 반입본입니다.</p>
<p>첨부7개: 코드 ZIP, 별도 실행 TXT, 워크플로우 편집기 전체본, 적용 안내,
검증 JSON, 최종 ZIP 검증 JSON, SHA-256 목록. ZIP 안에도 실행 TXT·안내를 넣었으며 중첩 압축까지 JavaScript 파일0개를 확인했습니다.</p>
<p>ZIP SHA-256: <code>{seal['files'][N + '.zip']['sha256']}</code></p>
</body></html>'''
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
rows = []
for n in names:
    raw = (H / n).read_bytes()
    mime = {'.zip': 'application/zip', '.json': 'application/json'}.get(Path(n).suffix, 'text/plain')
    parts.append({'mime_type': mime, 'filename': n, 'content_disposition': 'attachment',
                  'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
    rows.append({'name': n, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
args = {'to': 'hyungjininfocz.son@partner.samsung.com',
        'subject': '[GENOS] MAIN92 최신 누적본 — 조사 복구·대사 화면·모델명 오류 수정 (2026-10-20 R1)',
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
        'response_fields': ['id', 'thread_id', 'label_ids']}
(H / 'EMAIL_ARGS.json').write_bytes(json.dumps(args, ensure_ascii=True).encode())
(H / 'EMAIL_BODY_UTF8.html').write_text(body)
(H / 'EMAIL_ATTACHMENT_BINDING.json').write_bytes(enc(rows))
(H / 'EMAIL_PRECHECK.json').write_bytes(enc({
    'status': 'PASS', 'to': args['to'], 'subject': args['subject'], 'attachments': rows,
    'args_bytes': (H / 'EMAIL_ARGS.json').stat().st_size, 'members_scanned': count,
    'javascript_exclusions': 'PASS', 'bash_syntax': 'PASS'}))
print(json.dumps({'status': 'PASS', 'to': args['to'], 'attachments': len(rows),
                  'args_bytes': (H / 'EMAIL_ARGS.json').stat().st_size}))
