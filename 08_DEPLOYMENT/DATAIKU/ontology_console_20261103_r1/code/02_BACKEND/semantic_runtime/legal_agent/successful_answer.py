"""Native shortcut eligibility is a durable final-publication receipt, not READY.

Receipts use the existing immutable event ledger. No failed intake is deleted.
Operator-curated source packages retain their separate, explicitly checked contract.
"""
from . import journal_storage
import json
from .corrected_memory import MemoryError, digest

POLICY='successful-answer-publication-v1'


def receipts(repo, investigation, *, goal=None):
    from ..ad_store import table_exists, excluded
    if not table_exists(repo.db,'goal') or excluded(repo.db,'shortcut',investigation):return []
    values=[]
    for row in repo.db.execute("SELECT payload,hash,seq FROM sw_event WHERE aggregate_id=? AND kind='ANSWER_PUBLISHED' ORDER BY seq DESC",(investigation,)):
        try:
            p=json.loads(row['payload'])
            if digest(p)!=row['hash'] or p.get('policy')!=POLICY:continue
            if goal is not None and p['goal_id']!=goal:continue
            if repo.db.execute("SELECT 1 FROM sw_event WHERE aggregate_id=? AND kind='ANSWER_PUBLICATION_FAILED' AND run=? AND seq>?",(investigation,p['run_id'],row['seq'])).fetchone():continue
            g=repo.db.execute('SELECT revision,status FROM goal WHERE id=?',(p['goal_id'],)).fetchone()
            route=repo.db.execute("SELECT hash,payload FROM route WHERE id=? AND goal=? AND revision=? AND status='ACTIVE'",(p['route_id'],p['goal_id'],p['goal_revision'])).fetchone()
            intake=repo.db.execute('SELECT status,investigation FROM sw_intake WHERE id=?',(p['intake_id'],)).fetchone()
            if not g or g['status']!='READY' or g['revision']!=p['goal_revision']:continue
            if not route or route['hash']!=p['route_hash'] or digest(json.loads(route['payload']))!=p['route_hash']:continue
            if not intake or intake['status']!='COMPLETED' or intake['investigation']!=investigation:continue
            value=json.loads(route['payload'])
            compose=repo.db.execute('SELECT payload,hash FROM node WHERE id=?',(value['nodes']['COMPOSE'],)).fetchone()
            if not compose or compose['hash']!=p['composition_hash'] or digest(json.loads(compose['payload']))!=p['composition_hash']:continue
            if not str(json.loads(compose['payload']).get('text','')).strip():continue
            values.append({**p,'receipt_hash':row['hash'],'judgment_refs':value['judgment_refs']})
        except (ValueError,KeyError,TypeError):continue
    return values


def eligible(repo, investigation, *, goal=None):
    return bool(receipts(repo,investigation,goal=goal))


def require(repo, investigation, *, goal=None):
    rows=receipts(repo,investigation,goal=goal)
    if not rows:raise MemoryError('SHORTCUT_UNPUBLISHED: no current successful final answer publication')
    return rows


def record(cases,result,principal,envelope,work):
    """Called in the same case transaction as core route finalization."""
    if result.get('status')!='READY' or not result.get('goal_id'):return None
    if (cases.route(result['goal_id']) or {}).get('payload',{}).get('state',{}).get('scenario_context'):return None
    answer=envelope.get('answer') or {}
    if not str(answer.get('text','')).strip() or not answer.get('claims'):return None
    publication=work.db.execute('SELECT status,result_hash FROM publication WHERE singleton=1').fetchone()
    if not publication or publication['status']!='PUBLISHED' or work.run()['status']!='COMPLETED' or publication['result_hash']!=digest(envelope):
        raise MemoryError('SHORTCUT_UNPUBLISHED: final publication is not durably exported')
    repo=cases.shortcut;case=repo.investigation(cases.active_case,principal,cases.original_session)
    route=cases.route(result['goal_id']);parts=cases.parts(result['goal_id'])
    if not route or route['revision']!=result['revision']:raise MemoryError('SHORTCUT_UNPUBLISHED: stale answer route')
    run=envelope['run_id']
    payload={'policy':POLICY,'run_id':run,'goal_id':result['goal_id'],'goal_revision':result['revision'],
             'route_id':route['id'],'route_hash':route['hash'],'composition_hash':digest(parts['COMPOSE']['payload']),
             'intake_id':result['intake_id'],'publication_hash':publication['result_hash'],
             'answer_hash':digest(answer),'semantic_quality_certified':False}
    existing=repo.db.execute("SELECT payload,hash FROM sw_event WHERE aggregate_id=? AND kind='ANSWER_PUBLISHED' AND run=? ORDER BY seq DESC LIMIT 1",(case['id'],run)).fetchone()
    if existing:
        if json.loads(existing['payload'])!=payload or existing['hash']!=digest(payload):raise MemoryError('shortcut publication receipt conflict')
    if not existing or not any(p['run_id']==run for p in receipts(repo,case['id'])):repo._event(case['scope'],case['id'],'ANSWER_PUBLISHED',payload,session=cases.original_session,run=run)
    cases.successful_shortcut_run=run
    require(repo,case['id'],goal=result['goal_id'])
    repo.enqueue(case['scope'],'wiki',case['id'],case['revision'])
    return payload


def fail(cases,principal):
    run=getattr(cases,'successful_shortcut_run',None)
    if not run:return
    repo=cases.shortcut
    with repo.transaction():
        case=repo.investigation(cases.active_case,principal,cases.original_session)
        repo._event(case['scope'],case['id'],'ANSWER_PUBLICATION_FAILED',{'policy':POLICY,'run_id':run},run=run)


def check_knowledge(repo,value):
    path=value.get('core_evidence_route',{})
    if path.get('contract')=='curated-core-evidence-route-v1':return
    cases=value.get('input_cases',[])
    if not cases:raise MemoryError('SHORTCUT_UNPUBLISHED: native wiki has no successful case binding')
    for ident in cases:
        current=require(repo,ident,goal=path.get('goal_id'))
        if path:
            if not any(p['route_id']==path['route_id'] for p in current):raise MemoryError('shortcut route receipt changed')
        elif not set(value.get('successful_publications',{}).get(ident,[])) & {p['receipt_hash'] for p in current}:
            raise MemoryError('SHORTCUT_UNPUBLISHED: compiled wiki lacks current successful input binding')


def compiler_binding(repo,snapshots):
    return {s['case']['id']:sorted({p['receipt_hash'] for p in require(repo,s['case']['id'])}) for s in snapshots}


def compiler_records(repo,snapshots):
    """Only accepted judgment traces and successful utterances reach the compiler.

Current source/fact records remain explicit premises; raw failed attempts stay in SQL.
The original snapshot/cursor is retained by the caller, including excluded record IDs.
"""
    filtered=[];excluded=[]
    for s in snapshots:
        published=require(repo,s['case']['id'])
        refs={digest(ref) for p in published for ref in p['judgment_refs'].values()}
        intakes=[repo.db.execute('SELECT event,request FROM sw_intake WHERE id=?',(p['intake_id'],)).fetchone() for p in published]
        events={r['event'] for r in intakes};requests={r['request'] for r in intakes}
        events.update(f['event'] for f in s['facts'])
        kept_events=[r for r in s['events'] if r['id'] in events or r.get('request') in requests]
        kept_traces=[]
        for r in s['traces']:
            payload=json.loads(r['payload']) if isinstance(r['payload'],str) else r['payload']
            if r['kind']=='JUDGMENT' and digest(payload.get('native_ref')) in refs:kept_traces.append(r)
        admitted={r['id'] for r in kept_events+kept_traces}
        excluded.extend(r['id'] for r in s['events']+s['traces'] if r['id'] not in admitted)
        filtered.append({**s,'events':kept_events,'traces':kept_traces})
    return filtered,excluded


def backfill(repo, runtime):
    """Explicit, offline verification of legacy success. Never invent lost receipts.

    Only existing case journals with a matching durable exported answer qualify.
    Current ACL/source guards remain mandatory in the downstream wiki consumer.
    """
    from .. import runtime_sqlite as sqlite3
    from ..oracle_runtime_paths import Path
    from types import SimpleNamespace
    from .shortcut_cases import ShortcutCases
    runtime=Path(runtime).resolve();report={'verified':0,'skipped':0,'errors':[]}
    for path in sorted((runtime/'legal-agent'/'runs').glob('*/*/journal.sqlite')):
        try:
            with journal_storage.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
                db.row_factory=journal_storage.row
                pub=db.execute('SELECT * FROM publication WHERE singleton=1').fetchone()
                run=db.execute('SELECT * FROM run WHERE singleton=1').fetchone()
                commit=db.execute('SELECT * FROM case_commit WHERE singleton=1').fetchone()
                if not pub or not run or not commit or pub['status']!='PUBLISHED' or run['status']!='COMPLETED':
                    report['skipped']+=1;continue
                value=json.loads(pub['result_json']);c=dict(commit);h=c.pop('payload_hash')
                if digest(c)!=h or Path(c['case_db']).resolve()!=Path(repo.path).resolve():raise ValueError('case journal binding differs')
                if value.get('status')!='READY' or not value.get('investigation_id'):
                    report['skipped']+=1;continue
                if value['run_id']!=run['run_id'] or path.parent.name!=run['run_id'] or pub['destination_key']!=run['run_id']+'.json':raise ValueError('run binding differs')
                saved=runtime/'runs'/pub['destination_key']
                if digest(value)!=pub['result_hash'] or digest(json.loads(saved.read_text()))!=pub['result_hash']:raise ValueError('durable exported answer differs')
                p=json.loads(c['principal_json']);cases=ShortcutCases.__new__(ShortcutCases)
                cases.db=repo.db;cases.shortcut=repo;cases.path=repo.path;cases.active_case=value['investigation_id']
                cases.original_session=value['session_id'];cases.internal_session=c['session_id']
                route=cases.route(value['goal_id'])
                if not route or route['id']!=c['route_id'] or value['goal_id']!=c['question_id'] or value['revision']!=c['revision']:raise ValueError('current case route differs')
                raw=cases.parts(value['goal_id'])['COMPOSE']['payload']
                if raw.get('text')!=value['answer'].get('text'):raise ValueError('composition differs')
                with repo.transaction():
                    receipt=record(cases,value,p,value,SimpleNamespace(db=db,run=lambda:dict(run)))
                if receipt:report['verified']+=1
                else:report['skipped']+=1
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,MemoryError) as exc:
            report['skipped']+=1;report['errors'].append({'journal':str(path.relative_to(runtime)),'reason':str(exc)})
    return report


if __name__=='__main__':
    import argparse
    from .shortcut_repository import ShortcutRepository
    parser=argparse.ArgumentParser(description='Verify legacy successful publications without deleting or compiling records')
    parser.add_argument('--database',required=True);parser.add_argument('--runtime',required=True)
    args=parser.parse_args();repo=ShortcutRepository(args.database)
    try:print(json.dumps(backfill(repo,args.runtime),ensure_ascii=False,indent=2))
    finally:repo.close()
