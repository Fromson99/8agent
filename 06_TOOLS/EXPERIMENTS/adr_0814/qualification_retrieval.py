"""Finite native retrieval/navigation contract census; never legal quality.

Read only the prospectively enumerated cases. Invoke identical public product
interfaces in both arms; the fixture adapter persists only literal source reads,
evidence and physical tool budget. It makes no retrieval or completion decision.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import argparse
import hashlib
import importlib
import json
import os
import resource
import sqlite3
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[3]
DESIGN=ROOT/'04_EXPERIMENTS/ADR/ADR-0814-evidence-completeness-qualification/artifacts/design'


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def position(did,node):
    return {'doc_id':did,'node':int(node)}


def load_native(code_root):
    sys.dont_write_bytecode=True
    os.environ.update(SOURCE_PROVIDER_PROJECT_ROOT=str(ROOT),LAWRAG_WORKSPACE_ROOT=str(ROOT),
                      LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
    sys.path[:0]=[str(code_root/'02_BACKEND'),str(code_root),str(ROOT/'02_BACKEND')]
    names={'sq':'structure_query','availability':'tool_availability','ur':'unit_reading',
           'source':'source_tools','errors':'errors'}
    native=NS(**{key:importlib.import_module('semantic_runtime.legal_agent.'+name) for key,name in names.items()})
    native.match=importlib.import_module('semantic_runtime.navigation_match')
    native.paths={}
    for module in [getattr(native,key) for key in names]+[native.match]:
        path=Path(module.__file__).resolve()
        if not path.is_relative_to(code_root):raise RuntimeError('product import escaped selected arm: '+str(path))
        native.paths[module.__name__]={'path':str(path),'sha256':sha(path.read_bytes())}
    return native


class ReadJournal:
    """Durable fixture-side physical tool adapter, not a simulated retrieval."""
    def __init__(self,path,limit):
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.executescript('''CREATE TABLE IF NOT EXISTS budget(used INTEGER,lim INTEGER);
            CREATE TABLE IF NOT EXISTS action_context(action_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,json TEXT);
            CREATE TABLE IF NOT EXISTS event(kind TEXT,json TEXT);
            CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY,json TEXT);''')
        if not self.db.execute('SELECT 1 FROM budget').fetchone():
            self.db.execute('INSERT INTO budget VALUES(0,?)',(limit,))
        elif self.budget()['tool_limit']!=limit:raise AssertionError('fixture budget changed on reopen')

    def budget(self):
        used,limit=self.db.execute('SELECT used,lim FROM budget').fetchone()
        return {'tool_used':used,'tool_limit':limit}

    def evidence(self,ident=None):
        if ident is not None:
            row=self.db.execute('SELECT json FROM evidence WHERE id=?',(ident,)).fetchone()
            return json.loads(row[0])
        return [json.loads(r[0]) for r in self.db.execute('SELECT json FROM evidence ORDER BY id')]

    def save_state(self,value):
        self.db.execute('INSERT OR REPLACE INTO checkpoint VALUES(1,?)',(encode(value),))

    def load_state(self):
        row=self.db.execute('SELECT json FROM checkpoint WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'count':0,'chars':0,'sequence':0}

    def event(self,kind,value):
        self.db.execute('INSERT INTO event VALUES(?,?)',(kind,encode(value)))
        if kind=='UNIT_READ_FAILED' and 'read_state' in value:self.save_state(value['read_state'])

    def record_observation(self,action,result,items,*,verify):
        for item in items:
            verify(item)
            self.db.execute('INSERT OR REPLACE INTO evidence VALUES(?,?)',(item['evidence_id'],encode(item)))

    def close(self):
        self.db.close()


def source_fixture(native,case,directory):
    n=case['structured_groups'];extra=case['source_only_groups'];embedded=case['attachment_mode']=='embedded'
    did='finite-policy' if embedded else 'finite-attachment'
    title='[별표 14의2] 합성 운영 기준';policy='합성 운영약정'
    names=native.match.SurfaceIndex();names.add(policy,'finite-policy')
    if not embedded:names.add(title,did)
    documents={'finite-policy':policy,did:policy if embedded else title}
    context={'finite-policy':{'document_title':policy,'document_role':'body'}}
    if not embedded:context[did]={'document_title':title,'document_role':'annex','folder_names':[policy]}
    matcher=NS(documents=documents,document_names=names,title_keys={native.match.norm(policy),native.match.norm(title)},
        structures=native.match.SurfaceIndex(),document_context=context,document_aliases={},
        units={},stored_coordinates={},sources={})
    raw=[];sources={}
    for i in range(n+extra):
        uid=str(i) if i<n else None;sid='canonical-group-'+str(i).zfill(3)
        text='합성 원문 '+str(i)+' — 독립 조건과 끝의 예외를 보존한다. 🙂'
        raw.append({'document_id':did,'block_id':str(i),'unit_id':uid,'text':text})
        if uid is not None:
            parent=None if i==0 else str(i-1) if case['hierarchy']=='chain' else '0'
            end=n if case['hierarchy']=='chain' or i==0 else i+1
            surface='별표 14의2' if embedded and i==0 else str(i+1)+'.'
            matcher.units[(did,uid)]={'surface':surface,'title':'구조 '+str(i),'parent':parent,
                'span':[i,end],'coordinate_scope':'annex','coordinate_binding':{'mode':'stored'}}
        matcher.sources[sid]={'document_id':did,'unit_id':uid}
        sources[sid]={'id':sid,'document_id':did,'unit_id':uid,'document_name':documents[did],
            'heading':'원문 그룹 '+str(i),'blocks':[{'block_id':str(i),'text':text}],
            'text_sha256':sha(text.encode())}
    artifact_hash=sha(encode(raw).encode())
    for row in raw:row['source_artifact_sha256']=artifact_hash
    for source in sources.values():source['source_artifact_sha256']=artifact_hash
    def members(document,uid):
        found=[]
        for sid,src in matcher.sources.items():
            current=src['unit_id'];seen=set()
            while src['document_id']==document and current is not None and current not in seen:
                if current==str(uid):found.append(sid);break
                seen.add(current);current=matcher.units.get((document,current),{}).get('parent')
        return sorted(found)
    matcher._unit_sources=members
    path=directory/'immutable-source.sqlite'
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT)')
    db.executemany('INSERT INTO source_block VALUES(:document_id,:block_id,:unit_id,:text,:source_artifact_sha256)',raw)
    db.commit();db.close()
    return NS(did=did,matcher=matcher,sources=sources,raw=tuple(deepcopy(raw)),path=path,
        original_sha256=sha(path.read_bytes()),question=policy+' 별표14의2',artifact_hash=artifact_hash)


def open_session(native,fixture,case,directory,deadline):
    db=sqlite3.connect('file:'+str(fixture.path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    def original(document,bid):
        row=db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(document,str(bid))).fetchone()
        if row is None:raise KeyError((document,bid))
        return dict(row)
    store=NS(db=db,source=original,sources=lambda did,bids:[original(did,b) for b in bids])
    scope=set() if case['access_budget']=='deny' else set(fixture.matcher.documents)
    repo=ReadJournal(directory/'read-journal.sqlite',case['tool_budget'])
    def remaining():
        left=deadline-time.monotonic()
        if left<=0:raise native.errors.DeadlineExceeded('finite family deadline')
        return left
    s=NS(matcher=fixture.matcher,tools=NS(sources=fixture.sources),store=store,scope=scope,repo=repo,
        profile={'max_read_chars':4096,'page_size':1},context=NS(request={'question':fixture.question},
        query={'generation_id':'finite-original-v1','scope':{'document_version_ids':sorted(scope)}},
        remaining=remaining,binding_hash=fixture.artifact_hash))
    s.source=NS(verify=lambda item:native.source.SourceSession.verify(s,item))
    s.handle=lambda kind,value:deepcopy(value)
    s._unit_read_checkpoint=lambda items,state:repo.save_state(state)
    def execute(action,action_id,actor):
        if actor!='SYSTEM_POLICY':raise AssertionError('unexpected actor')
        budget=repo.budget()
        if budget['tool_used']>=budget['tool_limit']:raise native.errors.BudgetExhausted('persistent request tool budget')
        target=action['args']['target'];sid=target['source_id'];source=s.tools.sources[sid]
        if target['document_id'] not in s.scope or source['document_id']!=target['document_id']:
            raise native.errors.ContractError('fixture tool denied source')
        index=action['args']['cursor'] or 0;part=target['read_segments'][index]
        raw=original(target['document_id'],part['block_id'])
        literal=raw['text'][part['start_cp']:part['end_cp']]
        span={**part,'text':literal,'block_hash':sha(raw['text'].encode()),'span_hash':sha(literal.encode())}
        origin={'source_id':sid,'document_id':target['document_id'],'unit_id':source['unit_id'],
            'generation_id':'finite-original-v1','source_artifact_hash':source['source_artifact_sha256'],
            'role':'body','temporal_status':'UNKNOWN','metadata':{'document_name':source['document_name']}}
        evidence=native.source.canonical_evidence(origin,[span]);s.source.verify(evidence)
        repo.db.execute('BEGIN')
        try:
            repo.db.execute('INSERT INTO action_context VALUES(?)',(action_id,))
            repo.db.execute('UPDATE budget SET used=used+1')
            repo.db.execute('INSERT OR REPLACE INTO evidence VALUES(?,?)',(evidence['evidence_id'],encode(evidence)))
            repo.db.commit()
        except Exception:repo.db.rollback();raise
        next_cursor=index+1 if index+1<len(target['read_segments']) else None
        return {'status':'OK','items':[{'evidence':evidence['evidence_id']}],
            'evidence_ids':[evidence['evidence_id']],'budget':{'new_read_chars':len(literal)},
            'coverage':{'complete':next_cursor is None},'next_cursor':next_cursor}
    s.execute=execute
    s._qualification_state=native.ur.read_state(s,repo.load_state())
    return s


def close_session(s):
    s.repo.save_state(s._qualification_state);s.repo.close();s.store.db.close()


def identity(pair):
    # The baseline predates read_identity, but the READ_ARTICLES identity is the
    # same public contract. Copy declared fields without inventing source IDs.
    return {k:pair[k] for k in ('document_id','source_id','unit_id','source_partition') if k in pair}


def read_pass(native,s,pairs,*,stop_after=None):
    results=[];failure=None
    for pair in pairs:
        plan,reason=native.availability.article_plan(s,identity(pair))
        if reason:raise native.errors.ContractError('native read plan unavailable: '+reason)
        hit,offer=plan
        try:result=native.ur.read(s,hit,offer,action_state=s._qualification_state)
        except native.errors.BudgetExhausted as error:
            failure={'type':type(error).__name__,'message':str(error),
                'read_progress':deepcopy(getattr(error,'read_progress',None))};break
        results.append(result)
        if stop_after is not None and len(results)==stop_after:break
    return results,failure


def retrieval_case(native,case,directory,deadline):
    start=time.monotonic();fixture=source_fixture(native,case,directory);s=None
    denied=case['access_budget']=='deny'
    result={'case_id':case['case_id'],'passed':False,'checks':{},
        'available':[] if denied else [position(fixture.did,i) for i in range(case['structured_groups'])],
        'presented':[],'executed_retrieval':False,'skip_reason':None,'tool_calls':0,'stub_model_calls':0}
    checks=result['checks']
    try:
        s=open_session(native,fixture,case,directory,deadline)
        result['executed_retrieval']=True
        route=native.sq.resolve(fixture.question,s.matcher,s.scope)
        result['native_route']={'status':route['status'],'reason':route.get('reason'),'failure':route.get('failure')}
        if denied:
            checks['denied_no_locations']=route['status']=='MISS' and not route.get('pairs') and not route.get('source_ids')
            checks['denied_no_reads']=s.repo.budget()['tool_used']==0 and not s.repo.evidence()
        else:
            checks['all_original_groups_located']=(route['status']=='MATCH' and set(route['source_ids'])==set(fixture.sources))
            if not checks['all_original_groups_located']:
                result['error']={'type':'NativeCapabilityFailure','message':'native route did not locate the complete declared attachment'}
                return result
            pairs=route['pairs'];checks['all_read_identities_bound']=all('source_id' in p for p in pairs)
            if not checks['all_read_identities_bound']:
                result['error']={'type':'NativeCapabilityFailure','message':'native route did not expose canonical read identities'}
                return result
            checks['canonical_groups_not_duplicated']=len(pairs)==len({p['source_id'] for p in pairs})==case['total_groups']
            expected={(r['document_id'],r['block_id']):r for r in fixture.raw}
            complete=case['access_budget']=='allow_complete'
            first,first_failure=read_pass(native,s,pairs,stop_after=case['interrupt_after_groups'] if complete else None)
            before=s.repo.budget();saved_state=deepcopy(s._qualification_state)
            checks['first_returned_groups_complete']=all(r['complete'] for r in first)
            checks['first_native_count_matches_physical_budget']=saved_state['count']==before['tool_used']
            close_session(s);s=None
            s=open_session(native,fixture,case,directory,deadline)
            checks['restart_preserves_budget_and_state']=s.repo.budget()==before and s._qualification_state==saved_state
            resumed,resume_failure=read_pass(native,s,pairs)
            after=s.repo.budget();all_evidence=s.repo.evidence()
            spans=[(e,span) for e in all_evidence for span in e['spans']]
            actual={(e['document_id'],str(span['block_id'])) for e,span in spans}
            checks['exact_original_spans']=all(
                (e['document_id'],str(span['block_id'])) in expected
                and span['start_cp']==0 and span['end_cp']==len(expected[(e['document_id'],str(span['block_id']))]['text'])
                and span['text']==expected[(e['document_id'],str(span['block_id']))]['text']
                and e['source_artifact_hash']==fixture.artifact_hash for e,span in spans)
            checks['no_duplicate_original_reads']=len(spans)==len(actual)==after['tool_used']
            checks['tool_budget_preserved']=after['tool_limit']==case['tool_budget'] and after['tool_used']<=after['tool_limit']
            if complete:
                checks['complete_exact_union']=actual==set(expected) and len(resumed)==len(pairs) and all(r['complete'] for r in resumed)
                checks['complete_no_failure']=first_failure is None and resume_failure is None
                checks['resume_reads_only_missing']=after['tool_used']-before['tool_used']==case['total_groups']-case['interrupt_after_groups']
            else:
                checks['partial_never_complete']=actual<set(expected) and first_failure is not None and resume_failure is not None
                checks['incomplete_progress_preserved']=bool(first_failure and first_failure['read_progress']
                    and resume_failure and resume_failure['read_progress'])
                checks['budget_consumed_exactly']=after['tool_used']==case['tool_budget']
                checks['exhausted_resume_no_new_reads']=after==before
            result['native_read_failure']=resume_failure
            result['original_blocks']={'expected':len(expected),'read':len(actual),
                'expected_sha256':sha(encode(list(fixture.raw)).encode()),
                'read_block_ids':sorted((b for _,b in actual),key=int)}
            result['presented']=[position(fixture.did,expected[key]['unit_id']) for key in sorted(actual)
                if expected[key]['unit_id'] is not None]
            final_state=deepcopy(s._qualification_state);close_session(s);s=None
            s=open_session(native,fixture,case,directory,deadline)
            checks['second_restart_preserves_budget_and_state']=s.repo.budget()==after and s._qualification_state==final_state
            repeated,repeated_failure=read_pass(native,s,pairs)
            checks['repeat_zero_new_reads']=s.repo.budget()==after
            checks['repeat_same_completion']=(all(r['complete'] for r in repeated) and len(repeated)==len(pairs) and repeated_failure is None
                if complete else repeated_failure is not None)
        checks['original_fixture_immutable']=sha(fixture.path.read_bytes())==fixture.original_sha256
        result['passed']=all(checks.values())
    except Exception as error:
        result['error']={'type':type(error).__name__,'message':str(error)}
        if not result['executed_retrieval']:
            result['skip_reason']='Fixture failed before native retrieval: '+str(error)
    finally:
        if s is not None:
            result['tool_calls']=s.repo.budget()['tool_used'];close_session(s)
        result['elapsed_seconds']=time.monotonic()-start
    return result


def navigation_case(native,case):
    start=time.monotonic();did='finite-definition-document';name='합성 정의규정';term='합성산정값'
    count=case['definitions'];scope={did} if case['access'] else set()
    question=(name+'에서 ' if case['named_document'] else '')+"'"+term+"'의 정의 위치"
    units={(did,str(i)):{'surface':'제'+str(i+1)+'조','coordinate_key':'body:제'+str(i+1)+'조'} for i in range(count)}
    definitions={str(i):{'id':str(i),'key':term,'document_id':did,'unit_id':str(i),
        'source_id':'source-'+str(i),'scope_status':'UNRESOLVED'} for i in range(count)}
    matcher=NS(documents={did:name},units=units,tools=NS(terms={'term':{'label':term}},definitions=definitions))
    matched={'documents':[{'id':did,'name':name}] if case['named_document'] else [],
        'structures':[],'terms':[{'id':'term','question_spans':[{'text':term}]}]}
    result={'case_id':case['case_id'],'passed':False,'checks':{},
        'available':[position(did,i) for i in range(count)] if case['access'] else [],
        'presented':[],'executed_retrieval':False,'skip_reason':None,'tool_calls':0,'stub_model_calls':0}
    try:
        result['executed_retrieval']=True
        hints=native.sq.navigation_context(question,matcher,scope,matches=matched)
        rows=[(r['document_id'],str(r['unit_id'])) for r in hints['definitions']]
        bound=all(d in scope and (d,u) in units for d,u in rows)
        if bound:result['presented']=[position(d,u) for d,u in sorted(set(rows),key=lambda x:int(x[1]))]
        result['checks']={'all_allowed_positions_preserved':result['presented']==result['available'],
            'scope_and_structure_bound':bound,'no_duplicate_positions':len(rows)==len(set(rows)),
            'hint_not_evidence':hints['navigation_hint_only'] is True and hints['citation_eligible'] is False,
            'no_false_document':all(d['document_id'] in scope for d in hints['documents'])}
        result['hint_counts']={k:len(hints[k]) for k in ('documents','structures','terms','definitions')}
        result['native_hint_sha256']=sha(encode(hints).encode())
        result['passed']=all(result['checks'].values())
    except Exception as error:result['error']={'type':type(error).__name__,'message':str(error)}
    result['elapsed_seconds']=time.monotonic()-start
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--code-root',type=Path,required=True)
    parser.add_argument('--arm',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    existing=[args.output_dir/(family+'.json') for family in ('retrieval','navigation')
              if (args.output_dir/(family+'.json')).exists()]
    if existing:
        raise RuntimeError('refusing to replace qualification results: '+', '.join(map(str,existing)))
    native=load_native(args.code_root.resolve());args.output_dir.mkdir(parents=True,exist_ok=True)
    for family,expected_count in [('retrieval',60),('navigation',16)]:
        started=time.monotonic();path=DESIGN/(family+'-cases.json');declaration=json.loads(path.read_text())
        cases=declaration['cases']
        if len(cases)!=expected_count or len({c['case_id'] for c in cases})!=expected_count:
            raise RuntimeError('frozen finite case inventory mismatch')
        results=[]
        with tempfile.TemporaryDirectory(prefix='adr0814-'+family+'-') as temp:
            for case in cases:
                directory=Path(temp)/case['case_id'];directory.mkdir()
                case_started=time.monotonic()
                try:
                    result=(retrieval_case(native,case,directory,started+180) if family=='retrieval'
                            else navigation_case(native,case))
                except Exception as error:
                    result={'case_id':case['case_id'],'passed':False,'checks':{},'available':[],
                        'presented':[],'executed_retrieval':False,
                        'skip_reason':'Fixture failed before native retrieval: '+str(error),
                        'elapsed_seconds':time.monotonic()-case_started,'tool_calls':0,'stub_model_calls':0,
                        'error':{'type':type(error).__name__,'message':str(error),'owner':'fixture_or_runner'}}
                results.append(result)
        output={'family':family,'arm':args.arm,'results':results,'elapsed_seconds':time.monotonic()-started,
            'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'real_model_calls':0,
            'case_inventory_sha256':sha(path.read_bytes()),'selected_modules':native.paths,
            'evaluation_scope':'finite synthetic software contract census; no legal holdout or legal quality claim',
            'presented_semantics':'retrieval: exact native reader output spans; navigation: native first-planner location hints; neither implies model adoption'}
        target=args.output_dir/(family+'.json')
        with target.open('x') as handle:
            handle.write(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'family':family,'passed':sum(r['passed'] for r in results),'total':len(results),'output':str(target)}))


if __name__=='__main__':main()
