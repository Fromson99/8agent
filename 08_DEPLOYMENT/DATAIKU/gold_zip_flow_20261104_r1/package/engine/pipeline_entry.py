"""Resume the existing full OR reduced job with existing Dataiku JDBC, no new release."""
import json
import os
from pathlib import Path
import sys


def select_mode(old_job, package):
    from gold_io import Contract, Stop, digest
    contract = Contract(package/'contract.json')
    directory = old_job.parent/('gold-shape-'+contract.sha256[:12])
    reduced = directory.with_name(directory.name+'-reduced-r4')
    current = digest(json.loads((package/'CODE_MANIFEST.json').read_text()))
    parents = json.loads((package/'RESUME_PARENTS.json').read_text())['parents']
    mode, path = ('reduced', reduced) if (reduced/'state.json').exists() else ('full', directory)
    if not (path/'state.json').is_file(): raise Stop('R6_EXISTING_CHECKPOINT_REQUIRED')
    state = json.loads((path/'state.json').read_text())
    if state.get('binding', {}).get('code') not in {current} | {p['code_binding'] for p in parents if p['mode'] == mode}:
        raise Stop('R6_UNREGISTERED_CHECKPOINT_KEEP_PRIOR_STATE')
    if ('projection_policy' in state['binding']) != (mode == 'reduced'):
        raise Stop('R6_CHECKPOINT_MODE_MISMATCH')
    return mode, path


def main():
    import run_full
    from error_diagnostics import install
    from jdbc_transport import install as install_transport
    from transport_gate import check as transport_check
    run_full.verify_code()
    action = sys.argv[1]
    if action not in {'check', 'load', 'publish'}: raise ValueError('ACTION')
    old_job = Path(os.environ.get('G19_OLD_JOB_DIR') or run_full.DEFAULT_OLD_JOB).resolve(strict=True)
    mode, directory = select_mode(old_job, Path(__file__).parent)
    loader = run_full
    import fast_loader
    install_transport(loader)
    report = install(loader, os.environ['G19_DIAGNOSTIC_FILE'])
    try:
        contract = loader.Contract(Path(__file__).parent/'contract.json')
        if contract.value.get('physical_suffix') != '_1' or any(not t['name'].endswith('_1') for t in contract.tables.values()):
            raise ValueError('FRESH_SUFFIX_CONTRACT_REQUIRED')
        print(json.dumps({'phase':'JDBC_R6_PIPELINE','action':action,'mode':mode,
                          'checkpoint':str(directory),'reset':False,'new_query_release':False}), flush=True)
        if action == 'check':
            import dataiku
            db = loader.Database(dataiku.SQLExecutor2(connection='AIDP'))
            try:
                transport_check(db)
                print(json.dumps({'phase':'JDBC_CHECK_PASS','table_writes':0,'ddl':0,
                                  'checkpoint_changes':0,'transport':db.last_transport}), flush=True)
            finally: db.close()
        else:
            fast_loader.run(action, old_job, mode, directory)
    except BaseException as exc:
        report(exc, {'stage':'JDBC_R6_'+action.upper()})
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
