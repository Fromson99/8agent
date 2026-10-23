"""Sealed R1 client plus R2 entry script, with non-seekable Dataiku streams."""
import fcntl
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import sys
import types
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r1"
R2 = ROOT / "08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r2"
RUN = "DATAIKU_PIPELINE_RUN_20261022_R2"
PREFIXES = ("transport", "restore_inputs", "dataiku_run", "lawrag", "semantic_runtime")


class Stream(io.BytesIO):
    def __init__(self, data, fail=False):
        super().__init__(data)
        self.fail, self.calls = fail, 0

    def read(self, n=-1):
        assert 0 < n <= 1024**2, "All reads must be bounded"
        self.calls += 1
        if self.fail and self.calls > 1:
            raise ConnectionError("test secret must not leak")
        return super().read(min(n, 31) if self.fail else n)

    def seek(self, *args):
        raise AssertionError("remote streams are not seekable")


class Folder:
    def __init__(self, data):
        self.data, self.reads, self.fail = data, [], None

    def get_id(self):
        return "actual-test-folder-id"

    def list_paths_in_partition(self):
        return list(self.data)

    def get_download_stream(self, path):
        self.reads.append(path)
        return Stream(self.data[path], self.fail == path)

    def get_path(self):
        raise AssertionError("SFTP/S3 cannot expose a local path")


@pytest.fixture
def env(tmp_path, monkeypatch):
    # Preserve other tests' imports while exercising the sealed client modules.
    old = {k: v for k, v in sys.modules.items() if any(k == p or k.startswith(p + ".") for p in PREFIXES)}
    for k in old:
        del sys.modules[k]
    old_path = sys.path[:]
    spec = importlib.util.spec_from_file_location("fixture_transport", R1 / "src/transport.py")
    transport = importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)
    data = {"/DATAIKU_PIPELINE_CLIENT_20261022_R1.zip": (R1 / "DATAIKU_PIPELINE_CLIENT_20261022_R1.zip").read_bytes()}
    source = tmp_path / "source"; source.write_bytes(b"tiny verified source")
    for name, member in [("RAW_INPUT.zip", "01_DATA/RAW/external/test.xml"),
                         ("PIPELINE_SUPPORT.zip", "01_DATA/LEXICON/test.txt")]:
        receipt = transport.pack({member: source}, tmp_path / name)
        data["/" + name] = (tmp_path / name).read_bytes()
        data["/" + name + ".receipt.json"] = json.dumps(receipt).encode()
    folder, variables = Folder(data), {}
    def select(name, project_key=None):
        assert name == "LEGAL_PIPELINE_WORKSPACE" and project_key == "LEGAL_RAG"
        return folder
    fake = types.SimpleNamespace(Folder=select, default_project_key=lambda: "LEGAL_RAG",
                                 get_custom_variables=lambda: variables)
    monkeypatch.setitem(sys.modules, "dataiku", fake)
    module = runpy.run_path(str(R2 / (RUN + ".txt")), run_name="delivery_test")
    work = tmp_path / "work"
    try:
        yield types.SimpleNamespace(m=module, folder=folder, work=work, variables=variables, fake=fake,
                                    run=lambda action="prepare": module["run"](action, work_dir=str(work)))
    finally:
        for k in list(sys.modules):
            if any(k == p or k.startswith(p + ".") for p in PREFIXES):
                del sys.modules[k]
        sys.modules.update(old)
        sys.path[:] = old_path


def test_final_zip_has_exact_executable_and_pins():
    source = (R2 / "DATAIKU_PIPELINE_RUN.py").read_bytes()
    assert source == (R2 / (RUN + ".txt")).read_bytes()
    with zipfile.ZipFile(R2 / (RUN + ".zip")) as z:
        assert z.read(RUN + "/" + RUN + ".txt") == source
        pins = json.loads(z.read(RUN + "/SHA256.json"))
        for name, sha in pins.items():
            assert hashlib.sha256(z.read(RUN + "/" + name)).hexdigest() == sha


def test_complete_notebook_entry_from_delivered_zip(env, monkeypatch):
    monkeypatch.chdir(env.work.parent)
    with zipfile.ZipFile(R2 / (RUN + ".zip")) as z:
        source = z.read(RUN + "/" + RUN + ".txt")
    namespace = {"__name__": "__main__"}
    exec(compile(source, "delivered-notebook-cell", "exec"), namespace)
    result = namespace["PIPELINE_RESULT"]
    assert result["status"] == "READY" and result["oracle_written"] is False
    assert Path(result["input_dir"]) == env.work.parent / "legal_pipeline_work/inputs"


@pytest.mark.parametrize("leading_slash", [True, False])
def test_stream_folder_prepare_and_idempotent_resume(env, leading_slash):
    if not leading_slash:
        env.folder.data = {k.lstrip("/"): v for k, v in env.folder.data.items()}
    assert env.run()["status"] == "READY"
    assert (env.work / "inputs/01_DATA/RAW/external/test.xml").read_bytes() == b"tiny verified source"
    assert (env.work / "inputs/01_DATA/LEXICON/test.txt").exists()
    assert not (env.work / "jobs/run_20261022_01/client.json").exists()
    first = list(env.folder.reads)
    assert env.run()["status"] == "READY"
    assert all(n.endswith("receipt.json") for n in env.folder.reads[len(first):])


def test_missing_file_stops_before_download(env):
    del env.folder.data["/RAW_INPUT.zip"]
    with pytest.raises(env.m["RunError"], match="RAW_INPUT.zip"):
        env.run()
    assert not env.folder.reads


def test_receipt_archive_mismatch_rejected(env):
    p = "/RAW_INPUT.zip.receipt.json"
    receipt = json.loads(env.folder.data[p]); receipt["archive"] = "wrong.zip"
    env.folder.data[p] = json.dumps(receipt).encode()
    with pytest.raises(env.m["RunError"], match="RECEIPT_INVALID"):
        env.run()


def test_corrupt_client_never_imported(env):
    p = "/DATAIKU_PIPELINE_CLIENT_20261022_R1.zip"
    env.folder.data[p] = b"x" * len(env.folder.data[p])
    with pytest.raises(env.m["RunError"], match="DOWNLOAD_HASH_OR_SIZE"):
        env.run()
    assert "dataiku_run" not in sys.modules


def test_corrupt_raw_never_restored(env):
    p = "/RAW_INPUT.zip"
    env.folder.data[p] = b"x" * len(env.folder.data[p])
    with pytest.raises(env.m["RunError"], match="DOWNLOAD_HASH_OR_SIZE"):
        env.run()
    assert not (env.work / "inputs/restored-inputs.json").exists()


def test_download_interruption_resume_and_secret_redaction(env):
    env.folder.fail = "/RAW_INPUT.zip"
    with pytest.raises(env.m["RunError"], match="ConnectionError"):
        env.run()
    assert (env.work / "download/RAW_INPUT.zip.partial").stat().st_size == 31
    env.folder.fail = None
    assert env.run()["status"] == "READY"
    log = (env.work / "runner-events.jsonl").read_text()
    assert "RESTART_DOWNLOAD" in log and "STOPPED" in log
    assert "test secret" not in log


def test_changed_upload_binding_preserves_original(env):
    env.run()
    p = "/RAW_INPUT.zip.receipt.json"
    receipt = json.loads(env.folder.data[p]); receipt["sha256"] = "0" * 64
    env.folder.data[p] = json.dumps(receipt).encode()
    before = (env.work / "input-binding.json").read_bytes()
    with pytest.raises(env.m["RunError"], match="INPUT_BINDING_CHANGED"):
        env.run()
    assert (env.work / "input-binding.json").read_bytes() == before


def test_disk_capacity_fails_before_large_write(env, monkeypatch):
    monkeypatch.setattr(env.m["shutil"], "disk_usage", lambda _: types.SimpleNamespace(free=0))
    with pytest.raises(env.m["RunError"], match="DOWNLOAD_CAPACITY"):
        env.run()
    assert not list(env.work.rglob("*.partial"))


def test_symlink_destination_is_rejected(env, tmp_path):
    target = tmp_path / "elsewhere"; target.mkdir()
    env.work.symlink_to(target, target_is_directory=True)
    with pytest.raises(env.m["RunError"], match="SYMLINK_REFUSED"):
        env.run()
    assert not list(target.iterdir())


@pytest.mark.parametrize("relative,code", [("inputs/01_DATA/RAW/external/test.xml", "RESTORE_CONFLICT"),
    ("code/DATAIKU_PIPELINE_CLIENT_20261022_R1/dataiku_run.py", "INSTALLED_CODE_CHANGED")])
def test_local_tampering_not_hidden_by_ready_marker(env, relative, code):
    env.run()
    (env.work / relative).write_text("changed")
    with pytest.raises(env.m["RunError"], match=code):
        env.run()


def test_concurrent_work_is_rejected(env):
    env.work.mkdir()
    with (env.work / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(env.m["RunError"], match="RUNNING"):
            env.run()
    assert not env.folder.reads


def test_missing_run_settings_before_data_transfer(env):
    with pytest.raises(env.m["RunError"], match="LEGAL_PIPELINE_URL"):
        env.run("run")
    assert "/RAW_INPUT.zip" not in env.folder.reads


def test_run_calls_verified_client_and_preserves_paused_status(env, monkeypatch):
    env.run()
    env.variables.update(LEGAL_PIPELINE_URL="https://example.invalid/pipeline", LEGAL_PIPELINE_TOKEN="secret",
                         LEGAL_ORACLE_CONNECTION="AIDP")
    called = []
    def execute(inputs, support, job):
        called.append((inputs, support, job))
        assert (inputs / "restored-inputs.json").exists()
        assert support.name == "PIPELINE_SUPPORT.zip"
        assert job == env.work / "jobs/run_20261022_01"
        return {"status": "PAUSED", "identity": "do-not-print"}
    monkeypatch.setattr(sys.modules["dataiku_run"], "run_dataiku", execute)
    result = env.run("run")
    assert result == {"status": "PAUSED"} and len(called) == 1


def test_old_kernel_module_rejected(env, monkeypatch):
    monkeypatch.setitem(sys.modules, "dataiku_run", types.SimpleNamespace(__file__="/old/client.py"))
    with pytest.raises(env.m["RunError"], match="KERNEL_RESTART_REQUIRED"):
        env.run()
