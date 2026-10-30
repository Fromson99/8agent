"""Same request resumes share the first deadline and durable physical attempts."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from .completion_contracts import enabled
from .corrected_memory import digest
from .errors import ContractError


def restore(model):
    session=model.session
    cases=getattr(model,'cases',None)
    if cases is None or not enabled(session.profile):return
    if not getattr(cases,'owner_held',False):raise ContractError('request accounting requires case owner')
    db=cases.db
    db.executescript("""
      CREATE TABLE IF NOT EXISTS completion_request_budget(
        request_key TEXT PRIMARY KEY,input_hash TEXT NOT NULL,binding_hash TEXT NOT NULL,deadline_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS completion_request_run(
        request_key TEXT NOT NULL,run_id TEXT NOT NULL,journal TEXT NOT NULL,
        PRIMARY KEY(request_key,run_id));
    """)
    key=cases.request_key(model.body,model.principal)
    ih=digest({'body':model.body,'principal':model.principal})
    binding=digest(cases.executor.binding)
    old=db.execute('SELECT * FROM completion_request_budget WHERE request_key=?',(key,)).fetchone()
    if old and (old['input_hash']!=ih or old['binding_hash']!=binding):
        raise ContractError('request resume input or execution binding changed')
    deadline_at=old['deadline_at'] if old else session.context.deadline_at
    deadline=min(session.context.deadline,time.monotonic()+
        (datetime.fromisoformat(deadline_at)-datetime.now(timezone.utc)).total_seconds())
    carried={'model_reserved':0,'tool_used':0};previous=[]
    transport=session.transport if hasattr(session,'transport') else session.gateway.transport if session.gateway is not None else None
    routing=getattr(transport,'provider_policy',None);provider_resume=None
    budget=session.work.budget()
    root=(Path(model.runtime)/'legal-agent'/'runs').resolve()
    for row in db.execute('SELECT * FROM completion_request_run WHERE request_key=?',(key,)):
        path=Path(row['journal']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ContractError('request resume journal missing or outside runtime')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as prior:
            prior.row_factory=sqlite3.Row
            run=prior.execute('SELECT run_id,deadline_at,binding_hash FROM run WHERE singleton=1').fetchone()
            b=prior.execute('SELECT * FROM budget WHERE singleton=1').fetchone()
            if routing and run:
                from types import SimpleNamespace
                from . import provider_routing
                state,hashed=provider_routing.current(SimpleNamespace(db=prior),routing,transport.routing_hash,run['binding_hash'])
                if state['switches'] and (provider_resume is None or state['switches']>provider_resume['switches']):
                    provider_resume={**state,'binding_hash':session.context.binding_hash,'prior_run_id':run['run_id'],'prior_state_hash':hashed,'previous':None}

        if not run or run['run_id']!=row['run_id'] or run['deadline_at']!=deadline_at or b is None:
            raise ContractError('request resume journal identity changed')
        if any(b[k]!=budget[k] for k in ('model_limit','finalization_reserve','tool_limit')):
            raise ContractError('request resume physical limits changed')
        for k in carried:carried[k]=max(carried[k],b[k])
        previous.append(row['run_id'])
    session.context=replace(session.context,deadline=deadline,deadline_at=deadline_at)
    session.work.context=session.context
    session.sources.context=session.context;session.sources.source.context=session.context
    if session.gateway is not None:session.gateway.context=session.context
    with session.work.transaction():
        session.work.db.execute('UPDATE budget SET model_reserved=?,tool_used=? WHERE singleton=1',
            (carried['model_reserved'],carried['tool_used']))
        session.work.db.execute('UPDATE run SET deadline_at=? WHERE singleton=1',(deadline_at,))
        if provider_resume:session.work.event(provider_routing.EVENT+'_RESUMED',provider_resume)
        session.work.event('REQUEST_BUDGET_BOUND',{'request_key':key,'binding_hash':binding,
            'previous_run_ids':previous,'carried':carried,'deadline_at':deadline_at})
    journal=session.work.db.execute('PRAGMA database_list').fetchone()[2]
    # Registered before any model/tool call. A crash retains its reservations in
    # this journal, which the next owner reads without granting a fresh budget.
    with cases.transaction():
        db.execute('INSERT OR IGNORE INTO completion_request_budget VALUES(?,?,?,?)',
            (key,ih,binding,deadline_at))
        db.execute('INSERT INTO completion_request_run VALUES(?,?,?)',
            (key,session.context.run_id,str(Path(journal).resolve())))
