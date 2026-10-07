"""No-network CM003 vertical-slice contracts; not model behavior or answer accuracy."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0475/source-first-v2'
FIXTURE=json.loads((ADR/'fixture.json').read_text())
BINDING={'provider':'fixture','model':'scripted-no-network','adapter_version':'fixture-v1',
         'endpoint_identity':'no-network','trust_zone':'internal','max_input_bytes':500000}

def write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')

def pin(revision):
    manifest=json.loads((CAND/'candidate.json').read_text())
    rev=next(r for r in manifest['revisions'] if r['revision_id']==revision)
    for row in rev['files']:
        assert hashlib.sha256((ROOT/row['frozen_path']).read_bytes()).hexdigest()==row['snapshot_sha256']
    frozen=CAND/'revisions'/revision/'snapshot/02_BACKEND'
    sys.path.insert(0,str(ROOT/'02_BACKEND'))
    sys.path.insert(0,str(frozen))
    return rev,frozen


def isolated_contract_root(frozen, destination):
    """Bind unchanged ports to this frozen candidate, without weakening hash checks."""
    import shutil
    destination.mkdir(parents=True,exist_ok=False)
    pipeline=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())
    receipt=[]
    def copy(relative):
        src=frozen.parent/relative
        if not src.is_file():
            src=ROOT/relative
        dst=destination/relative
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst)
        receipt.append({'path':relative,'from':str(src.relative_to(ROOT)),
                        'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()})
        return dst
    for contract in pipeline['contracts'].values():
        copy(contract['schema_path'])
    for step in pipeline['profiles']['legal-agent-rag-v1']['nodes']:
        entry=pipeline['engines'][step['engine']]
        manifest=json.loads((ROOT/entry['manifest']).read_text())
        files=set(manifest['files'])
        files.update(str(p.relative_to(frozen.parent)) for p in
                     (frozen/'semantic_runtime/legal_agent').glob('source_first_*.py'))
        manifest['files']={relative:hashlib.sha256(copy(relative).read_bytes()).hexdigest() for relative in sorted(files)}
        write(destination/entry['manifest'],manifest)
        entry['sha256']=hashlib.sha256((destination/entry['manifest']).read_bytes()).hexdigest()
    configs=[n['parameters'].get('term_agent') for profile in pipeline['profiles'].values()
             for n in profile['nodes'] if 'parameters' in n]
    for config in filter(None,configs):
        for key in ('origin_projections','alias_projections'):
            for binding in config.get(key,[]):
                copy(binding['path'])
        for binding in config.get('legal_agent',{}).values():
            copy(binding['path'])
    write(destination/'00_SYSTEM/PIPELINE.json',pipeline)
    write(destination/'binding-receipt.json',receipt)
    return destination

class ScriptedWire:
    binding=BINDING
    def __init__(self):
        self.calls=[]
        self.response=None
        self.auto=False
    def validate_model(self):
        return {'verified':False,'simulated':True,'model':BINDING['model']}
    def send_once(self,*,body,ticket):
        self.calls.append(deepcopy(body))
        value=json.loads(body['messages'][1]['content'])['view']
        schema=body['response_format']['json_schema']['name']
        if self.auto:
            if schema=='InvestigateDecision':
                chosen=[x['evidence'] for x in value['evidence']
                        if (x['document_name']=='코스닥시장 상장규정' and x['heading'].startswith('제26조'))
                        or (x['document_name']=='코스닥시장 상장규정 시행세칙' and x['heading'].startswith('제23조'))]
                # Scripted fixture selection from offered text, never gold IDs.
                if len(chosen)>=2:
                    response={'actions':[],'select':chosen,'unselect':[],'dismiss':[],'intent':'DRAFT'}
                else:
                    target=next((c for c in value['cards']
                        if c['document_name']=='코스닥시장 상장규정 시행세칙' and c['heading'].startswith('제23조')),None)
                    if not target:
                        raise AssertionError('CM003 related source was not offered')
                    response={'actions':[{'tool':'read','card':target['card'],'cursor':None}],
                              'select':[],'unselect':[],'dismiss':[],'intent':'CONTINUE'}
            elif schema=='Draft':
                response={'paragraphs':[{'text':'모의 연결 검사: 두 저장 조문을 함께 읽었습니다. 법률 정답 판정이 아닙니다.',
                                        'evidence':value['selected']}],'limitations':[]}
            else:
                response={'checks':[{'claim':c['claim'],'verdict':'SUPPORTED','reason':'합성 검토 영수증',
                                     'evidence':c['evidence'],'actions':[]} for c in value['claims']],
                          'question':{'status':'RESOLVED','reason':'모의 연결 검사'}}
        else:
            response=self.response
        return {'status_code':200,'body_json':{'model':BINDING['model'],
                'choices':[{'message':{'content':json.dumps(response,ensure_ascii=False)}}],
                'usage':{'prompt_tokens':0,'completion_tokens':0,'simulated':True}}}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--revision',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    out=Path(args.out)
    if out.exists():
        raise SystemExit('output already exists; preserve prior run')
    revision,frozen=pin(args.revision)
    # Fail closed: this entire process is forbidden from opening a network socket.
    def denied(*args,**kwargs):
        raise AssertionError('network is forbidden in this contract test')
    socket.socket.connect=denied
    socket.create_connection=denied
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.legal_agent.domain import DEFAULT_PROFILE
    from semantic_runtime.legal_agent.source_first_adapter import SourceFirstAgent
    from semantic_runtime.legal_agent.errors import ProposalError, StaleProposal
    from semantic_runtime.legal_agent.packer import pack
    from semantic_runtime.legal_agent.repository import encoded
    import semantic_runtime.legal_agent.source_first_session as implementation
    assert Path(implementation.__file__).is_relative_to(frozen)
    checks=[]
    def check(name,condition,details=None):
        checks.append({'name':name,'passed':bool(condition),'details':details})
        if not condition:
            raise AssertionError(name)
    def rejects(name,fn):
        try:
            fn()
        except (ProposalError,StaleProposal):
            check(name,True)
        else:
            check(name,False)
    started=time.monotonic()
    wire=ScriptedWire()
    settings={**DEFAULT_PROFILE,'model_binding':BINDING}
    store=Store(ROOT/FIXTURE['generation'])
    contract_root=isolated_contract_root(frozen,out/'contract-root')
    p=Pipeline(contract_root,store,implementation='legal-agent-v1',legal_agent_profile=settings,legal_agent_transport=wire)
    old_agent=p.term_agent
    p.term_agent=SourceFirstAgent(p,old_agent.config,execution_profile=settings,transport=wire)
    q=p.plan(FIXTURE['question'],FIXTURE['public_scope_document_ids'])
    request={'question':FIXTURE['question'],'document_ids':FIXTURE['public_scope_document_ids'],'use_llm':True}
    evidence_snapshot=[]
    try:
        with p.term_agent.open_session(request,query=q,runtime=out/'manual') as s:
            result=s.nav.search(FIXTURE['question'])
            located=[c for c in result['items'] if c['document_name']=='코스닥시장 상장규정' and c['heading'].startswith('제26조')]
            check('question locator reaches article 26',len(located)==1)
            target=located[0]
            v=s.view('investigate')
            check('preview is present in offered model view',any(c['card']==target['card'] and c['preview'] for c in v['cards']))
            check('preview did not create any evidence',not s.work.evidence())
            wire.response={'actions':[],'select':[],'unselect':[],'dismiss':[],'intent':'CONTINUE'}
            s.gateway.generate('investigate',v,'InvestigateDecision')
            rejects('preview-only citation rejected',lambda:s.apply_decision(v,
                {'actions':[],'select':[target['card']],'unselect':[],'dismiss':[],'intent':'DRAFT'}))
            action={'tool':'read','card':target['card'],'cursor':None}
            s.apply_decision(v,{'actions':[action],'select':[],'unselect':[],'dismiss':[],'intent':'CONTINUE'})
            check('READ stored original spans server-side',len(s.work.evidence())>=1)
            check('model supplied no issue assessment or finding',s.work.heads()==[])
            related=next((c for c in s.nav.cards.values() if c['document_name']=='코스닥시장 상장규정 시행세칙'
                          and c['heading'].startswith('제23조')),None)
            check('reading article 26 offers rule article 23 as a reference candidate',related is not None,
                  None if not related else related['routes'])
            v2=s.view('investigate')
            check('related preview reaches next model input',any(c['card']==related['card'] for c in v2['cards']))
            check('reference preview not automatically adopted',not s.selected)
            check('reference preview not automatically read',related['source_id'] not in {e['source_id'] for e in s.work.evidence()})
            wire.response={'actions':[{'tool':'read','card':related['card'],'cursor':None}],
                           'select':[],'unselect':[],'dismiss':[],'intent':'CONTINUE'}
            response=s.gateway.generate('investigate',v2,'InvestigateDecision')
            s.apply_decision(v2,response)
            v3=s.view('investigate')
            aliases=[e['evidence'] for e in v3['evidence']]
            wire.response={'actions':[],'select':aliases,'unselect':[],'dismiss':[],'intent':'DRAFT'}
            response=s.gateway.generate('investigate',v3,'InvestigateDecision')
            s.apply_decision(v3,response)
            check('both original sources selected without findings',len(s.selected)==2 and not s.work.heads('finding'))
            for e in s.work.evidence():
                s.sources.verify(e)
            check('original spans hashes verified',True)
            selected=s.select({'retrieval':s.retrieval()})
            check('evidence-first selection not blocked by absent finding',len(selected['selected'])==2)
            check('unchanged v1 pack still needs findings',pack(s.work,settings)['finding_ids']==[])
            v4=s.view('compose')
            wire.response={'paragraphs':[{'text':'모의 연결 검사: 첫 원문을 확인했습니다.','evidence':[aliases[0]]},
                                         {'text':'모의 연결 검사: 둘째 원문을 확인했습니다.','evidence':[aliases[1]]}],'limitations':[]}
            s.commit_draft(v4,s.gateway.generate('compose',v4,'Draft'))
            check('draft claims server generated without finding chain',len(s.work.heads('claim',current=True))==2)
            v5=s.view('review')
            wire.response={'checks':[{'claim':v5['claims'][0]['claim'],'verdict':'SUPPORTED','reason':'모의 확인',
                                      'evidence':v5['claims'][0]['evidence'],'actions':[]},
                                     {'claim':'C999','verdict':'SUPPORTED','reason':'의도적인 잘못된 별칭',
                                      'evidence':v5['claims'][1]['evidence'],'actions':[]}],
                           'question':{'status':'UNRESOLVED','reason':'일부 검토 미완료'}}
            s.commit_review(v5,s.gateway.generate('review',v5,'Review'))
            accepted,unresolved,decision=s.evaluate()
            check('bad review item preserves independently supported claim',len(accepted)==1 and bool(unresolved))
            check('physical mock attempts equal wire sends',s.work.budget()['model_reserved']==len(wire.calls))
            check('complete serialized requests within character bound',all(len(encoded(x))<=settings['max_context_chars'] for x in wire.calls))
            check('no database updates protocol in model requests',all('expected_version' not in encoded(x) and 'propose_finding' not in encoded(x) for x in wire.calls))
            preview=next(c for c in v['cards'] if c['card']==target['card'])
            check('preview unchanged by later reads',preview['preview']==target['preview'])
            evidence_snapshot=s.work.evidence()
            trace={'cards':list(s.nav.cards.values()),'observations':s.work.observations(1000),
                   'evidence':evidence_snapshot,'selection':selected,'reviews':s.work.heads('review'),
                   'views':[v,v2,v3,v4,v5],'budget':s.work.budget()}
            write(out/'manual-trace.json',trace)
        write(out/'manual-wire.json',wire.calls)
        wire2=ScriptedWire();wire2.auto=True
        p.term_agent=SourceFirstAgent(p,old_agent.config,execution_profile=settings,transport=wire2)
        result=p.run(FIXTURE['question'],FIXTURE['public_scope_document_ids'],
                     execution_context={'runtime':out/'pipeline'})
        check('existing Pipeline and publication consumers accept candidate',bool(result['answer']['claims']))
        check('model output marked as not quality certified',result['answer']['provider_receipt']['quality_certified'] is False)
        check('pipeline used no more than physical budget',len(wire2.calls)<=settings['max_model_attempts'])
        write(out/'pipeline-result.json',result)
        write(out/'pipeline-wire.json',wire2.calls)
        report={'case_id':'cm-003','candidate_revision':revision['revision_id'],'checks':checks,
                'passed':sum(c['passed'] for c in checks),'total':len(checks),
                'network_calls':0,'mock_transport_calls':len(wire.calls)+len(wire2.calls),
                'quality_evaluated':False,'main_wiring':'unchanged','seconds':round(time.monotonic()-started,3)}
        write(out/'result.json',report)
        print(json.dumps(report,ensure_ascii=False,indent=2))
    except BaseException as exc:
        write(out/'failure.json',{'checks':checks,'error':type(exc).__name__+': '+str(exc),'network_calls':0,
                                 'mock_transport_calls':len(wire.calls),'seconds':round(time.monotonic()-started,3)})
        raise
    finally:
        store.close()

if __name__=='__main__':
    main()

