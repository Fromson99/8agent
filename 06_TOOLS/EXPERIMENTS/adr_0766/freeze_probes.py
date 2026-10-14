"""Freeze exact accepted public assessments from immutable archived journals."""
from pathlib import Path
import hashlib,json,sqlite3,tarfile,tempfile,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0766-rich-grounded-answer-stream';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0766/narrative';S=C/'revisions/rev-003/snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'public-probes.json').exists()
sys.path.insert(0,str(S/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
transport=LocalGemmaTransport(S,R)
cases=[]
selected=[('A','ADR-0761-scoped-title-public-qualification','integrated','H01'),('B','ADR-0761-scoped-title-public-qualification','integrated','R01'),('C','ADR-0762-main53-three-public-cases','main53','P01')]
for cid,adr,arm,case in selected:
    base=R/'04_EXPERIMENTS/ADR'/adr/'artifacts/run-001';archive=base/'raw.tar.gz'
    with tarfile.open(archive) as tar:
        members=[x for x in tar.getmembers() if x.name.startswith(arm+'/'+case+'/') and x.name.endswith('journal.sqlite')]
        assert len(members)==1
        raw=tar.extractfile(members[0]).read()
    with tempfile.NamedTemporaryFile(suffix='.sqlite') as temp:
        temp.write(raw);temp.flush();db=sqlite3.connect('file:'+temp.name+'?mode=ro',uri=True)
        assessed=db.execute("SELECT payload_json FROM event WHERE kind='ASSESSMENT_VALIDATED' ORDER BY seq DESC LIMIT 1").fetchone()
        assert assessed
        assessment=json.loads(assessed[0])['assessment']
        db.close()
    source_path=R/read(D/'baseline.json')['manifest']['data_path']/'navigation/navigation.sqlite'
    db=sqlite3.connect(source_path.resolve().as_uri()+'?mode=ro',uri=True)
    ids={r['source_id'] for c in assessment['claims'] for r in [c]+c.get('evidence',[])}
    sources=[]
    for ident in sorted(ids):
        source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(ident,)).fetchone()[0])
        source['source_id']=ident;sources.append(source)
    db.close()
    assert sources and all(s['document_id'] in transport.public_scope for s in sources)
    question=read(base/arm/case/'request.json')['question']
    cases.append({'case_id':cid,'question':question,'assessment':assessment,'sources':sources,
        'provenance':{'archive':str(archive.relative_to(R)),'archive_sha256':sha(archive),'member':members[0].name,'member_sha256':hashlib.sha256(raw).hexdigest(),'assessment_event_sha256':hashlib.sha256(assessed[0].encode()).hexdigest(),'source_run':adr+'/'+arm+'/'+case}})
put(D/'public-probes.json',{'scope':'public accepted source judgments, presentation-only replay','no_private_questions':True,'cases':cases})
put(D/'probe-freeze.json',{'candidate':str(S.relative_to(R)),'candidate_manifest_sha256':sha(C/'candidate.json'),'code':{str(p.relative_to(S)):sha(p) for p in (S/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py')},'dataset_sha256':sha(D/'public-probes.json'),'runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0766/run_probe.py'),'order':['A','B','C'],'repeats':1,'adaptive_reruns':False,'max_calls_per_case':1,'max_seconds_per_call':180,'provider_policy_sha256':sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')})
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates'][0].update(runner_path='06_TOOLS/EXPERIMENTS/adr_0766/run_probe.py',runner_sha256=sha(R/'06_TOOLS/EXPERIMENTS/adr_0766/run_probe.py'))
m['dataset'].update(frozen_source=str((D/'public-probes.json').relative_to(R)),sha256=sha(D/'public-probes.json'))
put(A/'실험/manifest.json',m)
print('Frozen public-only probes:',[c['case_id'] for c in cases])
