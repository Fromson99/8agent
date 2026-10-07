"""A frozen experiment cannot replace changes made in MAIN after it branched."""
import hashlib
import json

import pytest

from semantic_runtime.release_integration import check, draft


def digest(value):
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def workspace(tmp_path):
    root = tmp_path
    release = root / "08_DEPLOYMENT/RELEASES/current/release.json"
    release.parent.mkdir(parents=True)
    before = {"rag.py": digest("current rag"), "scope.py": digest("new MAIN scope")}
    release.write_text(json.dumps({"files": before}))
    pointer = root / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"generation": 2, "release_id": "current",
                                   "manifest_path": str(release.relative_to(root)),
                                   "release_manifest_sha256": digest(release.read_bytes())}))
    binding = {"pointer": json.loads(pointer.read_text()),
               "pointer_sha256": digest(pointer.read_bytes())}
    return root, binding, before


def candidate(root, upstream):
    directory = root / "02_BACKEND/lawrag/research/candidates/adr_9999/feature"
    frozen = directory / "revisions/rev-001/snapshot/rag.py"
    frozen.parent.mkdir(parents=True)
    frozen.write_text("candidate rag")
    relative = str(frozen.relative_to(root))
    manifest = directory / "candidate.json"
    revision = {"revision_id": "rev-001", "frozen_at": "2026-09-30T00:00:00Z",
                "files": [{"snapshot_path": "snapshot/rag.py", "frozen_path": relative,
                           "snapshot_sha256": digest(frozen.read_bytes())}]}
    revision["revision_sha256"] = digest(json.dumps(
        revision, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    manifest.write_text(json.dumps({
        "schema_version": "adr-code-candidate-v2", "status": "research-only",
        "production_loadable": False,
        "files": [{"target_path": "rag.py", "snapshot_path": "snapshot/rag.py",
                   "upstream_state": "present", "upstream_sha256": upstream}],
        "revisions": [revision]}))
    return {"manifest_path": str(manifest.relative_to(root)),
            "manifest_sha256": digest(manifest.read_bytes()),
            "revision_id": "rev-001", "revision_sha256": revision["revision_sha256"]}


def declaration(root, binding, files, source):
    value = draft(root, binding["pointer"], files)
    for row in value["changes"]:
        row["reason"] = "frozen experiment change"
    value["candidate"] = source
    return value


def test_preserves_unrelated_main_feature_and_accepts_scoped_candidate(tmp_path):
    root, binding, before = workspace(tmp_path)
    after = {**before, "rag.py": digest("candidate rag")}
    source = candidate(root, before["rag.py"])
    result = check(root, binding, after, declaration(root, binding, after, source))
    assert result["candidate_files"] == ["rag.py"]
    assert result["preserved_files"] == 1


def test_rejects_old_snapshot_after_same_main_file_changed(tmp_path):
    root, binding, before = workspace(tmp_path)
    after = {**before, "rag.py": digest("candidate rag")}
    source = candidate(root, digest("old rag"))
    with pytest.raises(ValueError, match="rebased on active MAIN"):
        check(root, binding, after, declaration(root, binding, after, source))


def test_rejects_undeclared_loss_of_other_main_feature(tmp_path):
    root, binding, before = workspace(tmp_path)
    after = {"rag.py": digest("candidate rag"), "scope.py": digest("old scope")}
    source = candidate(root, before["rag.py"])
    value = declaration(root, binding, {**before, "rag.py": after["rag.py"]}, source)
    with pytest.raises(ValueError, match="missing=\\['scope.py'\\]"):
        check(root, binding, after, value)


def test_rejects_plan_when_main_pointer_moves(tmp_path):
    root, binding, before = workspace(tmp_path)
    after = {**before, "rag.py": digest("candidate rag")}
    source = candidate(root, before["rag.py"])
    value = declaration(root, binding, after, source)
    pointer = root / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json"
    pointer.write_text(pointer.read_text() + "\n")
    with pytest.raises(ValueError, match="active MAIN changed"):
        check(root, binding, after, value)


def test_rejects_frozen_candidate_drift_after_review(tmp_path):
    root, binding, before = workspace(tmp_path)
    after = {**before, "rag.py": digest("candidate rag")}
    source = candidate(root, before["rag.py"])
    value = declaration(root, binding, after, source)
    check(root, binding, after, value)
    frozen = root / "02_BACKEND/lawrag/research/candidates/adr_9999/feature/revisions/rev-001/snapshot/rag.py"
    frozen.write_text("changed after review")
    with pytest.raises(ValueError, match="frozen file changed"):
        check(root, binding, after, value)


def test_activation_rejects_old_prepared_release_without_integration(tmp_path, monkeypatch):
    from semantic_runtime import control, storage

    root, binding, _ = workspace(tmp_path)
    monkeypatch.setattr(storage, "Store", lambda path: type("Checked", (), {"close": lambda self: None})())
    destination = root / "08_DEPLOYMENT/RELEASES/unreviewed"
    (destination / "code").mkdir(parents=True)
    (destination / "code/rag.py").write_text("old experiment rag")
    generation = root / "01_DATA/GENERATIONS/synthetic"
    generation.mkdir(parents=True)
    (generation / "manifest.json").write_text("{}")
    (destination / "authorization.json").write_text("{}")
    (destination / "validation.json").write_text(json.dumps({"structural_checks_passed": True}))
    manifest = destination / "release.json"
    manifest.write_text(json.dumps({
        "schema_version": "semantic-runtime-release-v2",
        "code_root": str((destination / "code").relative_to(root)),
        "files": {"rag.py": digest("old experiment rag")},
        "data_path": str(generation.relative_to(root)),
        "data_manifest_sha256": digest((generation / "manifest.json").read_bytes()),
        "authorization_sha256": digest((destination / "authorization.json").read_bytes()),
        "validation_sha256": digest((destination / "validation.json").read_bytes()),
        "previous_active_sha256": binding["pointer_sha256"],
        "release_id": "unreviewed"}))
    with pytest.raises(ValueError, match="integration declaration is required"):
        control.activate(root, manifest, confirm=True)
    pointer = root / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json"
    assert digest(pointer.read_bytes()) == binding["pointer_sha256"]


def test_prepare_requires_reviewed_delta_and_activation_rechecks_it(tmp_path, monkeypatch):
    from semantic_runtime import control, storage

    root = tmp_path / "workspace"
    stage = tmp_path / "stage"
    for base in (root, stage):
        (base / "02_BACKEND/semantic_runtime").mkdir(parents=True)
        (base / "02_BACKEND/ENGINES/term_runtime").mkdir(parents=True)
        (base / "06_TOOLS").mkdir(parents=True)
        (base / "00_SYSTEM").mkdir(parents=True)
        (base / "service.py").write_text("# service\n")
        (base / "06_TOOLS/serve.sh").write_text("# serve\n")
        (base / "00_SYSTEM/PIPELINE.json").write_text(json.dumps({
            "engines": {}, "contracts": {},
            "profiles": {"legal-rag": {"nodes": [{"id": "retrieve", "parameters": {}}]}}}))
    (stage / "02_BACKEND/semantic_runtime/rag.py").write_text("old rag")
    pointer = root / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"generation": 0, "release_id": "bootstrap"}))
    generation = root / "01_DATA/GENERATIONS/sample"
    generation.mkdir(parents=True)
    (generation / "store.sqlite").write_bytes(b"synthetic store")
    (generation / "manifest.json").write_text(json.dumps({"store_sha256": digest(b"synthetic store")}))
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps({"quality_gate_override": True}))
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"structural_checks_passed": True}))
    base_manifest = control.prepare(root, stage, generation, "base", authorization, validation)
    pointer.write_text(json.dumps({"generation": 1, "release_id": "base",
                                   "manifest_path": str(base_manifest.relative_to(root)),
                                   "release_manifest_sha256": digest(base_manifest.read_bytes())}))
    (stage / "02_BACKEND/semantic_runtime/rag.py").write_text("new rag")
    with pytest.raises(ValueError, match="integration declaration is required"):
        control.prepare(root, stage, generation, "missing-review", authorization, validation)
    assert not (root / "08_DEPLOYMENT/RELEASES/missing-review").exists()

    preview = tmp_path / "integration-draft.json"
    control.prepare(root, stage, generation, "preview-only", authorization, validation, preview)
    assert not (root / "08_DEPLOYMENT/RELEASES/preview-only").exists()
    reviewed = json.loads(preview.read_text())
    assert [row["path"] for row in reviewed["changes"]] == ["02_BACKEND/semantic_runtime/rag.py"]
    reviewed["changes"][0]["reason"] = "reviewed RAG update"
    validation.write_text(json.dumps({"structural_checks_passed": True, "integration": reviewed}))
    manifest = control.prepare(root, stage, generation, "reviewed", authorization, validation)
    assert json.loads(manifest.read_text())["integration"]["changed_files"] == 1
    monkeypatch.setattr(storage, "Store", lambda path: type("Checked", (), {"close": lambda self: None})())
    applied = control.activate(root, manifest, confirm=True)
    assert applied["release_id"] == "reviewed"
    assert applied["generation"] == 2
