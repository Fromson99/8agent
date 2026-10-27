"""Read-only post-selection source verification, no product or model calls."""
from common import *
import sqlite3,collections,gzip
def db(p):
    d=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
G=ROOT/read(DES/'baseline.json')['release']['data_path'];source=db(G/'store.sqlite');nav=db(G/'navigation/navigation.sqlite')
def origin(sid):
    row=nav.execute('select json from source where id=?',(sid,)).fetchone();return json.loads(row[0]) if row else None
def coord(v):
    if not v:return None
    a=v.get('article_coordinate') or {};did=a.get('doc_id',v.get('document_id'));node=a.get('node',v.get('unit_id'))
    return {'doc_id':did,'node':int(node)} if did and str(node).isdigit() else None
def uniq(items):return [json.loads(v) for v in sorted({json.dumps(v,sort_keys=True,separators=(',',':')) for v in items if v})]
def ht(v):return hashlib.sha256(v.encode()).hexdigest()
def cited(value):
    found=set()
    if isinstance(value,list):
        for v in value:found|=cited(v)
    elif isinstance(value,dict):
        if isinstance(value.get('source_ids'),list):found|={s for s in value['source_ids'] if isinstance(s,str)}
        for k,v in value.items():
            if k!='source_ids':found|=cited(v)
    return found
for case in read(DES/'cases.json'):
    P=RUN/case['id']
    if not (P/'result.json').exists():continue
    if (P/'audit.json').exists():continue
    r=read(P/'result.json');body=read(P/'response.json').get('body',{}) if (P/'response.json').exists() else {};answer=body.get('answer') or {}
    finalids=sorted(cited(answer));allowed=set(read(P/'request.json')['json']['document_ids']) if (P/'request.json').exists() else set()
    summary={'case_id':case['id'],'http_status':r.get('http_status'),'answer_status':body.get('answer_status') or body.get('status'),'error_code':body.get('error_code'),
      'final_source_ids':finalids,'final_coordinates':uniq(coord(origin(s)) for s in finalids),'unmapped_final':[s for s in finalids if not origin(s)],
      'read_evidence':[],'read_coordinates':[],'span_checks':[],'events':[],'state':[],'reference_availability':[],'provider_errors':[],'model_decisions':[],'legal_accuracy':'not_scored'}
    for rel in r.get('journal_paths',[]):
        j=db(ROOT/rel)
        for row in j.execute('select status,phase,state_revision,evidence_revision from run'):summary['state'].append(dict(row))
        for row in j.execute('select * from evidence_unit'):
            e=dict(row);spans=[dict(x) for x in j.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],))];v=origin(e['source_id']);valid=bool(spans)
            for span in spans:
                raw=source.execute('select text,source_artifact_sha256 from source_block where document_id=? and block_id=?',(e['document_id'],span['block_id'])).fetchone()
                valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and ht(raw['text'])==span['block_hash'] and raw['text'][span['start_cp']:span['end_cp']]==span['text'] and ht(span['text'])==span['span_hash']
            valid=valid and ht('\n'.join(x['text'] for x in spans))==e['text_hash']
            summary['span_checks'].append({'evidence_id':e['evidence_id'],'span_count':len(spans),'exact_original_match':bool(valid),'within_scope':e['document_id'] in allowed})
            summary['read_evidence'].append({'evidence_id':e['evidence_id'],'source_id':e['source_id'],'canonical':coord(v),'document':(v or {}).get('document_name'),'heading':(v or {}).get('heading'),'chars':sum(len(x['text']) for x in spans)})
        for row in j.execute('select seq,kind,payload_json from event order by seq'):
            if any(s in row['kind'] for s in ('FAIL','REJECT','ERROR','REPAIR','READ_CHOICE','LAW','STRUCTURE')):summary['events'].append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
        j.close()
    summary['read_coordinates']=uniq(e['canonical'] for e in summary['read_evidence'])
    for p in sorted((P/'raw').glob('call-*/response.json')):
        raw=read(p)
        if raw.get('error'):
            error=raw['error'];summary['provider_errors'].append({'call':p.parent.name,'code':error.get('code'),'message':error.get('message'),'metadata':error.get('metadata')})
        else:
            try:v=json.loads(raw['choices'][0]['message']['content'])
            except (ValueError,IndexError,KeyError,TypeError):continue
            summary['model_decisions'].append({'call':p.parent.name,'action':v.get('action') or v.get('next_action'),'reason':v.get('reason'),'target_id':v.get('target_id'),'targets':v.get('targets')})
    put(P/'audit.json',summary)
    print(case['id'],summary['http_status'],summary['answer_status'],'read',len(summary['read_coordinates']),'cited',len(summary['final_coordinates']),'provider429',sum(x['code']==429 for x in summary['provider_errors']),flush=True)
source.close();nav.close()
