"""Post-run structural audit; display is never counted as legal correctness."""
from common import *
import sqlite3, html, gzip, collections

def escape(s):return html.escape(str(s),quote=False).replace('*','\\*').replace('[','\\[').replace(']','\\]')
rows=[]
for result in read(RUN/'result.json')['results']:
    p=RUN/'agent_layer'/result['arm']/result['case_id']
    response=read(p/'response.json')['body'] if (p/'response.json').exists() else {}
    meta=response.get('assembly',{}).get('term_agent',{}).get('legal_knowledge',{})
    receipt=meta.get('required_review');text=response.get('answer',{}).get('text','')
    events=[]
    for name in result['journal_paths']:
        with sqlite3.connect((ROOT/name).resolve().as_uri()+'?mode=ro',uri=True) as db:
            events += [{'kind':k,'payload':json.loads(v),'hash':h} for k,v,h in db.execute(
                "SELECT kind,payload_json,payload_hash FROM event WHERE kind LIKE 'REQUIRED_%' ORDER BY seq")]
    bound=[e['payload'] for e in events if e['kind']=='REQUIRED_ITEMS_BOUND']
    accepted=[e['payload'] for e in events if e['kind']=='REQUIRED_ITEMS_ACCEPTED']
    expected=bound[-1]['items'] if bound else []
    actual=receipt.get('rows',[]) if receipt else []
    display=[]
    for item in actual:
        display.append({'item_id':item['item_id'],'status':item['status'],'model_processed':item['model_processed'],
            'note_count':text.count('등록 메모: '+escape(item['note'])),'reason_present':escape(item['reason']) in text,
            'claim_count':len(item['claims'])})
    wire=[]
    for path in sorted((p/'wire').glob('*.gz')):
        with gzip.open(path,'rt') as f:w=json.load(f)
        v=json.loads(w['messages'][1]['content'])['view'];phase=v.get('source_stage',v.get('phase'))
        if str(phase).startswith('memory-assess'):
            wire.append({'path':str(path.relative_to(ROOT)),'phase':phase,
                'has_required_items':'required_review_items' in v,
                'has_required_schema':'required_review' in json.dumps(w['response_format']),
                'has_required_instruction':'required_review_items는 현재 원문에 연결된' in w['messages'][0]['content']})
    candidate=result['arm']=='candidate'
    checks={'bound_items_present':bool(expected) if candidate else not expected,
        'exact_item_identity':{i['item_id'] for i in expected}=={i['item_id'] for i in actual},
        'metadata_matches_journal':receipt==accepted[-1] if accepted else receipt is None,
        'display_exactly_once':all(d['note_count']==1 and d['reason_present'] for d in display),
        'no_semantic_approval':all(i.get('semantic_verified') is False for i in actual),
        'wire_flag_matches_arm':bool(wire) and all(all(w[k]==candidate for k in
            ('has_required_items','has_required_schema','has_required_instruction')) for w in wire)}
    row={'case_id':result['case_id'],'arm':result['arm'],'expected_count':len(expected),'displayed_count':len(actual),
        'statuses':dict(collections.Counter(i['status'] for i in actual)),'checks':checks,
        'structural_pass':all(checks.values()),'display':display,'wire':wire,'events':events,
        'semantic_pass':None,'meaning':'EXPLAINED means source-bound claims are linked, not that the legal explanation is correct.'}
    put(p/'required-audit.json',row);rows.append({k:v for k,v in row.items() if k not in ('events','display','wire')})
put(RUN/'required-audit.json',rows)
print(json.dumps(rows,ensure_ascii=False,indent=2))
