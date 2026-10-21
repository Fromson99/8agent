"""Sequential post-run observations; no model or pipeline import."""
from pathlib import Path
from collections import Counter
import gzip, hashlib, json, sqlite3, sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance';O=A/'artifacts/run-001';arm,scenario,turn=sys.argv[1:];S=O/arm/scenario;C=S/turn
read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def connect(p):
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    db.execute('PRAGMA cache_size=-1024');db.execute('PRAGMA mmap_size=0');return db
def hashtext(s):return hashlib.sha256(s.encode()).hexdigest()

run=read(C/'result.json');body=read(C/'response.json').get('body',{})
calls=read(C/'calls.json') if (C/'calls.json').exists() else []
generations=read(C/'generations.json') if (C/'generations.json').exists() else []
rows=[]
for call in calls:
    g=next((g for g in generations if g['number']==call.get('generation')), {})
    detail={}
    if call.get('generation'):
        n=call['generation']
        with gzip.open(C/'canonical'/f'{n:03d}.json.gz','rt') as f:view=json.load(f)['view']
        out=C/'canonical'/f'{n:03d}-output.json.gz'
        if out.exists():
            with gzip.open(out,'rt') as f:value=json.load(f)
        else:value={}
        candidates={x.get('target'):x for x in view.get('read_candidates',[]) if isinstance(x,dict)}
        selections=value.get('selections',[])
        sources=view.get('sources',[])
        detail={'choice':value.get('choice',value.get('next_action')),
            'selected_read_targets':[{'target':x.get('target'),
                'coordinate':candidates.get(x.get('target'),{}).get('coordinate'),
                'missing_need':x.get('missing_need')} for x in selections],
            'structure_filter':value.get('structure_filter'),
            'missing_need':value.get('missing_need'),
            'read_candidates':list(candidates.values()),
            'source_card_count':len(sources) if isinstance(sources,list) else None,
            'unique_source_count':len({x.get('source_id') for x in sources if isinstance(x,dict) and x.get('source_id')}) if isinstance(sources,list) else None,
            'reference_group_count':len(view.get('groups',[]))}
    rows.append({**call,**detail,'input_card_counts':g.get('input_card_counts',{}),
        'source_labels':g.get('source_labels',[]),'decision':g.get('decision'),
        'reference_decisions':g.get('reference_decisions',[]),'accepted':g.get('accepted')})
put(C/'call-summary.json',rows)
answer=body.get('answer',{});(C/'answer.txt').write_text((answer.get('text','') if isinstance(answer,dict) else str(answer))+'\n')
release=read(A/'artifacts/design/baseline.json')['manifest'];G=R/release['data_path']
source=connect(G/'store.sqlite');nav=connect(G/'navigation/navigation.sqlite');coordinates={}
def coord(sid):
    if sid not in coordinates:
        row=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
        v=json.loads(row[0]) if row else {}
        coordinates[sid]={'doc_id':v['document_id'],'node':int(v['unit_id'])} if v.get('unit_id') is not None else None
    return coordinates[sid]
acquired=[];span_checks=[];events=[];journals=[];selected_source_ids=[]
for path in sorted((S/'runtime/legal-agent/runs').glob('*/'+body.get('run_id','NO_RUN')+'/journal.sqlite')):
    db=connect(path);journals.append(str(path.relative_to(R)))
    row=db.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:SELECT' ORDER BY version DESC LIMIT 1").fetchone()
    if row:selected_source_ids.extend(json.loads(row[0]).get('final_ids',[]))
    for e in db.execute('SELECT evidence_id,source_id,document_id,source_artifact_hash,text_hash FROM evidence_unit'):
        valid=True;texts=[];n=0
        for s in db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal',(e['evidence_id'],)):
            n+=1;texts.append(s['text'])
            raw=source.execute('SELECT text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?',(e['document_id'],s['block_id'])).fetchone()
            valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and hashtext(raw['text'])==s['block_hash'] and raw['text'][s['start_cp']:s['end_cp']]==s['text'] and hashtext(s['text'])==s['span_hash']
        valid=valid and n>0 and hashtext('\n'.join(texts))==e['text_hash']
        span_checks.append({'evidence_id':e['evidence_id'],'source_id':e['source_id'],'spans':n,'exact_original_match':bool(valid)})
        if coord(e['source_id']):acquired.append(coord(e['source_id']))
    for row in db.execute("SELECT seq,kind,payload_json FROM event WHERE kind LIKE '%REJECT%' OR kind LIKE '%REPAIR%' OR kind LIKE '%REENTRY%' OR kind IN ('UNIT_READ_CHOICE','INVESTIGATION_BOUNDED_STOP','INVESTIGATION_CHAIN_STEP','ACQUIRED_ORIGINALS_TO_ASSESS','ASSESSMENT_RESEARCH_DEFERRED_TO_USER') ORDER BY seq"):
        value=json.loads(row['payload_json']);events.append({'seq':row['seq'],'kind':row['kind'],'payload':value})
    db.close()
selected=[coord(sid) for sid in selected_source_ids if coord(sid)]
cited=[coord(sid) for claim in (answer.get('claims',[]) if isinstance(answer,dict) else []) for sid in claim.get('source_ids',[]) if coord(sid)]
scope=read(C/'request.json')['json']['document_ids']
corpus=nav.execute('SELECT COUNT(*) FROM source WHERE json_extract(json,\'$.unit_id\') IS NOT NULL AND json_extract(json,\'$.document_id\') IN ('+','.join('?' for _ in scope)+')',scope).fetchone()[0]
source.close();nav.close()
metrics=body.get('execution_stats');failures=[]
for line in (A/('artifacts/live-'+arm+'-'+scenario+'.log')).open():
    try:event=json.loads(line)
    except ValueError:continue
    if event.get('event')=='execution.metrics' and event.get('run_id')==body.get('run_id'):metrics=event.get('execution_stats')
    if event.get('event')=='request.error' and event.get('run_id')==body.get('run_id'):
        diagnostic=event.get('failure_diagnostics',{})
        failures.append({k:diagnostic.get(k) for k in ('error_code','error_type','error_message','stage')})
audit={'calls':rows,'journal_paths':journals,'span_checks':span_checks,'events':events,
    'canonical_sets':{'native_read':acquired,'selected':selected,'cited':cited},'corpus_total':corpus,
    'corpus_basis':'canonical structured source roots within the request public document scope',
    'execution_stats':metrics,'response_keys':list(body),'failures':failures,
    'selection_basis':'Committed SELECT final_ids, including delivered fallback originals. Not a claim of model adoption or legal correctness.',
    'stage_counts':dict(Counter(c['phase'] for c in calls)),
    'quality_certified':False,'golden_recall':None}
put(C/'audit.json',audit)
print(json.dumps({'calls':len(calls),'request_seconds':run.get('request_seconds'),
    'http_status':run.get('http_status'),'journal_count':len(journals),
    'span_checks':len(span_checks),'span_mismatches':sum(not x['exact_original_match'] for x in span_checks),
    'read_occurrences':len(acquired),'selected_occurrences':len(selected),'cited_occurrences':len(cited)},ensure_ascii=False))
