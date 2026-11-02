"""Run the unchanged, hash-checked R1 loader with explicit diagnostic sidecars."""
import os
from pathlib import Path
import sys
from error_diagnostics import event, install
import json


def main():
    package=Path(sys.argv[1]).resolve()
    sys.path.insert(0,str(package))
    import run as loader
    loader.verify_code()
    from jdbc_transport import install as install_transport
    install_transport(loader)
    report=install(loader,os.environ['G19_DIAGNOSTIC_FILE'])
    print(json.dumps({'phase':'RESET_EXECUTION_ADAPTER_ACTIVE','scope':'one-time source reset; UTF8_HEX JDBC transport; R1 files preserved'}),flush=True)
    try:
        from reset_source import reset_if_needed
        old_job=Path(os.environ.get('G19_OLD_JOB_DIR') or loader.DEFAULT_OLD_JOB).resolve(strict=True)
        reset_if_needed(loader,package,old_job)
        loader.run(sys.argv[2],os.environ.get('G19_OLD_JOB_DIR'),
                   retry_missing=os.environ.get('G19_RETRY_MISSING')=='1')
    except BaseException as exc:
        report(exc,{'stage':'EXECUTION_FAILED'})
        return 1
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(event(exc,{'stage':'BOOTSTRAP'}),ensure_ascii=False),flush=True)
        raise SystemExit(1)
