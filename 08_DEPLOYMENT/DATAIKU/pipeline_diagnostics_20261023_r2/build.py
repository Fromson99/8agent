"""Extend the sealed R1 entrypoint; keep client and server pins/identity unchanged."""
from pathlib import Path
import hashlib
import json
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "pipeline_mapped_20261023_r1"
NAME = "DATAIKU_PIPELINE_RUN_20261023_R2"


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("BASE_RUNNER_CONTEXT_CHANGED: " + before[:80])
    return source.replace(before, after, 1)


def build():
    baseline = (BASE / "DATAIKU_PIPELINE_RUN_20261023_R1.txt").read_bytes()
    expected = json.loads((BASE / "DELIVERY_MANIFEST.json").read_text())["files"]["DATAIKU_PIPELINE_RUN_20261023_R1.txt"]
    if hashlib.sha256(baseline).hexdigest() != expected:
        raise ValueError("SEALED_RUNNER_CHANGED")
    source = baseline.decode()
    source = replace_once(source, 'ACTION = "prepare"', '_previous_settings = getattr(globals().get("run"), "__defaults__", None)\nACTION = "prepare"')
    source = replace_once(source, 'JOB_NAME = "run_20261023_01"', '''JOB_NAME = "run_20261023_01"
# Keep the actual current work/job names when replacing a cell in this notebook.
# After a kernel restart, set FOLDER_NAME / WORK_DIR / JOB_NAME above to the same
# values shown in the previous notebook output. Never invent a new name for BUSY.
if isinstance(_previous_settings, tuple) and len(_previous_settings) == 4:
    FOLDER_NAME, WORK_DIR, JOB_NAME = _previous_settings[1:]
''')
    source = replace_once(source, '    return importlib.import_module("restore_inputs"), importlib.import_module("dataiku_run")', '''    restore = importlib.import_module("restore_inputs")
    client = importlib.import_module("dataiku_run")
    _observe_client(client)
    return restore, client''')
    marker = '\ndef run(action=ACTION, folder_name=FOLDER_NAME, work_dir=WORK_DIR, job_name=JOB_NAME):'
    source = replace_once(source, marker, '\n' + (HERE / 'diagnostics.py').read_text() + '\n' + marker)
    source = replace_once(source, '        try:\n            event(work, "START", action=action, job=job_name)', '''        folder = None
        phase = "MANAGED_INPUTS"
        try:
            event(work, "START", action=action, job=job_name, diagnostic_revision=DIAGNOSTIC_REVISION)''')
    source = replace_once(source, '            restore.restore(upload, inputs)', '            phase = "RESTORE_AND_VERIFY"\n            restore.restore(upload, inputs)')
    source = replace_once(source, '                result = client.run_dataiku(', '                phase = "SCHEMA_OR_PIPELINE"\n                result = client.run_dataiku(')
    start = source.index('        except BaseException as exc:\n', source.index(marker))
    end = source.index('\n\n\nif __name__ == "__main__":', start)
    source = source[:start] + '''        except BaseException as exc:
            try:
                report = report_failure(exc, work=work, action=action, job_name=job_name,
                                        folder=folder, phase=phase)
            except Exception as diagnostic_exc:
                print("DIAGNOSTIC_FAILED", type(diagnostic_exc).__name__,
                      "ORIGINAL_ERROR_TYPE", type(exc).__name__, flush=True)
                report = {"code": type(exc).__name__, "exceptions": [], "next_step": "원래 예외 연결을 보존했습니다."}
            try:
                event(work, "STOPPED", action=action, job=job_name, error_type=type(exc).__name__,
                      error_code=report["code"], next_step=report["next_step"])
            except Exception as logging_error:
                print("LOG_WRITE_FAILED", type(logging_error).__name__, "ORIGINAL_ERROR", report["code"], flush=True)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            detail = "\\n".join(e["type"] + ": " + e["message"] for e in report["exceptions"])
            raise RunError(report["code"] + "\\n" + detail + "\\n" + report["next_step"]) from None
''' + '''

if __name__ == "__main__":
    print("RUNNER_READY", DIAGNOSTIC_REVISION)
    print("FOLDER_NAME", FOLDER_NAME, "WORK_DIR", WORK_DIR, "JOB_NAME", JOB_NAME)
    print("코드 등록 완료. 배치는 자동 실행하지 않았습니다. BUSY 상태 확인: pipeline_jobs()")
'''
    compile(source, NAME + '.txt', 'exec')
    (HERE / (NAME + '.txt')).write_text(source)
    (HERE / 'runner.py').write_text(source)
    names = [NAME + '.txt', 'GUIDE.txt', 'WORK_CONTRACT.txt']
    if (HERE / 'VALIDATION.json').exists():
        names.append('VALIDATION.json')
    pins = {n: hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in names}
    manifest = {'revision': NAME, 'files': pins, 'base_runner_sha256': expected,
                'client_zip_sha256': '9d553a32d460b6ddfe4b73a4186dea5501a0b878512ccd622fa7cbae631b9bb3',
                'client_changed': False, 'service_changed': False, 'main_changed': False,
                'field_applied': False, 'busy_cause_confirmed': True, 'busy_job_identified': False}
    (HERE / 'SHA256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(HERE / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for name in names + ['SHA256.json']:
            z.write(HERE/name, name)
    with zipfile.ZipFile(HERE / (NAME + '.zip')) as z:
        assert z.testzip() is None
        assert z.read(NAME + '.txt') == (HERE / (NAME + '.txt')).read_bytes()
        assert all(Path(n).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
    print(json.dumps({'runner': NAME, 'bytes': len(source.encode()), 'base_runner_sha256': expected}))


if __name__ == '__main__':
    build()
