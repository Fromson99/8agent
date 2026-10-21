"""Post-selection diagnostics from immutable observations, never product inputs."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,json,sqlite3,unicodedata
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0955-main94-design-weakness-probe';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def normalize(v):
    if isinstance(v,str):return ' '.join(unicodedata.normalize('NFKC',v).split()).casefold()
    if isinstance(v,dict):return {k:normalize(x) for k,x in v.items()}
    if isinstance(v,list):return [normalize(x) for x in v]
    return v
out={}
for case in read(D/'cases.json'):
    P=O/'observed'/case['id'];audit=read(P/'audit.json');body=read(P/'response.json')['body']
    rows=audit['tool_trace'];searches=[r for r in rows if 'search' in r['tool'].lower() and r['status']=='OK']
    keys=Counter(canon({'side':r['side'],'tool':r['tool'],'args':normalize(json.loads(r['request_json'])['args'])}) for r in searches)
    dup_table=[]
    for n,row in enumerate(body['comparison_table']['rows']):
        groups=defaultdict(list)
        for e in row['external']:
            k=canon({f:e[f] for f in ('document_id','generation_id','source_artifact_hash','coordinate_label','quote')})
            groups[k].append(e['selection_id'])
        dup_table.extend({'row':n,'source':json.loads(k),'evidence_ids':v} for k,v in groups.items() if len(v)>1)
    first=None
    for path in sorted((P/'canonical').glob('*.json.gz')):
        if '-output' in path.name:continue
        v=json.loads(gzip.decompress(path.read_bytes()))['view']
        if v.get('source_stage','').startswith('source-law-sources-') and v.get('workflow_task',{}).get('source_category')=='external':
            first={'file':str(path.relative_to(R)),'task':v['workflow_task']};break
    spill=[]
    if first:
        anchors=[s for a in first['task'].get('internal_anchors',[]) for s in a['sources']]
        for item in first['task'].get('basis_snapshot',{}).get('items',[]):
            ends=item['binding'] or item['link']
            matches=any(a['document_id']==e['document_id'] and
                any(a['quote'] in s['text'] or s['text'] in a['quote'] for s in e['spans'])
                for a in anchors for e in ends['internal'])
            if not matches:
                spill.append({'link_id':item['link']['link_id'],
                    'internal':[(e['document_id'],e['unit_id']) for e in ends['internal']],
                    'external':[(e['document_id'],e['unit_id']) for e in ends['external']],
                    'anchor_quotes':[a['quote'] for a in anchors]})
    calls=read(P/'calls.json')
    out[case['id']]={'search_observations':len(searches),'exact_repeated_search_executions':sum(n-1 for n in keys.values()),
        'search_queries':[json.loads(r['request_json']) for r in searches],
        'basis_links_outside_selected_concept':spill,'first_external_view':first['file'] if first else None,
        'duplicate_source_rows':dup_table,'native_read_observations':sum(r['tool'] in ('read','read_node') for r in rows),
        'actual_model_attempts':len(calls),'unknown_outcome_calls':sum(c.get('outcome') in (None,'UNKNOWN') for c in calls),
        'rejected_calls':sum(c.get('http_status')!=200 for c in calls),
        'scope': 'Tool observation duplicate metric excludes restored/imported evidence and does not equate all repeated display or additional queries with network/database re-execution.'}
record={'schema':'main94-design-post-audit-v1','computed_after_product':True,'cases':out,
    'code_findings':[
        {'path':'02_BACKEND/semantic_runtime/basis_links/integration.py','line':48,
         'finding':'parent_task matches reviewed links against all acquired internal evidence; it does not limit the snapshot to selected concept citations.'},
        {'path':'02_BACKEND/workflow/risk_team_compare_workflow/retrieval.py','line':31,
         'finding':'parent_task compiles basis_targets before internal_anchors are added; anchors are context, not the scope used for that automatic target selection.'},
        {'path':'02_BACKEND/workflow/risk_team_compare_workflow/contracts.py','line':46,
         'finding':'ADDITIONAL_INTERNAL already exists. False CONFLICT is a model judgment failure despite the available category, not an absent enum.'},
    ]}
(O/'post-audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{'duplicate_searches':v['exact_repeated_search_executions'],
    'outside_concept_links':len(v['basis_links_outside_selected_concept']),'duplicate_display_groups':len(v['duplicate_source_rows']),
    'unknown_calls':v['unknown_outcome_calls']} for k,v in out.items()}))
