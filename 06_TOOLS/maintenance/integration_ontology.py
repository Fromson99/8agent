"""Load a reviewed test package through the existing ontology Workflow.

The host supplies the authenticated source reader and writable repository.
No model, answer-key injection, source creation, automatic retry or service switch.
"""
import argparse
from contextlib import closing, nullcontext
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import sys


def read_package(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Reviewed package hash changed')
    data = json.loads(raw)
    if (data.get('version') != 'reviewed-integration-ontology-v1'
            or data.get('namespace') != 'cb-it35-r1-'
            or data.get('purpose') != 'USER_REQUESTED_PREBUILT_IN_SAMPLE_TEST_KNOWLEDGE'):
        raise ValueError('Unexpected test package contract')
    return data


def preflight(data, workflow):
    from semantic_runtime.contracts import digest
    from semantic_runtime.ontology_work import schema
    from semantic_runtime.ontology_work.repository import COLUMNS
    from semantic_runtime.legal_agent.ontology_scenarios import compile_package
    from semantic_runtime.legal_agent.errors import ContractError
    entries = data['entries']
    if not entries or len(entries) > 128:
        raise ContractError('test package count')
    seen = set()
    result = []
    with workflow.repo.session() as cursor:
        for key, fields in COLUMNS.items():
            workflow.repo.execute(cursor, 'SELECT '+','.join(f[0] for f in fields)+
                ' FROM '+workflow.repo.tables[key]+' WHERE 1=0')
    for entry in entries:
        bid, work, proposal = entry['bundle_id'], entry['input'], entry['proposal']
        if not bid.startswith(data['namespace']) or bid in seen:
            raise ContractError('test namespace or duplicate bundle')
        seen.add(bid)
        review = entry['review']
        if (review['decision'] != 'APPROVED_FOR_TEST_DATA' or not review['reason'].strip()
                or review['entry_sha256'] != digest({'input': work, 'proposal': proposal})):
            raise ContractError('review missing or reviewed contents changed')
        workflow.verify_sources(work)  # destination version, ACL and literal bytes
        preview = compile_package(schema.recipe_for(work, proposal, bid), work['originals'])
        if preview['package_sha256'] != entry['preview_package_sha256']:
            raise ContractError('reviewed recipe changed')
        old, head = workflow.repo.latest(bid), workflow.repo.head(bid)
        if old:
            saved = workflow.load(bid)
            if saved['input'] != work or saved['proposal'] != proposal:
                raise ContractError('existing test bundle has different contents; no overwrite')
            if old['status'] not in ('DRAFT', 'APPROVED'):
                raise ContractError('existing test bundle is not publishable')
        if head['sequence'] > 0 and head['publication_id'] is None:
            raise ContractError('withdrawn test bundle must not be republished by import')
        result.append({'bundle_id': bid, 'existing_revision': old['revision'] if old else 0,
                       'existing_publication': head['publication_id']})
    return result


def install(data, workflow, *, record=None):
    """Source validation of ALL entries precedes the first write.

Each bundle uses the existing transaction and CAS. A later transport failure may
leave an earlier bundle committed; explicit repeat reconciles its existing ID.
    """
    from semantic_runtime.legal_agent.errors import ContractError
    preflight(data, workflow)
    receipts = []
    for entry in data['entries']:
        bid = entry['bundle_id']
        old = workflow.repo.latest(bid)
        if old is None:
            workflow.save(entry['input'], entry['proposal'], bundle_id=bid)
        saved = workflow.load(bid)
        if saved['input'] != entry['input'] or saved['proposal'] != entry['proposal']:
            raise ContractError('test bundle changed during import')
        if saved['status'] == 'DRAFT':
            workflow.review(bid, saved['revision'], saved['work_hash'], True,
                            entry['review']['reason'] + ' 검토 해시: ' + entry['review']['entry_sha256'])
        elif saved['status'] != 'APPROVED':
            raise ContractError('test bundle rejected during import')
        head = workflow.repo.head(bid)
        if head['sequence'] > 0 and head['publication_id'] is None:
            raise ContractError('test bundle withdrawn during import')
        receipt = workflow.publish(bid, saved['revision'], saved['work_hash'], head['sequence'])
        if not receipt['active']:
            raise ContractError('previous publication is no longer active')
        allowed = {s['anchor']['document_id'] for s in entry['input']['originals']}
        stored = workflow.repo.publication(receipt['publication_id'], allowed)
        if stored['package_sha256'] != receipt['package_sha256']:
            raise ContractError('publication readback changed')
        for source in entry['input']['originals']:
            rows = workflow.repo.lookup(source['anchor'], allowed)
            if not any(r['publication_id'] == receipt['publication_id'] for r in rows):
                raise ContractError('source-arrival consumer cannot find published test bundle')
        item = {'bundle_id': bid, **receipt}
        receipts.append(item)
        if record: record(item)
    return receipts


def gold_workflow(*, store, request, mapping, writer_connection, work_store, actor, agent_owner):
    """Use the host's selected Gold/Development mapping and verified source port.

The operator creates/grants tables separately. No physical name is guessed here.
    """
    from semantic_runtime.ontology_work.workflow import Workflow
    return Workflow(mapping.ontology_repository(writer_connection, agent_owner=agent_owner, read_only=False),
                    work_store, actor=actor, source_reader=store.gold_ports.source_reader)


def mapped_source_reader(mapping, connection, *, dataset_version, documents):
    """Operator source port for registered Gold physical columns; values use binds.

The host fixes the dataset version and ACL. The importer cannot choose a latest
generation or broaden the document grant. Suitable for Dataiku DB-API writers.
    """
    from semantic_runtime.legal_agent.errors import ContractError
    allowed = frozenset(documents)
    if not dataset_version or not allowed: raise ValueError('Explicit source generation and ACL required')
    def read(anchor):
        did = anchor['document_id']
        if did not in allowed: raise ContractError('source outside operator scope')
        d = lambda field: mapping.column('DOC_VER', field)
        b = lambda field: mapping.column('DOC_BLK', field)
        with closing(connection()) as db, db.cursor() as c:
            c.execute('SELECT '+d('DOC_HASH_VALU')+' FROM '+mapping.physical_table('DOC_VER')+
                ' WHERE '+d('MNFST_HASH_VALU')+'=:1 AND '+d('DOC_ID')+'=:2', [dataset_version,did])
            doc = c.fetchone()
            if not doc or doc[0] != anchor['version']:
                raise ContractError('source version missing or changed')
            c.execute('SELECT '+b('BODY_CTNT')+' FROM '+mapping.physical_table('DOC_BLK')+
                ' WHERE '+b('MNFST_HASH_VALU')+'=:1 AND '+b('DOC_ID')+'=:2 AND '+b('STRC_UNIT_ID')+
                '=:3 ORDER BY TO_NUMBER('+b('BODY_SLC_ID')+') FETCH FIRST 4097 ROWS ONLY',
                [dataset_version,did,anchor['unit_id']])
            rows = c.fetchmany(4097)
            if not rows or len(rows)>4096: raise ContractError('source extent missing or oversized')
            text = '\n'.join(row[0].read() if hasattr(row[0],'read') else row[0] for row in rows)
            if len(text)>160000: raise ContractError('source text limit')
            return text
    return read


def local_workflow(ontology_db, source_db, work_folder, actor, documents, *, initialize=False):
    from semantic_runtime.ontology_work.repository import Repository
    from semantic_runtime.ontology_work.store import LocalFolderStore
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.legal_agent.errors import ContractError
    from semantic_runtime.oracle_dp import enabled
    import os
    if enabled() or os.environ.get('GENOS_BACKEND'):
        raise ContractError('SQLite test data requires a local non-Oracle process')
    ontology_db, source_db = Path(ontology_db).resolve(), Path(source_db).resolve()
    if ontology_db == source_db or not source_db.is_file():
        raise ValueError('Separate ontology database and existing source database required')
    if not ontology_db.exists() and not initialize:
        raise ValueError('Target database missing; --apply initializes the separate test database')
    if not ontology_db.exists():
        ontology_db.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents a racing installer from opening a new target twice.
        ontology_db.touch(exist_ok=False)
        repo = Repository(lambda: sqlite3.connect(ontology_db))
        repo.initialize()
    repo = Repository(lambda: sqlite3.connect('file:'+str(ontology_db)+'?mode=rw', uri=True))
    allowed = frozenset(documents)
    def source_reader(anchor):
        if anchor['document_id'] not in allowed:
            raise ContractError('source outside operator scope')
        # A sqlite transaction context does not close the connection; close it explicitly.
        with closing(sqlite3.connect('file:'+str(source_db)+'?mode=ro', uri=True)) as db:
            row = db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',
                             (anchor['document_id'],)).fetchone()
            if not row or row[0] != anchor['version']:
                raise ContractError('source version changed')
            rows = db.execute('SELECT text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',
                              (anchor['document_id'], anchor['unit_id'])).fetchmany(4097)
            if not rows or len(rows) > 4096:
                raise ContractError('source extent missing or oversized')
            text = '\n'.join(r[0] for r in rows)
            if len(text) > 160000: raise ContractError('source text limit')
            return text
    return Workflow(repo, LocalFolderStore(work_folder), actor=actor, source_reader=source_reader)


def main():
    p = argparse.ArgumentParser(description='검토된 통합시험 온톨로지 반입')
    p.add_argument('--code-root', type=Path, required=True, help='호환성을 검증한 코드 root')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--sha256', required=True, help='검토 완료 시 기록한 ontology.json SHA256')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--sqlite', type=Path)
    p.add_argument('--source-db', type=Path)
    p.add_argument('--work-folder', type=Path)
    p.add_argument('--factory', help='인증된 Oracle Workflow context manager를 반환하는 module:function')
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    if bool(a.factory) == bool(a.sqlite): p.error('choose --sqlite or --factory')
    sys.path.insert(0, str(a.code_root.resolve()/'02_BACKEND'))
    data = read_package(a.package, a.sha256)
    if a.factory:
        module, name = a.factory.split(':', 1)
        context = getattr(importlib.import_module(module), name)()
    else:
        if not a.source_db or not a.work_folder: p.error('SQLite requires --source-db and --work-folder')
        documents = {s['anchor']['document_id'] for e in data['entries'] for s in e['input']['originals']}
        context = nullcontext(local_workflow(a.sqlite, a.source_db, a.work_folder,
            'codex:user-requested-test-data', documents, initialize=a.apply))
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    # Append-only run log retains earlier completion/unknown records on repeat.
    def record(value):
        with a.receipt.open('a', encoding='utf-8') as f:
            f.write(json.dumps(value, ensure_ascii=False)+'\n');f.flush()
    record({'event':'START', 'package_sha256':a.sha256, 'apply':a.apply})
    try:
        with context as workflow:
            rows = install(data, workflow, record=record) if a.apply else preflight(data, workflow)
        record({'event':'COMPLETE', 'bundles':len(rows), 'apply':a.apply})
    except BaseException as exc:
        record({'event':'INCOMPLETE', 'error_type':type(exc).__name__,
                'instruction':'이미 commit된 묶음이 있을 수 있음. 원인 확인 후 같은 패키지·대상으로 명시 재개.'})
        raise
    print(json.dumps({'status':'COMPLETE', 'bundles':len(rows), 'applied':a.apply}, ensure_ascii=False))


if __name__ == '__main__': main()
