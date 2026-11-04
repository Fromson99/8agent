"""Finite dynamic query families used by the shared SQLite/Oracle consumers.

Cardinality of IN lists and literal/bind values are handled by query_shape;
these are structural alternatives (filters, projections and sort clauses).
Keep each family linked to its actual producer, and run the consumer tests.
"""


def queries():
    for table, key, value in [('term', 'id', 'json'), ('definition', 'id', 'json'), ('term_stats', 'term_id', 'n')]:
        for sql in [f'SELECT {value} FROM {table} WHERE 1=1 AND {key}=?',
                    f'SELECT {key} FROM {table} WHERE 1=1 ORDER BY {key}',
                    f'SELECT COUNT(*) FROM {table} WHERE 1=1',
                    f'SELECT {key},{value} FROM {table} WHERE 1=1 ORDER BY {key}']:
            yield sql, 'oracle_query_index.py:SQLMap'
    for extra in ('', ' AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<?'):
        predicate = 'document_id=?' + extra
        yield 'SELECT count(*) FROM source_block WHERE ' + predicate, 'document_browser.py:read'
        yield ('SELECT * FROM source_block WHERE ' + predicate +
               ' ORDER BY CAST(block_id AS INTEGER),block_id LIMIT ? OFFSET ?'), 'document_browser.py:read'
        yield ('SELECT document_id,block_id,unit_id FROM source_block WHERE document_id IN (?) AND instr(legal_normalized(text),?)>0' +
               extra + ' ORDER BY document_id,CAST(block_id AS INTEGER)'), 'legal_agent/exploration_tools.py:literal'
        yield ('SELECT document_id,block_id,unit_id FROM source_block WHERE document_id IN (?) AND instr(legal_normalized(text),?)>0' +
               extra + ' ORDER BY document_id,CAST(block_id AS INTEGER) LIMIT ? OFFSET ?'), 'legal_agent/source_tools.py:search_text'
    yield 'SELECT document_id,block_id,unit_id,text FROM source_block WHERE document_id IN (?) ORDER BY document_id,CAST(block_id AS INTEGER)', 'legal_agent/exploration_tools.py:literal'
    # The existing label search accepts one to eight labels. Oracle requires
    # CASE expressions for their numeric sum; those are prepared by the tool.
    for count in range(1, 9):
        for excluded in ('', ' AND id NOT IN (?)'):
            scores = '+'.join('(instr(text,?)>0)' for _ in range(count))
            predicates = ' OR '.join('instr(text,?)>0' for _ in range(count))
            yield ('SELECT id,text,(' + scores + ') AS score FROM source_literal WHERE document_id IN (?) AND (' +
                   predicates + ')' + excluded + ' ORDER BY score DESC,id LIMIT ?'), 'term_index.py:search_labels'
    yield 'SELECT o.source_id,o.term_id FROM occurrence o JOIN source s ON s.id=o.source_id WHERE o.term_id IN (?) AND s.document_id IN (?)', 'term_index.py:search'
    yield 'SELECT DISTINCT r.id,r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id IN (?)', 'term_index.py:navigation_menu'
    yield 'SELECT id,json FROM definition WHERE document_id IN (?)', 'term_index.py:IndexTools'
    yield 'SELECT id,json FROM reference WHERE id IN (?)', 'term_index.py:reference_batch'
    yield "SELECT count(*) FROM definition WHERE document_id IN (?) AND instr(json_extract(json,'$.key'),?)>0", 'legal_agent/source_tools.py:lookup_definition'
    yield "SELECT json FROM definition WHERE document_id IN (?) AND instr(json_extract(json,'$.key'),?)>0 ORDER BY id LIMIT ? OFFSET ?", 'legal_agent/source_tools.py:lookup_definition'
    yield 'SELECT * FROM source_block WHERE document_id=? AND block_id IN (?)', 'storage.py:sources'
    yield 'SELECT block_id,LENGTH(text),CASE WHEN instr(text,char(0))>0 THEN text END FROM source_block WHERE document_id=? AND block_id IN (?)', 'storage.py:source_lengths'
    yield 'SELECT o.source_id FROM occurrence o JOIN source s ON s.id=o.source_id WHERE o.term_id=? AND s.document_id IN (?) ORDER BY o.source_id', 'legal_agent/workflow_relation_cards.py:occurrences'
    for clause in ('', ' AND r.id IN (SELECT value FROM json_each(?))'):
        yield ('SELECT DISTINCT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id '
               'WHERE e.source_id=? AND r.id>?' + clause + ' ORDER BY r.id LIMIT ?'), 'legal_agent/unit_relations.py:catalog'
    yield 'SELECT DISTINCT label,key FROM label WHERE length(key)>=2 AND source IN (?)', 'navigation_match.py:_build'
    yield 'SELECT 1 FROM occurrence o JOIN source s ON s.id=o.source_id WHERE o.term_id=? AND s.document_id IN (?) LIMIT 1', 'navigation_match.py:_in_scope'
    for table in ('official_relation', 'moleg_relation'):
        yield ('SELECT DISTINCT source_id,code FROM ' + table +
               ' WHERE target_id=? AND code IN (?)'), 'navigation_match.py:_relations'
    yield 'SELECT DISTINCT source,node_id,label FROM label WHERE key=? AND source IN (?) ORDER BY source,node_id', 'navigation_match.py:starts'
    fields = ('id', 'document_id', 'document_name', 'heading', 'unit_id')
    yield ('SELECT ' + ','.join("json_extract(json,'$." + f + "')" for f in fields) +
           ' FROM source ORDER BY id'), 'reference_build.py:BuildSources.metadata'
    yield 'SELECT block_id,unit_id FROM source_block WHERE document_id=? AND block_id IN (?)', 'ontology_work/capture.py:capture'
    yield 'SELECT DISTINCT unit_id FROM source_block WHERE document_id=? AND block_id IN (?)', 'ontology_work/runtime.py:runtime'
    for family in ('family', 'NULL'):
        yield 'SELECT source_id,unit_id,parent_id,ordinal,surface,block_ids,' + family + ' FROM source_unit_map', 'term_references.py:unit_trees'
    for condition in ('entry_id=?', 'source=? AND node_id=?'):
        yield 'SELECT * FROM concept_mapping WHERE ' + condition + ' ORDER BY id LIMIT ?', 'full_glossary_connections.py:_mappings'
    for column in ('subject', 'target'):
        yield 'SELECT * FROM source_edge WHERE source=? AND ' + column + '=? ORDER BY id LIMIT ?', 'full_glossary_connections.py:_relations'
    columns = ('id', 'source_id', 'target_id', 'code', 'label', 'request_id')
    # SQLite preserves declaration order; published canonical JSON schemas
    # preserve sorted column keys. Both metadata readers generate this family.
    for order in (columns, sorted(columns)):
        fields = ','.join('"' + n + '"' for n in order)
        yield ('SELECT ' + fields + ' FROM official_relation WHERE source_id=? UNION SELECT ' + fields +
               ' FROM official_relation WHERE target_id=? ORDER BY id LIMIT ?'), 'full_glossary_connections.py:_relations'
        for endpoint in ('source_id', 'target_id'):
            yield ('SELECT ' + fields + ' FROM official_relation WHERE ' + endpoint + '=? ORDER BY id LIMIT ?'), 'Gold:engine_glossary.Links._relations'
    exact = 'SELECT DISTINCT source,node_id FROM label WHERE key=?'
    yield 'SELECT count(*) FROM (' + exact + ')', 'full_glossary.py:lookup'
    ranked = 'SELECT source,node_id,row_number() OVER(PARTITION BY source ORDER BY node_id) AS n FROM (' + exact + ')'
    yield 'SELECT source,node_id FROM (' + ranked + ') ORDER BY n,source,node_id LIMIT ? OFFSET ?', 'full_glossary.py:lookup'
    for table in ('document', 'source_unit', 'source_block', 'source', 'term', 'definition', 'reference', 'edge', 'occurrence'):
        yield 'SELECT count(*) FROM ' + table, 'relational:count'
