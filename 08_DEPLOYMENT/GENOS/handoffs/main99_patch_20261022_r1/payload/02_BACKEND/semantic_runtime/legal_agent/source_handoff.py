"""Durable comparison source return; never an accepted legal answer or experience."""
import json
from pathlib import Path
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError
from .corrected_memory import Conflict, encoded


def enabled():
    from .workflow_execution import task_context
    return (task_context() or {}).get('return_mode') == 'sources'


def selection(inv, decision):
    from .investigation_leads import export
    from ..research_state import progress_view
    from .structure_selection import progress
    leads=export(inv)
    evidence=inv.s.repo.evidence()
    for e in evidence:inv.s.source.verify(e)
    return {'status':'sources_returned','terminal':'SOURCE_HANDOFF',
        'next_action':'DONE','needs_fulltext':False,'final_ids':[],
        'selected_originals':[],'selected_evidence':evidence,
        'source_return':{'schema_version':'source-investigation-v2','leads':leads,
            'read_evidence_ids':sorted(e['evidence_id'] for e in evidence),
            'reason':decision['reason'],'stop_reason':inv.p.get('stop_reason'),
            'acquisition':deepcopy(inv.p.get('source_acquisition',{})),
            'research_tasks':deepcopy(inv.p.get('comparison_research',{})),
            'research_progress':progress_view(inv.p),
            'structure_selection_progress':progress(inv),
            'semantic_quality_certified':False,'absence_proven':False},
        'investigation_state':deepcopy(inv.p)}


def commit(cases,gid,revision,body,state,parts,executed,execution):
    payload=parts['SELECT']['payload']
    if not enabled() or payload.get('terminal')!='SOURCE_HANDOFF':raise ContractError('untrusted source terminal')
    from .workflow_execution import task_context
    result={'kind':'SOURCE_HANDOFF','status':'SOURCES_RETURNED','goal_id':gid,'revision':revision,
        'state':state,'answer':None,'executed':executed,'selection_node':parts['SELECT']['id'],
        'selection_hash':digest(payload),'binding':cases.executor.binding,
        'task_hash':digest(task_context()),'source_run_id':execution.s.context.run_id}
    with cases.transaction():
        if cases.goal(gid,body['session_id'])['revision']!=revision:raise Conflict('late source terminal')
        cases.db.execute('DELETE FROM stage_progress WHERE goal=?',(gid,))
        cases.db.execute('DELETE FROM stage_progress_evidence WHERE goal=?',(gid,))
        cases.db.execute("UPDATE goal SET status='SOURCES_RETURNED',pending='PLAN' WHERE id=?",(gid,))
        cases.db.execute("UPDATE request SET status='COMPLETE',response=? WHERE id=?",
            (encoded(result),cases.request_key(body,cases._entry_principal)))
    return result


def validate(cases,result,principal,session):
    if not enabled():raise ContractError('source handoff outside trusted workflow')
    from .workflow_execution import task_context
    g=cases.goal(result['goal_id'],session)
    if not g or g['revision']!=result['revision'] or g['status']!='SOURCES_RETURNED':raise Conflict('source handoff is historical')
    if result['task_hash']!=digest(task_context()) or result['binding']!=cases.executor.binding:raise ContractError('source task/binding changed')
    if not set(g['state']['document_ids'])<=set(principal['document_ids']):raise ContractError('source scope denied')
    p=cases.parts(g['id']);s=p['SELECT']
    if s['id']!=result['selection_node'] or digest(s['payload'])!=result['selection_hash']:raise ContractError('source terminal selection changed')
    cases.executor.verify(p['READ']['payload'])
    cases.executor.verify({'binding':p['READ']['payload']['binding'],'evidence':s['payload']['selected_evidence']})
    return result


def publish(cases,result,body,principal,runtime):
    """Idempotent after the terminal commit, including process loss before export."""
    from .unified_repository import UnifiedRepository
    ref=json.loads(cases.db.execute('SELECT ref FROM judgment_ref WHERE node=?',(result['selection_node'],)).fetchone()[0])
    paths=list((Path(runtime)/'legal-agent'/'runs').glob('*/'+result['source_run_id']+'/journal.sqlite'))
    if len(paths)!=1:raise ContractError('source terminal journal missing')
    child=UnifiedRepository(paths[0])
    try:
        from ..workflow_evidence import judgment
        selected=judgment(child,ref,'SELECT')
        if digest(selected)!=result['selection_hash']:raise ContractError('source native selection changed')
        envelope={'response_schema':('workflow-investigation-return-v2' if selected['source_return']['schema_version']=='source-investigation-v2' else 'workflow-investigation-return-v1'),'kind':'SOURCE_HANDOFF',
            'status':'SOURCES_RETURNED','run_id':result['source_run_id'],'goal_id':result['goal_id'],
            'revision':result['revision'],'session_id':body['session_id'],'request_id':body['request_id'],
            'investigation_id':None,'investigation_revision':None,'answer':None,
            'handoff':selected['source_return'],'selection_ref':ref,'selection_hash':result['selection_hash'],
            'task_hash':result['task_hash'],'binding_hash':child.run()['binding_hash'],
            'quality_certified':False}
        child.db.execute('CREATE TABLE IF NOT EXISTS source_handoff_export(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL)')
        child.db.execute('CREATE TABLE IF NOT EXISTS source_handoff_export(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL)')
        child.db.execute('CREATE TABLE IF NOT EXISTS source_handoff_export(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL)')
        child.db.execute('CREATE TABLE IF NOT EXISTS source_handoff_export(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL)')
        child.db.execute('CREATE TABLE IF NOT EXISTS source_handoff_export(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL)')
        with child.transaction():
            old=child.db.execute("SELECT payload_json,payload_hash FROM source_handoff_export WHERE singleton=1").fetchone()
            if old:
                if digest(json.loads(old[0]))!=old[1] or json.loads(old[0])!=envelope:raise ContractError('source publication changed')
                if child.run()['status']!='COMPLETED' or child.run()['phase']!='END':raise ContractError('source publication terminal changed')
            else:
                if child.run()['status']!='RUNNING':raise ContractError('source handoff cannot publish failed work')
                child.db.execute('INSERT INTO source_handoff_export VALUES(1,?,?)',(encoded(envelope),digest(envelope)))
                child.event('SOURCE_HANDOFF_PUBLISHED',{'goal_id':result['goal_id'],'revision':result['revision'],
                    'envelope_hash':digest(envelope),'legal_answer_accepted':False})
                child.db.execute("UPDATE run SET status='COMPLETED',phase='END' WHERE singleton=1")
        return envelope
    finally:child.close()


def validate_export(child,envelope):
    if child.run()['status']!='COMPLETED' or child.run()['phase']!='END':raise ContractError('source work is not complete')
    if envelope.get('kind')!='SOURCE_HANDOFF' or envelope.get('answer') is not None:raise ContractError('invalid source return')
    row=child.db.execute("SELECT payload_json,payload_hash FROM source_handoff_export WHERE singleton=1").fetchone()
    if not row or digest(json.loads(row[0]))!=row[1] or json.loads(row[0])!=envelope:raise ContractError('source return artifact changed')
    from ..workflow_evidence import judgment
    selected=judgment(child,envelope['selection_ref'],'SELECT')
    if selected.get('terminal')!='SOURCE_HANDOFF' or digest(selected)!=envelope['selection_hash'] or selected['source_return']!=envelope['handoff']:raise ContractError('source return selection changed')
    if envelope['handoff'].get('schema_version')=='source-investigation-v2':
        from .investigation_leads import validate as validate_leads
        validate_leads(envelope['handoff']['leads'])
    rows=child.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'").fetchall()
    if len(rows)!=1:raise ContractError('source return task missing')
    task=json.loads(rows[0][0])
    if (digest(task)!=rows[0][1] or digest(task['task'])!=task['task_hash']
            or task['task_hash']!=envelope['task_hash'] or task['task'].get('return_mode')!='sources'):
        raise ContractError('source return task changed')
    if envelope['binding_hash']!=child.run()['binding_hash']:raise ContractError('source return binding changed')


def schema():
    """Internal SELECT terminal; model output remains the three-field action wire."""
    def obj(**props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
    original=obj(status={'const':'sources_returned'},terminal={'const':'SOURCE_HANDOFF'},next_action={'const':'DONE'},
        needs_fulltext={'const':False},final_ids={'const':[]},selected_originals={'const':[]},
        selected_evidence={'type':'array','items':{'type':'object'}},investigation_state={'type':'object'},
        source_return=obj(schema_version={'const':'source-investigation-v1'},read_evidence_ids={'type':'array','items':{'type':'string'},'uniqueItems':True},
            reason={'type':'string'},stop_reason={'type':['string','null']},acquisition={'type':'object'},research_tasks={'type':'object'},
            semantic_quality_certified={'const':False},absence_proven={'const':False}))

    current=deepcopy(original)
    contract=current['properties']['source_return']
    contract['properties']['schema_version']={'const':'source-investigation-v2'}
    contract['properties']['leads']={'type':'object'}
    contract['properties']['research_progress']={'type':'object'}
    contract['properties']['structure_selection_progress']={'type':'array','items':{'type':'object'}}
    contract['required'].append('leads')
    return {'anyOf':[original,current]}
