"""Read-only checks of actual Gold consumers before and after the local width change."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261104-gold-docid100-local'
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import connect


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def verify(phase):
    path = OUT / ('consumers-' + phase + '.json')
    if path.exists():
        raise RuntimeError('Preserve existing verification; inspect instead of overwriting')
    logging.disable(logging.CRITICAL)
    result = {'model_calls': 0, 'embedding_calls': 0, 'data_writes': 0, 'checks': []}
    with connect.open_store(seconds=180, max_calls=500) as (store, request, transport):
        cfg = store.gold_ports.mapping
        expected = 'VARCHAR2(100 BYTE)' if phase == 'after' else 'VARCHAR2(1000 BYTE)'
        for key in ('DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRCH_ROW', 'ONTL_ANC', 'VCTR_ITEM'):
            assert cfg.tables[key]['columns']['DOC_ID']['type'] == expected
        store.selection.require_latest()
        result.update(mapping=store.gold_ports.preflight, query_release_id=request.release_id,
                      documents=len(request.sources.allowed))
        result['checks'].append('active_mapping_and_actual_13_tables_60_columns')
        did = sorted(request.sources.allowed)[0]
        document = request.sources.document(did)
        block = request.sources.blocks(did, limit=1)['rows'][0]
        anchor = {'document_id': did, 'version': document['source_artifact_sha256'], 'unit_id': block['unit_id']}
        source = store.gold_ports.source_reader(anchor)
        assert block['text'] in source
        result['checks'].append('document_block_unit_source_and_version')
        glossary = store.gold_ports.glossary_binding()
        try:
            page = glossary.reader.lookup('이사회', limit=1)
            assert page['concepts']
            first = page['concepts'][0]
            ref = glossary.restore(first['source'], first['node_id'])
            store.gold_ports.ontology.glossary_validator([ref])
        finally:
            glossary.reader.close()
        result['checks'].append('query_and_glossary_reference_restore')
        from gold_connection import VectorReader
        parent = SimpleNamespace(release_id=request.records.manifest['extension']['base_query_id'],
                                 snapshot=request.snapshot, sql=request.sql, sources=request.sources)
        reader = VectorReader(parent, cfg)
        head = reader.active()
        meta = reader.metadata(head['VCTR_POST_ID'])
        row = request.sql.query('SELECT VECTOR_SERIALIZE(EMBD_VCTR_VALU RETURNING CLOB) AS V FROM ' + cfg.table('VCTR_ITEM') +
                                ' WHERE VCTR_POST_ID=:pub AND DOC_ID=:did FETCH FIRST 1 ROWS ONLY',
                                [('pub', head['VCTR_POST_ID'], 'VARCHAR2'), ('did', did, 'VARCHAR2')], limit=1)[0]
        vector = json.loads(row['V'])
        hits = reader.search(vector, profile_sha256=meta['completion']['profile_sha256'], documents={did}, limit=3)
        assert len(vector) == 1024 and hits and all(r['DOC_ID'] == did for r in hits)
        result['checks'].append('stored_vector_search_scope_and_publication')
        # Actual publication lookup uses RGLT_DOC_ID through the active mapping.
        published = json.loads((ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-ontology-publication/prepared.json').read_text())
        ontology = []
        for entry in published['entries']:
            original = entry['work']['originals'][0]
            a = original['anchor']
            assert store.gold_ports.source_reader(a) == original['text']
            found = store.gold_ports.ontology.lookup(a, {a['document_id']})
            assert len(found) == 1
            assert not store.gold_ports.ontology.lookup(a, set())
            assert not store.gold_ports.ontology.lookup({**a, 'version': 'not-current-version'}, {a['document_id']})
            ontology.append(found)
        result['checks'].append('three_ontology_publications_originals_scope_and_version')
        result['content_sha256'] = {name: digest(value) for name, value in
                                   [('document', document), ('block', block), ('source', source),
                                    ('glossary', page), ('vector_input', vector), ('vector_hits', hits),
                                    ('ontology_publications', ontology)]}
        result.update(status='PASS', sql_calls=request.sql.calls, vector_dimensions=len(vector), vector_rows=len(hits))
    if phase == 'after':
        before = json.loads((OUT / 'consumers-before.json').read_text())
        assert result['content_sha256'] == before['content_sha256'], 'Consumer output changed'
        assert result['query_release_id'] == before['query_release_id']
        result['before_after_content_identical'] = True
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['before', 'after'])
    verify(parser.parse_args().phase)
