"""User-requested removal of this source/model's R1/R2 vectors only."""
import shutil
from gold_io import Stop, digest


def reset_previous(job, directory, loader):
    current = job.state['binding']['manifest']
    previous = dict(current, segment_profile='navigation-source-block-text-window800-step700-v1')
    publication = digest(previous)
    c = job.contract
    target = directory/'vectors-fast-r1'/publication
    receipt = job.work/'previous-vector-reset.json'
    identity = {'publication_id':publication, 'database':job.state['binding']['database'],
                'contract':c.sha256, 'source_release':current['source_release_id'], 'query':current['query_id']}
    if receipt.exists():
        saved = loader.read(receipt)
        if saved['binding'] != identity: raise Stop('VECTOR_RESET_BINDING_CHANGED')
        if saved['status'] == 'COMPLETE':
            job.progress.emit('VECTOR_PREVIOUS_RESET_ALREADY_DONE', publication_id=publication)
            return
    else:
        saved = {'binding':identity, 'status':'NEW'}
        if (target/'state.json').exists():
            old = loader.read(target/'state.json')
            if old['binding']['manifest'] != previous:
                raise Stop('VECTOR_RESET_OLD_STATE_MANIFEST_MISMATCH')
            # Preserve a small audit checkpoint, not the old embedding cache.
            loader.atomic(job.work/'previous-vector-state.json', old)
        loader.atomic(receipt, saved)
    job.guard()
    if saved['status'] != 'DB_CONFIRMED':
        # A repeated DELETE after uncertain ACK is idempotent and cannot touch R3.
        sql = ('DECLARE active_count NUMBER; BEGIN SELECT COUNT(*) INTO active_count FROM '+
               c.table('VCTR_HEAD')+' WHERE '+c.col('VCTR_HEAD','VCTR_POST_ID')+'=:p; '
               "IF active_count<>0 THEN RAISE_APPLICATION_ERROR(-20071,'VECTOR_RESET_ACTIVE_PUBLICATION'); END IF; "
               'DELETE FROM '+c.table('VCTR_ITEM')+' WHERE '+c.col('VCTR_ITEM','VCTR_POST_ID')+'=:p; '
               'DELETE FROM '+c.table('VCTR_POST')+' WHERE '+c.col('VCTR_POST','VCTR_POST_ID')+'=:p; '
               'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        job.progress.emit('VECTOR_PREVIOUS_RESETTING', publication_id=publication,
                          tables=[c.table('VCTR_ITEM'),c.table('VCTR_POST')])
        job.db.block(sql, [('p',publication,'VARCHAR2')], transaction_managed=True)
        saved['status'] = 'DB_CONFIRMED'; loader.atomic(receipt, saved)
    if target.exists():
        if target.is_symlink() or target.resolve().parent != (directory/'vectors-fast-r1').resolve():
            raise Stop('VECTOR_RESET_CACHE_PATH')
        shutil.rmtree(target)
    saved['status'] = 'COMPLETE'; loader.atomic(receipt, saved)
    job.progress.emit('VECTOR_PREVIOUS_RESET_COMPLETE', publication_id=publication,
                      old_cache_removed=True, source_and_query_preserved=True)
