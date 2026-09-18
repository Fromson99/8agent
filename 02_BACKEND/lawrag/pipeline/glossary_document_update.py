"""Append new document definitions to a new draft and nominate evidence review.

Existing pending candidates and new definition pairs share the GENOS review plan.
Completed observations and their evidence remain available for exact reuse.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from semantic_runtime.contracts import sha, digest, write
from . import glossary_assembly as assembly, glossary_v1 as v1
from . import glossary_definitions as definitions, glossary_knowledge


def augment(base, source, output):
    base, source, output = map(lambda p: Path(p).resolve(), (base, source, output))
    parent = assembly.inspect(base)
    knowledge = glossary_knowledge.selected_for(base)
    identity = {'parent_dictionary_sha256': parent['dictionary_sha256'],
                'source_sha256': sha(source), 'compiler_sha256': sha(__file__),
                'definition_compiler_sha256': sha(definitions.__file__)}
    if output.exists():
        report = assembly.inspect(output)
        if report['document_update']['identity'] != identity:
            raise ValueError('Document glossary inputs changed; use a new run ID')
        return report
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name, dir=output.parent))
    try:
        shutil.copyfile(base / 'dictionary.sqlite', temp / 'dictionary.sqlite')
        with closing(sqlite3.connect(':memory:')) as local, closing(v1.read_db(source)) as corpus, closing(sqlite3.connect(temp / 'dictionary.sqlite')) as db:
            local.row_factory = db.row_factory = sqlite3.Row
            v1.create_tables(local); definitions.tables(local)
            definitions.add(local, corpus, identity['source_sha256'])
            # Keep pending candidates as well as completed observations. The review
            # planner reuses only completed jobs with exactly matching evidence.
            # Previous release builders archived the parent queue. Recover it into
            # this new draft without changing the immutable parent or its ledgers.
            for table in ('external_candidate', 'review_queue'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", ('inherited_' + table,)).fetchone():
                    db.execute(f'INSERT OR IGNORE INTO {table} SELECT * FROM inherited_{table}')
            added = []
            for row in local.execute('SELECT * FROM corpus_document'):
                existing = db.execute('SELECT * FROM corpus_document WHERE document_id=?', (row['document_id'],)).fetchone()
                if existing and existing['source_sha256'] != row['source_sha256']:
                    raise ValueError('Document version ID reused with changed content')
                db.execute('INSERT OR IGNORE INTO corpus_document VALUES (?,?,?)', tuple(row))
            for d in local.execute('SELECT * FROM corpus_definition ORDER BY id'):
                old = db.execute('SELECT id FROM corpus_definition WHERE document_id=? AND block_id=? AND term_start=? AND term_end=? AND source_text_sha256=?',
                                 (d['document_id'], d['block_id'], d['term_start'], d['term_end'], d['source_text_sha256'])).fetchone()
                if old:
                    continue
                entry = local.execute('SELECT * FROM entry WHERE id=?', (d['id'],)).fetchone()
                db.execute('INSERT INTO entry VALUES (?,?,?,?,?,?,?,?)', tuple(entry))
                db.executemany('INSERT INTO surface VALUES (?,?,?,?)',
                               [tuple(r) for r in local.execute('SELECT * FROM surface WHERE entry_id=?', (d['id'],))])
                db.execute('INSERT INTO corpus_definition VALUES (' + ','.join('?' * len(d)) + ')', tuple(d))
                db.execute('INSERT INTO classification VALUES (?,?)', (d['id'], 'CORPUS_PRESENT'))
                added.append((d['id'], d['key']))
            db.executemany('INSERT OR IGNORE INTO occurrence VALUES (?,?,?,?,?,?)', [tuple(r) for r in local.execute('SELECT * FROM occurrence')])
            for ident, key in added:
                targets = db.execute('SELECT DISTINCT entry_id FROM surface WHERE key=? AND entry_id!=? ORDER BY entry_id', (key, ident)).fetchall()
                for target, in targets:
                    db.execute('INSERT INTO external_candidate VALUES (?,?,?,?,?,?,?,?)',
                               (digest([ident, target, identity]), ident, target, target, key,
                                'NEW_DOCUMENT_DEFINITION_LABEL', None, 'MEANING_REVIEW'))
                db.execute('INSERT INTO review_queue VALUES (?,?,?)',
                           (ident, 'MEANING_REVIEW' if targets else 'UNLINKED_REVIEW', len(targets)))
            root_hash = (glossary_knowledge.binding(knowledge)['dictionary_sha256'] if knowledge
                         else parent.get('document_update', {}).get('root_dictionary_sha256', parent['dictionary_sha256']))
            report = {**parent, 'identity': {**parent.get('identity', {}), 'corpus': str(source.parent),
                                           'corpus_sha256': identity['source_sha256']},
                      'collection': parent.get('collection', {'complete': False}),
                      'document_update': {'identity': identity, 'root_dictionary_sha256': root_hash,
                                          'new_definitions': len(added), 'review_policy': 'existing-and-new-evidence',
                                          'canonical_approval': False},
                      'counts': {**parent.get('counts', {}), **v1.counts(db),
                                 'corpus_definitions': definitions.counts(db)},
                      'status': 'draft', 'canonical_approval': False, 'runtime_promoted': False}
            if knowledge:
                report['knowledge_binding'] = {'path': str(knowledge), 'manifest_sha256': sha(knowledge / 'manifest.json')}
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('report', v1.encode(report)))
            db.commit()
            if db.execute('PRAGMA foreign_key_check').fetchone() or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Document glossary integrity failure')
        report['dictionary_sha256'] = sha(temp / 'dictionary.sqlite')
        write(temp / 'report.json', report)
        if sha(source) != identity['source_sha256'] or assembly.inspect(base)['dictionary_sha256'] != identity['parent_dictionary_sha256']:
            raise ValueError('Document glossary input changed')
        os.rename(temp, output)
        return report
    except BaseException:
        shutil.rmtree(temp)
        raise
