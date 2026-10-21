"""Prepare the explicitly authorized Samsung message from verified, sealed files."""
from pathlib import Path
import base64, hashlib, io, json, subprocess, zipfile
H = Path(__file__).resolve().parent
N = "GENOS_MAIN94_INVESTIGATION_DEDUP_20261020_R1"
sha = lambda b: hashlib.sha256(b).hexdigest()
enc = lambda v: (json.dumps(v, ensure_ascii=False, indent=2) + "\n").encode()
assert not (H / "EMAIL_SENT.json").exists()
final = json.loads((H / "FINAL_VERIFICATION.json").read_bytes())
validation = json.loads((H / "VALIDATION.json").read_bytes())
assert final["status"] == "PASS" and validation["status"] == "PASS"
assert final["outer_zip_sha256"] == sha((H / (N + ".zip")).read_bytes())
names = [N + ".zip", N + "_RUN.txt", N + "_WORKFLOW_PASTE_ALL.txt",
         "GUIDE_UTF8.txt", "VALIDATION.json", "FINAL_VERIFICATION.json"]
with zipfile.ZipFile(H / names[0]) as z:
    for n in names[1:-1]:
        assert z.read(n) == (H / n).read_bytes(), n
def scan(raw):
    count = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        for i in z.infolist():
            assert Path(i.filename).suffix.lower() not in {".js", ".jsx", ".mjs", ".cjs"}
            count += 1
            if i.filename.lower().endswith((".zip", ".whl")):
                count += scan(z.read(i.filename))
    return count
count = scan((H / names[0]).read_bytes())
subprocess.run(["bash", "-n", str(H / names[1])], check=True)
(H / "SHA256SUMS.txt").write_text("".join(sha((H / n).read_bytes()) + "  " + n + "\n" for n in names))
names.append("SHA256SUMS.txt")
seal = {"version": N, "files": {n: {"sha256": sha((H / n).read_bytes()),
        "bytes": (H / n).stat().st_size} for n in names}, "field_deployment": "NOT_VERIFIED"}
with (H / "SEALED.json").open("xb") as f:
    f.write(enc(seal))
body = f"""<!doctype html><html lang="ko"><body>
<p>요청하신 <strong>반복 탐색·불필요한 추가 조사 세 가지를 수정하여 로컬 MAIN94 / workflow 1.20.1에 반영</strong>했습니다.</p>
<ol><li>대사 전용 조사에서도 동일 검색어·동일 범위의 재검색을 실행 전에 차단합니다. 기존 한 번의 수정 기회 이후에도 반복하면 확보 원문과 미확인 내용을 반환합니다.</li>
<li>미확보 설명만으로 검색 과제를 자동 생성하지 않습니다. 부모가 명시한 추가 조사만 실행하며 미확보 상태와 원문은 보존합니다.</li>
<li>같은 근거의 인용 문구·범위 변경을 새 원문 확보로 취급하지 않습니다. 실제 다른 원문·범위·버전의 필요한 조사는 유지합니다.</li></ol>
<p><strong>앞서 보낸 GENOS_MAIN93_INTERNAL_ANCHOR_20261020_R1 코드 ZIP 대신 이번 {N}.zip을 사용하세요.</strong>
MAIN93의 내규→개념→외규 연결→원문 대사표와 기존 Oracle·관계 기능을 포함한 누적 설치본입니다.
기존 데이터·승인 관계·환경·조사 기록은 보존합니다.</p>
<p>ZIP을 업로드한 <strong>실제 TRANSFER 폴더에서</strong> 다음을 실행합니다. 적용 대상은 기존 <code>~/DEV</code> Git checkout입니다.</p>
<pre>python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt check
bash ./{N}/{N}_RUN.txt apply
bash ./{N}/{N}_RUN.txt status</pre>
<p>첫 단계부터 로그·종료 상태를 남기고 백업 후 적용합니다. Python3.11 이상과 기존 의존성을 사용합니다.
sqlglot30.23.0이 없을 때만 동봉 deps를 먼저 실행합니다.
적용 후 기존 checkout에서 검토·commit → TRANSFER에서 gate-code
(현재 SQLite/NFS 현장은 같은 선택 세대의 gate-sqlite도 확인) → push → 같은 commit의 새 리비전 배포 순서입니다.
Oracle 현장은 기존 조회 설정을 유지하며 전체 로컬 데이터 복원을 요구하지 않습니다.</p>
<p>동봉 WORKFLOW_PASTE_ALL.txt는 워크플로우 Python 편집기 전체본입니다. MAIN93 편집기본을 이미 적용한 경우 내용은 같습니다.
미적용이면 전체 반영 후 저장하세요. 현장 질의 확인은 <strong>워크플로우 테스트 화면</strong>의 새 채팅에서 합니다.
같은 자료를 반복 탐색했던 질문으로 확인하고 요청 ID·조사 기록을 보관하세요.</p>
<p>이전 코드에 결속된 중단/실패 요청과 배치 PLAN·STATE는 보존하며 새 코드로 강제 재개하지 않습니다.
구 실행기의 해시 검사를 우회하지 마세요. 이번 설치는 기존 후보의 자동 승인·DB 이관·전체 배치 실행을 수행하지 않습니다.</p>
<p><strong>검증:</strong> 작업·동결·선택·인계 runtime393파일 일치.
로컬 계약366건 통과, 구 일반 RAG 검사6건은 이전 MAIN93에서도 동일 실패임을 대조했습니다.
인계본 계약{validation['handoff_contracts']}건, 설치2시나리오{validation['installation_commands']}명령,
최종 ZIP 재추출·적용·상태·원복5명령을 확인했습니다.
모의 API에서 동일 검색 실행3회→1회, 명시 요청 없는 추가 조사1회→0회이며 미확인과 원문은 남습니다.
이는 합성 결함 재현이며 실제 내부 모델의 품질·시간·비용 개선 수치가 아닙니다.</p>
<p><strong>로컬 MAIN94 선택과 실제 로컬 서비스 확인은 완료했습니다. GENOS 반입·push·리비전·편집기·Oracle/NFS·내부 모델 현장 검증은 별도입니다.</strong>
quality_certified=false이며 기존 실패/실험 판정은 보존합니다. 실행·재실행·게이트·원복은 GUIDE_UTF8.txt를 따르세요.</p>
<p>첨부7개: 코드 ZIP, 독립 실행 TXT, 워크플로우 편집기 전체본, 안내, 검증 JSON, 최종 ZIP 검증 JSON, SHA256 목록.
ZIP 내부에도 실행 TXT·안내가 있으며 중첩 압축까지 JavaScript 파일0개를 확인했습니다.</p>
<p>ZIP SHA-256: <code>{seal['files'][N+'.zip']['sha256']}</code></p>
</body></html>"""
parts = [{"mime_type": "text/html", "charset": "UTF-8", "body": {"content": body}}]
rows = []
for n in names:
    raw = (H / n).read_bytes()
    mime = {".zip": "application/zip", ".json": "application/json"}.get(Path(n).suffix, "text/plain")
    parts.append({"mime_type": mime, "filename": n, "content_disposition": "attachment",
                  "body": {"base64_url_content": base64.urlsafe_b64encode(raw).decode()}})
    rows.append({"name": n, "bytes": len(raw), "sha256": sha(raw), "mime_type": mime})
args = {"to": "hyungjininfocz.son@partner.samsung.com",
        "subject": "[GENOS] MAIN94 — 중복 검색·자동 재조사 3건 수정 (2026-10-20 R1)",
        "payload": {"mime_type": "multipart/mixed", "parts": parts},
        "response_fields": ["id", "thread_id", "label_ids"]}
(H / "EMAIL_ARGS.json").write_bytes(json.dumps(args, ensure_ascii=True).encode())
(H / "EMAIL_BODY_UTF8.html").write_text(body)
(H / "EMAIL_ATTACHMENT_BINDING.json").write_bytes(enc(rows))
(H / "EMAIL_PRECHECK.json").write_bytes(enc({"status": "PASS", "to": args["to"],
    "subject": args["subject"], "attachments": rows, "members_scanned": count,
    "javascript_exclusions": "PASS", "bash_syntax": "PASS",
    "args_bytes": (H / "EMAIL_ARGS.json").stat().st_size}))
print(json.dumps({"status": "PASS", "to": args["to"], "attachments": len(rows),
                  "args_bytes": (H / "EMAIL_ARGS.json").stat().st_size}))
