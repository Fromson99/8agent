"""Final response outbox, no-clobber durable export, and owner-lock recovery."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import sqlite3
from ..contracts import digest
from .errors import ContractError, PublicationConflict
from .repository import WorkRepository, encoded
from .context import now


@contextmanager
def owner_lock(directory, *, blocking=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'owner.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def prepare(repo, result, release, contracts, *, metadata=None):
    contracts.validate_port('runtime.result', result)
    from .source_bundle import validate_saved
    validate_saved(repo, result)
    if repo.VERSION in (4,5,6):
        guard = getattr(repo, 'publication_guard', None)
        if guard is None: raise ContractError('v4 publication requires current source authorization')
        guard(result)
    r = repo.run()
    state = result['assembly']['term_agent']
    last_control = repo.db.execute("SELECT payload_json FROM event WHERE kind='CONTROL' ORDER BY seq DESC LIMIT 1").fetchone()
    if not state.get('final') or not last_control or json.loads(last_control[0])['decision'] != 'FINAL':
        raise ContractError('only a FINAL result may be published')
    if (result['query']['id'] != r['query_id'] or result['answer']['generation_id'] != repo.binding['generation_id']
            or result['answer']['source_store_sha256'] != repo.binding['store_sha256']
            or result['answer']['scope'] != repo.binding['scope']):
        raise ContractError('publication result binding mismatch')
    if repo.VERSION==6 and metadata is None:
        row=repo.db.execute("SELECT payload_json FROM event WHERE kind='CASE_RESPONSE_METADATA' ORDER BY seq DESC LIMIT 1").fetchone()
        metadata=json.loads(row[0]) if row else None
    envelope = {**result, 'run_id': r['run_id'], 'release': release, **(metadata or {})}
    with repo.transaction():
        if r['status'] != 'RUNNING':
            raise ContractError('run cannot prepare publication')
        seq = repo.event('PUBLICATION_PREPARED', {'result_hash': digest(envelope)})
        repo.db.execute("INSERT INTO publication VALUES(1,?,?,?,'PENDING',?,NULL)",
                        (encoded(envelope), digest(envelope), r['run_id']+'.json', seq))
        repo.db.execute("UPDATE run SET status='COMMIT_READY',phase='PUBLISH' WHERE singleton=1")
    return envelope


def export(repo, runs):
    publication = repo.db.execute('SELECT * FROM publication WHERE singleton=1').fetchone()
    if not publication:
        raise ContractError('no prepared publication')
    value = json.loads(publication['result_json'])
    if digest(value) != publication['result_hash']:
        raise ContractError('publication hash mismatch')
    if publication['destination_key'] != repo.run()['run_id']+'.json':
        raise ContractError('invalid publication destination')
    if repo.VERSION in (4,5,6):
        guard = getattr(repo, 'publication_guard', None)
        if guard is None: raise ContractError('v4 export requires current source authorization')
        guard(value)
    runs = Path(runs)
    runs.mkdir(parents=True, exist_ok=True)
    destination = runs/publication['destination_key']
    fd, temporary = tempfile.mkstemp(prefix='.legal-publication-', dir=runs)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(value).encode()+b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            try:
                same = digest(json.loads(destination.read_text())) == publication['result_hash']
            except (ValueError, OSError):
                same = False
            if not same:
                raise PublicationConflict('existing run result differs from prepared publication')
        fsync_dir(runs)
    finally:
        os.unlink(temporary)
    with repo.transaction():
        repo.event('PUBLICATION_EXPORTED', {'result_hash': publication['result_hash']})
        repo.db.execute("UPDATE publication SET status='PUBLISHED',published_at=? WHERE singleton=1", (now(),))
        repo.db.execute("UPDATE run SET status='COMPLETED',phase='END' WHERE singleton=1")
    return value


def recover(journals, runs, *, publication_guard=None, contracts=None, release=None):
    results = []
    for path in sorted(Path(journals).glob('*/*/journal.sqlite')):
        try:
            with owner_lock(path.parent):
                with sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True) as probe:
                    version = probe.execute('PRAGMA user_version').fetchone()[0]
                if version in (4,5,6):
                    from .tiers_repository import TiersRepository
                    if version == 6:
                        from .unified_repository import UnifiedRepository
                        repo = UnifiedRepository(path)
                    elif version == 5:
                        from .obligation_repository import ObligationRepository
                        repo = ObligationRepository(path)
                    else:
                        repo = TiersRepository(path)
                    if version == 6:
                        # A source-only recovery guard cannot authorize a case commit.
                        from .unified_publication import recover_guard
                        repo.publication_guard=lambda value: recover_guard(repo,value,publication_guard)
                    elif publication_guard is not None:
                        repo.publication_guard = lambda value: publication_guard(repo, value)
                elif version == 3:
                    from .relations_repository import RelationsRepository
                    repo = RelationsRepository(path)
                elif version == 2:
                    from .tools_repository import ToolsRepository
                    repo = ToolsRepository(path)
                else:
                    repo = WorkRepository(path)
                try:
                    status = repo.run()['status']
                    if status == 'COMMIT_READY':
                        try:
                            export(repo, runs)
                        except ContractError:
                            if repo.VERSION not in (4,5,6): raise
                            with repo.transaction(): repo.event('PUBLICATION_BLOCKED', {'reason':'CURRENT_SOURCE_AUTHORIZATION_REQUIRED'})
                            results.append({'run_id':repo.run()['run_id'],'status':'BLOCKED'})
                            continue
                        results.append({'run_id': repo.run()['run_id'], 'status': 'COMPLETED'})
                    elif status == 'RUNNING':
                        # A deferred response may have left a FINAL answer in
                        # the durable journal before its publisher ran.
                        answer = repo.db.execute("SELECT payload_json FROM stage_artifact "
                            "WHERE stage='answer' AND valid=1 ORDER BY artifact_revision DESC LIMIT 1").fetchone()
                        control = repo.db.execute("SELECT payload_json FROM event WHERE kind='CONTROL' "
                            "ORDER BY seq DESC LIMIT 1").fetchone()
                        if (contracts is not None and publication_guard is not None and answer and control
                                and json.loads(control[0]).get('decision') == 'FINAL'):
                            try:
                                prepare(repo, json.loads(answer[0]), release, contracts)
                                export(repo, runs)
                            except ContractError:
                                if repo.run()['status'] == 'RUNNING':
                                    repo.fail('PUBLICATION_BLOCKED')
                                results.append({'run_id':repo.run()['run_id'],'status':'BLOCKED'})
                            else:
                                results.append({'run_id':repo.run()['run_id'],'status':'COMPLETED'})
                        else:
                            repo.fail('OWNER_LOST', interrupted=True)
                            results.append({'run_id': repo.run()['run_id'], 'status': 'INTERRUPTED'})
                finally:
                    repo.close()
        except BlockingIOError:
            continue
    return results
