"""Long-name restoration regression and final Dataiku/GENOS package wiring."""
import asyncio
import errno
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import zipfile

import pytest
import test_dataiku_pipeline_managed_folder as base

ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r1"
R2 = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r2"
R3 = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r3"
RUN = "DATAIKU_PIPELINE_RUN_20261022_R3"
SERVICE = "GENOS_PIPELINE_SERVICE_20261022_R2"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "R2", R3)
    monkeypatch.setattr(base, "RUN", RUN)
    yield from base.env.__wrapped__(tmp_path, monkeypatch)


def test_final_zip_and_actual_notebook_entry(env, monkeypatch):
    base.test_final_zip_has_exact_executable_and_pins()
    base.test_complete_notebook_entry_from_delivered_zip(env, monkeypatch)


@pytest.mark.parametrize("case", [base.test_missing_file_stops_before_download,
    base.test_receipt_archive_mismatch_rejected, base.test_corrupt_client_never_imported,
    base.test_corrupt_raw_never_restored, base.test_download_interruption_resume_and_secret_redaction,
    base.test_changed_upload_binding_preserves_original, base.test_missing_run_settings_before_data_transfer,
    base.test_concurrent_work_is_rejected])
def test_inherited_input_and_resume_contracts(env, case):
    case(env)


@pytest.mark.parametrize("filename", ["가" * 80 + ".xml", "가" * 83 + "aa.xml", "x" * 251 + ".xml"])
def test_original_failure_and_fixed_byte_boundaries(tmp_path, filename):
    old = module(R1 / "src/transport.py", "old_t")
    new = module(R3 / "src/transport.py", "new_t")
    source = tmp_path / filename; source.write_bytes(b"original")
    name = "01_DATA/RAW/external/" + filename
    old.pack({name: source}, tmp_path / "RAW_INPUT.zip")
    with pytest.raises(OSError) as failure:
        old.unpack(tmp_path / "RAW_INPUT.zip", tmp_path / "restored")
    assert failure.value.errno == errno.ENAMETOOLONG
    new.unpack(tmp_path / "RAW_INPUT.zip", tmp_path / "restored")
    target = tmp_path / "restored" / name
    before = target.stat().st_mtime_ns
    assert target.read_bytes() == b"original"
    new.unpack(tmp_path / "RAW_INPUT.zip", tmp_path / "restored")
    assert target.stat().st_mtime_ns == before
    assert not list((tmp_path / "restored").rglob("*.tmp"))


def test_long_json_atomic_write(tmp_path):
    new = module(R3 / "src/transport.py", "write_t")
    p = tmp_path / ("가" * 80 + ".json")
    new.write(p, {"status": "original"}); new.write(p, {"status": "updated"})
    assert new.read(p) == {"status": "updated"}
    assert not list(tmp_path.glob("*.tmp"))


def test_interrupted_long_restore_cleans_only_temporary_and_resumes(tmp_path, monkeypatch):
    new = module(R3 / "src/transport.py", "interrupted_t")
    source = tmp_path / "source"; source.write_bytes(b"source data")
    name = "01_DATA/RAW/" + "가" * 80 + ".xml"
    archive = tmp_path / "RAW_INPUT.zip"
    new.pack({name: source}, archive)
    before = new.sha(archive)
    original = zipfile.ZipFile.open
    class FailRead:
        def __init__(self, stream):
            self.stream, self.first = stream, True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def read(self, size):
            if self.first:
                self.first = False
                return self.stream.read(3)
            raise OSError(errno.ENOSPC, "injected interruption")
    def open_entry(z, member, *args, **kwargs):
        stream = original(z, member, *args, **kwargs)
        return FailRead(stream) if member == name else stream
    with monkeypatch.context() as patch:
        patch.setattr(zipfile.ZipFile, "open", open_entry)
        with pytest.raises(OSError) as failure:
            new.unpack(archive, tmp_path / "out")
        assert failure.value.errno == errno.ENOSPC
    assert not (tmp_path / "out" / name).exists()
    assert not list((tmp_path / "out").rglob("*.tmp"))
    assert new.sha(archive) == before
    new.unpack(archive, tmp_path / "out")
    assert (tmp_path / "out" / name).read_bytes() == b"source data"


def test_long_restore_still_checks_member_hash_and_existing_conflict(tmp_path):
    new = module(R3 / "src/transport.py", "hash_t")
    source = tmp_path / "source"; source.write_bytes(b"original")
    name = "01_DATA/RAW/" + "가" * 80 + ".xml"
    archive, bad = tmp_path / "good.zip", tmp_path / "bad.zip"
    new.pack({name: source}, archive)
    with zipfile.ZipFile(archive) as z, zipfile.ZipFile(bad, "w") as out:
        out.writestr("TRANSPORT.json", z.read("TRANSPORT.json"))
        out.writestr(name, b"tampered")
    with pytest.raises(ValueError, match="RESTORE_HASH"):
        new.unpack(bad, tmp_path / "out")
    assert not (tmp_path / "out" / name).exists()
    new.unpack(archive, tmp_path / "out")
    (tmp_path / "out" / name).write_bytes(b"modified")
    with pytest.raises(ValueError, match="RESTORE_CONFLICT"):
        new.unpack(archive, tmp_path / "out")
    assert (tmp_path / "out" / name).read_bytes() == b"modified"


@pytest.mark.parametrize("filename", ["short.xml", "가" * 80 + ".xml", "x" * 251 + ".xml"])
def test_raw_copy_preserves_original_metadata_and_normal_paths(tmp_path, filename):
    rawstore = module(ROOT / "02_BACKEND/lawrag/core/rawstore.py", "rawstore_regression")
    raw = b"immutable source bytes"
    sha = hashlib.sha256(raw).hexdigest()
    result = rawstore.ensure(raw, filename, corpus=tmp_path / "corpus")
    target = Path(result["path"])
    assert target.read_bytes() == raw and len(target.name.encode()) <= 255
    assert result["item"]["orig_filename"] == filename
    assert result["item"]["body_sha256"] == sha
    if filename == "short.xml":
        assert target.name == sha[:16] + "__short.xml"
    else:
        assert target.name == sha + ".xml"
    assert rawstore.ensure(raw, filename, corpus=tmp_path / "corpus")["new"] is False


def test_r2_failure_to_r3_resume_without_redownload(env, tmp_path):
    old_t = module(R1 / "src/transport.py", "fixture_old")
    short = tmp_path / "short.xml"; short.write_bytes(b"short")
    long = tmp_path / ("가" * 80 + ".xml"); long.write_bytes(b"long original")
    archive = tmp_path / "long/RAW_INPUT.zip"
    receipt = old_t.pack({"01_DATA/RAW/external/a.xml": short,
                         "01_DATA/RAW/external/" + long.name: long}, archive)
    env.folder.data["/RAW_INPUT.zip"] = archive.read_bytes()
    env.folder.data["/RAW_INPUT.zip.receipt.json"] = json.dumps(receipt).encode()
    old = runpy.run_path(str(R2 / "DATAIKU_PIPELINE_RUN_20261022_R2.txt"), run_name="old_runner")
    with pytest.raises(old["RunError"], match="OSError"):
        old["run"]("prepare", work_dir=str(env.work))
    existing = env.work / "inputs/01_DATA/RAW/external/a.xml"
    before = existing.stat().st_mtime_ns
    reads = len(env.folder.reads)
    # Simulate the instructed kernel restart, retaining all filesystem state.
    for name in ("transport", "restore_inputs", "dataiku_run"):
        sys.modules.pop(name, None)
    assert env.run()["status"] == "READY"
    assert existing.stat().st_mtime_ns == before
    assert (existing.parent / long.name).read_bytes() == b"long original"
    assert all(n.endswith("receipt.json") for n in env.folder.reads[reads:])
    fixed = env.work / "code-r3" / env.m["CLIENT_NAME"]
    assert (fixed / "transport.py").read_bytes() == (R3 / "src/transport.py").read_bytes()
    assert (env.work / "code" / env.m["CLIENT_NAME"] / "transport.py").read_bytes() == (R1 / "src/transport.py").read_bytes()


def test_oserror_details_survive_log_failure(env, monkeypatch, capsys):
    env.run()
    def failed_restore(*a):
        raise OSError(errno.EDQUOT, "sensitive custom text", str(env.work / "inputs/entry"))
    monkeypatch.setattr(sys.modules["restore_inputs"], "restore", failed_restore)
    original_event = env.m["run"].__globals__["event"]
    def event(work, phase, **kwargs):
        if phase == "STOPPED":
            raise OSError(errno.ENOSPC, "log is full")
        return original_event(work, phase, **kwargs)
    monkeypatch.setitem(env.m["run"].__globals__, "event", event)
    with pytest.raises(env.m["RunError"], match="errno=122"):
        env.run()
    output = capsys.readouterr().out
    assert "LOG_WRITE_FAILED" in output and "sensitive custom text" not in output


def test_client_requires_new_service_pin_before_start(env):
    env.run()
    dku = sys.modules["dataiku_run"]
    expected = (env.work / "code-r3" / env.m["CLIENT_NAME"] / "SERVICE_CODE_SHA256.txt").read_text().strip()
    manifest = json.loads((R3 / "CODE_MANIFEST.json").read_text())
    assert expected == manifest["service_code_sha256"]
    class OldService:
        calls = []
        def call(self, operation, **fields):
            self.calls.append(operation)
            return {"code_sha256": "0" * 64}
    service = OldService()
    with pytest.raises(ValueError, match="DEPLOYED_CODE_MISMATCH"):
        dku.process(service, env.work / "inputs", env.work / "download/PIPELINE_SUPPORT.zip", env.work / "job",
                    expected_code_sha256=expected)
    assert service.calls == ["HEALTH"]
    assert not (env.work / "job/client.json").exists()


def test_service_derivation_and_committed_checkout_gate(tmp_path):
    with zipfile.ZipFile(R1 / "GENOS_PIPELINE_SERVICE_20261022_R1.zip") as z:
        old = {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(R3 / (SERVICE + ".zip")) as z:
        new = {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}
        z.extractall(tmp_path)
    assert {n for n in old if old[n] != new[n]} == {"transport.py", "GUIDE.txt", "CODE_PINS.json",
                                                  "02_BACKEND/lawrag/core/rawstore.py"}
    assert set(new) - set(old) == {"VERIFY_PIPELINE_RELEASE.py", "GENOS_PIPELINE_CHECK.txt"}
    assert all(Path(n).suffix.lower() not in {".js", ".jsx", ".mjs", ".cjs"} for n in new)
    root = tmp_path / SERVICE
    pins = json.loads(new["CODE_PINS.json"])
    assert all(hashlib.sha256(new[n]).hexdigest() == h for n, h in pins["files"].items())
    check = module(root / "VERIFY_PIPELINE_RELEASE.py", "verify_release")
    assert check.verify(root)["status"] == "CODE_VERIFIED"
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    git("init", "-q"); git("add", ".")
    git("-c", "user.name=Contract", "-c", "user.email=contract@example.invalid", "commit", "-qm", "fixture")
    assert check.verify(root, True)["commit"]
    command = ["bash", str(root / "GENOS_PIPELINE_CHECK.txt"), str(root)]
    passed = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert passed.returncode == 0 and "CHECK_EXIT=0" in passed.stdout
    (root / "transport.py").write_bytes(old["transport.py"])
    with pytest.raises(ValueError, match="DEPLOYMENT_CODE_DIFFER"):
        check.verify(root, True)
    failed = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert failed.returncode != 0 and "DEPLOYMENT_CODE_DIFFER" in failed.stdout


def test_packaged_genos_full_pipeline_with_long_original_name(tmp_path, term_glossary, monkeypatch):
    import test_dataiku_pipeline_delivery as delivery
    with zipfile.ZipFile(R3 / (SERVICE + ".zip")) as z:
        z.extractall(tmp_path)
    code = tmp_path / SERVICE
    fixed = module(code / "transport.py", "fixed_service_transport")
    monkeypatch.setitem(sys.modules, "transport", fixed)
    api = module(code / "service.py", "packaged_pipeline_service_r2")
    client = module(R1 / "src/dataiku_run.py", "packaged_client_r3")
    dev = tmp_path / "dev"
    delivery.support(dev, term_glossary)
    raw = dev / "01_DATA/RAW/external/test_team" / ("가" * 80 + ".xml")
    raw.parent.mkdir(parents=True)
    raw.write_text('''<?xml version="1.0" encoding="UTF-8"?><법령><기본정보><법령명_한글>모의법</법령명_한글><법령ID>999</법령ID><시행일자>20261022</시행일자></기본정보><조문><조문단위 조문키="0001001"><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목><조문내용>제1조(정의) 영업일은 은행이 영업하는 날을 말한다.</조문내용></조문단위></조문></법령>''')
    delivery.selection(dev, [])
    upload = tmp_path / "export"
    delivery.exporter.export(dev, upload)
    shutil.copyfile(dev / "00_SYSTEM/GLOSSARY_PIPELINE.json", code / "00_SYSTEM/GLOSSARY_PIPELINE.json")
    pins = fixed.read(code / "CODE_PINS.json")
    pins["files"]["00_SYSTEM/GLOSSARY_PIPELINE.json"] = fixed.sha(code / "00_SYSTEM/GLOSSARY_PIPELINE.json")
    fixed.write(code / "CODE_PINS.json", pins)
    restore = module(R1 / "src/restore_inputs.py", "packaged_restore_r3")
    restore.restore(upload, tmp_path / "inputs")
    monkeypatch.setenv("PIPELINE_SCRATCH", str(tmp_path / "scratch"))
    class LocalClient:
        def call(self, operation, **fields):
            reply = asyncio.run(api.service({}, {"API_TYPE": operation, **fields}))
            if reply["code"]:
                raise ValueError(reply["error"])
            return reply["data"]
    try:
        returned = client.process(LocalClient(), tmp_path / "inputs", upload / "PIPELINE_SUPPORT.zip", tmp_path / "job",
                                  expected_code_sha256=fixed.sha(code / "CODE_PINS.json"), poll_seconds=.2)
    except BaseException:
        for log in (tmp_path / "scratch").rglob("*.log"):
            print(log.name, log.read_text(errors="replace")[-8000:])
        raise
    receipt = fixed.read(returned / "audit/release.json")
    assert receipt["serving_verified"] and receipt["offline_e2e"] == "PASS"
    assert receipt["document_count"] == 1 and receipt["model_calls"] == 0
    assert (returned / "query/query-data.db").exists()
    assert fixed.read(tmp_path / "job/client.json")["scratch_released"]
    assert not list((tmp_path / "scratch").rglob("store.sqlite"))
