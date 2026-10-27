"""Compile committed child claim spans into immutable parent evidence.

Exploration stays in the child journal. No model, inferred relevance or legal
conclusion is introduced here; source completeness remains a separate check.
"""
from copy import deepcopy
import json
import sqlite3
from .contracts import digest
from .legal_agent.errors import ContractError
from .legal_agent.repository import text_hash
from .legal_agent.source_tools import canonical_evidence
from .legal_agent.unified_publication import _ref, validate_current


def judgment(child, ref, stage):
    if not isinstance(ref, dict):
        raise ContractError('workflow export requires committed judgment refs')
    if ref['run_id'] == child.run()['run_id']:
        _ref(child.db, ref, stage)
        row = child.db.execute('SELECT payload_json FROM entity_version WHERE kind=? AND entity_id=? AND version=?',
                              (ref['kind'], ref['entity_id'], ref['version'])).fetchone()
        return json.loads(row[0])
    paths = list(child.path.parents[2].glob('*/'+ref['run_id']+'/journal.sqlite'))
    if len(paths) != 1:
        raise ContractError('workflow origin judgment missing')
    with sqlite3.connect(paths[0].resolve().as_uri()+'?mode=ro', uri=True) as db:
        _ref(db, ref, stage)
        return json.loads(db.execute('SELECT payload_json FROM entity_version WHERE kind=? AND entity_id=? AND version=?',
                                    (ref['kind'], ref['entity_id'], ref['version'])).fetchone()[0])


def receipt_evidence(receipt, origin, verify):
    """A new canonical ID for an exact adopted subspan, never an edited old ID."""
    if (receipt['source_id'], receipt['document_id']) != (origin['source_id'], origin['document_id']):
        raise ContractError('workflow claim receipt source mismatch')
    if receipt['evidence_id']!=origin['evidence_id']:
        raise ContractError('workflow receipt origin identity mismatch')
    start, end = receipt['start_cp'], receipt['end_cp']
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ContractError('workflow claim range invalid')
    matching = [s for s in origin['spans'] if s['block_id'] == receipt['block_id']
                and s['start_cp'] <= start < end <= s['end_cp']]
    if not matching or digest(receipt['text']) != receipt['text_hash']:
        raise ContractError('workflow claim receipt unread or hash mismatch')
    s = matching[0]
    if s['text'][start-s['start_cp']:end-s['start_cp']] != receipt['text']:
        raise ContractError('workflow claim differs from read original')
    span = dict(block_id=s['block_id'], start_cp=start, end_cp=end, text=receipt['text'],
                block_hash=s['block_hash'], span_hash=text_hash(receipt['text']))
    # Display coordinates are stable source coordinates, not the route used to read it.
    metadata = {**origin['metadata'], 'read_location':origin['metadata'].get('heading', '')}
    value = canonical_evidence({**origin, 'metadata':metadata}, [span])
    verify(value)
    return value


def parent_issues(child):
    """Recover host-owned joins from the child journal, including after restart."""
    rows=child.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND' ORDER BY seq").fetchall()
    if not rows:return None
    if len(rows)!=1:raise ContractError('ambiguous workflow parent task binding')
    payload=json.loads(rows[0][0])
    if digest(payload)!=rows[0][1] or digest(payload['task'])!=payload['task_hash']:
        raise ContractError('workflow parent task hash mismatch')
    expected={'Q'+str(n):issue['id'] for n,issue in enumerate(payload['task'].get('issues',[]),1)}
    if payload['issue_map']!=expected or len(set(expected.values()))!=len(expected):
        raise ContractError('workflow parent issue mapping mismatch')
    return expected if 'issues' in payload['task'] else None


def parent_refs(value, mapping):
    result=deepcopy(value)
    if mapping is not None:
        refs=result.get('issue_refs',[])
        if 'issue_id' in result:refs=list(dict.fromkeys([*refs,result['issue_id']]))
        result['parent_issue_refs']=list(dict.fromkeys(mapping[i] for i in refs if i in mapping))
        result['unmapped_child_issue_refs']=[i for i in refs if i not in mapping]
    return result


def compile_bundle(child, envelope, side, verify, store, docs, *, current=True):
    if current:
        validate_current(child, envelope, store, allowed_documents=docs)
    meta = envelope.get('assembly', {}).get('term_agent', {})
    case = meta.get('case', {})
    refs = case.get('judgment_refs') or {}
    claims, evidence, origin_refs = [], {}, {}
    issue_map=parent_issues(child)
    assessment = judgment(child, refs['ASSESS'], 'ASSESS') if 'ASSESS' in refs else {}
    selection = judgment(child, refs['SELECT'], 'SELECT') if 'SELECT' in refs else {}
    from .legal_agent.completion_contracts import verify_span_claim
    originals = selection.get('selected_originals', [])
    for claim in assessment.get('claims', []):
        verify_span_claim(claim, originals)
        ids = [];span_map={}
        for receipt in claim['span_receipts']:
            origin = child.evidence(receipt['evidence_id'])
            if origin['document_id'] not in docs:
                raise ContractError('workflow adopted evidence escaped side')
            item = receipt_evidence(receipt, origin, verify)
            ident = item['evidence_id']
            if ident in evidence and evidence[ident] != item:
                raise ContractError('workflow evidence identity collision')
            evidence[ident] = item
            ids.append(ident);span_map[receipt['id']]=ident
            origin_refs.setdefault(ident, []).append({'run_id':child.run()['run_id'],
                'claim_id':claim['claim_id'], 'receipt':deepcopy(receipt)})
        claims.append(parent_refs({k:deepcopy(claim[k]) for k in ('claim_id', 'text', 'issue_refs', 'rule', 'answer_content') if k in claim}
                      | {'evidence_ids':list(dict.fromkeys(ids)), 'span_map':span_map},issue_map))
    if envelope.get('answer', {}).get('claims') and not claims:
        raise ContractError('workflow answer claims have no committed span receipts')
    result = {'schema_version':'workflow-comparison-bundle-v1', 'side':side,
        'producer':{'run_id':child.run()['run_id'], 'case':case, 'result_hash':digest(envelope)},
        'binding_hash':child.run()['binding_hash'], 'claims':claims,
        'evidence_ids':sorted(evidence), 'origin_refs':origin_refs,
        'gaps':[parent_refs(g,issue_map) for g in assessment.get('gaps', [])],
        'limitations':deepcopy(assessment.get('limitations', [])),
        'stop_reason':assessment.get('stop_reason'),
        'semantic_quality_certified':False,
        'counts':{'read_evidence':len(child.evidence()), 'adopted_spans':sum(len(c.get('span_receipts', [])) for c in assessment.get('claims', [])),
                  'unique_spans':len(evidence), 'text_chars':sum(len(e['spans'][0]['text']) for e in evidence.values())}}
    if issue_map is not None:result['issue_map']=issue_map
    result['bundle_hash'] = digest(result)
    return result, list(evidence.values())


def save_export(parent, call_id, child, envelope, bundle):
    parent.db.execute('''CREATE TABLE IF NOT EXISTS workflow_child_export(
        call_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, envelope_json TEXT NOT NULL,
        envelope_hash TEXT NOT NULL, bundle_json TEXT NOT NULL, bundle_hash TEXT NOT NULL)''')
    values = (call_id, child.run()['run_id'], json.dumps(envelope, ensure_ascii=False), digest(envelope),
              json.dumps(bundle, ensure_ascii=False), digest(bundle))
    old = parent.db.execute('SELECT * FROM workflow_child_export WHERE call_id=?', (call_id,)).fetchone()
    if old and tuple(old) != values:
        raise ContractError('workflow return changed for same call')
    parent.db.execute('INSERT OR IGNORE INTO workflow_child_export VALUES(?,?,?,?,?,?)', values)


def compile_read_bundle(child, side, verify, store, docs):
    """Export actual reads independently of the child's completion opinion.

    No child claims, legal conclusions or successful investigation are inferred.
    Every original is checked again against the parent's current source binding.
    """
    run=child.run()
    if digest(child.binding)!=run['binding_hash']:
        raise ContractError('workflow read export binding changed')
    if set(child.binding['scope']['document_version_ids'])!=set(docs):
        raise ContractError('workflow read export scope changed')
    for key in ('generation_id','store_sha256','export_allowed'):
        if child.binding[key]!=store.manifest[key]:
            raise ContractError('workflow read export source generation changed')
    evidence={}
    for original in child.evidence():
        if original['document_id'] not in docs:
            raise ContractError('workflow read export escaped side scope')
        verify(original)
        item=canonical_evidence(original,original['spans'])
        verify(item)
        evidence[item['evidence_id']]=item
    bundle={'schema_version':'workflow-comparison-bundle-v1','side':side,
        'export_mode':'READ_ORIGINALS','producer':{'run_id':run['run_id']},
        'binding_hash':run['binding_hash'],'claims':[],'evidence_ids':sorted(evidence),
        'origin_refs':{},'gaps':[],
        'limitations':['원문은 읽었으나 자식 RAG의 조사 판단은 완료되지 않았습니다. 원문의 관련성과 의미는 비교 단계에서 검토합니다.'],
        'stop_reason':'CHILD_INVESTIGATION_INCOMPLETE','semantic_quality_certified':False,
        'counts':{'read_evidence':len(evidence),'adopted_spans':0,'unique_spans':len(evidence),
                  'text_chars':sum(len(s['text']) for e in evidence.values() for s in e['spans'])}}
    bundle['bundle_hash']=digest(bundle)
    return bundle,list(evidence.values())


def compile_source_bundle(child,envelope,side,verify,store,docs):
    from .legal_agent.source_handoff import validate_export
    validate_export(child,envelope)
    bundle,evidence=compile_read_bundle(child,side,verify,store,docs)
    if sorted(e['evidence_id'] for e in child.evidence())!=envelope['handoff']['read_evidence_ids']:
        raise ContractError('source handoff read inventory changed')
    bundle.update(schema_version=('workflow-comparison-bundle-v3' if envelope['handoff'].get('schema_version')=='source-investigation-v2' else 'workflow-comparison-bundle-v2'),export_mode='SOURCE_HANDOFF',
        producer={'run_id':child.run()['run_id'],'result_hash':digest(envelope)},
        limitations=['원문 조사 반환입니다. 관련성·적용성·차이는 부모 LLM이 검토합니다.'],
        stop_reason=envelope['handoff'].get('stop_reason'),investigation_return=envelope['handoff'],
        issue_map=parent_issues(child))
    bundle.pop('bundle_hash',None);bundle['bundle_hash']=digest(bundle)
    return bundle,evidence


def verify_export(parent, call_id, child, result, port):
    row = parent.db.execute('SELECT * FROM workflow_child_export WHERE call_id=?', (call_id,)).fetchone()
    if row is None:
        if result.get('bundle'):
            raise ContractError('workflow committed export missing')
        return
    envelope, saved = json.loads(row['envelope_json']), json.loads(row['bundle_json'])
    if digest(envelope) != row['envelope_hash'] or digest(saved) != row['bundle_hash']:
        raise ContractError('workflow committed export hash changed')
    docs = [d for d in port.all_scope if port.categories[d] == result['side']]
    if saved.get('export_mode')=='SOURCE_HANDOFF':
        bundle,evidence=compile_source_bundle(child,envelope,result['side'],port.session.verify,port.session.store,docs)
        if result.get('answer') is not None or result.get('continuation')!={k:envelope.get(k) for k in ('goal_id','revision','investigation_id','investigation_revision')}:
            raise ContractError('source handoff continuation changed')
        if bundle!=saved or bundle!=result.get('bundle') or result.get('evidence_ids')!=bundle['evidence_ids']:raise ContractError('source export changed')
        for e in evidence:
            actual=parent.evidence(e['evidence_id'])
            if canonical_evidence(actual,actual['spans'])!=e:raise ContractError('source export differs from original')
        return
    if saved.get('export_mode')=='READ_ORIGINALS':
        if envelope is not None or result.get('answer') is not None or result.get('status')!='failed':
            raise ContractError('incomplete read export must not become a completed child answer')
        bundle,evidence=compile_read_bundle(child,result['side'],port.session.verify,port.session.store,docs)
        if bundle!=saved or bundle!=result.get('bundle') or result.get('evidence_ids')!=bundle['evidence_ids']:
            raise ContractError('workflow read export changed')
        for e in evidence:
            actual=parent.evidence(e['evidence_id'])
            if canonical_evidence(actual,actual['spans'])!=e:
                raise ContractError('workflow read export differs from original')
        return
    bundle, evidence = compile_bundle(child, envelope, result['side'], port.session.verify,
                                      port.session.store, docs, current=False)
    if (result.get('answer')!=envelope.get('answer') or result.get('evidence_ids')!=bundle['evidence_ids']
            or result.get('continuation')!={k:envelope.get(k) for k in ('goal_id','revision','investigation_id','investigation_revision')}):
        raise ContractError('workflow return differs from committed answer or evidence')
    checkpoint=json.loads(parent.db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
    if checkpoint.get('rag_results',{}).get(result['side'],{}).get('request_id')==call_id:
        if not retained_after_failure(parent,checkpoint,call_id,child,result,port):
            validate_current(child,envelope,port.session.store,allowed_documents=docs)
    elif any(r.get('request_id')==call_id for r in checkpoint.get('rag_valid_results',{}).get(result['side'],[])):
        retained_context(child,port)
    if bundle != saved or bundle != result.get('bundle'):
        raise ContractError('workflow bundle differs from accepted child judgment')
    for e in evidence:
        actual = parent.evidence(e['evidence_id'])
        if canonical_evidence(actual, actual['spans']) != e:
            raise ContractError('workflow parent evidence differs from committed span')


def compact_result(result):
    """One copy of structured judgments; generated prose stays in audit export.

    The parent receives every claim and unresolved gap, with explicit issue joins.
    It does not need a second natural-language rendition of the same assertions.
    """
    bundle=result.get('bundle') or {}
    return {k:result.get(k) for k in ('side','status')} | {
        'bundle_hash':bundle.get('bundle_hash'),
        'issue_map':bundle.get('issue_map'),
        'claims':[{k:c[k] for k in ('claim_id','issue_refs','parent_issue_refs','unmapped_child_issue_refs',
                                  'rule','evidence_ids','span_map') if k in c}
                  | ({'text':c['text']} if not c.get('rule') and 'text' in c else {}) for c in bundle.get('claims',[])],
        'gaps':bundle.get('gaps',[]),'limitations':bundle.get('limitations',[]),
        'stop_reason':bundle.get('stop_reason'),'audit_ref':result.get('run_id'),
        'source_investigation':{
            'leads':{k:v for k,v in (bundle.get('investigation_return',{}).get('leads') or {}).items() if k in ('schema_version','catalogue_hash','omitted_count','recording_status')},
            'reason':bundle.get('investigation_return',{}).get('reason'),
            'documents':{k:{n:v.get(n) for n in ('status','read_complete','delivered','missing_blocks','reason')} for k,v in bundle.get('investigation_return',{}).get('acquisition',{}).get('documents',{}).items()},
            'references':list(bundle.get('investigation_return',{}).get('acquisition',{}).get('references',{}).values())},
        'semantic_quality_certified':False}


def retained_after_failure(parent,checkpoint,call_id,child,result,port):
    """Historical successful export, only after this parent's failed continuation.

    Source and committed claim checks still run in compile_bundle. This is not
    permission to publish a stale native case as the current native answer.
    """
    latest=checkpoint.get('rag_attempts',{}).get(result['side'],{})
    if latest.get('status')!='failed' or latest.get('request_id')==call_id:return False
    attempt=parent.db.execute("SELECT input_json,result_json,result_hash FROM workflow_call WHERE call_id=? AND kind='rag' AND status='COMPLETE'",(latest.get('request_id'),)).fetchone()
    if not attempt:raise ContractError('retained result lacks a failed continuation receipt')
    current=json.loads(attempt['result_json']);request=json.loads(attempt['input_json'])
    if digest(current)!=attempt['result_hash'] or current!=latest or request['args']['previous']!=result:
        raise ContractError('retained result failed continuation lineage changed')
    retained_context(child,port)
    return True


def retained_context(child,port):
    from .legal_agent.unified_publication import _commit
    from .legal_agent.shortcut_store import selected_store
    from pathlib import Path
    c=_commit(child);path=Path(c['case_db']);runtime=child.path.parents[4]
    if path.resolve() not in {(runtime/'case-memory'/'cases-v3.sqlite').resolve(),selected_store(runtime).resolve()}:
        raise ContractError('retained result authority path changed')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        owner=db.execute('SELECT owner,team FROM session WHERE id=?',(c['session_id'],)).fetchone()
        principal=json.loads(c['principal_json'])
        if owner!=(principal['user_id'],principal['team_id']):raise ContractError('retained result owner changed')
        goal=db.execute('SELECT state FROM goal WHERE id=? AND session=?',(c['question_id'],c['session_id'])).fetchone()
        context=child.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='CASE_EXECUTION_CONTEXT' ORDER BY seq DESC LIMIT 1").fetchone()
        if not goal or not context or digest(json.loads(context[0]))!=context[1] or digest(json.loads(goal[0]))!=json.loads(context[0])['state_hash']:
            raise ContractError('retained result case facts or scope changed')
    for k in ('generation_id','store_sha256','export_allowed'):
        if child.binding[k]!=port.session.store.manifest[k]:raise ContractError('retained result data binding changed')
    return True
