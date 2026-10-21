"""Prepare the explicitly requested Samsung handoff without sending it."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "GENOS_OUTPUT_UNLIMITED_20261015_R1"
NAMES = [f"{VERSION}.zip", f"{VERSION}_RUN.txt", "GUIDE_UTF8.txt", "VALIDATION_SUMMARY.txt", "VALIDATION.json", "SHA256SUMS.txt"]
BANNED = {".js", ".jsx", ".mjs", ".cjs"}
for line in (ROOT / "SHA256SUMS.txt").read_text().splitlines():
    expected, name = line.split(maxsplit=1)
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name

def inspect_archive(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        for member in archive.infolist():
            assert Path(member.filename).suffix.lower() not in BANNED, member.filename
            if member.filename.lower().endswith(".zip"):
                inspect_archive(archive.read(member))

inspect_archive((ROOT / NAMES[0]).read_bytes())
with zipfile.ZipFile(ROOT / NAMES[0]) as archive:
    scripts = [n for n in archive.namelist() if Path(n).name == NAMES[1]]
    assert len(scripts) == 1
    assert archive.read(scripts[0]) == (ROOT / NAMES[1]).read_bytes()
subprocess.run(["bash", "-n", str(ROOT / NAMES[1])], check=True)

body = f"""<!doctype html><html><body>
<p>GENOS RAG·AD <strong>출력 토큰 상한 제거 R1</strong> 적용본을 보냅니다.</p>
<p>이번에 사용할 파일은 <strong>{VERSION}.zip</strong>입니다.
LENGTH_RECOVERY R1 또는 R2를 적용한 기존 DEV에 필요한 이전 복구·문구 패치를 먼저 적용하고,
<strong>이번 출력 상한 제거 R1을 마지막에 적용</strong>해 주세요. FACT_REASON R1 적용 여부는 모두 지원합니다.</p>
<p>GENOS 모델 요청에서 앱의 max_tokens를 생략하고, 단계별 6,400/12,800 기본 상한과
기존 GENOS_RAG_MAX_OUTPUT_TOKENS 환경변수도 적용하지 않습니다.
모델 서버 자체의 기본 생성 길이·컨텍스트·출력 한도는 서버 설정에 따라 남습니다.</p>
<p><strong>1. 실제 업로드한 TRANSFER 폴더에서 실행</strong></p>
<pre>python3 -m zipfile -e ./{VERSION}.zip ./{VERSION}
bash ./{VERSION}/{VERSION}_RUN.txt install</pre>
<p>기존 ~/DEV를 사전 검사하고 백업·적용·검증합니다. 실제 checkout이 다를 때만 확인한 경로를
GENOS_DEV_ROOT로 지정합니다. 독립 RUN.txt와 ZIP 안 RUN.txt는 같은 완전한 실행 파일입니다.
실행 로그는 TRANSFER/output-unlimited-r1-logs에 남으며 출력된 BACKUP과 APPLIED_CODE_ZIP을 보관해 주세요.</p>
<p><strong>2. 기존 DEV에서 변경 확인·commit → 실제 TRANSFER에서 gate</strong></p>
<p>git diff --check를 확인하고 설치 receipt의 파일 및 CODE_MANIFEST.json만 commit합니다.
아래 두 한글 예시는 실제 절대경로로 바꿔 실행해 주세요.</p>
<pre>bash ./{VERSION}/{VERSION}_RUN.txt gate "실제 BACKUP 절대경로" --generation "현재 선택된 generation 절대경로"</pre>
<p>gate 통과 commit을 push하고 같은 commit의 새 코드서빙 리비전을 배포한 뒤 분리 SSE 프로세스를 재시작합니다.
원문/NFS generation 재구축이나 이번 변경을 위한 워크플로우 Python 편집기 교체는 필요 없습니다.</p>
<p><strong>3. 워크플로우 테스트 화면에서 확인</strong></p>
<p>새 요청으로 정상 질문과 길이 종료 질문을 확인합니다. 같은 요청의 모델 request에 max_tokens와
max_completion_tokens가 없는지, 실제 usage·finish_reason·최종 상태를 확인하고 request ID와
commit/리비전/generation을 남겨 주세요. 서버가 length로 종료하면 미완료 상태를 보존합니다.</p>
<p>로컬 신규 계약 20개, 설치 관련 10개, 두 설치 구성 계약/API 156개를 통과했습니다.
확대 검사 182개 통과와 수정 전에도 재현된 기존 실패 총 5개를 구분해 기록했습니다.
실제 GENOS 반입·배포·내부 모델 성공은 아직 확인하지 않았고, 로컬 MAIN66은 유지했습니다.</p>
<p>첨부 6개: 적용 ZIP, 독립 실행 TXT, 적용·원복 안내, 검증 요약, 상세 검증 JSON, SHA-256 목록.</p>
<p>ZIP SHA-256: c3cc490ed37dc6edf8d80712541ae6bb4afddb2678e4ff24be0f8818b761b554</p>
</body></html>"""
parts = [{"mime_type": "text/html", "charset": "UTF-8", "body": {"content": body}}]
bindings = []
for name in NAMES:
    path = ROOT / name
    assert path.suffix.lower() not in BANNED
    raw = path.read_bytes()
    mime = {".zip": "application/zip", ".json": "application/json"}.get(path.suffix, "text/plain")
    parts.append({"mime_type": mime, "content_disposition": "attachment", "filename": name,
                  "body": {"base64_url_content": base64.urlsafe_b64encode(raw).decode()}})
    bindings.append({"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "mime_type": mime})
args = {"to": "hyungjininfocz.son@partner.samsung.com", "subject": "[GENOS 출력 상한 제거 R1] 적용 ZIP·실행 TXT 및 검증 자료",
        "payload": {"mime_type": "multipart/mixed", "parts": parts}, "response_fields": ["id", "thread_id", "label_ids"]}
(ROOT / "EMAIL_BODY_UTF8.html").write_text(body, encoding="utf-8")
(ROOT / "EMAIL_ATTACHMENT_BINDING.json").write_text(json.dumps(bindings, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
(ROOT / "EMAIL_ARGS.json").write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"to": args["to"], "subject": args["subject"], "attachments": bindings,
                  "args_characters": len((ROOT / "EMAIL_ARGS.json").read_text()), "archive_scan": "PASS", "bash_syntax": "PASS"}, ensure_ascii=False))
