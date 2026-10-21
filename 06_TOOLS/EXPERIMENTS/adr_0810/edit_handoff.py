from pathlib import Path
R=Path.cwd();C=R/'02_BACKEND/lawrag/research/candidates/adr_0810/connected/snapshot'
p=C/'02_BACKEND/semantic_runtime/workflow_evidence.py';s=p.read_text()
pos=s.index('\ndef compile_bundle(')
s=s[:pos]+'''
def parent_issues(child):
    """Recover host-owned joins from the child journal, including after restart."""
    rows=child.db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND' ORDER BY seq").fetchall()
    if not rows:return None
    if len(rows)!=1:raise ContractError('ambiguous workflow parent task binding')
    payload=json.loads(rows[0][0])
    if digest(payload)!=rows[0][1] or digest(payload['task'])!=payload['task_hash']:
        raise ContractError('workflow parent task hash mismatch')
    expected={'Q'+str(n):issue['id'] for n,issue in enumerate(payload['task']['issues'],1)}
    if payload['issue_map']!=expected or len(set(expected.values()))!=len(expected):
        raise ContractError('workflow parent issue mapping mismatch')
    return expected


def parent_refs(value, mapping):
    result=deepcopy(value)
    if mapping is not None:
        refs=result.get('issue_refs',[])
        result['parent_issue_refs']=list(dict.fromkeys(mapping[i] for i in refs if i in mapping))
        result['unmapped_child_issue_refs']=[i for i in refs if i not in mapping]
    return result

''' + s[pos:]
s=s.replace("    claims, evidence, origin_refs = [], {}, {}", "    claims, evidence, origin_refs = [], {}, {}\n    issue_map=parent_issues(child)")
s=s.replace("claims.append({k:deepcopy(claim[k]) for k in ('claim_id', 'text', 'issue_refs', 'rule', 'answer_content') if k in claim}\n                      | {'evidence_ids':list(dict.fromkeys(ids)), 'span_map':span_map})", "claims.append(parent_refs({k:deepcopy(claim[k]) for k in ('claim_id', 'text', 'issue_refs', 'rule', 'answer_content') if k in claim}\n                      | {'evidence_ids':list(dict.fromkeys(ids)), 'span_map':span_map},issue_map))")
s=s.replace("'gaps':deepcopy(assessment.get('gaps', [])),", "'gaps':[parent_refs(g,issue_map) for g in assessment.get('gaps', [])],")
s=s.replace("    result['bundle_hash'] = digest(result)", "    if issue_map is not None:result['issue_map']=issue_map\n    result['bundle_hash'] = digest(result)")
start=s.index('def compact_result(')
s=s[:start]+'''def compact_result(result):
    """One copy of structured judgments; generated prose stays in audit export.

    The parent receives every claim and unresolved gap, with explicit issue joins.
    It does not need a second natural-language rendition of the same assertions.
    """
    bundle=result.get('bundle') or {}
    return {k:result.get(k) for k in ('side','status')} | {
        'bundle_hash':bundle.get('bundle_hash'),
        'issue_map':bundle.get('issue_map'),
        'claims':[{k:c[k] for k in ('claim_id','issue_refs','parent_issue_refs','unmapped_child_issue_refs',
                                  'rule','evidence_ids','span_map') if k in c} for c in bundle.get('claims',[])],
        'gaps':bundle.get('gaps',[]),'limitations':bundle.get('limitations',[]),
        'stop_reason':bundle.get('stop_reason'),'audit_ref':result.get('run_id'),
        'semantic_quality_certified':False}
'''
p.write_text(s)
# Context is already read and verified. Acquire it once through the same recorded
# lookup before asking a model whether it needs to read those same blocks again.
p=C/'02_BACKEND/workflow/risk_team_compare_workflow/retrieval.py';s=p.read_text();s+='''

def restore_context(ctx,state):
    """Restore complete already-read originals for current adopted sources."""
    for side,result in state.get('rag_results',{}).items():
        adopted=sorted(result.get('evidence_ids',[]))
        if not adopted:continue
        key='source-context:'+digest([side,result.get('bundle',{}).get('bundle_hash'),adopted])
        old=ctx.repo.intent(key,'context',{'side':side,'evidence_ids':adopted})
        if old['status']=='COMPLETE':ids=old['result']['evidence_ids']
        elif old['status']=='FAILED':continue
        else:
            ids=ctx.rag.port.saved_context(adopted,key)
            ctx.repo.finish(key,{'evidence_ids':ids})
        state['context_evidence']=sorted(set(state.get('context_evidence',[]))|set(ids))
        by_side=state.setdefault('context_by_side',{})
        by_side[side]=sorted(set(by_side.get(side,[]))|set(ids))
        ctx.repo.save(state)
''';p.write_text(s)
p=C/'02_BACKEND/workflow/risk_team_compare_workflow/flow.py';s=p.read_text().replace("        elif stage=='VERIFY_BASIS':\n            value=", "        elif stage=='VERIFY_BASIS':\n            retrieval.restore_context(ctx,state)\n            value=");p.write_text(s)
# Preserve physical source blocks as indivisible model presentation units.
p=C/'02_BACKEND/workflow/presentation.py';s=p.read_text();s=s.replace("                split=ctx.rag.port.split_evidence(e,max(1,available//3))", "                split=ctx.rag.port.split_evidence(e,max(1,available))")
s=s.replace('    out=[deepcopy(by_id[i]) for i in sorted(selected)]', '''    out=[deepcopy(by_id[i]) for i in sorted(selected)]
    issue_refs={}
    for result in state.get('rag_results',{}).values():
        for claim in result.get('bundle',{}).get('claims',[]):
            for ident in claim.get('evidence_ids',[]):
                if ident in by_id:
                    issue_refs.setdefault(by_id[ident]['source_id'],set()).update(claim.get('parent_issue_refs',[]))''')
s=s.replace("        e['source_complete']=native.spans_complete", "        e['parent_issue_refs']=sorted(issue_refs.get(e['source_id'],set()))\n        e['source_complete']=native.spans_complete")
s=s.replace("'version_verified','source_complete','citation_names','spans')", "'version_verified','source_complete','citation_names','spans','parent_issue_refs')")
p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/workflow_bridge.py';s=p.read_text();a=s.index('        pieces=[]\n',s.index('    def split_evidence('));b=s.index('        self.session.repo.record_observation',a)
s=s[:a]+'''        pieces=[]
        for span in e['spans']:
            if len(span['text'])>max_chars:
                raise ContractError('complete source span exceeds model context; original and unfinished scope preserved')
            item=canonical_evidence(e,[span])
            self.session.verify(item);pieces.append(item)
'''+s[b:];p.write_text(s)
for p in C.rglob('*.py'):compile(p.read_text(),str(p),'exec')
print('handoff, saved original context and intact block presentation implemented')
