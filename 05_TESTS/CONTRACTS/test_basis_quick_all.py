"""All-document coordinator: no model or production data access."""
import csv
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("basis_quick", ROOT / "06_TOOLS/COMMANDS/basis_quick.py")
quick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quick)


class FakeRunner:
    def __init__(self, rows, runtime):
        self.rows, self.runtime, self.calls = rows, runtime, []
        self.stop = None
        self.partial = None
        self.corrupt = None
        self.fail_plan = None
        self.change_binding = None
        self.structure_errors = set()
        self.preflight_error = None
        self.preflight_calls = []

    def preflight(self, folder, ids=None, listing=False):
        self.preflight_calls.append((str(folder), ids))
        if self.preflight_error:
            raise ValueError(self.preflight_error)
        rows = [r for r in self.rows if ids is None or r["document_id"] in ids]
        if listing:
            self.call("list", folder)
        failures = [{**{k: r[k] for k in ("document_id", "name", "source_artifact_sha256")},
                     "status": "failed", "phase": "plan", "code": "BASIS_STRUCTURE",
                     "message": "상위 구조의 범위가 하위를 포함하지 않습니다.", "research_attempted": False}
                    for r in rows if ids is not None and r["document_id"] in self.structure_errors]
        return {"schema": "basis-structure-preflight-v1", "documents": rows, "failures": failures,
                "binding": {"generation": "g", "principal": "u", "profile": "fixed"}, "receipt_sha256": "mock"}

    def call(self, action, job=None, *, ids=None, count=None, output=None, log=None):
        self.calls.append((action, str(job), ids))
        job.mkdir(parents=True, exist_ok=True)
        if action == "list":
            with (job / "LATEST_INTERNAL.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]) if self.rows else
                                        ["document_id", "name", "chars", "is_latest", "source_artifact_sha256"])
                writer.writeheader()
                writer.writerows(self.rows)
            return 0
        if action == "plan":
            if self.fail_plan == job.name:
                return 1
            docs = [{k: d[k] for k in ("document_id", "name", "source_artifact_sha256")}
                    for d in self.rows if d["document_id"] in ids]
            value = {"schema_version": "basis-batch-v1", "batch_id": job.name, "documents": docs,
                     "binding": {"generation": "g", "principal": "u",
                                 "profile": "changed" if self.change_binding == job.name else "fixed"},
                     "candidate_storage": {"kind": "json-candidates-v1", "path": str(job / "CANDIDATES.json"),
                                           "publication": "manual-review-only"}}
            quick.atomic(job / "PLAN.json", value, "plan_sha256")
            return 0
        if action in ("run", "resume"):
            plan = quick.checked(job / "PLAN.json", "plan_sha256")
            prior = quick.read(job / "STATE.json") if (job / "STATE.json").exists() else {}
            state = {"plan_sha256": plan["plan_sha256"], "status": "completed", "documents": {},
                     "usage": prior.get("usage", 7), "deadline": prior.get("deadline", "fixed-deadline")}
            for doc in plan["documents"]:
                state["documents"][doc["document_id"]] = {"status": "completed"}
            if self.stop == job.name:
                state["status"] = "interrupted"
                state["documents"] = {plan["documents"][0]["document_id"]: {"status": "running"}}
                quick.atomic(job / "STATE.json", state, "state_sha256")
                return 1
            if self.partial == job.name:
                state["status"] = "partial"
                state["documents"][plan["documents"][0]["document_id"]]["status"] = "failed"
            if self.corrupt == job.name:
                del state["documents"][plan["documents"][0]["document_id"]]
            quick.atomic(job / "STATE.json", state, "state_sha256")
            return 2 if state["status"] == "partial" else 0
        if action == "report":
            output.write_text("<p>내규 원문 / 외규 원문 / 미확인</p>", encoding="utf-8")
            log.write(json.dumps({"event": "basis.artifacts.html", "links": 0}) + "\n")
            return 0
        raise AssertionError(action)


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(quick, "resources", lambda path: None)
    rows = [{"document_id": f"doc{i:03d}", "name": f"내규{i}", "chars": str(i + 1),
             "source_artifact_sha256": str(i % 10) * 64, "is_latest": "True"} for i in range(43)]
    runner = FakeRunner(rows, tmp_path)
    c = quick.Campaign(runner, tmp_path / "all", tmp_path, {"code": "fixed"})
    return c, runner


def test_all_43_documents_freezes_disjoint_plans_before_run_and_reuses(campaign):
    c, r = campaign
    c.initialize()
    assert c.run() == 0
    assert [a for a, _, _ in r.calls] == ["list", "plan", "plan", "plan", "run", "run", "run"]
    ids = [ids for a, _, ids in r.calls if a == "plan"]
    assert [len(v) for v in ids] == [20, 20, 3]
    assert len(set(sum(ids, []))) == 43
    before = list(r.calls)
    c.initialize()
    assert c.run() == 0
    assert before == r.calls
    result = c.status()
    assert result["documents"]["completed"] == 43


def test_interrupt_preserves_usage_and_resume_does_not_repeat_completed(campaign):
    c, r = campaign
    c.initialize()
    r.stop = "part-00002"
    with pytest.raises(ValueError, match="하위 조사 중단"):
        c.run()
    state_path = c.job / "parts/part-00002/STATE.json"
    before = quick.read(state_path)
    r.stop = None
    offset = len(r.calls)
    assert c.run() == 0
    assert [a for a, _, _ in r.calls[offset:]] == ["resume", "run"]
    after = quick.read(state_path)
    assert after["usage"] == before["usage"] and after["deadline"] == before["deadline"]


def test_partial_and_failed_documents_remain_and_continue(campaign):
    c, r = campaign
    c.initialize()
    r.partial = "part-00001"
    assert c.run() == 2
    assert c.status()["documents"] == {"completed": 42, "failed": 1, "partial": 0, "running": 0, "pending": 0}
    before = list(r.calls)
    assert c.run() == 2 and r.calls == before


def test_planning_failure_runs_no_model_and_resumes_plans(campaign):
    c, r = campaign
    c.initialize()
    r.fail_plan = "part-00002"
    with pytest.raises(ValueError, match="하위 계획 실패"):
        c.run()
    assert not any(a in ("run", "resume") for a, _, _ in r.calls)
    r.fail_plan = None
    assert c.run() == 0
    assert sum(a == "plan" and path.endswith("00001") for a, path, _ in r.calls) == 1


@pytest.mark.parametrize("target,key", [("ALL_PLAN.json", "plan_sha256"), ("ALL_STATE.json", "state_sha256")])
def test_corrupt_parent_hash_blocks_without_calls(campaign, target, key):
    c, r = campaign
    c.initialize()
    c.run()
    p = c.job / target
    value = quick.read(p)
    value[key] = "bad"
    quick.atomic(p, value)
    offset = len(r.calls)
    with pytest.raises(ValueError, match="해시 불일치"):
        c.run()
    assert len(r.calls) == offset


def test_changed_binding_blocks_before_research(campaign):
    c, r = campaign
    c.initialize()
    r.change_binding = "part-00002"
    with pytest.raises(ValueError, match="결속"):
        c.run()
    assert not any(a in ("run", "resume") for a, _, _ in r.calls)


def test_deleted_finished_child_state_is_not_new_budget(campaign):
    c, r = campaign
    c.initialize()
    c.run()
    (c.job / "parts/part-00001/STATE.json").unlink()
    offset = len(r.calls)
    with pytest.raises(ValueError, match="사라지거나"):
        c.run()
    assert len(r.calls) == offset


def test_result_missing_document_is_not_complete(campaign):
    c, r = campaign
    c.initialize()
    r.corrupt = "part-00001"
    with pytest.raises(ValueError, match="처리 문서가 누락"):
        c.run()
    assert not any(a == "run" and p.endswith("00002") for a, p, _ in r.calls)


def test_existing_single_plan_preserved(campaign):
    c, r = campaign
    c.job.mkdir()
    path = c.job / "PLAN.json"
    path.write_text("original")
    with pytest.raises(ValueError, match="개별 작업"):
        c.initialize()
    assert path.read_text() == "original" and not r.calls


def test_catalogue_change_blocks(campaign):
    c, r = campaign
    c.initialize()
    p = c.job / "catalogue/LATEST_INTERNAL.csv"
    with p.open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="목록이 변경"):
        c.run()
    assert len(r.calls) == 1


def test_atomic_plan_created_before_parent_receipt_is_recovered(campaign):
    c, r = campaign
    c.initialize()
    c.load()
    part = c.plan["parts"][0]
    folder = c.job / "parts" / part["name"]
    r.call("plan", folder, ids=[d["document_id"] for d in part["documents"]])
    previous = (folder / "PLAN.json").read_bytes()
    assert c.run() == 0
    assert (folder / "PLAN.json").read_bytes() == previous


def test_child_hash_change_and_symlink_rejected(campaign, tmp_path):
    c, r = campaign
    c.initialize()
    c.run()
    p = c.job / "parts/part-00001/PLAN.json"
    data = quick.read(p)
    data["documents"][0]["name"] = "changed"
    quick.atomic(p, data)
    with pytest.raises(ValueError, match="해시 불일치"):
        c.run()
    link = tmp_path / "link"
    link.symlink_to(p)
    with pytest.raises(ValueError, match="심볼릭"):
        quick.read(link)


def test_global_lock_prevents_simultaneous_launch(tmp_path):
    with quick.lock(tmp_path / "lock"):
        with pytest.raises(ValueError, match="실행 중"):
            with quick.lock(tmp_path / "lock"):
                pytest.fail("lock bypass")


def test_report_index_uses_original_reporter_and_preserves_sources(campaign, tmp_path):
    c, r = campaign
    c.initialize()
    c.run()
    before = (c.job / "ALL_PLAN.json").read_bytes()
    assert c.render(tmp_path / "report") == 0
    index = (tmp_path / "report/INDEX.html").read_text()
    assert "part-00001.html" in index and "part-00003.html" in index
    assert "내규 43개" in index
    assert before == (c.job / "ALL_PLAN.json").read_bytes()


def test_resource_pressure_prevents_new_child(campaign, monkeypatch):
    c, r = campaign
    c.initialize()
    def fail(path):
        raise ValueError("가용 RAM")
    monkeypatch.setattr(quick, "resources", fail)
    with pytest.raises(ValueError, match="가용 RAM"):
        c.run()
    assert not any(a == "plan" for a, _, _ in r.calls)


def test_empty_catalogue_not_silent_success(campaign):
    c, r = campaign
    r.rows = []
    with pytest.raises(ValueError, match="최신 내규가 없습니다"):
        c.initialize()
    assert not c.plan_path.exists()


def test_diagnostic_reports_exact_engine_path_and_hash_without_mutation(tmp_path):
    root = tmp_path / "root"
    (root / "00_SYSTEM").mkdir(parents=True)
    manifest = root / "engine.json"
    manifest.write_text('{"files":{}}')
    pipeline = {"engines": {"a": {"manifest": "engine.json", "sha256": "0" * 64}}}
    quick.atomic(root / "00_SYSTEM/PIPELINE.json", pipeline)
    before = manifest.read_bytes()
    assert quick.diagnose(root, tmp_path, [{"folder": "fixed", "pipeline_sha256":
                                          quick.sha(root / "00_SYSTEM/PIPELINE.json")}]) == 1
    result = quick.read(next(tmp_path.glob("BASIS_CODE_CHECK_*.json")))
    assert result["manifest_mismatches"][0]["path"] == str(manifest)
    assert result["manifest_mismatches"][0]["actual"] == quick.sha(manifest)
    assert manifest.read_bytes() == before


def test_old_loaded_pipeline_and_new_manifest_reproduce_photo(tmp_path):
    from types import SimpleNamespace as S
    from semantic_runtime.stage_runner import StageRunner
    manifest = tmp_path / "engine.json"
    manifest.write_text('{"kind":"x","inputs":{},"outputs":{},"files":{}}')
    value = {"profiles": {"p": {"nodes": [{"engine": "e", "slot": "s"}]}},
             "engines": {"e": {"manifest": "engine.json", "sha256": quick.sha(manifest)}},
             "slots": {"s": {"kind": "x", "inputs": {}, "outputs": {}}}}
    runner = StageRunner(S(contracts=S(root=tmp_path, pipeline=value), profile_id="p"))
    assert runner.verify_profile()
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="engine manifest hash mismatch"):
        runner.verify_profile()
    # This reproduces one possible trigger only, not the user's exact field cause.


@pytest.mark.parametrize('bad', [{'doc000'}, {'doc023', 'doc041'}, {f'doc{i:03d}' for i in range(20)}, {f'doc{i:03d}' for i in range(43)}])
def test_structure_errors_skip_only_documents_before_plan_and_are_reported(campaign, bad):
    c, r = campaign
    r.structure_errors = bad
    c.initialize()
    original = c.plan_path.read_bytes()
    assert c.run() == 2
    counts = c.status()['documents']
    assert counts['failed'] == len(bad) and counts['completed'] == 43 - len(bad)
    planned = [did for action, _, ids in r.calls if action == 'plan' for did in ids]
    assert len(planned) == 43 - len(bad) and not set(planned) & bad
    before = list(r.calls), list(r.preflight_calls)
    assert c.run() == 2
    assert (r.calls, r.preflight_calls) == before
    assert c.plan_path.read_bytes() == original
    out = c.job / 'report'
    c.render(out, export=True)
    report = (out / 'INDEX.html').read_text()
    assert all(did in report for did in bad) and 'BASIS_STRUCTURE' in report


def test_structure_receipt_saved_before_plan_is_reused_after_interruption(campaign):
    c, r = campaign
    r.structure_errors = {'doc022'}
    r.fail_plan = 'part-00002'
    c.initialize()
    with pytest.raises(ValueError, match='하위 계획 실패'):
        c.run()
    preflight_count = len(r.preflight_calls)
    r.fail_plan = None
    assert c.run() == 2
    assert len(r.preflight_calls) == preflight_count + 1  # only unvisited part 3


@pytest.mark.parametrize('mode', ['tamper', 'delete'])
def test_structure_failure_receipt_cannot_disappear_or_change(campaign, mode):
    c, r = campaign
    r.structure_errors = {'doc001'}
    c.initialize()
    c.run()
    path = c.job / 'parts/part-00001/STRUCTURE_CHECK.json'
    if mode == 'delete':
        path.unlink()
    else:
        value = quick.read(path)
        value['failures'] = []
        quick.atomic(path, value, 'receipt_sha256')
    offset = len(r.calls)
    with pytest.raises(ValueError, match='기록이|하위 계획'):
        c.run()
    assert len(r.calls) == offset


def test_unknown_preflight_failure_blocks_without_model_calls(campaign):
    c, r = campaign
    c.initialize()
    r.preflight_error = 'BASIS_HASH: unchanged check failed'
    with pytest.raises(ValueError, match='BASIS_HASH'):
        c.run()
    assert not any(a in ('plan', 'run', 'resume') for a, _, _ in r.calls)


def test_exact_r2_binding_upgrade_preserves_existing_plans_and_failure_history(campaign):
    c, r = campaign
    source = ROOT / '08_DEPLOYMENT/GENOS/handoffs/basis_quick_commands_20261020_r2/BASIS_QUICK_R2/basis_quick.py'
    assert quick.sha(source) == quick.R2_COORDINATOR
    spec = importlib.util.spec_from_file_location('sealed_r2_quick', source)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    prior = old.Campaign(r, c.job, c.runtime, {'code': 'fixed', 'coordinator_sha256': quick.R2_COORDINATOR})
    prior.initialize()
    r.fail_plan = 'part-00002'
    with pytest.raises(ValueError):
        prior.run()
    # R2 did not have structure preflight receipts. Keep its valid original PLAN/STATE.
    first = c.job / 'parts/part-00001/PLAN.json'
    original = first.read_bytes(), c.plan_path.read_bytes()
    events = c.events.read_bytes()
    c.binding = {'code': 'fixed', 'coordinator_sha256': 'r3', 'preflight_sha256': 'r3-helper'}
    r.fail_plan = None
    r.structure_errors = {'doc025'}
    assert c.run() == 2
    assert (first.read_bytes(), c.plan_path.read_bytes()) == original
    assert c.events.read_bytes().startswith(events)
    assert (c.job / 'COORDINATOR_UPGRADE.json').is_file()
    assert sum(a == 'plan' and path.endswith('00001') for a, path, _ in r.calls) == 1
    c.binding['code'] = 'changed'
    with pytest.raises(ValueError, match='결속'):
        c.run()


@pytest.mark.parametrize('kind', ['structure', 'hash', 'permission', 'unknown'])
def test_actual_preflight_classifier_only_quarantines_structure(tmp_path, monkeypatch, kind):
    from types import SimpleNamespace as S
    from semantic_runtime.basis_links import grouping
    from semantic_runtime.basis_links.contracts import BasisError
    monkeypatch.syspath_prepend(str(ROOT / '06_TOOLS/COMMANDS'))
    import basis_preflight
    errors = {'structure': BasisError('BASIS_STRUCTURE', 'span failed', 409),
              'hash': BasisError('BASIS_HASH', 'hash changed', 409),
              'permission': PermissionError('denied'), 'unknown': RuntimeError('unknown')}
    calls = []
    def inventory(store, did):
        calls.append(did)
        if did == 'bad':
            raise errors[kind]
        return []
    monkeypatch.setattr(grouping, 'inventory', inventory)
    rows = [{'document_id': did, 'name': did, 'source_artifact_sha256': '0' * 64} for did in ('bad', 'good')]
    batch = S(catalogue=lambda app, team: (rows, 'principal'), selected_binding=lambda app, who: {'data': 'fixed'})
    app = S(state=S(pipeline=S(store=None)))
    if kind == 'structure':
        result = basis_preflight.inspect(app, batch, ['bad', 'good'])
        assert [d['document_id'] for d in result['failures']] == ['bad']
        assert calls == ['bad', 'good']
    else:
        with pytest.raises(type(errors[kind])):
            basis_preflight.inspect(app, batch, ['bad', 'good'])
        assert calls == ['bad']
