from common import *
C=ROOT/read(ART/'stage.json')['root'];B=C/'02_BACKEND/semantic_runtime/legal_agent'
p=B/'read_judgment.py';t=p.read_text().replace("return bool(inv.policy.get('read_judgment'))", "return bool(getattr(inv,'policy',{}).get('read_judgment'))")
t=t.replace("head.update(id=jid, version=", "head.update(document_name=original.get('document_name'),heading=original.get('heading'),\n            id=jid, version=")
p.write_text(t)
p=B/'judgment_view.py';t=p.read_text();anchor="""                row['actions'] += [str(d['decision']['next_action'])+' · '+str(d['decision']['reason'])
                                   for d in payload.get('decisions',[]) if 'next_action' in d.get('decision',{})]
"""
addition="""            for ledger in ledgers:
                labels={'CORE':'직접 근거 후보','SUPPORT':'보조 근거 후보','CONDITIONAL':'조건부 사용 후보',
                        'DEFER':'판단 보류','EXCLUDE':'사용 제외'}
                for head in ledger['heads'].values():
                    label=sources.get(head['source_id'],{'source_id':head['source_id'],
                        'document_name':head.get('document_name') or head['document_id'],
                        'coordinate':head.get('heading') or ''})
                    row['data'].append({**label,'action':'잠정 판단 · '+labels[head['use']],
                        'judgment':head['finding'],'reason':head['reason'],'judgment_id':head['id'],
                        'judgment_version':head['version']})
                    row['decisions'].append(labels[head['use']]+' · '+head['finding']+' · 이유: '+head['reason'])
                row.setdefault('limitations',[]).extend('미확인: '+n['text']+' · '+n['reason']
                    for n in ledger['needs'].values() if n['status']=='OPEN')
                row['limitations'].extend('판단 충돌: '+c['reason']
                    for c in ledger['conflicts'].values() if c['status']=='OPEN')
"""
assert anchor in t;t=t.replace(anchor,anchor+addition)
anchor="""                row['read_judgment_review'] = payload['read_judgment_review']
"""
addition="""                review=payload['read_judgment_review'].get('review') or {}
                dispositions={'USE':'최종 사용','CONDITIONAL':'조건부 사용','UNRESOLVED':'미해결','NOT_USED':'최종 미사용',
                              'OPEN':'미확인','RESOLVED':'해결 판단','NOT_NEEDED':'이번 답변에 불필요'}
                row['decisions'].extend(dispositions[r.get('disposition',r.get('status'))]+' · '+r['reason']
                    for field in ('judgments','needs','conflicts') for r in review.get(field,[]))
"""
assert anchor in t;t=t.replace(anchor,anchor+addition);p.write_text(t)
p=C/'05_TESTS/CONTRACTS/test_read_judgment_api.py';t=p.read_text().replace("        assert stages['SELECT']['read_judgments']", "        assert stages['SELECT']['read_judgments']\n        assert len([r for r in stages['SELECT']['data'] if r.get('judgment_id')])==2\n        assert any('이유:' in r for r in stages['SELECT']['decisions'])\n        if mode!='final_truncated':assert stages['ASSESS']['decisions']")
p.write_text(t)
