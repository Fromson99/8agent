"""CM003 one-hop relation/READ wiring, no model calls or autonomous selection."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0480-cm003-reviewed-source-relations'
CAND = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link'
REG = 'article:3e4ab92e38b531a09f6419a9'
RULE = 'article:1fa6eb7a10072f0d8f71bfc1'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def pin():
    design = json.loads((ADR/'artifacts/frozen-design.json').read_text())
    for path, expected in design['file_hashes'].items():
        if sha(ROOT/path) != expected:
            raise ValueError('frozen input drift: '+path)
    cand = json.loads((CAND/'candidate.json').read_text())
    rev = cand['revisions'][-1]
    for row in rev['files']:
        if sha(ROOT/row['frozen_path']) != row['snapshot_sha256']:
            raise ValueError('candidate drift')
    frozen = CAND/'revisions'/rev['revision_id']/'snapshot/02_BACKEND'
    sys.path[:0] = [str(frozen), str(ROOT/'02_BACKEND'), str(ROOT)]
    return rev, frozen

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    rev, frozen = pin()
    args.out.mkdir(parents=True,exist_ok=False)
    def denied(*a,**kw):
        raise RuntimeError('network forbidden in no-model probe')
    socket.socket.connect = socket.create_connection = denied
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.repository import WorkRepository
    from semantic_runtime.legal_agent.domain import DEFAULT_PROFILE
    from semantic_runtime.legal_agent.source_tools import SourceSession
    from semantic_runtime.legal_agent.source_relations import RelationStore, anchor_from_unit, read_target
    import semantic_runtime.legal_agent.source_relations as implementation
    assert Path(implementation.__file__).is_relative_to(frozen)
    spec=importlib.util.spec_from_file_location('base_contract',ROOT/'06_TOOLS/EXPERIMENTS/adr_0475/check_cm003.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    contract_root=helper.isolated_contract_root(frozen,args.out/'contract-root')
    fixture=json.loads((ADR/'fixture.json').read_text())
    settings=dict(DEFAULT_PROFILE, page_size=3)  # Force cursor continuation; same both arms.
    store=Store(ROOT/fixture['generation'])
    p=Pipeline(contract_root,store,implementation='legal-agent-v1',legal_agent_profile=settings)
    query=p.plan(fixture['question'],fixture['public_scope_document_ids'])
    request={'question':fixture['question'],'document_ids':fixture['public_scope_document_ids'],'use_llm':False}
    report={'case_id':'cm-003','revision':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
            'network_calls':0,'model_calls':0,'main_wiring':'unchanged','quality_evaluated':False,
            'autonomous_search_evaluated':False,'human_approvals':0,'arms':{},'error':None}
    start=time.monotonic()
    try:
        agent=ServingDocumentAgent(p,p.term_agent.config)
        with agent.resources(query['scope']['document_version_ids']) as (index,tools,glossary,matcher):
            sources_scope=fixture['public_scope_document_ids']
            report['corpus_total']=tools.db.execute('SELECT count(*) FROM source WHERE document_id IN ('+','.join('?' for _ in sources_scope)+')',sources_scope).fetchone()[0]
            for arm in ('baseline','explicit-link'):
                out=args.out/arm;out.mkdir()
                binding={k:store.manifest[k] for k in ('generation_id','store_sha256','export_allowed')}
                binding.update(scope=query['scope'],model=None,relation_release=arm+'-fixture-v1')
                context=RequestContext.create(query,request,binding,settings['wall_seconds'])
                repo=WorkRepository(out/'journal.sqlite',context,settings)
                relation=RelationStore(out/'relations.sqlite')
                try:
                    sources=SourceSession(store,tools,glossary,matcher,repo,context,settings)
                    reg=anchor_from_unit(sources,REG,'286','제26조제1항제3호 단서',
                                         start_cp=store.source('3521c3aaa5a735fd','301')['text'].index('다만,'))
                    rule=anchor_from_unit(sources,RULE,'218','제23조제4항')
                    r={'id':'cm003-delegated-cases:1','relation_id':'cm003-delegated-cases','revision':1,
                       'relation_type':'SPECIFIES_DELEGATED_CASES_OF','from_anchor':rule['id'],
                       'to_anchor':reg['id'],'qualifiers':{'target_role':'proviso','scope':'delegated_cases_only'},
                       'witness':{'anchor_id':rule['id'],'span':rule['selector']['spans'][0]},
                       'origin':'experiment_fixture','supersedes':None}
                    release=arm+'-fixture-v1'
                    if arm=='explicit-link':
                        relation.seed_experiment(release,r,[rule,reg],sources)
                    else:
                        with relation.db:
                            relation.db.execute('INSERT INTO relation_release VALUES(?,?,?,?,?)',
                                (release,query['generation_id'],store.manifest['store_sha256'],'experiment_fixture',hashlib.sha256(b'empty').hexdigest()))
                    # Same explicit initial article READ; this is not a search autonomy test.
                    node=sources.node('3521c3aaa5a735fd','282',REG)
                    cursor=None
                    while True:
                        obs=sources.execute({'tool':'read_node','args':{'node':node,'cursor':cursor},'reason':'fixed CM003 starting article'})
                        assert obs['status'] in ('OK','TRUNCATED')
                        cursor=obs['next_cursor']
                        if cursor is None:break
                    before=len(repo.evidence())
                    lookup=relation.lookup(REG,sources,release_id=release,allow_experiment=True)
                    assert len(repo.evidence())==before  # Relation metadata is not READ evidence.
                    reads=[read_target(hit,sources) for hit in lookup['items']]
                    evidence=repo.evidence()
                    target=[e for e in evidence if e['source_id']==RULE]
                    blocks={s['block_id']:s['text'] for e in target for s in e['spans']}
                    if arm=='explicit-link':
                        assert len(lookup['items'])==1 and all(x['complete'] for x in reads)
                        assert set(blocks)=={str(i) for i in range(236,245)}
                        assert blocks['238']==store.source('eae25aa6e8a83c58','238')['text']
                        assert len(reads[0]['pages'])==3
                        # Simulated model feedback submissions exercise persistence, not generation accuracy.
                        relation.propose(action='MISSING',from_anchor=reg['id'],reason='합성 계약 검사: 다른 위임 대상 확인 필요',
                            producer_kind='llm',producer_id='simulated-not-qwen',run_id='synthetic-feedback',
                            idempotency_key='synthetic-missing-1',candidate={'target_locator':'미상'})
                        relation.propose(action='CORRECT',from_anchor=reg['id'],reason='합성 계약 검사: 연결 재확인 요청',
                            producer_kind='llm',producer_id='simulated-not-qwen',run_id='synthetic-feedback',
                            idempotency_key='synthetic-correct-1',base_revision=r['id'])
                        assert len(relation.lookup(REG,sources,release_id=release,allow_experiment=True)['items'])==1
                    else:
                        assert not lookup['items'] and not target
                    assert repo.db.execute('SELECT count(*) FROM model_attempt').fetchone()[0]==0
                    write(out/'input.json',{'request':request,'start_source_id':REG,'relation':r if arm=='explicit-link' else None,
                                           'anchors':[rule,reg] if arm=='explicit-link' else [],'settings':settings})
                    write(out/'lookup.json',lookup)
                    write(out/'reads.json',reads)
                    write(out/'evidence.json',evidence)
                    write(out/'observations.json',repo.observations(1000))
                    report['arms'][arm]={'matched_relations':len(lookup['items']),'read_sources':sorted({e['source_id'] for e in evidence}),
                        'target_block_ids':sorted(blocks,key=int),'target_chars':sum(len(t) for t in blocks.values()),
                        'target_read_pages':sum(len(x['pages']) for x in reads),'model_presented_sources':0,
                        'tool_actions':repo.budget()['tool_used'],'proposal_count':relation.db.execute('SELECT count(*) FROM proposal').fetchone()[0],
                        'source_store_sha256':store.manifest['store_sha256']}
                finally:
                    repo.close();relation.close()
            glossary.check_unchanged()
    except BaseException as exc:
        report['error']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        report['seconds']=round(time.monotonic()-start,3)
        write(args.out/'result.json',report)
        store.close()
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
