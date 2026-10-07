import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '06_TOOLS/OFFLINE/genos_release_progress.py'
spec = importlib.util.spec_from_file_location('release_progress', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_counts_are_read_only_and_remaining_is_not_success(tmp_path):
    release = tmp_path / 'TERM_RELEASES/r/review'
    release.mkdir(parents=True)
    dbpath = release / 'review.sqlite'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE job(status TEXT)')
        db.executemany('INSERT INTO job VALUES (?)', [('complete',), ('pending',), ('running',), ('failed',)])
    before = dbpath.read_bytes()
    value = m.snapshot(tmp_path, 'r')['용어·정의 LLM 검토']
    assert '완료 1/4' in value and '남은 처리 2' in value and '실패 1' in value
    assert dbpath.read_bytes() == before
    assert m.counts(tmp_path / 'absent.sqlite', 'job', 'status') is None
    assert not (tmp_path / 'absent.sqlite').exists()


def test_only_changed_status_and_single_unchanged_heartbeat(tmp_path, monkeypatch, capsys):
    state = {'선택': '완료 2121건', 'LLM 검토': '대기'}
    monkeypatch.setattr(m, 'snapshot', lambda *a: dict(state))
    d = m.Display()
    d.stack.append(('준비: 정의 추출', m.time.monotonic()))
    d.show(tmp_path, 'r')
    first = capsys.readouterr().out
    assert '선택: 완료 2121건' in first and 'LLM 검토: 대기' in first
    d.show(tmp_path, 'r')
    second = capsys.readouterr().out
    assert len(second.splitlines()) == 1 and '현재 기능' in second
    assert '선택:' not in second and 'LLM 검토:' not in second
    state['LLM 검토'] = '완료 1/4 | 남은 처리 3'
    d.show(tmp_path, 'r')
    third = capsys.readouterr().out
    assert 'LLM 검토: 완료 1/4' in third and '선택:' not in third


def test_watch_unchanged_does_not_claim_job_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, 'snapshot', lambda *a: {'선택': '완료 1건'})
    d = m.Display()
    d.show(tmp_path, 'r')
    capsys.readouterr()
    d.show(tmp_path, 'r')
    out = capsys.readouterr().out
    assert len(out.splitlines()) == 1 and '실행·정상 여부는 미확인' in out


def test_scope_change_displays_full_initial_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, 'snapshot', lambda *a: {'선택': '완료 1건'})
    d = m.Display()
    d.show(tmp_path, 'r1')
    capsys.readouterr()
    d.show(tmp_path, 'r2')
    assert '선택: 완료 1건' in capsys.readouterr().out


def test_repeated_snapshot_error_is_never_deduplicated(tmp_path, monkeypatch, capsys):
    def fail(*a): raise sqlite3.OperationalError('KEEP_THIS_ERROR')
    monkeypatch.setattr(m, 'snapshot', fail)
    d = m.Display()
    d.show(tmp_path, 'r')
    capsys.readouterr()
    d.show(tmp_path, 'r')
    out, err = capsys.readouterr()
    assert 'KEEP_THIS_ERROR' in out and 'Traceback' in err and 'KEEP_THIS_ERROR' in err


def test_reference_errors_are_pending_and_unknown_decisions_terminal(tmp_path):
    folder = tmp_path / 'TERM_RELEASES/r/reference-review'
    folder.mkdir(parents=True)
    with sqlite3.connect(folder / 'review.sqlite') as db:
        db.execute('CREATE TABLE case_record(state TEXT)')
        db.executemany('INSERT INTO case_record VALUES (?)', [('APPROVED',), ('UNKNOWN',), ('MODEL_UNKNOWN',)])
    value = m.snapshot(tmp_path, 'r')['명시 참조 LLM 보정']
    assert '종료 판정 2/3' in value and '남은 판정 1' in value and '실패·미확인 1' in value


def test_wrapper_preserves_return_and_exception(capsys):
    d = m.Display()
    def call(value):
        if value == 0: raise ValueError('original')
        return value
    module = SimpleNamespace(call=call)
    assert d.wrap(module, 'call', '모의 작업') is call
    assert module.call(7) == 7
    with pytest.raises(ValueError, match='original'): module.call(0)
    assert d.stack == []
    output = capsys.readouterr().out
    assert '기능 시작' in output and '기능 중단' in output


def test_watch_once_never_imports_pipeline_or_starts_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(m, 'processes', lambda *a: [])
    assert m.main(['--run-id', 'r', '--once']) == 0
    assert '전체 수 미확정' in capsys.readouterr().out
    assert not (tmp_path / 'TERM_RELEASES').exists()


def test_runtime_logging_does_not_change_code_or_cli_arguments(tmp_path, monkeypatch):
    from lawrag.pipeline import document_release, term_generation
    import sys
    original = document_release.selected_sources
    original_argv = sys.argv
    bytes_before = Path(document_release.__file__).read_bytes()
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(m, 'processes', lambda *a: [])
    seen = []
    def runner(path, run_name):
        seen.extend(sys.argv)
        assert run_name == '__main__'
        assert document_release.selected_sources.__wrapped__ is original
        assert hasattr(term_generation.fulltext.build, '__wrapped__')
    monkeypatch.setattr(m.runpy, 'run_path', runner)
    m.main(['--run-id', 'r', '--build'])
    assert document_release.selected_sources is original and sys.argv is original_argv
    assert bytes_before == Path(document_release.__file__).read_bytes()
    assert seen[1:5] == ['document-release', 'build', '--run-id', 'r']


def test_txt_exact_source_and_syntax():
    import subprocess
    txt = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_RELEASE_PROGRESS_R3_UTF8.txt'
    embedded = txt.read_text().split("<<'GENOS_PROGRESS_PY'\n", 1)[1].rsplit('GENOS_PROGRESS_PY\n', 1)[0]
    # R3 remains the historical mailed bytes; current selected-only tool is in its own TXT.
    compile(embedded, str(txt), 'exec')
    assert 'traceback.print_exc()' in embedded and '--reference-model-profile' in embedded
    subprocess.run(['bash', '-n', str(txt)], check=True)


def test_missing_field_function_does_not_abort_logging(capsys):
    module = SimpleNamespace()
    assert m.Display().wrap(module, 'advance', '명시 참조') is None
    assert not hasattr(module, 'advance')
    assert '현장 코드에 없음' in capsys.readouterr().out


def test_build_with_old_field_reference_module(tmp_path, monkeypatch):
    from lawrag.pipeline import reference_resolution
    monkeypatch.delattr(reference_resolution, 'advance')
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(m, 'processes', lambda *a: [])
    calls = []
    monkeypatch.setattr(m.runpy, 'run_path', lambda *a, **k: calls.append(k['run_name']))
    m.main(['--build'])
    assert calls == ['__main__']
    assert not hasattr(reference_resolution, 'advance')


def test_selected_only_keeps_reference_model_and_omits_base(tmp_path, monkeypatch):
    import sys
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(m, 'processes', lambda *a: [])
    commands = []
    monkeypatch.setattr(m.runpy, 'run_path', lambda *a, **k: commands.append(list(sys.argv)))
    m.main(['--build', '--selected-only', '--run-id', 'financial-risk-success-20261001-r2'])
    command = commands[0]
    assert '--base-generation' not in command
    assert '--reference-model-profile' in command and '--max-reference-cases' in command
    assert 'financial-risk-success-20261001-r2' in command


def test_replacement_policy_is_forwarded_to_existing_cli(tmp_path, monkeypatch):
    import sys
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(m, 'processes', lambda *a: [])
    commands = []
    monkeypatch.setattr(m.runpy, 'run_path', lambda *a, **k: commands.append(list(sys.argv)))
    m.main(['--build', '--selected-only', '--glossary-corpus-policy', 'replace', '--run-id', 'r3'])
    command = commands[0]
    assert command[command.index('--glossary-corpus-policy') + 1] == 'replace'
    assert '--base-generation' not in command and '--reference-model-profile' in command


def test_errors_keep_message_traceback_and_no_trailing_status(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GENOS_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(m, 'processes', lambda *a: [])
    def fail(*a, **k): raise ValueError('EXACT_ORIGINAL_FAILURE')
    monkeypatch.setattr(m.runpy, 'run_path', fail)
    with pytest.raises(ValueError, match='EXACT_ORIGINAL_FAILURE'): m.main(['--build'])
    out, err = capsys.readouterr()
    assert 'EXACT_ORIGINAL_FAILURE' in out and 'EXACT_ORIGINAL_FAILURE' in err
    assert 'Traceback' in err
    assert out.rstrip().endswith("'8']")


def test_monitor_errors_are_not_replaced_with_generic_message(tmp_path, monkeypatch, capsys):
    def fail(*a): raise sqlite3.OperationalError('original database detail')
    monkeypatch.setattr(m, 'snapshot', fail)
    m.Display().show(tmp_path, 'r')
    out, err = capsys.readouterr()
    assert 'OperationalError: original database detail' in out
    assert 'Traceback' in err and 'original database detail' in err
