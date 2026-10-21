"""Seal verified artifacts and prepare the explicitly requested Samsung handoff."""
from pathlib import Path
import base64, hashlib, io, json, subprocess, zipfile

H = Path(__file__).resolve().parent
N = 'GENOS_MAIN90_RESEARCH_20261020_R1'
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
<p>요청하신 <strong>MAIN90 조사·근거 갱신·RP 수정 누적본</strong>을 보내드립니다.</p>
<p><strong>앞서 보낸 GENOS_WORKFLOW_PROGRESS_20261019_R1 대신 이번 {N} ZIP을 사용하세요.</strong>
기존 Oracle 직접 조회·세션·진행 로그·화면 코드를 유지한 전체 코드 반입본입니다.</p>
<ul>
<li>필요한 조사 항목이 후속 단계에서 사라지지 않도록 보존하고, 추가 조사의 우선순위와 상태를 이어갑니다.</li>
<li>새 근거를 반영할 때 중첩된 갱신 형식 때문에 실패하던 경로를 보완했습니다.</li>
<li>연결 원문·문서 내 용어 추가 탐색과 RP 연결 문서 등록 오류 수정을 포함합니다.</li>
</ul>
<p>로컬 MAIN90에서 선택한 실행 코드·엔진·프로필과 같은 바이트입니다.
PIPELINE의 Oracle 안내 경로만 ZIP 안의 문서로 바꿨습니다.
이번 패키지에 별도 작업 중인 최신 보고서 화면 변경은 포함하지 않았습니다.</p>
<p>ZIP을 실제 업로드한 <strong>TRANSFER 폴더에서</strong> 아래를 실행하세요.
<code>/workspace</code>는 앞선 현장 사진의 기존 Git checkout 실경로입니다.
현재 경로가 다르면 확인한 실제 checkout 경로로 바꾸세요.</p>
<pre>python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt check --root /workspace
bash ./{N}/{N}_RUN.txt apply --root /workspace
bash ./{N}/{N}_RUN.txt status --root /workspace</pre>
<p>실행 시작부터 <code>main90-research-r1-logs</code>에 로그와 종료 코드를 남기고,
기존 checkout 파일을 백업한 뒤 적용합니다. 중단 후 재실행과 원복은 GUIDE를 따릅니다.
Python 3.11 이상이 필요하며, sqlglot 30.23.0이 없을 때만 동봉 wheel의 <code>deps</code> 명령을 먼저 실행하세요.</p>
<p>적용 후 기존 checkout에서 변경 검토·commit → <code>gate-code</code> → push → 같은 commit의 새 코드서빙 리비전 배포를 진행하세요.
<strong>코드 적용과 현장 배포는 별도 단계입니다.</strong> 이번 설치는 원문·색인 재구축이나 Oracle 조회 채널 변경을 하지 않습니다.</p>
<p>첨부 WORKFLOW_PASTE_ALL.txt는 앞서 보낸 WORKFLOW_PROGRESS R1 편집기본과 같습니다.
이미 그 버전을 저장했다면 다시 교체할 필요는 없습니다. 그렇지 않으면 워크플로우 Python 편집기에 전체 반영 후 저장하세요.</p>
<p>현장 확인은 <strong>워크플로우 테스트 화면</strong>의 새 채팅에서 같은 4문항
(PF 악화, 일반고객 원화 RP 대상채권, 대손충당금/대손준비금, 레버리지비율)으로 진행하세요.
조사 항목과 새 원문 반영, 직접 인용, 미확보 내용 및 partial/실패 표시를 확인합니다.</p>
<p><strong>로컬 검증:</strong> 실제 반입 코드의 계약/API 87개 통과,
ZIP/TXT 설치 2개 시나리오·43개 명령 통과(중단 복구·재적용·committed checkout 코드 게이트·변조 거부·정확한 원복),
Python 3.11에서 755모듈 컴파일 통과. 최종 ZIP도 다시 추출·설치·상태·원복 확인했습니다.
이번 패키지 검증에서 외부/내부 모델을 새로 호출하지 않았습니다.</p>
<p><strong>남아 있는 한계:</strong> 이전 4문항에서 RP 제5-18조·시행령 제181조 미확보와
레버리지 제3-26조제7항의 현재 직접 인용 누락이 남았습니다.
이번 버전은 조사 목록 보존·갱신 형식 오류의 수정이며, 모든 근거 누락이 해소되었다는 품질 인증은 아닙니다.
GENOS 실제 반입·리비전·Oracle/NFS·편집기 저장·내부 모델 결과는 아직 미확인입니다.</p>
<p>첨부 7개: 코드 ZIP, 별도 실행 TXT, 워크플로우 편집기 전체본, 적용 안내,
검증 JSON, 최종 ZIP 검증 JSON, SHA-256 목록. ZIP 안에도 실행 TXT와 안내가 들어 있습니다.
JavaScript 파일은 중첩 ZIP까지 확인하여 제외했습니다.</p>
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
        'subject': '[GENOS] MAIN90 조사·근거 갱신·RP 수정 누적본 (2026-10-20 R1)',
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
        'response_fields': ['id', 'thread_id', 'label_ids']}
(H / 'EMAIL_ARGS.json').write_bytes(json.dumps(args, ensure_ascii=False).encode())
(H / 'EMAIL_BODY_UTF8.html').write_text(body)
(H / 'EMAIL_ATTACHMENT_BINDING.json').write_bytes(enc(rows))
(H / 'EMAIL_PRECHECK.json').write_bytes(enc({
    'status': 'PASS', 'to': args['to'], 'subject': args['subject'], 'attachments': rows,
    'args_bytes': (H / 'EMAIL_ARGS.json').stat().st_size, 'members_scanned': count,
    'javascript_exclusions': 'PASS', 'bash_syntax': 'PASS'}))
print(json.dumps({'status': 'PASS', 'to': args['to'], 'attachments': len(rows),
                  'args_bytes': (H / 'EMAIL_ARGS.json').stat().st_size}))
