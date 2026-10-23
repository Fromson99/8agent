"""Post-run source subgraph and actual navigation receipts, kept distinct."""
from common import *
import sqlite3,sys
def db(p):
    c=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
G=ROOT/read(DES/'baseline.json')['release']['data_path']
nav=db(G/'navigation/navigation.sqlite')
for case in read(DES/'cases.json'):
    P=RUN/case['id']
    if not (P/'audit.json').exists():continue
    audit=read(P/'audit.json');result=read(P/'result.json')
    reads={e['source_id'] for e in audit['read_evidence']};cites=set(audit['final_source_ids'])
    nodes=[]
    for sid in sorted(reads|cites):
        row=nav.execute('select json from source where id=?',(sid,)).fetchone()
        if row:
            v=json.loads(row[0]);nodes.append({'id':sid,'document':v.get('document_name'),'article':v.get('article') or (v.get('article_coordinate') or {}).get('article'),'heading':v.get('heading'),'read':sid in reads,'cited':sid in cites})
    edges={}
    for sid in sorted(reads):
        for row in nav.execute('select p.json from reference_end e join reference_payload p on p.id=e.reference_id where e.source_id=?',(sid,)):
            v=json.loads(row[0]);src=v.get('source_id')
            for dst in v.get('target_source_ids',[]):
                if src in reads and dst in reads and src!=dst:
                    edges[(v['id'],dst)]={'reference_id':v['id'],'from':src,'to':dst,'mention':v.get('mention_text'),'role':v.get('reference_role'),'resolution':v.get('resolution'),'source_block_id':v.get('block_id'),'mention_start':v.get('mention_start'),'mention_end':v.get('mention_end'),'both_cited':src in cites and dst in cites,'basis':'Stored explicit reference between actually read article roots; does not establish this edge was traversed or the full articles were read.'}
    observations=[];model_choices=[];scan=[];proposals=[]
    for p in sorted((P/'raw').glob('call-*/response.json')):
        raw=read(p)
        try:value=json.loads(raw['choices'][0]['message']['content'])
        except (ValueError,KeyError,IndexError,TypeError):continue
        proposals.append({'call':p.parent.name,'choice':value.get('choice'),'action':value.get('action') or value.get('next_action'),
          'selections':value.get('selections'),'exploration':value.get('exploration'),'request_scope':value.get('request_scope'),'reason':value.get('reason'),'raw_response':str(p.relative_to(ROOT))})
    for rel in result.get('journal_paths',[]):
        j=db(ROOT/rel)
        for row in j.execute('select observation_id,tool,request_json,result_json,status,created_seq from observation order by created_seq'):
            request=json.loads(row['request_json']);value=json.loads(row['result_json'])
            observations.append({'observation_id':row['observation_id'],'seq':row['created_seq'],'tool':row['tool'],'request':request,'status':row['status'],'result_keys':list(value) if isinstance(value,dict) else [],'returned_source_ids':value.get('source_ids',[]) if isinstance(value,dict) else []})
        for row in j.execute('select seq,kind,payload_json from event order by seq'):
            if any(x in row['kind'] for x in ('READ_CHOICE','NAVIGATION','LAW_STRUCTURE','REFERENCE','CONNECTED')):
                model_choices.append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
        scan.extend(dict(row) for row in j.execute('select * from relation_scan'))
        j.close()
    adjacent={}
    for e in edges.values():adjacent.setdefault(e['from'],set()).add(e['to'])
    paths=[]
    def walk(path):
        if len(path)>=7:paths.append(path);return
        more=[x for x in adjacent.get(path[-1],[]) if x not in path]
        if not more:paths.append(path)
        for x in sorted(more):walk(path+[x])
    for sid in sorted(adjacent):walk([sid])
    longest=sorted(paths,key=lambda v:(-len(v),v))[:5]
    put(P/'law-connections.json',{'case_id':case['id'],'nodes':nodes,'stored_reference_edges':list(edges.values()),'longest_simple_paths_among_read_sources':longest,
      'graph_limit':'At most6edges, no cycles; source subgraph only, not a legal applicability finding or proof of sequential model traversal.',
      'model_proposals_not_necessarily_executed':proposals,'actual_tool_observations':observations,'actual_navigation_events':model_choices,'actual_relation_scans':scan})
    print(case['id'],'read/cited',len(reads),len(cites),'stored edges',len(edges),'max edges',max((len(x)-1 for x in longest),default=0))
nav.close()
