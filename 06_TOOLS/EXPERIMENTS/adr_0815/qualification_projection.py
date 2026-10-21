"""Reserved ADR0814 finite source/provenance census; never call a real model.

The fixture is a pre-read source inventory and pre-committed child export, not a
retrieval execution or an assertion of legal correctness. Only public product
consumers run. No product function is patched. Run only after root freeze.
"""
from collections import Counter
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace as NS
import argparse
import hashlib
import json
import resource
import sqlite3
import sys
import time
from jsonschema.exceptions import ValidationError

ROOT=Path(__file__).resolve().parents[3]
DESIGN=ROOT/'04_EXPERIMENTS/ADR/ADR-0815-complete-contract-retest/artifacts/design'
DAY='2028-03-17'
UNIT='모의 조건 λ🙂와 결합문자 e\u0301. 따옴표 "원문" 및 탭\t; 줄끝\r\n'
TAIL='최종 예외: Ω-말단 대상만 제외한다.\n'
SCHEMA={'type':'object','properties':{'citations':{'type':'array','items':{'type':'object',
    'properties':{'evidence':{'type':'string'},'quote':{'type':'string'}},
    'required':['evidence','quote'],'additionalProperties':False}}},'required':['citations'],'additionalProperties':False}


def read(p):return json.loads(Path(p).read_text())
def put(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(v):return hashlib.sha256(v.encode()).hexdigest()
def digest(v):return sha(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')))
def record(checks,name,condition,**details):checks.append({'name':name,'passed':bool(condition),**details})


def load(code):
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND')]
    names={'p':'workflow.presentation','projection':'workflow.adapters.projection',
        'basis':'workflow.risk_team_compare_workflow.basis','compare':'workflow.risk_team_compare_workflow.compare',
        'contracts':'workflow.risk_team_compare_workflow.contracts','repo':'workflow.repository',
        'workflow':'workflow.contracts','exports':'semantic_runtime.workflow_evidence',
        'bridge':'semantic_runtime.workflow_bridge','source':'semantic_runtime.legal_agent.source_tools',
        'work':'semantic_runtime.legal_agent.repository','context':'semantic_runtime.legal_agent.context',
        'completion':'semantic_runtime.legal_agent.completion_contracts','errors':'semantic_runtime.legal_agent.errors'}
    modules={k:import_module(v) for k,v in names.items()}
    for key,m in modules.items():
        if not Path(m.__file__).resolve().is_relative_to(code):raise RuntimeError('selected runtime escaped code root: '+key)
    return NS(**modules)


class Services:
    __module__='semantic_runtime.workflow_bridge'
    def __init__(self,profile):self.profile=deepcopy(profile)


def make_source(m,sid,did,side,blocks,*,verified=True,artifact_hash=None):
    spans=[{'block_id':bid,'start_cp':0,'end_cp':len(text),'text':text,
        'block_hash':m.work.text_hash(text),'span_hash':m.work.text_hash(text)} for bid,text in blocks]
    origin={'source_id':sid,'document_id':did,'unit_id':'unit-'+sid,
        'generation_id':'adr0814-fixed-synthetic','source_artifact_hash':artifact_hash or digest(blocks),
        'role':'normative','temporal_status':'unknown',
        'metadata':{'document_name':did,'heading':'모의 조항','read_location':'모의 조항'}}
    e=m.source.canonical_evidence(origin,spans)
    return {**e,'side':side,'text':'\n'.join(t for _,t in blocks),'citation_names':[did],
        'source_complete':True,'version_verified':verified}


class SourceInventory:
    """Fixed original supplier; delegates whole-span splitting to selected code."""
    def __init__(self,m,values,services):
        self.m=m;self.values={e['evidence_id']:deepcopy(e) for e in values};self.receipts=[]
        self.services=services;self.originals={}
        for e in values:
            for span in e['spans']:
                self.originals[(e['source_id'],span['block_id'])]=deepcopy(span)
        native={}
        for e in values:
            source=native.setdefault(e['source_id'],{'id':e['source_id'],'document_id':e['document_id'],'blocks':[]})
            for span in e['spans']:
                block={'block_id':span['block_id'],'text':span['text']}
                if block not in source['blocks']:source['blocks'].append(block)
        self.session=NS(verify=self.verify,tools=NS(sources=native),repo=NS(record_observation=self.record))
    def evidence(self):return deepcopy(list(self.values.values()))
    def verify(self,e):
        if self.m.source.canonical_evidence(e,e['spans'])['evidence_id']!=e['evidence_id']:raise ValueError('fixture canonical source ID changed')
        for s in e['spans']:
            original=self.originals[(e['source_id'],s['block_id'])]
            if not 0<=s['start_cp']<s['end_cp']<=len(original['text']):raise ValueError('fixture span escaped original')
            if s['text']!=original['text'][s['start_cp']:s['end_cp']]:raise ValueError('fixture literal original changed')
            if s['span_hash']!=self.m.work.text_hash(s['text']) or s['block_hash']!=original['block_hash']:raise ValueError('fixture source hash changed')
    def record(self,action,result,items,*,verify):
        for e in items:
            verify(e)
            origin=next(v for v in self.values.values() if v['source_id']==e['source_id'])
            self.values[e['evidence_id']]={**e,'side':origin['side'],'version_verified':origin['version_verified'],
                'citation_names':origin['citation_names'],'source_complete':True,'text':'\n'.join(s['text'] for s in e['spans'])}
        self.receipts.append({'action':deepcopy(action),'result':deepcopy(result),'ids':[e['evidence_id'] for e in items]})
    def split_evidence(self,e,max_chars):return self.m.bridge.SourcePort.split_evidence(self,e,max_chars)


class Parent:
    """Actual native budget journal and workflow checkpoint repository."""
    def __init__(self,m,path,profile,values,issues):
        self.m=m;self.path=path;self.services=Services(profile);self.inventory=SourceInventory(m,values,self.services)
        self.request={'workflow_id':'risk_team_compare_workflow','question':'모의 원문의 전체 조건과 마지막 예외를 쟁점별로 확인한다.',
            'as_of':DAY,'use_llm':True}
        self.binding={'generation_id':'adr0814-fixed-synthetic','export_allowed':False,'fixture_hash':digest(values)}
        self.context=m.context.RequestContext.create({'id':'qualification','question':self.request['question']},
            self.request,self.binding,profile['wall_seconds'],digest([values,issues])[:32])
        self.profile=profile;self.open()
        self.state=self.repo.state()['checkpoint']
        self.state.update(stage='BASIS',scope={'issues':deepcopy(issues),'missing_user_facts':[]},
            gaps=[],rag_results={},context_evidence=[e['evidence_id'] for e in values])
        self.repo.save(self.state)
    def open(self):
        self.work=self.m.work.WorkRepository(self.path,self.context,self.profile)
        self.repo=self.m.repo.Repository(self.work,self.request,self.binding)
        self.ctx=NS(request=self.request,context=self.context,repo=self.repo,
            rag=NS(port=self.inventory,evidence=self.inventory.evidence),model=NS(services=self.services))
    def reopen(self):
        self.work.close();self.open();self.state=self.repo.state()['checkpoint']
    def close(self):self.work.close()


def coordinates(e):
    return [{'source_id':e['source_id'],'document_id':e['document_id'],'block_id':s['block_id'],
        'start_cp':s['start_cp'],'end_cp':s['end_cp'],'text_sha256':sha(s['text'])} for s in e['spans']]


def projection_case(m,case,path,profile,result):
    checks=result['checks'];text=UNIT*case['unit_repetitions']+TAIL
    if sha(text)!=case['text_sha256']:raise ValueError('frozen source generator hash mismatch')
    values=[];source_blocks=[[(f'block-{origin}-{n}',text) for n in range(case['spans_per_origin'])] for origin in range(2)]
    shared_hash=digest([b for blocks in source_blocks for b in blocks])
    for origin in range(2):
        sid='shared-origin' if case['origins']=='shared' else 'distinct-origin-'+str(origin)
        did='shared-document' if case['origins']=='shared' else 'distinct-document-'+str(origin)
        blocks=source_blocks[origin]
        values.append(make_source(m,sid,did,'internal',blocks,artifact_hash=shared_hash if case['origins']=='shared' else None))
    before=deepcopy(values);available=[c for e in values for c in coordinates(e)]
    parent=Parent(m,path/'parent.sqlite',profile,values,[{'id':'exact-original-93','label':'전체 원문','numeric':False}])
    packets=[];failure=None;presented=[];wire_sizes=[]
    result['available']=available;result['presented']=presented
    try:
        try:packets=m.p.packets(parent.ctx,parent.state,'FIXED_ORIGINALS')
        except (m.workflow.WorkflowError,m.errors.BudgetExhausted) as exc:
            failure={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}
        record(checks,'original_inventory_unchanged',values==before)
        if case['budget']=='fits':record(checks,'whole_dependency_fits',failure is None and len(packets)==1 and packets[0][0]['packet']['dependency_closure_complete'])
        else:record(checks,'overflow_is_explicit',failure is not None or bool(packets) and all(not d['packet']['dependency_closure_complete'] for d,_ in packets))
        whole=[];expanded=[];counts=[];catalogues=[]
        for data,es in packets:
            presented.extend(c for e in es for c in coordinates(e))
            view,wire,expand,receipt=m.projection.prepare('FIXED_ORIGINALS',data,SCHEMA)
            wire_sizes.append(m.p.size(view));catalogues.append(receipt['catalogue_hash'])
            wanted=[];chosen=[]
            for source in view['sources']:
                original=next(e for e in es if e['evidence_id']==source['evidence_id'])
                options=source.get('citation_options',[])
                counts.append(len(options)==len(original['spans']))
                wanted.extend({'evidence':original['evidence_id'],'quote':s['text']} for s in original['spans'])
                chosen.extend({'citation_id':o['citation_id']} for o in options)
                whole.extend(o['text'].endswith(TAIL) for o in options)
            got=expand({'citations':chosen})['citations'];expanded.append(got==wanted)
            try:expand({'citations':[{'citation_id':'not-in-this-catalogue'}]})
            except ValidationError as exc:
                record(checks,'unknown_citation_rejected',exc.validator=='enum' and exc.instance=='not-in-this-catalogue' and list(exc.path)[-1:]==['citation_id'])
            except (KeyError,ValueError):record(checks,'unknown_citation_rejected',True)
            else:record(checks,'unknown_citation_rejected',False)
            # A changed current catalogue must bind a different receipt; no old
            # label or old text is substituted into the new source mapping.
            changed=deepcopy(data);changed['sources']=list(reversed(changed['sources']))
            if len(changed['sources'])>1:
                v2,_,expand2,r2=m.projection.prepare('FIXED_ORIGINALS',changed,SCHEMA)
                first=v2['sources'][0];option=first['citation_options'][0]
                literal=expand2({'citations':[{'citation_id':option['citation_id']}]})['citations'][0]
                record(checks,'current_catalogue_resolves_current_origin',literal['evidence']==first['evidence_id'] and literal['quote']==option['text'])
        if packets:
            record(checks,'complete_original_coordinate_union_preserved',{digest(x) for x in presented}=={digest(x) for x in available},
                repeated_presented_coordinates=len(presented)-len({digest(x) for x in presented}))
            record(checks,'one_full_quote_per_original_span',all(counts) and all(expanded) and all(whole))
            record(checks,'actual_projected_payload_within_reserved_capacity',all(n<=profile['max_context_chars']-6000 for n in wire_sizes),wire_sizes=wire_sizes)
        else:
            record(checks,'atomic_failure_keeps_all_originals',failure is not None and all(parent.inventory.values.get(e['evidence_id'])==e for e in before))
        record(checks,'no_model_or_retrieval_budget_used',parent.work.budget()['model_reserved']==0 and parent.work.budget()['tool_used']==0)
        return checks,available,presented,0,0,{'capacity_failure':failure,'catalogue_hashes':catalogues,'projection_receipts':len(parent.inventory.receipts),'derived_inventory_entries':len(set(parent.inventory.values)-{e['evidence_id'] for e in before})}
    finally:parent.close()


class Child:
    """Persisted pre-committed fixture records consumed by native compile_bundle.

    current=False checks immutable export lineage, not live case authority.
    The selected-generation API family separately checks active publication.
    """
    def __init__(self,m,path,values,issues,gap):
        self.m=m;self.path=path;self.values={e['evidence_id']:e for e in values};self.issues=issues
        self.run_id=digest([values,issues,gap])[:32];self.open()
        self.db.executescript('CREATE TABLE event(seq INTEGER,kind TEXT,payload_json TEXT,payload_hash TEXT);'
            'CREATE TABLE entity_version(kind TEXT,entity_id TEXT,version INTEGER,payload_json TEXT,payload_hash TEXT);'
            'CREATE TABLE domain_choice(id TEXT,stage TEXT,offer_json TEXT,choice_json TEXT);'
            'CREATE TABLE evidence_dependency(kind TEXT,entity_id TEXT,version INTEGER,evidence_id TEXT);'
            'CREATE TABLE evidence_unit(evidence_id TEXT,source_id TEXT);'
            'CREATE TABLE presentation(evidence_id TEXT,view_id TEXT);'
            'CREATE TABLE model_attempt(view_id TEXT,status TEXT);')
        task={'issues':deepcopy(issues)};mapping={'Q'+str(n):i['id'] for n,i in enumerate(issues,1)}
        payload={'task':task,'task_hash':m.exports.digest(task),'issue_map':mapping}
        self.db.execute('INSERT INTO event VALUES(1,?,?,?)',('WORKFLOW_PARENT_TASK_BOUND',json.dumps(payload),m.exports.digest(payload)))
        selected=[];claims=[]
        for n,e in enumerate(values):
            adopted=[{**s,'evidence_id':e['evidence_id']} for s in e['spans']]
            original={'source_id':e['source_id'],'document_id':e['document_id'],'text':e['text'],'adopted_spans':adopted}
            selected.append(original);options=m.completion.evidence_options([original])
            if len(options)!=1:raise ValueError('fixed short child original must have one adopted option')
            o=options[0];issue=issues[n]
            claims.append({'claim_id':'C'+str(n+1),'issue_refs':['Q'+str(issues.index(issue)+1)],
                'text':e['text'],'rule':None,'source_id':e['source_id'],'quote':o['text'],'evidence':[],
                'evidence_refs':[o['id']],'span_receipts':[o]})
            self.db.execute('INSERT INTO evidence_unit VALUES(?,?)',(e['evidence_id'],e['source_id']))
            self.db.execute('INSERT INTO presentation VALUES(?,?)',(e['evidence_id'],'fixture-delivery'))
            self.db.execute('INSERT INTO evidence_dependency VALUES(?,?,?,?)',('assessment','assessment',1,e['evidence_id']))
        self.db.execute('INSERT INTO model_attempt VALUES(?,?)',('fixture-delivery','SUCCEEDED'))
        gaps=[] if gap=='none' else [{'issue_id':'Q1' if gap=='mapped' else 'Q-unmapped',
            'kind':'MISSING_SOURCE','material':True,'missing_target':'아직 확보하지 않은 모의 부속 원문',
            'suggested_action':'READ_SCOPE','reason':'원문 미확보 상태','material_id':None}]
        refs={}
        for stage,kind,value in [('SELECT','selection',{'selected_originals':selected}),
                                 ('ASSESS','assessment',{'claims':claims,'gaps':gaps,'limitations':[],'stop_reason':None})]:
            ph=m.exports.digest(value);choice='choice-'+stage
            self.db.execute('INSERT INTO entity_version VALUES(?,?,?,?,?)',(kind,kind,1,json.dumps(value),ph))
            offer={'method_id':'fixed-committed-fixture','paths':['fixed'],'concepts':[],'relations':[]}
            decision={'method_id':offer['method_id'],'path':'fixed','concept_ids':[],'relation_ids':[]}
            self.db.execute('INSERT INTO domain_choice VALUES(?,?,?,?)',(choice,stage,json.dumps(offer),json.dumps(decision)))
            refs[stage]={'kind':kind,'entity_id':kind,'version':1,'payload_hash':ph,'choice_id':choice,'run_id':self.run_id}
        self.db.commit();self.envelope={'assembly':{'term_agent':{'case':{'judgment_refs':refs}}},'answer':{'text':'모의 원문 반환','claims':[]}}
    def open(self):self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
    def reopen(self):self.db.close();self.open()
    def run(self):return {'run_id':self.run_id,'binding_hash':digest(self.issues)}
    def evidence(self,ident=None):return deepcopy(self.values[ident] if ident is not None else list(self.values.values()))
    def close(self):self.db.close()


class BasisStub:
    def __init__(self,services,pairs,blocked,unknown,checks):
        self.services=services;self.pairs=deepcopy(pairs);self.blocked=blocked;self.unknown=unknown;self.checks=checks;self.calls=0
    def decide(self,stage,data,schema,instructions,validator):
        self.calls+=1
        value={'pairs':deepcopy(self.pairs),'gaps':[],'summary':'고정 모의 원문 대응 관계'}
        for issue in self.blocked:
            bad=deepcopy(value);p=next(p for p in bad['pairs'] if p['issue_id']==issue)
            if p['issue_id']==self.unknown:continue
            p['comparison_eligibility']=True
            try:validator(bad)
            except ValueError:record(self.checks,'material_gap_override_rejected:'+issue,True)
            else:record(self.checks,'material_gap_override_rejected:'+issue,False)
        bad=deepcopy(value);p=next(p for p in bad['pairs'] if p['issue_id']==self.unknown)
        p['comparison_eligibility']=True;p['applicability']['status']='MATCH'
        try:validator(bad)
        except ValueError:record(self.checks,'unknown_version_override_rejected',True)
        else:record(self.checks,'unknown_version_override_rejected',False)
        validator(value)
        return value


def issues_case(m,case,path,profile,result):
    checks=result['checks'];ids=case['parent_ids']
    issues=[{'id':ident,'label':'모의 쟁점 '+ident,'numeric':False} for ident in ids]
    values=[]
    for n,issue in enumerate(issues):
        ext='모의외규-'+issue['id']
        for side in ('internal','external'):
            name=ext if side=='external' else '모의내규-'+issue['id']
            text=(ext+'에 따른 모의 확인 조건. '+TAIL).replace('\n','')
            values.append(make_source(m,side+'-'+issue['id'],name,side,[('clause',text)],verified=n!=1))
    parent=Parent(m,path/'parent.sqlite',profile,values,issues)
    children={side:Child(m,path/('child-'+side+'.sqlite'),[e for e in values if e['side']==side],issues,
        case['material_gap'] if side=='internal' else 'none') for side in ('internal','external')}
    available=[c for e in values for c in coordinates(e)];presented=[];model=None
    result['available']=available;result['presented']=presented
    try:
        def bundles():return {side:m.exports.compile_bundle(child,child.envelope,side,parent.inventory.verify,None,
            [e['document_id'] for e in values if e['side']==side],current=False) for side,child in children.items()}
        exported=bundles();initial=deepcopy(exported)
        if case['state']=='restart':
            for child in children.values():child.reopen()
            parent.reopen();exported=bundles()
        record(checks,'committed_child_export_stable',exported==initial)
        mapping={'Q'+str(n):i for n,i in enumerate(ids,1)}
        record(checks,'explicit_parent_identity_preserved',all(b.get('issue_map')==mapping for b,_ in exported.values()))
        record(checks,'all_claims_keep_parent_issue',all(len(b['claims'])==len(ids) and all(
            claim.get('parent_issue_refs')==[ids[n]] for n,claim in enumerate(b['claims'])) for b,_ in exported.values()))
        for e in [e for _,adopted in exported.values() for e in adopted]:
            origin=next(v for v in values if v['source_id']==e['source_id'])
            parent.inventory.values[e['evidence_id']]={**e,'side':origin['side'],'text':origin['text'],
                'citation_names':origin['citation_names'],'source_complete':True,'version_verified':origin['version_verified']}
        parent.state['rag_results']={side:{'side':side,'status':'partial' if b['gaps'] else 'completed',
            'run_id':children[side].run_id,'bundle':b,'evidence_ids':b['evidence_ids']} for side,(b,_) in exported.items()}
        active_ids=[ident for b,_ in exported.values() for ident in b['evidence_ids']]
        parent.state['context_evidence']=active_ids;parent.repo.save(parent.state)
        compact=[m.exports.compact_result(r) for r in parent.state['rag_results'].values()]
        record(checks,'consumer_sees_all_exported_claims',all(len(c.get('claims',[]))==len(ids) and c.get('issue_map')==mapping for c in compact))
        blocked=set(ids if case['material_gap']=='unmapped' else ids[:1] if case['material_gap']=='mapped' else [])
        unknown=ids[1];pairs=[]
        for n,ident in enumerate(ids):
            members=[e for e in parent.inventory.evidence() if e['source_id'] in ('internal-'+ident,'external-'+ident)]
            # Adopted IDs, not historical pre-export IDs, own the current packet.
            members=[e for e in members if e['evidence_id'] in active_ids]
            a=next(e for e in members if e['side']=='internal');b=next(e for e in members if e['side']=='external')
            cs=[{'evidence':e['evidence_id'],'quote':e['text']} for e in (a,b)]
            pairs.append({'pair_id':'pair-'+ident,'issue_id':ident,'internal':[a['evidence_id']],'external':[b['evidence_id']],
                'applicability':{'status':'UNKNOWN' if ident==unknown else 'MATCH','reason':'고정 모의 판본 관측','as_of':DAY,'citations':cs},
                'basis_relation':'DIRECT','basis_path':[{'from_evidence':a['evidence_id'],'to_evidence':b['evidence_id'],'citation':cs[0]}],
                'comparison_eligibility':ident not in blocked and ident!=unknown,'reason':'원문의 명시적 모의 문서명',
                'content_difference':'','content_citations':cs})
        model=BasisStub(parent.services,pairs,blocked,unknown,checks);parent.ctx.model=model
        assessed=m.basis.assess(parent.ctx,parent.state)
        record(checks,'all_independent_parent_issues_retained',{p['issue_id'] for p in assessed['pairs']}==set(ids))
        record(checks,'eligibility_only_for_completed_issues',{p['issue_id'] for p in assessed['pairs'] if p['comparison_eligibility']}==set(ids)-blocked-{unknown})
        if blocked:record(checks,'material_gap_cannot_disappear',blocked<={g['issue_id'] for g in assessed['gaps']})
        if case['material_gap']=='unmapped':record(checks,'unmapped_gap_is_explicit',bool(parent.state.get('basis_child_gaps')) and any(
            not g.get('mapping_complete',True) for g in parent.state['basis_child_gaps']))
        packets=m.p.packets(parent.ctx,parent.state,'BASIS')
        for data,es in packets:
            presented.extend(c for e in es for c in coordinates(e))
            record(checks,'presented_parent_joins_cover_all_issues',set().union(*(set(e.get('parent_issue_refs',[])) for e in data['sources']))==set(ids))
            record(checks,'unverified_source_metadata_preserved',all(not e['version_verified'] for e in data['sources'] if e['document_id'].endswith(unknown)))
        record(checks,'all_exported_originals_preserved',{digest(x) for x in presented}=={digest(x) for x in available},
            repeated_presented_coordinates=len(presented)-len({digest(x) for x in presented}))
        return checks,available,presented,0,model.calls,{'export_bundle_hashes':{s:b['bundle_hash'] for s,(b,_) in exported.items()},'publication_current_validation':False,'projection_receipts':len(parent.inventory.receipts),'derived_inventory_entries':len(set(parent.inventory.values)-{e['evidence_id'] for e in before})}
    finally:
        if model is not None:result['stub_model_calls']=model.calls
        for child in children.values():child.close()
        parent.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--code-root',required=True);parser.add_argument('--arm',required=True)
    parser.add_argument('--output-dir',required=True);parser.add_argument('--family',choices=['projection','issues','all'],default='all')
    args=parser.parse_args()
    if not (DESIGN/'freeze.json').exists():raise SystemExit('ADR0814 must be frozen before qualification execution')
    code=Path(args.code_root).resolve();out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    modules=None;load_error=None
    try:modules=load(code)
    except Exception as exc:load_error={'type':type(exc).__name__,'message':str(exc)}
    profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    for family in (['projection','issues'] if args.family=='all' else [args.family]):
        spec=read(DESIGN/(family+'-cases.json'));rows=[];started=time.monotonic()
        for case in spec['cases']:
            start=time.monotonic();folder=out/(family+'-'+case['case_id']);folder.mkdir(exist_ok=False)
            row={'case_id':case['case_id'],'passed':False,'checks':[],'available':[],'presented':[],
                'executed_retrieval':False,'skip_reason':'fixed source inventory; no retrieval execution',
                'tool_calls':0,'stub_model_calls':0,'fixture_sha256':digest(case)}
            try:
                if load_error:raise RuntimeError('selected capability load failure: '+json.dumps(load_error))
                if profile['max_context_chars']!=spec['max_context_chars']:raise ValueError('selected profile differs from frozen fixture capacity')
                checks,available,presented,tool,stub,extra=globals()[family+'_case'](modules,case,folder,profile,row)
                row.update(checks=checks,available=available,presented=presented,tool_calls=tool,stub_model_calls=stub,**extra)
                row['passed']=bool(checks) and all(c['passed'] for c in checks)
            except Exception as exc:row['error']={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}
            row['elapsed_seconds']=time.monotonic()-start;rows.append(row)
            put(out/(family+'.json'),{'arm':args.arm,'family':family,'results':rows,'elapsed_seconds':time.monotonic()-started,
                'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'real_model_calls':0,
                'quality_certified':False,'case_manifest_sha256':sha((DESIGN/(family+'-cases.json')).read_text())})
        print(json.dumps({'arm':args.arm,'family':family,'cases':len(rows),'passed':sum(r['passed'] for r in rows),'real_model_calls':0}),flush=True)


if __name__=='__main__':main()
