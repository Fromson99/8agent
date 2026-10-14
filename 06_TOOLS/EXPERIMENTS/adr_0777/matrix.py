"""Prospectively enumerated syntax/completion and durable-state contract audit."""
from pathlib import Path
from contextlib import contextmanager
import copy,hashlib,json,sqlite3,sys,tempfile

def cases():
    values=[None,True,123,-99,'제1조 1,000원/1.5%',{'facts':[1,2]}]
    raw=[]
    for value in values:
        text=json.dumps(value,ensure_ascii=False)
        raw += [(text,True),('{"k":'+text+',"k":'+text+'}',False),
                ('{"k":'+text+',"k":{"different":true}}',False)]
    raw += [(x,False) for x in ('{"n":NaN}','{"n":Infinity}','{"n":-Infinity}',
        '{"n":1e10000}','{"unfinished":','{"n":1} extra','{"n":,}')]
    result=[]
    for layers in range(4):
        for text,valid in raw:
            for depth in range(layers):text='{"경로/a~b":['+text+']}'
            for finish in ('stop','length','content_filter','refusal'):
                category=(None if valid else 'OUTPUT_JSON_INVALID') if finish=='stop' else (
                    'OUTPUT_INCOMPLETE' if finish=='length' else 'OUTPUT_REFUSED')
                result.append({'id':f'json-{len(result)+1:03}','raw':text,'finish':finish,
                    'accepted':valid and finish=='stop','category':category,
                    'repairable':finish in ('stop','length')})
    assert len(result)==400
    return result

STATE_CASES=['normal_live','normal_restart','repair_live','repair_restart',
 'exhaust_live','exhaust_restart','unknown_first','unknown_correction','streamed_resume','tampered']

def run(code,out):
    sys.path[:0]=[str(code/'02_BACKEND')];sys.dont_write_bytecode=True
    from semantic_runtime.legal_agent.model_contract import structured_value
    from semantic_runtime.contracts import digest
    try:from semantic_runtime.legal_agent import output_contract as oc
    except ImportError:oc=None
    rows=[]
    for c in cases():
        body={'choices':[{'finish_reason':c['finish'],'message':{'content':c['raw']}}]};before=copy.deepcopy(body)
        value=None;error=None
        try:value=structured_value(body)
        except Exception as exc:error=exc
        acceptance=(error is None)==c['accepted']
        classification=(error is None and c['category'] is None) or (
            error is not None and oc is not None and oc.diagnostics(error)['category']==c['category']
            and oc.diagnostics(error)['repairable']==c['repairable'])
        preserved=not c['accepted'] or error is None and value==json.loads(c['raw'])
        rows.append({'id':c['id'],'accepted':error is None,'acceptance_correct':acceptance,
            'classification_correct':bool(classification),'input_preserved':body==before,
            'value_preserved':preserved,'contract_correct':acceptance and bool(classification) and body==before and preserved})
    class Repo:
        binding={'principal':'synthetic-auditor','source_generation':'synthetic-fixed'}
        def __init__(self,path):
            self.db=sqlite3.connect(path)
            self.db.execute('CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash)')
        @contextmanager
        def transaction(self):
            with self.db:yield
        def event(self,kind,value):self.db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',
            (kind,json.dumps(value),digest(value)))
    schema={'type':'object','required':['permit'],'additionalProperties':False,'properties':{'permit':{'const':True}}}
    for name in STATE_CASES:
        if oc is None:
            rows.append({'id':name,'contract_correct':False,'reason':'persistent correction contract absent'});continue
        with tempfile.TemporaryDirectory(prefix='schema-qualification-') as tmp:
            path=Path(tmp)/'journal.sqlite';repo=Repo(path);sent=[];published=[]
            data={'original_request':'synthetic','evidence':['immutable-source']}
            j=oc.DecisionJournal(repo,'qualified-decision',data,schema)
            reject=oc.OutputContractError('invalid proposal',[oc.issue('SCHEMA_CONST')])
            def invoke(payload,attempt):
                assert payload['evidence']==data['evidence'];sent.append(attempt)
                return {'permit': name.startswith('normal') or name.startswith('repair') and attempt==1}
            def decide():return oc.bounded_decision(repo,'qualified-decision',data,schema,invoke,
                lambda v:oc.validate_shape(v,schema),can_repair=lambda:name!='streamed_resume')
            if name.endswith('restart') and not name.startswith('normal'):
                j.reserve(0);sent.append(0);j.reject(0,reject,{'permit':False});repo.db.close();repo=Repo(path)
            if name in ('unknown_first','unknown_correction'):
                j.reserve(0);sent.append(0)
                if name=='unknown_correction':j.reject(0,reject,{'permit':False});j.reserve(1);sent.append(1)
                repo.db.close();repo=Repo(path)
            if name=='tampered':
                j.reserve(0);j.accept(0,{'permit':True})
                with repo.transaction():repo.db.execute("UPDATE event SET payload_hash='changed' WHERE seq=2")
            try:published.append(decide())
            except Exception:pass
            if name in ('normal_restart','streamed_resume'):
                repo.db.close();repo=Repo(path)
                try:
                    value=oc.bounded_decision(repo,'qualified-decision',data,schema,
                        lambda *_:sent.append('unexpected') or {'permit':True},lambda v:oc.validate_shape(v,schema))
                    if name=='normal_restart':assert value==published[0]
                    else:published.append(value)
                except Exception:
                    if name=='normal_restart':published=[]
            expected=1 if name.startswith('normal') or name in ('unknown_first','streamed_resume') else 0 if name=='tampered' else 2
            correct=(len(sent)==expected and bool(published)==name.startswith(('normal','repair'))
                and 'unexpected' not in sent)
            rows.append({'id':name,'sends':sent,'published':bool(published),'contract_correct':correct})
            repo.db.close()
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'cases':len(rows),'correct':sum(x['contract_correct'] for x in rows)}))

if __name__=='__main__':run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]))
