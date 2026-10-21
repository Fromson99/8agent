"""Post-run formatting, lossless runtime archival and integrity inventory only."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import tarfile
from datetime import datetime, timezone

R = Path(__file__).resolve().parents[3]
A = R / "04_EXPERIMENTS/ADR/ADR-0955-main94-design-weakness-probe"
F = A / "artifacts"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


questions = sorted((A / "실험").glob("질문-*.md"))
backup = F / "question-format-before.json.gz"
assert not backup.exists(), "One-shot record closure; do not overwrite."
with gzip.open(backup, "wt", encoding="utf-8") as stream:
    json.dump({str(p.relative_to(R)): p.read_text() for p in questions}, stream,
              ensure_ascii=False)
format_rows = []
for p in questions:
    original = p.read_text()
    top, tail = original.split("\n## 사용자 질문 원문\n", 1)
    question, tail = tail.split("\n## 기준과 필수 원문 — 채점 전용, 제품 입력 비공개\n", 1)
    gold, tail = tail.split("\n## 실제 답변\n", 1)
    answer, tail = tail.split("\n## 제품·중간 호출 원값\n", 1)
    payload, tail = tail.split("\n## 단계별 원문 회수·반환·인용\n", 1)
    ledger, judgement = tail.split("\n## 오프라인 판정\n", 1)
    title, metadata = top.split("\n", 1)
    formatted = (
        title + "\n\n## 1. 실행 메타\n" + metadata +
        "\n## 2. 사용자 질문 원문\n" + question +
        "\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n" + gold +
        "\n## 4. 제품 입력을 구성한 원값\n" + payload +
        "\n### 회수·탈락 단계 원장 — run·arm별\n" + ledger +
        "\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n"
        "각 호출의 전체 입력·출력은 4절의 request/response/receipt 링크에 보존했다.\n"
        "다음은 실제 최종 답변이며 판정 오류를 수정하지 않았다.\n\n" + answer +
        "\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n"
        "중간 호출도 4절의 연속 call 번호에 포함한다. 단계별 view·schema·출력과 "
        "공급자 실제 응답을 원본 그대로 보존했으며 별도 재생성은 없다.\n"
        "\n## 7. 채점 호출과 반복 판정\n"
        "채점 모델 호출 0회, 저장 기록을 한 평가자가 1회 검토했다. 독립 평가자 "
        "일치도는 측정하지 않았다. 사전 기준과 추가 관찰을 구분하며 재실행하지 않았다.\n"
        "\n## 8. 사례 최종 판정\n" + judgement
    )
    for section in (question, gold, answer, payload, ledger, judgement):
        assert section in formatted
    before = digest(p)
    p.write_text(formatted)
    format_rows.append({"path": str(p.relative_to(R)), "before": before,
                        "after": digest(p), "original_sections_preserved": True})
put(F / "record-format-receipt.json", {
    "kind": "post_run_formatting_only",
    "first_validation_issue": "Required numbered headings missing; artifact inventory scaffold unfinished.",
    "product_calls_added": 0, "scores_or_criteria_changed": False,
    "backup": str(backup.relative_to(R)), "files": format_rows,
})

frozen = json.loads((F / "design/freeze.json").read_text())["files"]
for name, expected in frozen.items():
    assert digest(R / name) == expected, name
selected = json.loads((F / "design/selected-main.json").read_text())
assert json.loads((R / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text()) == selected["pointer"]
assert digest(R / selected["pointer"]["manifest_path"]) == selected["pointer"]["release_manifest_sha256"]
for name, expected in selected["manifest"]["files"].items():
    assert digest(R / name) == expected, name
put(F / "final-integrity.json", {
    "status": "PASS", "frozen_files_checked": len(frozen),
    "working_product_files_checked": len(selected["manifest"]["files"]),
    "main_pointer_unchanged": True, "selected_release_hash_unchanged": True,
    "release_id": selected["pointer"]["release_id"],
    "model_calls_added": 0, "genos_executed": False,
})

# Only completed, experiment-specific mutable runtimes are archived. Frozen
# source data, candidate snapshot and raw model-call evidence remain in place.
runtimes = sorted((F / "run-001/observed").glob("*/runtime"))
assert len(runtimes) == 4
runtime_files = [p for root in runtimes for p in sorted(root.rglob("*")) if p.is_file()]
assert all(str(p.relative_to(R)) not in frozen for p in runtime_files)
inventory = {str(p.relative_to(R)): {"sha256": digest(p), "bytes": p.stat().st_size}
             for p in runtime_files}
archive = F / "completed-runtime.tar.gz"
assert not archive.exists()
with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
    for root in runtimes:
        bundle.add(root, arcname=str(root.relative_to(R)))
with tarfile.open(archive, "r:gz") as bundle:
    members = [m for m in bundle.getmembers() if m.isfile()]
    assert {m.name for m in members} == set(inventory)
    for member in members:
        stream = bundle.extractfile(member)
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
        assert h.hexdigest() == inventory[member.name]["sha256"]
put(F / "completed-runtime-inventory.json", {
    "archive": str(archive.relative_to(R)), "sha256": digest(archive),
    "bytes": archive.stat().st_size, "files": inventory,
    "verified_all_members": True, "processes_completed": True,
    "restore_from_repository_root": f"tar -xzf {archive.relative_to(R)}",
})
for root in runtimes:
    shutil.rmtree(root)
(A / "RESTORE.txt").write_text(
    "완료된 사례별 임시 runtime은 파일별 해시 검증 후 무손실 압축 보존했다.\n"
    "원문 데이터·candidate snapshot·raw 모델 요청/응답·판정은 원래 경로에 있다.\n"
    "runtime journal을 다시 열거나 사후 audit를 재현할 때 저장소 루트에서 복원:\n"
    f"tar -xzf {archive.relative_to(R)}\n"
    "파일별 원본 해시: artifacts/completed-runtime-inventory.json\n"
    "완료 실행은 덮어쓰거나 재호출하지 않는다. 후속 실행은 새 ADR에 동결한다.\n"
)

files = sorted(p for p in F.rglob("*")
               if p.is_file() and p != F / "manifest.json"
               and "__pycache__" not in p.parts)
files += sorted((R / "06_TOOLS/EXPERIMENTS/adr_0955").glob("*.py"))
files.append(A / "RESTORE.txt")
put(F / "manifest.json", {
    "schema_version": "adr-artifacts-v1", "adr_id": "ADR-0955",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "files": [{
        "path": str(p.relative_to(R)), "sha256": digest(p),
        "bytes": p.stat().st_size, "description": "Preserved experiment evidence or reproducibility input",
        "contains_raw_prompts_and_outputs": "raw" in p.parts or "canonical" in p.parts,
    } for p in files],
})
print(json.dumps({"formatting": len(questions), "frozen_files": len(frozen),
                  "product_files": len(selected["manifest"]["files"]),
                  "archived_runtime_files": len(runtime_files),
                  "artifact_files": len(files), "main_unchanged": True}))
