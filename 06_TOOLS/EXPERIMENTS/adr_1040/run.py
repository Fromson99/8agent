"""Real subset reference compilation using the existing checkpoint contract."""
import importlib.util
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.platform.paths import root_path
from semantic_runtime import reference_build
from semantic_runtime.term_references import ARTICLE, compile_references, load_reference_inputs

ADR = root_path('experiments', 'ADR', 'ADR-1040-law-version-partial-reference-compile')
NATIVE = root_path('experiments', 'ADR', 'ADR-1038-law-version-incremental-audit', 'artifacts', 'run-001')
spec = importlib.util.spec_from_file_location('immutable_audit1038', ROOT / '06_TOOLS/EXPERIMENTS/adr_1038/audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def canonical(db, structure):
    units = {str(n['id']): n for n in structure['nodes']}
    sources = {sid: json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
    articles = {sid: ARTICLE.match(s['heading']).group().replace(' ', '') if ARTICLE.match(s['heading']) else None
                for sid,s in sources.items()}
    def path(uid):
        result = []
        while uid is not None and str(uid) in units:
            n = units[str(uid)]
            result.append([n.get('family'), n.get('ordinal'), n.get('surface')])
            uid = n.get('parent')
        return list(reversed(result))
    result = []
    for raw, in db.execute('SELECT json FROM reference'):
        r = json.loads(raw)
        if articles[r['source_id']] is None:
            raise ValueError('out-of-scope supplementary reference produced')
        targets = [{'article': articles[t['source_id']], 'path': path(t.get('unit_id')), 'level': t.get('target_level'),
                    'texts': [b['text'] for b in sources[t['source_id']]['blocks'] if b['block_id'] in t.get('block_ids', [])]}
                   for t in r.get('targets', [])]
        result.append({'source_article': articles[r['source_id']], 'source_path': path(r.get('source_unit_id')),
                       **{k:r.get(k) for k in ('source_text','mention_text','mention_start','mention_end','document_name_hint',
                         'document_hint_basis','locator','resolution','resolution_state','reason','reference_role','coordinate_status','unresolved_paths')},
                       'targets':targets, 'origins':r.get('origins',[])})
    return sorted(result, key=audit.encode)

def main():
    frozen = json.loads((ADR / 'artifacts/design-frozen.json').read_text())
    for name, expected in frozen['inputs'].items():
        if audit.sha(ROOT / name) != expected:
            raise ValueError('frozen artifact drift: ' + name)
    out = ADR / 'artifacts/run-001'
    out.mkdir()
    versions = [json.loads((NATIVE / v / 'canonical.json').read_text())
                for v in ('254785-20230914','257829-20240703','277253-20260102')]
    results = []
    for old,new in zip(versions,versions[1:]):
        change,_ = audit.plan(old,new)
        target = out / (old['version'] + '--' + new['version'])
        target.mkdir()
        full = NATIVE / new['version'] / 'navigation/navigation.sqlite'
        partial = target / 'partial-navigation.sqlite'
        # Input schema/source/anchors are native output. Strip ALL reference
        # outputs before invoking the candidate path; no baseline answers remain.
        shutil.copyfile(full, partial)
        db = sqlite3.connect(partial)
        db.row_factory = sqlite3.Row
        sources = {sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
        selected = {sid for sid,s in sources.items() if ARTICLE.match(s['heading']) and
                    ARTICLE.match(s['heading']).group().replace(' ','') in change['reference_rebuild_sources']}
        source_before = audit.digest([(r['id'],r['json']) for r in db.execute('SELECT id,json FROM source ORDER BY id')])
        for table in ('reference','reference_end','reference_target','reference_candidate','reference_candidate_end','reference_witness_count'):
            db.execute('DELETE FROM '+table)
        db.execute('CREATE TABLE navigation_checkpoint(stage TEXT,item TEXT,json TEXT,PRIMARY KEY(stage,item))')
        # These are deliberate audit exclusions, not a production completion
        # claim. The database is never published as a serving generation.
        db.executemany('INSERT INTO navigation_checkpoint VALUES(?,?,?)',
            [('reference-source',sid,'{"audit_excluded":true}') for sid in sources if sid not in selected])
        db.commit()
        if db.execute('SELECT count(*) FROM reference').fetchone()[0] != 0:
            raise ValueError('reference output contamination')
        executed = []
        original = reference_build.ReferenceCheckpoint.sources
        def observed(self, catalogue, counts):
            for source in original(self,catalogue,counts):
                executed.append(source['id'])
                yield source
        reference_build.ReferenceCheckpoint.sources = observed
        aliases,delegations,input_hash = load_reference_inputs()
        if input_hash != new['navigation_manifest']['reference_inputs_sha256']:
            raise ValueError('reference inputs drift')
        started = time.monotonic()
        try:
            counts = compile_references(db,aliases,delegations)
            first_executed = list(executed)
            generated = {rid:json.loads(raw) for rid,raw in db.execute('SELECT id,json FROM reference')}
            first_hash = audit.digest(generated)
            executed.clear()
            compile_references(db,aliases,delegations)
            replay = {rid:json.loads(raw) for rid,raw in db.execute('SELECT id,json FROM reference')}
            repeat_ok = not executed and audit.digest(replay)==first_hash
        finally:
            reference_build.ReferenceCheckpoint.sources = original
        elapsed = time.monotonic()-started
        generated_canonical = canonical(db,json.loads((NATIVE/new['version']/'structure.json').read_text()))
        merged = sorted([r for r in old['references'] if r['source_article'] not in change['reference_rebuild_sources']]
                        + generated_canonical,key=audit.encode)
        # Baseline is read only AFTER real candidate output is fixed.
        with sqlite3.connect(full) as baseline:
            expected = {rid:json.loads(raw) for rid,raw in baseline.execute('SELECT id,json FROM reference')
                        if json.loads(raw)['source_id'] in selected}
        source_after = audit.digest([(r['id'],r['json']) for r in db.execute('SELECT id,json FROM source ORDER BY id')])
        checks = {'exact_executed_source_set':set(first_executed)==selected and len(first_executed)==len(selected),
                  'native_reference_json_equal':generated==expected,'canonical_merged_references_equal':merged==new['references'],
                  'duplicate_no_work':repeat_ok,'source_blocks_unchanged':source_before==source_after,
                  'input_native_db_unchanged':audit.sha(full)==frozen['inputs'][str(full.relative_to(ROOT))]}
        db.close()
        save_db = sqlite3.connect(target/'delta-state.sqlite')
        save_db.executescript('''CREATE TABLE payload(hash TEXT PRIMARY KEY,json TEXT);
          CREATE TABLE article(version TEXT,coordinate TEXT,hash TEXT,PRIMARY KEY(version,coordinate));
          CREATE TABLE ref(version TEXT,ordinal INTEGER,json TEXT,PRIMARY KEY(version,ordinal));
          CREATE TABLE selected(version TEXT); CREATE TABLE receipt(id TEXT PRIMARY KEY,json TEXT);''')
        audit.populate(save_db,old)
        save_db.execute('INSERT INTO selected VALUES(?)',(old['version'],))
        save_db.commit()
        receipt=audit.apply_delta(save_db,old,new,change,merged,expected=old['version'])
        checks['actual_partial_rows_applied']=audit.snapshot(save_db,new['version'])==new['articles']
        checks['old_version_preserved']=audit.snapshot(save_db,old['version'])==old['articles']
        save_db.close()
        row={'old':old['version'],'new':new['version'],'selected_body_articles':len(selected),
             'all_new_body_articles':len(new['articles']),'generated_references':len(generated),
             'old_references_reused':len(merged)-len(generated),'all_new_body_references':len(new['references']),
             'raw_reference_output_sha256':first_hash,'executed_source_ids':first_executed,
             'seconds_including_repeat':round(elapsed,4),'checks':checks,'receipt':receipt,
             'supplementary_sources_excluded':sum(not ARTICLE.match(s['heading']) for s in sources.values()),
             'catalogue_setup':'Document aliases and source metadata still read across selected law; not all processing is incremental.'}
        audit.save(target/'result.json',row)
        results.append(row)
    main_path=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    result={'status':'PASS' if all(all(x['checks'].values()) for x in results) else 'FAIL',
            'transitions':results,'checks_passed':sum(sum(x['checks'].values()) for x in results),
            'checks_total':sum(len(x['checks']) for x in results),
            'max_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
            'main_unchanged':audit.sha(main_path)==frozen['inputs'][str(main_path.relative_to(ROOT))],
            'llm_calls':0,'network_calls':0,'production_publisher':False,
            'limitations':['Full XML parsing and target catalogue setup retained.',
                'Only body explicit references. External target documents, terminology/Wiki and annex binaries excluded.',
                'Reuse demonstrated with canonical bindings, not direct copying of old physical source IDs.',
                'Isolated native reference and state application audit. Oracle/Dataiku/GENOS integration not performed.']}
    audit.save(out/'result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
