"""Use the unchanged Gold loader after checking the dedicated development target."""
import io
import json
from oneclick_config import ROOT
from oneclick_guard import check, verify_sample
import oneclick_pipeline as original
from oneclick_storage import open_folder


def prepare_test_tables(cfg, root):
    """Create missing test objects. Never truncate, replace or adopt populated unknown tables."""
    import dataiku
    from gold_io import digest, literal
    remote = open_folder(cfg, 'result')
    original.fixed(root/'contract.json', cfg['target'])
    contract = original.Contract(root/'contract.json')
    db = original.connection(cfg)
    try:
        rows = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, "
                        "SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, "
                        "SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
        if len(rows) != 1 or rows[0]['LOGIN_USER'] != cfg['params']['EXPECTED_DB_USER']:
            raise ValueError('FLOW_DATABASE_USER_MISMATCH')
        binding = {'target':cfg['target'], 'database':rows, 'project':cfg['project'],
                   'report_folder':cfg['folders']['report'], 'input_folder':cfg['input_folder'],
                   'storage':cfg['storage']}
        expected = digest(binding)
        from oneclick_state import read_folder
        saved = read_folder(remote, 'test-db-ready.json')
        if saved is not None and saved.get('binding') != expected:
            raise ValueError('TEST_DB_BINDING_CHANGED')
        if saved is None:
            for key, table in contract.tables.items():
                exists = db.query('SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER='+literal(table['owner'])+
                                  ' AND TABLE_NAME='+literal(table['name']))
                if exists and db.query('SELECT COUNT(*) AS N FROM '+contract.table(key)+' WHERE ROWNUM<=1') != [{'N':0}]:
                    raise ValueError('TEST_TABLE_ALREADY_HAS_DATA:'+contract.table(key))
        # The common schema checker probes native VECTOR before creating any table.
        # It checks column types, PKs, indexes, triggers and creates only missing objects.
        contract.create(db, lambda event, **kw: print(event, kw, flush=True),
                        allow_create=saved is None)
        identity = original.database_identity(db, cfg, contract)
        ready = {'binding':expected, 'identity':identity, 'state':'TEST_DB_READY'}
        if saved is not None and saved != ready:
            raise ValueError('TEST_DB_OBJECTS_CHANGED')
        if saved is None:
            remote.upload_stream('test-db-ready.json', io.BytesIO(json.dumps(ready).encode()))
            if read_folder(remote, 'test-db-ready.json') != ready:
                raise ValueError('TEST_DB_RECEIPT_READBACK')
    finally:
        db.close()


def execute(stage, cfg, root):
    import dataiku
    project = dataiku.api_client().get_default_project()
    expected = check(cfg['params'], project.project_key)
    if cfg['project'] != project.project_key or cfg['target'] != expected:
        raise ValueError('TEST_TARGET_CHANGED')
    original.code_binding()
    verify_sample(open_folder(cfg, 'input'))
    if stage == 'inspect':
        prepare_test_tables(cfg, root)
    else:
        from oneclick_state import read_folder
        saved = read_folder(open_folder(cfg, 'result'), 'test-db-ready.json')
        if saved is None or saved.get('state') != 'TEST_DB_READY':
            raise ValueError('TEST_DB_PREPARATION_REQUIRED')
    return original.execute(stage, cfg, root)
