"""Explicit snapshot/import/restore operations for shortcut v4; no live-file copying."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from semantic_runtime.legal_agent.corrected_memory import MemoryError, digest, encoded
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def backup(repo, directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    target=directory/'cases-v4.sqlite'
    # Writer ownership must be held by the caller for DB+artifact retention consistency.
    from semantic_runtime.legal_agent.publication import owner_lock
    with owner_lock(repo.path.parent/'maintenance'):
        with sqlite3.connect(target) as db: repo.db.backup(db)
        with sqlite3.connect(target) as db:
            artifacts=list(db.execute('SELECT relative_path,hash,bytes FROM sw_artifact'))
            counts={r[0]:db.execute('SELECT count(*) FROM "'+r[0]+'"').fetchone()[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sw_%'")}
        for relative,expected,size in artifacts:
            source=(repo.artifacts/relative).resolve()
            if not source.is_relative_to(repo.artifacts.resolve()) or source.stat().st_size!=size or sha(source)!=expected: raise MemoryError('backup artifact missing or damaged')
            destination=directory/'artifacts'/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        manifest={'schema_version':'shortcut-backup-v1','db_sha256':sha(target),'counts':counts,'artifacts':[{'path':r,'sha256':h,'bytes':b} for r,h,b in artifacts]}
        (directory/'manifest.json').write_text(encoded(manifest)+'\n')
    return manifest


def restore(directory, destination):
    directory=Path(directory);destination=Path(destination)
    if destination.exists(): raise MemoryError('restore destination must be a new generation')
    m=json.loads((directory/'manifest.json').read_text())
    if sha(directory/'cases-v4.sqlite')!=m['db_sha256']: raise MemoryError('snapshot hash mismatch')
    for a in m['artifacts']:
        p=(directory/'artifacts'/a['path']).resolve()
        if not p.is_relative_to((directory/'artifacts').resolve()) or sha(p)!=a['sha256'] or p.stat().st_size!=a['bytes']: raise MemoryError('snapshot artifact hash mismatch')
    destination.mkdir(parents=True,mode=0o700)
    shutil.copyfile(directory/'cases-v4.sqlite',destination/'cases-v4.sqlite')
    if (directory/'artifacts').exists(): shutil.copytree(directory/'artifacts',destination/'artifacts')
    repo=ShortcutRepository(destination/'cases-v4.sqlite')
    try:
        if repo.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or repo.db.execute('PRAGMA foreign_key_check').fetchall(): raise MemoryError('restored DB integrity failure')
        actual={name:repo.db.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0] for name in m['counts']}
        if actual!=m['counts']: raise MemoryError('restore count mismatch')
        return {'restored':True,'source_manifest_hash':digest(m),'status':repo.status()}
    finally: repo.close()


def migrate(source, destination, *, kind, principal=None, artifact_manifest=None):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination: raise MemoryError('migration cannot overwrite source')
    if kind not in {'v3','native','action-memory','query-shortcut','corrected-memory'}: raise MemoryError('unsupported legacy kind')
    directory=destination.parent/'imports';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    import uuid
    snapshot=directory/(uuid.uuid4().hex+'.sqlite')
    with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as original:
        with sqlite3.connect(snapshot) as copy: original.backup(copy)
    source_hash=sha(snapshot)
    supplied=json.loads(Path(artifact_manifest).read_text()) if artifact_manifest else {'artifacts':[]}
    if supplied['artifacts'] and principal is None:raise MemoryError('artifact import needs explicit trusted principal')
    for item in supplied['artifacts']:
        if set(item)!= {'path','sha256','documents'} or not Path(item['path']).is_absolute():raise MemoryError('explicit absolute artifact path, hash and document scope required')
        if sha(item['path'])!=item['sha256'] or not set(item['documents'])<=set(principal['document_ids']):raise MemoryError('legacy artifact hash or scope mismatch')
    fingerprint=digest([source_hash,supplied]) if artifact_manifest else source_hash
    permanent=directory/(fingerprint+'.sqlite')
    if permanent.exists(): snapshot.unlink()
    else: snapshot.rename(permanent)
    with sqlite3.connect('file:'+str(permanent)+'?mode=ro',uri=True) as legacy:
        legacy.row_factory=sqlite3.Row
        if kind=='v3' and legacy.execute('PRAGMA user_version').fetchone()[0]!=3: raise MemoryError('v3 source required')
        tables=[r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        records={table:[dict(r) for r in legacy.execute('SELECT * FROM "'+table.replace('"','""')+'"')] for table in tables}
    repo=ShortcutRepository(destination)
    try:
        old=repo.db.execute('SELECT payload FROM sw_import WHERE id=?',(fingerprint,)).fetchone()
        if old: return json.loads(old[0])
        source_id=digest([str(source),kind]);mapping={};artifact_mapping={};counts={k:len(v) for k,v in records.items()}
        with repo.transaction():
            for item in supplied['artifacts']:
                artifact_mapping[item['path']]=repo.artifact(Path(item['path']).read_bytes(),principal,documents=item['documents'])
            for table,rows in records.items():
                for i,row in enumerate(rows):
                    repo.db.execute('INSERT INTO sw_legacy VALUES(?,?,?,?)',(fingerprint,kind+':'+table,str(i),encoded(row)))
            if kind in {'v3','corrected-memory'}:
                sessions={s['id']:s for s in records.get('session',[])}
                for goal in records.get('goal',[]):
                    s=sessions[goal['session']];state=json.loads(goal['state'])
                    p={'user_id':s['owner'],'team_id':s['team'],'document_ids':state['document_ids'],'authenticated':True}
                    body={'session_id':'import:'+fingerprint+':'+goal['session'],'request_id':goal['id'],
                          'question':state['task'],'document_ids':state['document_ids'],'public_question':False}
                    previous=repo.db.execute('SELECT * FROM sw_migration_identity WHERE source_id=? AND legacy_id=?',(source_id,goal['id'])).fetchone()
                    state_hash=digest(goal)
                    if previous and previous['state_hash']==state_hash:
                        mapping[goal['id']]=previous['investigation'];continue
                    intake=repo.intake(body,p)
                    case=repo.connect(intake['id'],p,investigation_id=previous['investigation'] if previous else None)
                    mapping[goal['id']]=case['id']
                    repo.db.execute('INSERT INTO sw_migration_identity VALUES(?,?,?,?) ON CONFLICT(source_id,legacy_id) DO UPDATE SET state_hash=excluded.state_hash',
                        (source_id,goal['id'],case['id'],state_hash))
                    old_event=repo._event(case['scope'],case['id'],'LEGACY_STATE_IMPORTED',
                        {'source_hash':fingerprint,'source_id':source_id,'original_goal':goal['id'],'state':state,'binding':'LEGACY_UNBOUND'},session=body['session_id'])
                    # Facts are user assertions, never verified legal findings. A delta
                    # replaces individual current facts while preserving prior versions.
                    for item in state.get('facts',[]):
                        current=repo.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE investigation=? AND subject=? AND predicate=?',
                            (case['id'],goal['id'],item['name'])).fetchone()
                        value={'kind':'string','value':item['value']}
                        if current and json.loads(current['value'])==value:continue
                        case=repo.investigation(case['id'],p)
                        repo.fact(case['id'],p,expected_revision=case['revision'],event=old_event,subject=goal['id'],predicate=item['name'],value=value,
                            fact_id=current['id'] if current else None)

                    names={item['name'] for item in state.get('facts',[])}
                    for previous_fact in list(repo.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE investigation=? AND subject=?',(case['id'],goal['id']))):
                        if previous_fact['predicate'] in names or json.loads(previous_fact['value']).get('kind')=='unknown':continue
                        case=repo.investigation(case['id'],p)
                        repo.fact(case['id'],p,expected_revision=case['revision'],event=old_event,subject=goal['id'],predicate=previous_fact['predicate'],value={'kind':'unknown','value':None,'reason':'REMOVED_IN_LEGACY_DELTA'},fact_id=previous_fact['id'])

                    for event in records.get('event',[]):
                        if event['goal']==goal['id']:
                            repo._event(case['scope'],case['id'],'LEGACY_RECORD',{'legacy_kind':kind,'source_hash':fingerprint,'original_id':event['id'],
                                'record':event,'binding':'LEGACY_UNBOUND','reason_status':'NOT_RECORDED'},session=body['session_id'])
            else:
                if principal is None: raise MemoryError('native and legacy archive import requires an explicit trusted principal')
                scope=repo.scope(principal,create=True)
                body={'question':'과거 '+kind+' 실행 기록 아카이브','session_id':'legacy:'+source_id,'request_id':fingerprint,'document_ids':principal['document_ids'],'public_question':False}
                intake=repo.intake(body,principal);case=repo.connect(intake['id'],principal)
                mapping['archive_investigation']=case['id']
                repo._event(scope,case['id'],'LEGACY_IMPORT',{'kind':kind,'snapshot_hash':source_hash,'binding':'LEGACY_UNBOUND','reason_status':'NOT_RECORDED','documents':principal['document_ids'],'artifacts':artifact_mapping})
                # Preserve actual journal records as scoped durable trace artifacts.
                # Do not synthesize missing reasons or approve historical judgments.
                for table in ('observation','action','judgment','domain_choice','event'):
                    for index,row in enumerate(records.get(table,[])):
                        original=str(row.get('id',row.get('seq',index)))
                        trace=repo.trace(case['id'],principal,kind='LEGACY_'+table.upper(),payload={'legacy_kind':kind,'source_sha256':source_hash,'original_table':table,'original_id':original,'record':row,'binding':'LEGACY_UNBOUND','reason_status':'PRESERVED_AS_RECORDED'},documents=principal['document_ids'])
                        mapping[table+':'+original]=trace
            receipt={'schema_version':'shortcut-import-v1','source_sha256':source_hash,'import_id':fingerprint,'artifact_mapping':artifact_mapping,'artifact_manifest_hash':digest(supplied),'snapshot':str(permanent),'kind':kind,'counts':counts,'mapping':mapping,
                     'source_identity':source_id,'delta_supported':True,'reuse':'LEGACY_UNBOUND','source_preserved':True,'automatic_case_merging':False}
            repo.db.execute('INSERT INTO sw_import VALUES(?,?)',(fingerprint,encoded(receipt)))
        return receipt
    finally: repo.close()


def reconcile(repo):
    """Read-only integrity check, including every committed artifact and cursor."""
    issues=[]
    if repo.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':issues.append('SQLITE_INTEGRITY')
    if repo.db.execute('PRAGMA foreign_key_check').fetchall():issues.append('FOREIGN_KEY')
    for r in repo.db.execute('SELECT * FROM sw_artifact'):
        p=(repo.artifacts/r['relative_path']).resolve()
        if not p.is_relative_to(repo.artifacts.resolve()) or not p.is_file() or p.stat().st_size!=r['bytes'] or sha(p)!=r['hash']:issues.append('ARTIFACT:'+r['id'])
    for r in repo.db.execute('SELECT * FROM sw_trace'):
        if digest(json.loads(r['payload']))!=r['hash']:issues.append('TRACE:'+r['id'])
    for r in repo.db.execute('SELECT * FROM sw_cursor'):
        if repo.db.execute("SELECT 1 FROM sw_queue WHERE consumer=? AND id<=? AND status<>'DONE'",(r['consumer'],r['watermark'])).fetchone():issues.append('CURSOR:'+r['consumer'])
    return {'ok':not issues,'issues':issues,'status':repo.status()}


def store_plan(runtime, destination):
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    base=(Path(runtime)/'case-memory').resolve();destination=Path(destination).resolve()
    if not destination.is_relative_to(base/'generations') or destination.name!='cases-v4.sqlite':raise MemoryError('new store must be an explicit case-memory/generations/.../cases-v4.sqlite')
    if destination==selected_store(runtime).resolve():raise MemoryError('candidate is already selected')
    repo=ShortcutRepository(destination)
    try:
        check=reconcile(repo)
        if not check['ok']:raise MemoryError('candidate reconciliation failed')
        repo.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        artifacts=[dict(r) for r in repo.db.execute('SELECT relative_path,hash,bytes FROM sw_artifact')]
    finally:repo.close()
    pointer=base/'SHORTCUT_CURRENT.json'
    return {'schema_version':'shortcut-store-plan-v1','runtime':str(Path(runtime).resolve()),'path':str(destination.relative_to(base)),
        'db_sha256':sha(destination),'artifacts':artifacts,'before':json.loads(pointer.read_text()) if pointer.exists() else None,
        'before_hash':sha(pointer) if pointer.exists() else None,'reconciliation':check}


def apply_store(plan, *, confirm=False):
    if not confirm:raise MemoryError('explicit --confirm-store required')
    from semantic_runtime.legal_agent.shortcut_store import store_owner
    runtime=Path(plan['runtime']);base=runtime/'case-memory';pointer=base/'SHORTCUT_CURRENT.json'
    with store_owner(runtime,exclusive=True):
        if (sha(pointer) if pointer.exists() else None)!=plan['before_hash']:raise MemoryError('store plan is stale')
        destination=(base/plan['path']).resolve()
        if not destination.is_relative_to(base.resolve()/'generations') or sha(destination)!=plan['db_sha256']:raise MemoryError('candidate store changed')
        for item in plan['artifacts']:
            file=(destination.parent/'artifacts'/item['relative_path']).resolve()
            if not file.is_relative_to(destination.parent/'artifacts') or sha(file)!=item['hash'] or file.stat().st_size!=item['bytes']:raise MemoryError('candidate artifact changed')
        receipt={'plan_hash':digest(plan),'before':plan['before'],'path':plan['path'],'db_sha256':plan['db_sha256']}
        value={'schema_version':'shortcut-store-pointer-v1','path':plan['path'],'receipt':receipt,'receipt_hash':digest(receipt)}
        _atomic(pointer,value)
        _atomic(base/'receipts'/(digest(receipt)+'.json'),value)
        return value


def rollback_store(runtime, expected_receipt, archive):
    from semantic_runtime.legal_agent.shortcut_store import selected_store,store_owner
    runtime=Path(runtime);pointer=runtime/'case-memory'/'SHORTCUT_CURRENT.json'
    with store_owner(runtime,exclusive=True):
        value=json.loads(pointer.read_text())
        if value['receipt_hash']!=expected_receipt:raise MemoryError('rollback receipt is stale')
        repo=ShortcutRepository(selected_store(runtime))
        try:preserved=backup(repo,archive)
        finally:repo.close()
        before=value['receipt']['before']
        if before is None:pointer.unlink()
        else:_atomic(pointer,before)
        receipt={'rolled_back':True,'from':expected_receipt,'archive':str(archive),'archive_hash':digest(preserved),'v4_records_preserved':True,'v3_overwritten':False}
        _atomic(runtime/'case-memory'/'receipts'/('rollback-'+digest(receipt)+'.json'),receipt)
        return receipt


def _atomic(path,value):
    import uuid
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    with temporary.open('x') as f:f.write(encoded(value)+'\n');f.flush();os.fsync(f.fileno())
    temporary.chmod(0o600);os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def import_review(repo, principal, receipt, *, confirm=False):
    """Operator-only file import; never exposed as a normal conversation command."""
    if not confirm:raise MemoryError('explicit --confirm-review required')
    required={'unit_id','revision','target_hash','kind','result','policy','reviewer','evidence','expires','review_text'}
    if set(receipt)!=required or not receipt['review_text'].strip():raise MemoryError('closed source-bound review file required')
    if receipt['kind'] not in {'SOURCE','INTERPRETATION'}:raise MemoryError('operator review kind not supported')
    if receipt['kind']=='INTERPRETATION' and receipt['policy']!='reviewed-interpretation-v1':raise MemoryError('unsupported interpretation policy')
    if not principal.get('authenticated'):raise MemoryError('authenticated reviewer scope required')
    with repo.transaction():
        value=repo.current(receipt['unit_id'],receipt['revision'],principal,allow_draft=True)
        if value['hash']!=receipt['target_hash']:raise MemoryError('review target changed')
        key='review-import:'+digest([repo.scope(principal),receipt]);old=repo.db.execute('SELECT payload FROM sw_import WHERE id=?',(key,)).fetchone()
        if old:return json.loads(old[0])
        if receipt['kind']=='INTERPRETATION':
            source=repo.db.execute("SELECT result,expires,target_hash FROM sw_verification WHERE unit=? AND revision=? AND kind='SOURCE' ORDER BY rowid DESC LIMIT 1",(receipt['unit_id'],receipt['revision'])).fetchone()
            import time
            if not source or source['result']!='PASS' or source['expires']<=time.time() or source['target_hash']!=value['hash']:raise MemoryError('current source verification required before interpretation review')
        ident=repo.verification(receipt['unit_id'],receipt['revision'],principal,kind=receipt['kind'],result=receipt['result'],policy=receipt['policy'],verifier=receipt['reviewer'],evidence=receipt['evidence']+[{'review_file_sha256':digest(receipt),'review_text':receipt['review_text'],'authority':'explicit operator file import'}],expires=receipt['expires'])
        result={'verification_id':ident,'unit_id':receipt['unit_id'],'revision':receipt['revision'],'kind':receipt['kind'],'result':receipt['result'],'review_hash':digest(receipt)}
        repo.db.execute('INSERT INTO sw_import VALUES(?,?)',(key,encoded(result)))
        return result


def retention_inventory(repo, policy, *, backup_manifests=()):
    """Read-only inventory for an explicit policy; no guessed retention or deletion.

    The inventory covers originals, payloads, derived projections, import snapshots
    and explicitly registered backups. Unknown backup coverage prevents execution.
    """
    required={'policy_id','approved_by','original_days','payload_days','projection_days','backup_days'}
    if set(policy)!=required or not policy['policy_id'] or not policy['approved_by']:raise MemoryError('explicit approved retention policy required')
    if any(type(policy[k]) is not int or policy[k]<0 for k in required-{'policy_id','approved_by'}):raise MemoryError('retention days must be explicit non-negative integers')
    manifests=[]
    for path in backup_manifests:
        path=Path(path).resolve();value=json.loads(path.read_text())
        if value.get('schema_version')!='shortcut-backup-v1':raise MemoryError('registered backup manifest required')
        manifests.append({'path':str(path),'sha256':sha(path),'db_sha256':value['db_sha256'],'artifacts':value['artifacts']})
    refs=[]
    for row in repo.db.execute('SELECT id,scope,relative_path,hash,bytes,documents FROM sw_artifact'):
        linked=[dict(x) for x in repo.db.execute('SELECT id,investigation,kind FROM sw_trace WHERE artifact=?',(row['id'],))]
        refs.append({**dict(row),'trace_refs':linked})
    return {'schema_version':'shortcut-retention-inventory-v1','policy':policy,'policy_hash':digest(policy),'status':'REVIEW_REQUIRED','original_records':repo.db.execute('SELECT count(*) FROM sw_event').fetchone()[0],
        'artifacts':refs,'imports':[json.loads(x[0]) for x in repo.db.execute("SELECT payload FROM sw_import WHERE json_extract(payload,'$.schema_version')='shortcut-import-v1'")],
        'registered_backups':manifests,'backup_coverage':'EXPLICIT_LIST_ONLY','deletion_executed':False,'requires':'Verify holds, data-owner approval, all backup copies, and a new store-generation cutover before destructive deletion.'}
