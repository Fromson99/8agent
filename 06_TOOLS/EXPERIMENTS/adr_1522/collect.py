"""Offline collection of one full run (reference answers never enter product input).

Per case: the counted folder (the rerun when the queue run had a provider/resource failure), HTTP status,
error code, claims, physical calls, unknown/blank/429, model vs non-model seconds, process CPU seconds,
duplicate-request check. CM: registered required articles acquired/cited (law name + article label on the
generation, as ADR-1482). photo/대사: target articles found in the evidence inventory / answer text.
Writes artifacts/summary.json and prints a short table."""
from common import *
import sqlite3,re,statistics,argparse
from collections import Counter,defaultdict
ART_RE=re.compile(r'(제\d+(?:-\d+)?조(?:의\d+)?)')
def path_article(path):
    tail=str(path or '').split(' > ')[-1];m=ART_RE.search(tail)
    return (tail[:m.start()].strip(),m.group(1)) if m else (tail.strip(),None)
_names={}
def names(gen):
    if gen not in _names:
        g=read(DES/'generations.json')[gen];db=sqlite3.connect((ROOT/g['path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
        _names[gen]={d:n.split(' > ')[-1] for d,n in db.execute('SELECT document_id,name FROM document')}
    return _names[gen]
def counted(cid):
    q=ART/'live'/cid;r=ART/'live'/(cid+'-rerun')
    if r.is_dir() and ((r/'result.json').exists() or not (q/'result.json').exists()):return r,True
    return q,False
def inventory(term):
    inv=term.get('evidence_inventory') or []
    acquired={(e.get('document_id'),)+path_article(e.get('path')) for e in inv if e.get('availability')=='ACQUIRED' or e.get('status')=='READ'}
    return inv,acquired
def collect():
    grades={g['id']:g for g in read(DES/'grading-only.json')};rows=[]
    for case in read(DES/'cases.json'):
        cid=case['id'];folder,rerun=counted(cid)
        if not folder.is_dir():rows.append({'case_id':cid,'kind':case['kind'],'state':'NOT_RUN'});continue
        calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
        res=read(folder/'result.json') if (folder/'result.json').exists() else {}
        turn=(res.get('turns') or [{}])[-1]
        row={'case_id':cid,'kind':case['kind'],'rerun':rerun,'queue_run_provider_failure':rerun,
             'state':'ANSWERED' if turn.get('http_status')==200 else ('HTTP_'+str(turn['http_status']) if turn.get('http_status') else
                     ('RESOURCE_STOP' if (folder/'resource-stop.json').exists() else 'RUNNER_FAILURE' if (folder/'runner-failure.json').exists() else 'INCOMPLETE')),
             **{k:turn.get(k) for k in ('http_status','request_seconds','model_seconds','non_model_seconds','cpu_seconds','claims','needs_guidance','accepted_outcome','status','method','error_code','message','duplicate','answer_chars','sides','comparison_items')},
             'physical_calls':len(calls),'unknown':sum(c['status'] in ('unknown','started') for c in calls),'blank':sum(bool(c.get('blank')) for c in calls),
             'http429':sum(c.get('http_status')==429 for c in calls),'providers':dict(Counter(str(c.get('actual_provider')) for c in calls if c.get('actual_provider'))),
             'cost':round(sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls),5),
             'unknown_stages':[c.get('stage') for c in calls if c['status'] in ('unknown','started')],
             'rejected_generations':[{k:g.get(k) for k in ('stage','error_type','error')} for g in (read(folder/'generations.json') if (folder/'generations.json').exists() else []) if g.get('status')=='rejected'],
             'peak_rss_mib':(round(read(folder/'resource-final.json').get('peak_rss_KiB',0)/1024) if (folder/'resource-final.json').exists() else None),
             'runner_failure':(read(folder/'runner-failure.json').get('error')[:300] if (folder/'runner-failure.json').exists() else None)}
        resp=folder/'turn-1/response.json.gz'
        if resp.exists():
            saved=read(resp);body=saved['body'] or {};answer=body.get('answer') or {}
            term=(body.get('assembly') or {}).get('term_agent') or {}
            if not row.get('error_code') and saved['http_status']!=200:
                err=body.get('error') if isinstance(body.get('error'),dict) else {}
                row['error_code']=body.get('error_code') or err.get('code') or body.get('code');row['message']=str(body.get('message') or body.get('detail') or err.get('message') or '')[:300]
            claims=answer.get('claims',[]) if isinstance(answer,dict) else []
            cited={s for c in claims for s in c.get('source_ids',[])}
            inv,acquired=inventory(term)
            cited_arts={(e.get('document_id'),)+path_article(e.get('path')) for e in inv if e.get('source_id') in cited}
            text=answer.get('text','') if isinstance(answer,dict) else str(answer or '')
            reply=term.get('guided_reply') or {}
            row['followup']={'unused_sources':len(reply.get('unused_sources') or []),
                             'unused_model_reason':sum(r.get('reason_origin')=='MODEL_NOTE' for r in reply.get('unused_sources') or []),
                             'unread_connections':len(reply.get('unread_connections') or []),'numbered':len(reply.get('followup_reads') or [])}
            row['acquired_articles']=sorted(f"{names(case['generation']).get(d,n)} {a or ''}".strip() for d,n,a in acquired)[:80]
            g=grades[cid]
            if case['kind']=='cm':
                scope=set(case['document_ids']);nm=names('main');req=[]
                for t in g['targets']:
                    if t.get('role')!='required':continue
                    label=(t.get('article') or '').replace(' ','');cur=[d for d,n in nm.items() if n==t.get('law') and d in scope]
                    did=next((d for d in cur if d==t.get('doc_id')),cur[0] if cur else None)
                    req.append({'law':t.get('law'),'article':t.get('article'),'acquired':any(d==did and (a or '').replace(' ','')==label for d,_,a in acquired),
                                'cited':any(d==did and (a or '').replace(' ','')==label for d,_,a in cited_arts)})
                row.update(required_total=len(req),required_acquired=sum(x['acquired'] for x in req),required_cited=sum(x['cited'] for x in req),targets=req)
            elif case['kind']=='edge':
                # ADR-1518: required evidence -> (document, article); annex files without an article match the document.
                need={}
                for e in g['required_evidence']:
                    arts=ART_RE.findall(e.get('unit_label') or '');need[(e['document_id'],arts[-1] if arts else None)]=e['document']
                def hit(pool,d,a):return any(x==d and (a is None or (y or '').replace(' ','')==a) for x,_,y in pool)
                req=[{'document':n,'article':a,'acquired':hit(acquired,d,a),'cited':hit(cited_arts,d,a)} for (d,a),n in need.items()]
                row.update(required_total=len(req),required_acquired=sum(x['acquired'] for x in req),required_cited=sum(x['cited'] for x in req),targets=req,
                           connection_hops=g['connection_hops'])
            elif case['kind']=='photo':
                tg=[{'article':t['article'],'document_id':t['document_id'],'acquired':any(d==t['document_id'] and a==t['article'] for d,_,a in acquired)} for t in g['targets']]
                row.update(targets=tg,required_total=len(tg),required_acquired=sum(x['acquired'] for x in tg))
            elif case['kind']=='compare':
                tg=[{**t,'in_answer':bool(t.get('article')) and t['article'] in text and (t['document'] in text),'document_in_answer':t['document'] in text} for t in g['targets']]
                row.update(targets=tg)
        rows.append(row)
    return rows
def summarize(rows):
    by=defaultdict(list)
    for r in rows:by[r['kind']].append(r)
    out={}
    for kind,rs in by.items():
        done=[r for r in rs if r['state']!='NOT_RUN']
        out[kind]={'cases':len(rs),'run':len(done),'states':dict(Counter(r['state'] for r in done)),
            'unknown_calls':sum(r.get('unknown',0) for r in done),'blank_calls':sum(r.get('blank',0) for r in done),'http429':sum(r.get('http429',0) for r in done),
            'physical_calls':sum(r.get('physical_calls',0) for r in done),'cost':round(sum(r.get('cost',0) for r in done),4),
            'reruns':sum(r.get('rerun',False) for r in done),
            'median_seconds':statistics.median([r['request_seconds'] for r in done if r.get('request_seconds')] or [0]),
            'median_non_model_seconds':statistics.median([r['non_model_seconds'] for r in done if r.get('non_model_seconds') is not None] or [0]),
            'max_non_model_seconds':max([r['non_model_seconds'] for r in done if r.get('non_model_seconds') is not None] or [0]),
            'median_cpu_seconds':statistics.median([r['cpu_seconds'] for r in done if r.get('cpu_seconds') is not None] or [0]),
            'max_cpu_seconds':max([r['cpu_seconds'] for r in done if r.get('cpu_seconds') is not None] or [0]),
            'error_codes':dict(Counter(str(r.get('error_code')) for r in done if r['state']!='ANSWERED')),
            'claims_zero_answered':sum(1 for r in done if r['state']=='ANSWERED' and not r.get('claims')),
            'max_peak_rss_mib':max([r.get('peak_rss_mib') or 0 for r in done] or [0]),
            'duplicate_extra_calls':sum((r.get('duplicate') or {}).get('extra_model_calls',0) or 0 for r in done)}
        if kind in ('cm','photo','edge'):
            out[kind].update(required_total=sum(r.get('required_total',0) for r in done),required_acquired=sum(r.get('required_acquired',0) for r in done),
                             required_cited=sum(r.get('required_cited',0) for r in done if kind in ('cm','edge')))
    return out
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--quiet',action='store_true');a=ap.parse_args()
    rows=collect();s=summarize(rows)
    put(ART/'summary.json',{'rows':rows,'by_kind':s,'reference_input_is_offline_only':True,'semantic_grades_automatically_generated':False})
    print(json.dumps(s,ensure_ascii=False,indent=1))
    if not a.quiet:
        for r in rows:
            print(r['case_id'],r['state'],r.get('error_code') or '',r.get('physical_calls'),'unk',r.get('unknown'),'s',r.get('request_seconds') and round(r['request_seconds']),
                  'nm',r.get('non_model_seconds') and round(r['non_model_seconds']),'cpu',r.get('cpu_seconds') and round(r['cpu_seconds']),'claims',r.get('claims'),
                  ('req %s/%s cit %s'%(r.get('required_acquired'),r.get('required_total'),r.get('required_cited'))) if r['kind'] in ('cm','photo') else '')
