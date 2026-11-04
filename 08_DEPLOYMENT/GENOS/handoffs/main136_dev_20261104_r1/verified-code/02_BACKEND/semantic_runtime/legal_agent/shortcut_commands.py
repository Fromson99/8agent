"""Authenticated, closed mutation contract for case organization and review."""
from .corrected_memory import MemoryError,Conflict,digest,encoded

# Review receipts are deliberately excluded. A normal authenticated user can
# confirm a conversation, but cannot forge SOURCE or INTERPRETATION approval.
FIELDS={
 'issue':({'investigation_id','expected_revision','question'},{'branch','parent','constraints'}),
 'assign':({'event_id','issue_id','start','stop','reason'},{'role'}),
 'fact':({'investigation_id','expected_revision','event_id','subject','predicate','value'},{'fact_id','restore_revision','valid_time'}),
 'relate':({'source','target','kind','reason','expected_source','expected_target'},{'relation_id'}),
 'detach':({'investigation_id','session','expected_revision','reason'},set()),
 'publish':({'unit_id','revision','expected_head'},set()),
 'retire':({'unit_id','revision','reason'},{'disputed'}),
}


def execute(repo, principal, body):
    operation=body.get('operation');args=body.get('arguments')
    if operation not in FIELDS or not isinstance(args,dict):raise MemoryError('unsupported shortcut operation')
    required,optional=FIELDS[operation]
    if not required<=args.keys() or set(args)-required-optional:raise MemoryError('invalid shortcut operation fields')
    if not principal.get('authenticated'):raise MemoryError('authenticated command required')
    for field in ('session_id','request_id'):
        if not isinstance(body.get(field),str) or not body[field]:raise MemoryError('stable command identity required')
    scope=repo.scope(principal,create=True)
    key='command:'+digest([scope,body['session_id'],body['request_id']]);fingerprint=digest([operation,args])
    with repo.transaction():
        previous=repo.db.execute('SELECT payload FROM sw_import WHERE id=?',(key,)).fetchone()
        if previous:
            saved=__import__('json').loads(previous[0])
            if saved['input_hash']!=fingerprint:raise Conflict('command key changed')
            # Replay is fenced by fresh visibility to its original subject.
            _access(repo,principal,operation,args)
            return saved['result']
        _access(repo,principal,operation,args)
        if operation=='issue':
            ident=args['investigation_id'];case=repo.investigation(ident,principal)
            repo.advance(ident,principal,args['expected_revision'],'ISSUE_CREATED',{'question':args['question']})
            result={'issue_id':repo.issue(ident,principal,args['question'],**{k:args[k] for k in optional if k in args})}
        elif operation=='assign':
            result={'assignment_id':repo.assign(args['event_id'],args['issue_id'],principal,args['start'],args['stop'],reason=args['reason'],role=args.get('role','CONTEXT'))}
        elif operation=='fact':
            values={k:v for k,v in args.items() if k not in {'investigation_id','event_id'}}
            result=repo.fact(args['investigation_id'],principal,event=args['event_id'],**values)
        elif operation=='relate':
            event=repo.advance(args['source'],principal,args['expected_source'],'CASE_RELATION_ASSERTED',{'target':args['target'],'kind':args['kind'],'reason':args['reason']})
            repo.advance(args['target'],principal,args['expected_target'],'CASE_RELATION_ASSERTED',{'source':args['source'],'kind':args['kind'],'reason':args['reason']})
            result={'relation_id':repo.relation(args['source'],args['target'],principal,event=event,kind=args['kind'],reason=args['reason'],relation_id=args.get('relation_id'))}
        elif operation=='detach':
            result={'event_id':repo.detach_session(args['investigation_id'],args['session'],principal,expected_revision=args['expected_revision'],reason=args['reason'])}
        elif operation=='publish':result=repo.publish(args['unit_id'],args['revision'],principal,expected_head=args['expected_head'])
        else:
            repo.retire(args['unit_id'],args['revision'],principal,reason=args['reason'],disputed=args.get('disputed',False));result={'retired':True}
        repo.db.execute('INSERT INTO sw_import VALUES(?,?)',(key,encoded({'input_hash':fingerprint,'result':result})))
        return result


def _access(repo,principal,operation,args):
    if 'investigation_id' in args:repo.investigation(args['investigation_id'],principal)
    if 'unit_id' in args:
        row=repo.db.execute('SELECT scope FROM sw_unit WHERE id=?',(args['unit_id'],)).fetchone()
        if not row or row[0]!=repo.scope(principal):raise MemoryError('record inaccessible')
        # Currentness may be intentionally lost after retiring, so scope + pinned
        # document ACL is sufficient for idempotent replay of that mutation.
        import json
        row=repo.db.execute('SELECT payload FROM sw_knowledge WHERE unit=? AND revision=?',(args['unit_id'],args['revision'])).fetchone()
        if not row or not set(json.loads(row[0])['documents'])<=set(principal['document_ids']):raise MemoryError('record inaccessible')
    if operation=='assign':
        repo.event(args['event_id'],principal)
        row=repo.db.execute('SELECT investigation FROM sw_issue WHERE id=?',(args['issue_id'],)).fetchone()
        if not row:raise MemoryError('record inaccessible')
        repo.investigation(row[0],principal)
    if operation=='relate':
        repo.investigation(args['source'],principal);repo.investigation(args['target'],principal)
