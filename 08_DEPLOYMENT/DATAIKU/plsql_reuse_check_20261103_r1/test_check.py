import contextlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import re
import runpy
import sys
import types

import pytest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("g19_plsql_check_test", ROOT / "plsql_reuse_check.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Frame:
    def __init__(self, user="PIDD2APP", database="DB1"):
        self.row = {"OK": 1, "LOGIN_USER": user, "DB_NAME": database,
                    "CON_NAME": "PDB1", "INSTANCE_NAME": "INSTANCE1", "SID": "42"}

    def to_dict(self, orient):
        assert orient == "records"
        return [self.row]


class Executor:
    def __init__(self, fail_at=None, user="PIDD2APP", ignore_prequery=False,
                 fake_quoted_error=False, change_database=False):
        self.calls = []
        self.fail_at = fail_at
        self.user = user
        self.ignore_prequery = ignore_prequery
        self.fake_quoted_error = fake_quoted_error
        self.change_database = change_database

    def query_to_df(self, query, pre_queries=None):
        self.calls.append((query, pre_queries))
        if len(self.calls) == self.fail_at:
            raise ValueError("ORA-01031: insufficient privileges; secret sql must not be logged")
        if pre_queries and "G19_PREQUERY_OK_" in pre_queries[0]:
            marker = re.search("G19_PREQUERY_OK_[0-9a-f]+", pre_queries[0]).group()
            if self.fake_quoted_error:
                raise ValueError("ORA-06550: compilation error in " + pre_queries[0])
            if not self.ignore_prequery:
                raise ValueError("ORA-20986: " + marker + "\nORA-06512: at line 1")
        return Frame(self.user, "DB2" if self.change_database and len(self.calls) > 3 else "DB1")


def run(executor, path, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        result = mod.run_check(executor, path, **kwargs)
    files = list(path.glob("*/REPORT.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == result
    return result


def test_same_payload_same_size_only_comment_changes():
    run_id = "a" * 32
    payload = mod.synthetic_payload(run_id)
    a, b = (mod.make_block(payload, run_id, i) for i in (0, 1))
    assert a.split("\n", 1)[1] == b.split("\n", 1)[1]
    assert len(a) == len(b)
    assert 200 * 1024 < len(a) < 1024 * 1024
    pieces = re.findall(r"WRITEAPPEND\(z,(\d+),HEXTORAW\('([0-9A-F]+)'\)\)", a)
    assert all(int(n) == len(h) // 2 and len(h) <= 3600 for n, h in pieces)
    assert gzip.decompress(b"".join(bytes.fromhex(h) for _, h in pieces)).decode() == payload
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE TABLE|COMMIT|ALTER|DROP)\b", a)


def test_complete_balanced_order_and_warmup_exclusion(tmp_path):
    executor = Executor()
    report = run(executor, tmp_path)
    assert report["status"] == "COMPLETE"
    assert len(executor.calls) == 15
    assert report["summary"]["complete_pairs"] == 4
    samples = report["samples"]
    assert [s["label"] for s in samples[3:9]] == ["PING", "SAME", "NEW", "PING", "NEW", "SAME"]
    assert len({s["sql_sha256"] for s in samples if s["label"] in ("SAME", "SAME_FIRST")}) == 1
    assert len({s["sql_sha256"] for s in samples if s["label"] == "NEW"}) == 4
    assert report["bind_support"].startswith("NOT_TESTED")


@pytest.mark.parametrize("executor,call_count", [
    (Executor(user="WRONG"), 1),
    (Executor(ignore_prequery=True), 2),
    (Executor(fake_quoted_error=True), 2),
    (Executor(fail_at=3), 3),
    (Executor(change_database=True), 4),
])
def test_errors_stop_no_retry_and_no_false_success(tmp_path, executor, call_count):
    report = run(executor, tmp_path)
    assert report["status"] == "STOPPED"
    assert len(executor.calls) == call_count
    assert "new_over_same" not in report["summary"]
    assert "secret sql" not in json.dumps(report)
    assert report["samples"][-1]["status"] == "FAILED"


def test_slow_call_stops_before_next_call(tmp_path):
    class Clock:
        def __init__(self):
            self.n = 0

        def __call__(self):
            self.n += 1
            return 31.0 if self.n >= 4 else 0.0

    executor = Executor()
    report = run(executor, tmp_path, clock=Clock())
    assert report["status"] == "STOPPED"
    assert len(executor.calls) == 1
    assert "G19_SLOW_CALL_STOP" in report["stop"]["diagnostic_codes"]


def test_partial_pair_not_summarized(tmp_path):
    executor = Executor(fail_at=8)
    report = run(executor, tmp_path)
    assert report["summary"]["complete_pairs"] == 1
    assert "new_over_same" not in report["summary"]


def test_interrupted_call_saved_without_retry(tmp_path):
    class Interrupted(Executor):
        def query_to_df(self, query, pre_queries=None):
            if len(self.calls) == 3:
                self.calls.append((query, pre_queries))
                raise KeyboardInterrupt()
            return super().query_to_df(query, pre_queries)

    executor = Interrupted()
    report = run(executor, tmp_path)
    assert report["status"] == "INTERRUPTED"
    assert report["samples"][-1]["status"] == "INTERRUPTED"
    assert len(executor.calls) == 4


def test_complete_delivery_txt_bootstrap(tmp_path, monkeypatch):
    script = ROOT / "01_RUN_PLSQL_REUSE_CHECK_R1.txt"
    assert script.read_bytes() == (ROOT / "plsql_reuse_check.py").read_bytes()
    executor = Executor()
    dummy = types.ModuleType("dataiku")

    def factory(connection):
        assert connection == "AIDP"
        return executor

    dummy.SQLExecutor2 = factory
    monkeypatch.setitem(sys.modules, "dataiku", dummy)
    monkeypatch.chdir(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        result = runpy.run_path(str(script), run_name="__main__")
    assert result["G19_PLSQL_REPORT"]["status"] == "COMPLETE"
    assert len(list(tmp_path.glob("gold-plsql-checks/*/REPORT.json"))) == 1
