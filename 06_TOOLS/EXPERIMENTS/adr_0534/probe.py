"""Hash-pinned public-corpus contract probe for the reverse-reference gate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0534-reverse-reference-model-gate'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0534/gated-reference'


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frozen_candidate():
    manifest = json.loads((CANDIDATE/'candidate.json').read_text())
    revision = manifest['revisions'][-1]
    for row in revision['files']:
        path = ROOT/row['frozen_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['snapshot_sha256']:
            raise ValueError('candidate revision drift: '+str(path))
    return CANDIDATE/'revisions'/revision['revision_id']/'snapshot'/'02_BACKEND/semantic_runtime'


def main():
    bootstrap = load_file('adr0531_bootstrap', ROOT/'06_TOOLS/EXPERIMENTS/adr_0531/bootstrap.py')
    overlay = bootstrap.load_candidate()
    from semantic_runtime.reference_exploration import ReferenceNavigator
    candidate = frozen_candidate()
    gated = load_file('semantic_runtime.reference_gate', candidate/'reference_gate.py')
    scoped = load_file('adr0534_scoped_fulltext', candidate/'fulltext.py')
    generation = ROOT/'01_DATA/TERM_RELEASES/adr0531-reference-overlay-v1/generation'
    expected = '29b5e12e71f8b05210cc470edf39d4e92bc1c8d022593a486fa0d0daa3faa64c'
    if hashlib.sha256((generation/'manifest.json').read_bytes()).hexdigest() != expected:
        raise ValueError('overlay generation changed')
    public = json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/product-cases.json').read_text())
    scope = public['public_scope_document_ids']
    with overlay.closing(overlay.open_research_overlay(generation)) as db:
        placeholders = ','.join('?' for _ in scope)
        sources = {source['id']:source for (raw,) in db.execute(
            'SELECT json FROM source WHERE document_id IN ('+placeholders+')',scope)
            for source in [json.loads(raw)]}
        binding = 'fixed-start-public-v1'
        nav = gated.GatedReferenceNavigator(db,sources,scope,binding)
        baseline = ReferenceNavigator(db,sources,scope,binding)
        article433 = next(s for s in sources.values() if s.get('document_name')=='상법'
                          and s.get('heading','').startswith('제433조 '))
        article363 = next(s for s in sources.values() if s.get('document_name')=='상법'
                          and s.get('heading','').startswith('제363조 '))
        root433 = nav.root(article433['id'],query='정관 변경 의안의 요령을 통지에 기재하는 방법',
                           reason='질문의 명시 조문')
        outgoing = [edge for edge in nav.neighbors(root433['extent'],'outgoing')
                    if edge['traversal_allowed']]
        target363 = next(target for edge in outgoing for target in edge['targets']
                         if target['source_id']==article363['id'])
        fixed_graph = nav.walk([root433],max_states=40,max_seconds=2)
        if any(edge['direction']=='incoming' for edge in fixed_graph['edges']):
            raise AssertionError('reverse edge entered automatic graph')
        if article363['id'] not in fixed_graph['source_ids']:
            raise AssertionError('forward citation to article 363 lost')
        old_incoming = [edge for edge in baseline.neighbors(target363,'incoming')
                        if edge['traversal_allowed']]
        page = nav.incoming_candidates(target363,limit=100)
        annex = next(c for c in page['items'] if c['document_name']=='자본시장과 금융투자업에 관한 법률'
                     and c['heading'].startswith('별표 1 ')
                     and '363' in c['locator'])
        if annex['suggested_item_span']['item_label'] != '191':
            raise AssertionError('annex item 191 was not localized')
        decisions = []
        def reject(system, view, schema):
            decisions.append({'system':system,'view':view,'schema':schema})
            return {'selected':[]}
        skipped = nav.review_incoming(page,query=root433['query'],invoke=reject)
        if len(decisions)!=1 or skipped['roots']:
            raise AssertionError('one model decision must reject all irrelevant reverse roots')
        def accept(system, view, schema):
            return {'selected':[{'candidate_id':annex['candidate_id'],
                                 'reason':'별표 191번 제재 사유를 직접 묻는 질문'}]}
        chosen = nav.review_incoming(page,query='별표 1 제191호 제재 사유',invoke=accept)
        root191 = chosen['roots'][0]
        span = root191['extent']['spans'][0]
        annex_block = next(b['text'] for b in sources[annex['source_id']]['blocks']
                           if str(b['block_id']) == span['block_id'])
        selected_text = annex_block[span['start_cp']:span['end_cp']].strip()
        if not selected_text.startswith('191. ') or '제363조제1항 또는 제2항' not in selected_text or '112. ' in selected_text:
            raise AssertionError('selected annex root widened beyond item 191')
        item_edges = [e for e in nav.neighbors(root191['extent'],'outgoing') if e['traversal_allowed']]
        if any(e['locator']=='제97조' for e in item_edges):
            raise AssertionError('annex item 112 leaked into item 191')
        short = scoped.scoped_source_view(article363)
        if short['mode']!='FULL_SOURCE' or short['total_chars']!=804:
            raise AssertionError('article 363 must be available as full source')
        long = scoped.scoped_source_view(sources[annex['source_id']],query='제363조제1항 또는 제2항')
        if long['mode']!='SCOPED_LITERAL' or not any(m['start_cp']==12986 for m in long['matches']):
            raise AssertionError('annex scoped original search lost exact occurrence')
        result={'schema_version':'adr0534-gate-probe-v1','source_generation_sha256':expected,
                'model_calls':0,'model_decisions_simulated':2,'main_wiring_unchanged':True,
                'baseline_incoming_edges_at_363':len(old_incoming),
                'gated_incoming_candidates_at_363':page['total'],
                'forward_363_reached':True,'automatic_incoming_edges':0,
                'annex_191_candidate':annex['candidate_id'],'annex_191_span':span,
                'selected_191_outgoing_references':sorted({e['reference_id'] for e in item_edges}),
                'item_112_reference_excluded':True,'article_363_full_chars':short['total_chars'],
                'annex_search_match_count':long['match_count']}
    out = ADR/'artifacts/run-001/result.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        raise ValueError('run artifact already exists')
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
