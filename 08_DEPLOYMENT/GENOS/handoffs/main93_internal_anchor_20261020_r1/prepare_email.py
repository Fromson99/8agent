"""Prepare the explicitly authorized Samsung message from verified, sealed files."""
from pathlib import Path
import base64, hashlib, io, json, subprocess, zipfile
H = Path(__file__).resolve().parent
N = "GENOS_MAIN93_INTERNAL_ANCHOR_20261020_R1"
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
<p>요청하신 <strong>내규 기반 대사를 로컬 MAIN93 / workflow 1.20.0으로 전환</strong>하고, 같은 코드의 GENOS 누적 설치본을 보내드립니다.</p>
<p><strong>질문 → 관련 내규 원문 → 개념·조항 범위 → 연결 외규 원문 → 필요한 외규 참조 추가 탐색 → 대사표</strong> 순서입니다.
승인된 내규–외규 연결은 지정 원문을 우선 가져오고, 연결이 없거나 부족하면 내규 내용으로 외규를 조사합니다.
외규에서 다른 외규로 이어지는 참조도 필요에 따라 선택해 읽습니다. 연결 전체를 무한 자동 조회하지 않습니다.</p>
<p>표에는 내규 출처·조항, 개념, 실제 내규 원문, 연결 외규 출처·원문, 해석·미확인을 함께 표시합니다.
승인 연결은 조회 대상이며 법적 부합 확정을 뜻하지 않습니다. 미승인 후보와 미확보는 구분합니다.</p>
<p><strong>앞서 보낸 MAIN92_CUMULATIVE / BASIS_BATCH_R4 / BASIS_ENTRY_FIX 코드 적용본 대신 이번 {N}.zip을 사용하세요.</strong>
최근 관계 조회·후보 조사·BASIS_IDENTITY 오류 수정과 기존 Oracle 긴 조회키 처리를 포함했습니다.
기존 데이터·승인 관계·조사 기록·환경 설정은 유지합니다.</p>
<p>ZIP을 업로드한 <strong>실제 TRANSFER 폴더에서</strong> 실행합니다. 적용 대상은 기존 <code>~/DEV</code> Git checkout입니다.</p>
<pre>python3 -m zipfile -e ./{N}.zip ./{N}
bash ./{N}/{N}_RUN.txt check
bash ./{N}/{N}_RUN.txt apply
bash ./{N}/{N}_RUN.txt status</pre>
<p>첫 명령부터 로그·종료 상태를 보존하고 백업 후 적용합니다. Python3.11 이상과 기존 의존성을 사용합니다.
sqlglot30.23.0이 없을 때만 동봉 <code>deps</code>를 먼저 실행합니다.
적용 후 기존 checkout의 변경 검토·commit → TRANSFER에서 <code>gate-code</code>
(현재 SQLite/NFS 사용 시 같은 generation의 <code>gate-sqlite</code>도 확인) → push → 같은 commit의 새 리비전 배포 순서입니다.</p>
<p><strong>동봉 WORKFLOW_PASTE_ALL.txt 전체를 워크플로우 Python 편집기에 반영하고 저장하세요.</strong>
현장 질의 확인은 워크플로우 테스트 화면의 새 채팅에서 진행합니다.
예: “대사: 유동성비율 관련 외규가 위험관리기준시행세칙에 어떻게 반영되어 있나요?”</p>
<p>이전 코드에 결속된 실패/중단 요청을 강제 재개하지 마세요.
기존 BASIS_RUN/BATCH 실행기는 옛 코드 게이트에 고정돼 있으므로 이번 코드에 무리하게 사용하거나 해시를 고치지 않습니다.
이번 설치는 채팅 대사 MAIN 전환이며 전체 배치 실행·후보 자동 승인·DB 이관을 자동 수행하지 않습니다.</p>
<p><strong>검증:</strong> 선택 runtime393파일은 작업·동결·MAIN·인계본이 동일합니다.
로컬 계약193개, 인계본 계약{validation['handoff_contracts']}개, 설치2시나리오43명령,
최종 ZIP 재추출·적용·상태·원복5명령을 확인했습니다.
실제 로컬 service 선택·HEALTH·원문 읽기도 확인했고 새 모델 호출은0회입니다.</p>
<p><strong>로컬 MAIN93 완료, GENOS 실제 반입·push·리비전·편집기·Oracle/NFS·내부 모델 검증은 별도</strong>입니다.
기존 의미 판단·최종 품질/비용 한계는 유지하며 quality_certified=false입니다.
실행/재실행/배포 게이트/원복 상세는 GUIDE_UTF8.txt를 보세요.</p>
<p>첨부7개: 코드 ZIP, 독립 실행 TXT, 워크플로우 편집기 전체본, 안내, 검증 JSON, 최종 ZIP 검증 JSON, SHA256 목록.
ZIP 안에도 실행 TXT·안내를 넣었고 중첩 압축까지 JavaScript 파일0개를 확인했습니다.</p>
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
        "subject": "[GENOS] MAIN93 전환 — 내규 기반 외규 연결·연속 탐색 대사 (2026-10-20 R1)",
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
