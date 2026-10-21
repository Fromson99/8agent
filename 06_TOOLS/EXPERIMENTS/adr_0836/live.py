"""One fixed first attempt per arm/known source packet; no repairs or retrieval."""
from pathlib import Path
import ast,hashlib,json,sqlite3,sys,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0836-comparison-owned-tools';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mode,number=sys.argv[1],int(sys.argv[2]);assert mode in ('baseline','connected') and number in (17,19,21)
freeze=read(D/'model-freeze.json');assert all(sha(R/n)==h for n,h in freeze['files'].items())
binding=read(D/'verification-binding.json');base=read(D/'baseline.json')['manifest'];C=R/(base['code_root'] if mode=='baseline' else binding['code_root'])
files=base['files'] if mode=='baseline' else binding['serving_files'];assert all(sha(C/n)==h for n,h in files.items())
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
import lawrag;lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from workflow.adapters.projection import prepare
from workflow.adapters.model import SYSTEM
from workflow.risk_team_compare_workflow import task_board as tb
p=R/freeze['source_root'];request=next((p/'raw').glob(f'call-{number:03d}-*/request.json'));original=read(request)
data=json.loads(original['messages'][1]['content'])['view']
# Recover exactly the original read spans, not new surrounding material.
journal=p/'runtime/workflows/0600b8d87c9fe231c08f280bc2530817/journal.sqlite'
c=sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
for source in data['sources']:
    expected=[x['text'] for x in source.pop('citation_options')]
    spans=[dict(r) for r in c.execute('select block_id,start_cp,end_cp,text from evidence_span where evidence_id=? order by ordinal',(source['evidence_id'],))]
    assert [s['text'] for s in spans]==expected
    source['spans']=spans;source['text']='\n'.join(expected)
c.close()
view,schema,expand,receipt=prepare('ITEMS',data,tb.REVIEW)
syntax=ast.parse((C/'02_BACKEND/workflow/risk_team_compare_workflow/task_board.py').read_text())
instructions=next(ast.literal_eval(n.value) for n in ast.walk(syntax) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='instructions' for t in n.targets))
system=SYSTEM+'\n'+instructions+'\n인용은 citation_options의 citation_id만 선택한다. 인용 원문과 서버 소유 필드는 시스템이 조립한다.'
O=A/f'artifacts/model/{mode}-{number}';assert not O.exists();O.mkdir(parents=True)
client=ExperimentClient(R,O/'raw',max_calls=1,max_output_tokens=6400,max_repairs=0)
result={'arm':mode,'source_call':number,'known_in_sample':True,'retrieval_changed':False,'code_root':str(C.relative_to(R)),'projection':receipt,'source_count':len(data['sources']),'schema_chars':len(json.dumps(schema,ensure_ascii=False)),'system_chars':len(system)}
start=time.monotonic()
try:
    raw=client.generate(system,{'output_schema':schema,'view':view},schema,phase='workflow-items')
    value=expand(raw)
    (O/'canonical-proposal.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    try:tb.checked(value,data['sources'],list(data['fields']),data['locators'])
    except ValueError as exc:result.update(accepted=False,error=str(exc))
    else:result['accepted']=True
except Exception as exc:
    result.update(accepted=False,error_type=type(exc).__name__,error=str(exc)[:500])
result.update(model_calls=client.calls,usage=client.usage,seconds=time.monotonic()-start)
(O/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('usage','projection')},ensure_ascii=False),flush=True)
