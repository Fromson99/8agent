"""R7 exact producer-cursor resume; existing insert acknowledgement contract."""
import fcntl
from pathlib import Path
import time

import run_full as base
from gold_io import Stop, canonical, digest, error_codes
from fast_insert import Contract
from fast_inputs import inputs
from legacy_gold_mapping import mapped_query


class Job(base.Job):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.state['integrity_mode'] = 'INSERT_ACK_ONLY_R6'
        pending = self.state.get('pending')
        if pending and pending.get('verify_only'):
            self.state.setdefault('removed_verification_pending', []).append(pending)
            self.state['pending'] = None
        self.save()

    def guard(self):
        # Lightweight resources, at most once per minute; no per-batch file stat
        # or old seven-day deadline. Its original value remains in the history.
        now = time.monotonic()
        if now >= getattr(self, '_next_resource_check', 0):
            base.resource_check(self.directory)
            self._next_resource_check = now+60

    def batch(self, key, rows, next_progress=None, section=None, slot=None, verify_only=False):
        if verify_only: raise Stop('R6_FULL_VERIFICATION_REMOVED')
        self.guard()
        marker = {'table':key,'rows':len(rows),'sha256':digest(rows),'verify_only':False,
                  'section':section,'slot':slot,'next':next_progress}
        pending = self.state.get('pending')
        if pending:
            # Old source batches also saved a rolling chain. The old next value
            # is retained if this exact interrupted batch is being acknowledged.
            if {k:v for k,v in pending.items() if k!='next'} != {k:v for k,v in marker.items() if k!='next'}:
                raise Stop('PENDING_BATCH_BINDING_MISMATCH')
            marker = pending
            present = self.contract.pending_count(self.db,key,rows)
            if present not in (0,len(rows)):
                raise Stop('PENDING_PARTIAL_KEYS_REVIEW_REQUIRED')
            if present == len(rows):
                self._ack(marker)
                self.progress.emit('PENDING_KEYS_ACKNOWLEDGED',table=self.contract.table(key),rows=present,
                                   full_value_comparison=False)
                return
        self.state['pending'] = marker; self.save()
        sql,binds = self.contract.batch(key,rows)
        try:
            seconds = self.db.block(sql,binds,transaction_managed=True)
        except BaseException:
            self.state['status'] = 'WRITE_UNCONFIRMED';self.save();raise
        self._ack(marker)
        self.progress.set('LOAD',table=self.contract.table(key),batch_rows=len(rows),
                          request_s=round(seconds,2),rows=(marker['next'] or {}).get('rows'),
                          transport=getattr(self.db,'last_transport',{}))

    def _ack(self, marker):
        if marker['section']:
            self.state.setdefault(marker['section'],{})[marker['slot']] = marker['next']
        self.state['pending'] = None
        self.state['status'] = 'LOADING'
        self.save()


def load_sources(job,root,source):
    from lawrag.pipeline import oracle_migration as migration
    from semantic_runtime.oracle_dp_io import KEYS
    db = migration.source_open(root/'store.sqlite')
    try:
        for kind in base.SOURCE_MAP:
            current = job.state['source'].get(kind,{'cursor':None,'rows':0})
            expected = source['source_rows'][kind]['rows']
            if current['rows'] == expected:
                job.progress.emit('SOURCE_CHECKPOINT_REUSED',table=kind,rows=expected)
                continue
            while True:
                job.guard();combined=[];size=0;cursor=current['cursor']
                while len(combined)<1000:
                    part = migration.source_batch(db,kind,source['dataset_version'],cursor,batch_rows=100)
                    if not part: break
                    n = len(canonical(part).encode())
                    if combined and size+n>2*1024**2: break
                    combined.extend(part);size+=n
                    cursor = [part[-1][c] for c in KEYS[kind] if c!='DATASET_VERSION']
                if not combined: break
                nxt = {'cursor':cursor,'rows':current['rows']+len(combined),'chain_status':'NOT_RECOMPUTED_R6'}
                job.batch(base.SOURCE_MAP[kind][0],[base.source_row(kind,r)[1] for r in combined],
                          next_progress=nxt,section='source',slot=kind)
                current = job.state['source'][kind]
            if current['rows'] != expected: raise Stop('SOURCE_INPUT_ENDED_EARLY:'+kind)
            job.progress.emit('SOURCE_ACK',table=kind,rows=current['rows'])
    finally: db.close()


def load_query(job,root,source,query,paths,mode):
    from fast_export import projected_rows
    from reduced_projection import exclusions
    release = digest(query)
    for relative in paths:
        current_state = job.state['query'].get(relative,{})
        if current_state.get('complete') is True:
            job.progress.emit('QUERY_FILE_CHECKPOINT_REUSED',asset=relative);continue
        path = (root/relative).resolve(strict=True)
        if root not in path.parents: raise Stop('QUERY_INPUT_PATH')
        done = current_state.get('rows',0)
        resume=current_state.get('producer_cursor')
        current=done if resume else 0
        kwargs = {'excluded_tables':exclusions(query,relative)} if mode=='reduced' else {}
        for batch in base.grouped(projected_rows(path,relative,source,mode=mode,resume=resume,**kwargs)):
            job.guard();through=current+len(batch)
            if through<=done: current=through;continue
            if current<done: raise Stop('QUERY_CURSOR_BATCH_BOUNDARY')
            job.batch('SRCH_ROW',[mapped_query(release,row) for row in batch],
                      next_progress={'rows':through,'producer_cursor':batch[-1].producer_cursor},section='query',slot=relative)
            current=through
        if current<done: raise Stop('QUERY_CURSOR_EXCEEDS_INPUT')
        job.state['query'][relative]={'rows':current,'complete':True};job.save()
        job.progress.emit('QUERY_FILE_ACK',asset=relative,rows=current)


def ready(job,source,query,paths):
    # Only saved counters, no DB SELECT or source scan.
    return (all(job.state['source'].get(k,{}).get('rows',0)==v['rows'] for k,v in source['source_rows'].items())
            and all(job.state['query'].get(p,{}).get('complete') for p in paths)
            and sum(v.get('rows',0) for v in job.state['query'].values())==sum(t['rows'] for t in query['tables'].values()))


def publish(job,source,query):
    channel='g19_'+digest(query)[:24]
    rows=[('SRC_POST',{'DOC_POST_HASH_VALU':digest(source),'MNFST_HASH_VALU':source['dataset_version'],'DOC_POST_IFMN_CTNT':canonical(source)}),
          ('SRCH_POST',{'RFRN_POST_HASH_VALU':digest(query),'RFRN_POST_IFMN_CTNT':canonical(query)}),
          ('SRCH_CHNL',{'RFRN_CHNL_NAME':channel,'RFRN_POST_HASH_VALU':digest(query),'CHAN_NO':1})]
    for key,row in rows:
        if key not in job.state.setdefault('publication',{}):
            job.batch(key,[row],next_progress={'rows':1},section='publication',slot=key)
    job.state.update(status='SOURCE_QUERY_PUBLISHED',source_release_id=digest(source),query_release_id=digest(query),
                     test_channel=channel,full_values_verified=False)
    job.save()
    job.progress.emit('SOURCE_QUERY_PUBLISHED',channel=channel,full_values_verified=False,serving='NOT_SWITCHED')


def run(action,old_job,mode,directory):
    contract=Contract(base.HERE/'contract.json');progress=base.Progress();progress.thread.start()
    parent_directory=old_job.parent/('gold-shape-'+contract.sha256[:12])
    db=None;job=None
    from contextlib import ExitStack
    try:
        with ExitStack() as stack:
            for folder in dict.fromkeys([parent_directory,directory]):
                lock=stack.enter_context((folder/'job.lock').open('a'))
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            from pipeline_entry import select_mode
            if select_mode(old_job,base.HERE)!=(mode,directory):raise Stop('CHECKPOINT_SELECTION_CHANGED')
            prior=base.read(directory/'state.json')
            import dataiku
            db=base.Database(dataiku.SQLExecutor2(connection='AIDP'))
            identity=db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
            if identity!=prior['binding']['database'] or base.object_binding(db,contract)!=prior['binding']['objects']:
                raise Stop('TARGET_OR_TABLES_CHANGED')
            root,files,source,query,paths=inputs(base,old_job,directory,prior,progress)
            binding=dict(prior['binding'],code=base.verify_code())
            job=Job(db,contract,directory,binding,progress)
            if job.state['status'] in {'SOURCE_QUERY_VERIFIED','SOURCE_QUERY_PUBLISHED'}:
                progress.emit('ALREADY_PUBLISHED',full_values_rechecked=False);return
            if action=='load':
                if not ready(job,source,query,paths):
                    load_sources(job,root,source)
                    load_query(job,root,source,query,paths,mode)
                if not ready(job,source,query,paths):raise Stop('LOAD_INPUT_INCOMPLETE')
                job.state.update(status='LOADED_INSERT_ACK',full_values_verified=False);job.save()
                progress.emit('LOADED_INSERT_ACK',next_action='publish',full_values_verified=False)
            elif action=='publish':
                if not ready(job,source,query,paths):raise Stop('LOAD_FIRST')
                publish(job,source,query)
            else:raise Stop('ACTION')
    except BaseException as exc:
        if job:
            job.state['last_error']={'type':type(exc).__name__,'codes':error_codes(exc),'phase':progress.phase,'time':time.time()}
            if job.state.get('pending'):job.state['status']='WRITE_UNCONFIRMED'
            job.save()
        raise
    finally:
        if db is not None:db.close()
        progress.stop.set();progress.thread.join(timeout=2)
