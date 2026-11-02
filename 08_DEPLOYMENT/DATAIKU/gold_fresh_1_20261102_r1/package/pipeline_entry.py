"""Create/load/verify the fresh _1 tables; no reset or deletion path."""
import json
import os
from pathlib import Path
import sys


def main():
    import run as loader
    from error_diagnostics import install,event
    from jdbc_transport import install as install_transport
    loader.verify_code()
    install_transport(loader)
    action=sys.argv[1]
    if action not in {'load','verify_publish','vector'}:raise ValueError('ACTION')
    report=install(loader,os.environ['G19_DIAGNOSTIC_FILE'])
    try:
        contract=loader.Contract(Path(__file__).parent/'contract.json')
        if contract.value.get('physical_suffix')!='_1' or any(not t['name'].endswith('_1') for t in contract.tables.values()):
            raise ValueError('FRESH_SUFFIX_CONTRACT_REQUIRED')
        print(json.dumps({'phase':'FRESH_1_PIPELINE','action':action,'tables':len(contract.tables),
                          'reset':False,'old_tables_unchanged':True}),flush=True)
        if action=='vector':
            from vector_stage import execute
            old=Path(os.environ.get('G19_OLD_JOB_DIR') or loader.DEFAULT_OLD_JOB).resolve(strict=True)
            execute(Path(__file__).parent,old)
        else:
            loader.run(action,os.environ.get('G19_OLD_JOB_DIR'),retry_missing=False)
    except BaseException as exc:
        report(exc,{'stage':'FRESH_1_'+action.upper()})
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
