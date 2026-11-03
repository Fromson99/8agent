from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot'
B=S/'02_BACKEND/semantic_runtime'
p=B/'ontology_work/repository.py';s=p.read_text()
old='''            out=[]
            for pid in sorted(allowed):
                row=self.execute(c,f"SELECT PKG_HASH_VAL,PKG_JSON_CN FROM {self.tables['publication']} WHERE PUB_ID=:1",(pid,)).fetchone()
                raw=value(row[1])'''
new='''            out=[]
            ordered=sorted(allowed)
            if not ordered:return out
            marks=','.join(':'+str(i+1) for i in range(len(ordered)))
            rows=self.execute(c,f"SELECT PUB_ID,PKG_HASH_VAL,PKG_JSON_CN FROM {self.tables['publication']} WHERE PUB_ID IN ({marks})",tuple(ordered)).fetchmany(len(ordered)+1)
            by_id={row[0]:row[1:] for row in rows}
            if len(rows)!=len(by_id) or set(by_id)!=allowed:raise ContractError('ontology publication batch changed or incomplete')
            for pid in ordered:
                row=by_id[pid]
                raw=value(row[1])'''
assert old in s;s=s.replace(old,new);p.write_text(s)

p=B/'legal_agent/request_repair.py';s=p.read_text();pos=s.index('def no_progress_recovery(inv):')
helper='''def recovery_need_targets(inv,data):
    """Only an explicit outstanding need can extend an already-read search.

    Legacy or initial discovery keeps its bounded route. No need, judgment,
    source status or model opinion is rewritten by this eligibility check.
    """
    if not getattr(inv,'policy',{}).get('read_judgment') or not any(s.get('text') for s in data.get('sources',[])):
        return None
    from . import need_continuity,read_judgment
    targets=set()
    for need in need_continuity.known_needs(inv,data).values():
        if need.get('status') not in ('OPEN','REQUIRED','BLOCKED'):continue
        for declaration in need.get('declarations',[]):
            targets.update(a['target'] for a in declaration.get('proposed_actions',[]) if a.get('target'))
    for receipt in read_judgment.state_for(inv,data).get('history',[]):
        targets.update(a['target'] for a in receipt.get('next_actions',[]) if a.get('target'))
    for gap in data.get('gap_targets',[]):
        targets.update(gap.get('read_actions',[]));targets.update(gap.get('navigation_actions',[]))
    return targets


'''
s=s[:pos]+helper+s[pos:]
old="    if not any(a['action'] in useful for a in actions.values()):return None\n"
new="""    eligible=recovery_need_targets(inv,data)
    if eligible is not None:
        actions={ident:a for ident,a in actions.items() if ident in eligible}
    if not any(a['action'] in useful for a in actions.values()):return None
"""
assert old in s;s=s.replace(old,new);p.write_text(s)
print('ACL-first publication batch and need-bound recovery written')
