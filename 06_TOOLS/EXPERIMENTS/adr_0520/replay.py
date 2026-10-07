"""Frozen historical discovery receipts -> rebuilt references; no gold or model input."""
import hashlib,json,sqlite3,time,sys
from pathlib import Path
from bootstrap import R,A,C,pin
P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
def read(p):return json.loads(p.read_text())
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()
def prepare():
    pin();prod=read(A/'product-cases.json')
    inputs={};cases=[];kinds={'fulltext','document_fulltext','exact_law_coordinate','ambiguous_coordinate_candidate'}
    for c in prod['cases']:
        cid=c['case_id'];p=P/'artifacts/run-001'/cid/'result.json';row=read(p);inputs[str(p.relative_to(R))]=sha(p)
        entries=[]
        for sid in row['selected_for_read']:
            discovery=[r for r in row['routes'].get(sid,[]) if r['kind'] in kinds]
            if discovery:entries.append({'source_id':sid,'receipts':discovery})
        cases.append({'case_id':cid,'roots':entries,'historical_raw':str(p.relative_to(R))})
    source=R/prod['generation']/'navigation/navigation.sqlite'
    expected=read(source.with_name('manifest.json'))['index_sha256'];actual=sha(source)
    assert expected==actual
    from semantic_runtime.term_references import load_reference_inputs
    aliases,delegations,reference_inputs=load_reference_inputs()
    write(A/'artifacts/reference-inputs.json',{'aliases':aliases,'delegations':delegations,'hashes':reference_inputs})
    inputs[str((A/'artifacts/reference-inputs.json').relative_to(R))]=sha(A/'artifacts/reference-inputs.json')
    files=list(Path(__file__).parent.glob('*.py'))
    for f in files:inputs[str(f.relative_to(R))]=sha(f)
    write(A/'artifacts/replay-freeze.json',{'source_db':str(source.relative_to(R)),'source_sha256':actual,
        'source_manifest_sha256':sha(source.with_name('manifest.json')),'inputs':inputs,'cases':cases,
        'policy':'recursive-scoped-db-relations-v2','budget':{'max_states':10000,'max_seconds':30},
        'gold_visible_to_product':False,'root_rule':'Historical selected_for_read AND independent direct discovery receipt; one root per source; all original discovery receipts retained. No reference-only selected candidate becomes a root.',
        'candidate_revision':read(C/'candidate.json')['revisions'][-1]})
    print('frozen',len(cases),'cases',sum(len(c['roots']) for c in cases),'roots',flush=True)
def rebuild(f):
    target=A/'artifacts/reference-rebuild.sqlite'
    assert not target.exists(),'do not overwrite a completed or partial rebuild'
    db=sqlite3.connect(target)
    old=sqlite3.connect('file:'+str(R/f['source_db'])+'?mode=ro',uri=True)
    for table in ('source','source_unit_map','document_frame'):
        schema=old.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()[0]
        db.execute(schema)
        cursor=old.execute('SELECT * FROM '+table);count=0
        while rows:=cursor.fetchmany(5000):
            db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?'*len(rows[0]))+')',rows);count+=len(rows)
        db.commit();print('copied',table,count,flush=True)
    db.executescript('CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT); CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));')
    from semantic_runtime.term_references import compile_references
    refs=read(A/'artifacts/reference-inputs.json');started=time.monotonic()
    counts=compile_references(db,refs['aliases'],refs['delegations']);db.commit();db.close();old.close()
    write(A/'artifacts/rebuild-receipt.json',{'source':f['source_db'],'source_sha256':f['source_sha256'],
        'path':str(target.relative_to(R)),'sha256':sha(target),'counts':counts,'seconds':time.monotonic()-started,
        'schema_version':'reference-scope-v1','serving_generation':False,'canonical_original_db_unchanged':True})
    print('rebuilt',counts,flush=True)
def run(f):
    from semantic_runtime.reference_exploration import ReferenceNavigator
    prod=read(A/'product-cases.json');receipt=read(A/'artifacts/rebuild-receipt.json');db=sqlite3.connect('file:'+str(R/receipt['path'])+'?mode=ro',uri=True)
    assert sha(R/receipt['path'])==receipt['sha256']
    sources={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
    nav=ReferenceNavigator(db,sources,prod['public_scope_document_ids'],receipt['sha256']);results={}
    for case in f['cases']:
        cid=case['case_id'];path=A/'artifacts/run-001'/cid/'result.json';assert not path.exists()
        roots=[]
        for r in case['roots']:
            query=next((v.get('query') or v.get('locator') for v in r['receipts'] if v.get('query') or v.get('locator')),cid+' historical coordinate search')
            root=nav.root(r['source_id'],query=query,reason='Frozen historical independent discovery and read selection')
            root['discovery_receipts']=r['receipts'];roots.append(root)
        result=nav.walk(roots,**f['budget'])
        # Full source bytes remain available separately; graph extents are never widened.
        packet=A/'artifacts/run-001'/cid/'source-packet.json'
        write(packet,{'model_delivered':False,'sources':[sources[sid] for sid in result['source_ids']]})
        result.update(case_id=cid,source_packet=str(packet.relative_to(R)),source_packet_sha256=sha(packet),
            source_chars=sum(len(b['text']) for sid in result['source_ids'] for b in sources[sid]['blocks']),
            physical_model_calls=0,actual_model_presented=0,semantic_answer_quality_measured=False,
            historical_raw=case['historical_raw'])
        write(path,result);results[cid]=str(path.relative_to(R));print(cid,result['status'],'roots',len(roots),'sources',len(result['source_ids']),'states',len(result['states']),'seconds',round(result['seconds'],2),flush=True)
    write(A/'artifacts/run-001/results.json',{'cases':results,'model_calls':0,'policy':f['policy']})
def main():
    if sys.argv[1:] == ['prepare']:return prepare()
    pin();f=read(A/'artifacts/replay-freeze.json')
    for path,expected in f['inputs'].items():assert sha(R/path)==expected,path
    if sys.argv[1:] == ['rebuild']:rebuild(f)
    elif sys.argv[1:] == ['run']:run(f)
    else:raise SystemExit('prepare | rebuild | run')
if __name__=='__main__':main()
