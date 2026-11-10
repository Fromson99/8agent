"""Count the new definition-priority events per question from the stored journals (read only)."""
import sys,glob,collections,json
from pathlib import Path
sys.path.insert(0,'/home/jin/8-AGENT/02_BACKEND')
from semantic_runtime.legal_agent.journal_storage import connect
KINDS=('DEFINITION_ENTRY_DEFERRED','DEFINITION_ENTRY_SCOPED','GUIDED_ANSWER_VECTOR_READS')
adr=Path(sys.argv[1]);out={}
for d in sorted((adr/'artifacts/public-live').glob('cm-*-candidate')):
    hits=collections.Counter();detail={}
    for db in glob.glob(str(d/'runtime/legal-agent/runs/*/*/journal.sqlite')):
        c=connect(db)
        for kind,payload in c.execute('select kind,payload_json from event'):
            s=payload if isinstance(payload,str) else (payload.decode() if isinstance(payload,bytes) else json.dumps(payload))
            for k in KINDS:
                if k==kind or k in s[:4000]:
                    hits[k]+=1;detail.setdefault(k,s[:300])
    out[d.name[:6]]={'counts':dict(hits),'sample':detail}
print({k:sum(1 for v in out.values() if v['counts'].get(k)) for k in KINDS})
print({k:[c for c,v in out.items() if v['counts'].get(k)] for k in KINDS})
json.dump(out,open(adr/'artifacts/definition-events.json','w'),ensure_ascii=False,indent=1)
