"""Small, explicitly versioned online projection of immutable authoring knowledge."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
from semantic_runtime.contracts import sha, write
from . import glossary_knowledge

VERSION = 'glossary-serving-v2'
FILES = ('nodes.sqlite', 'translations.sqlite', 'identity.sqlite', 'lookup.sqlite')


def verify(directory, *, force=False):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('schema_version') != VERSION:
        raise ValueError('Unsupported glossary serving projection')
    rows = {r['path']: r for r in manifest['files']}
    if set(rows) != set(FILES) or len(rows) != len(manifest['files']):
        raise ValueError('Incomplete glossary serving inventory')
    from semantic_runtime.storage import verify_store_binding
    for name, row in rows.items():
        path = directory / name
        if path.is_symlink() or Path(str(path)+'-wal').exists() or path.stat().st_size != row['bytes']:
            raise ValueError('Unbound glossary serving file: '+name)
        if force:
            if sha(path) != row['sha256']: raise ValueError('Glossary projection hash mismatch')
        else:
            verify_store_binding(path, row['sha256'])
    return manifest


def project(knowledge, dictionary, output):
    """Keep definitions/labels exactly; raw RDF edges and audit payload stay at source."""
    knowledge, dictionary, output = map(Path, (knowledge, dictionary, output))
    source = glossary_knowledge.verify(knowledge, force=True)
    if output.exists(): raise ValueError('Glossary projection output already exists')
    output.mkdir(parents=True)
    nodes = output / 'nodes.sqlite'
    with closing(sqlite3.connect(nodes)) as db:
        db.execute('ATTACH DATABASE ? AS source', ((knowledge/'graph.sqlite').resolve().as_uri()+'?mode=ro',))
        db.executescript('''
          CREATE TABLE node(source TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,
                            PRIMARY KEY(source,id)) WITHOUT ROWID;
          INSERT INTO node SELECT source,id,json_object('definitions',json(COALESCE(json_extract(payload,'$.definitions'),'[]'))) FROM source.node;
          CREATE TABLE label(source TEXT NOT NULL,node_id TEXT NOT NULL,normalized TEXT NOT NULL);
          INSERT INTO label SELECT source,node_id,normalized FROM source.label WHERE normalized<>'';
          CREATE INDEX label_node ON label(source,node_id);
        ''')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Glossary projection integrity failure')
        counts = {n: db.execute('SELECT count(*) FROM '+n).fetchone()[0] for n in ('node','label')}
        db.commit()
    for name in FILES[1:]: shutil.copyfile(knowledge/name, output/name)
    original = {r['path']: r['sha256'] for r in source['files']}
    for name in FILES[1:]:
        if sha(output/name) != original[name]: raise ValueError('Copied glossary file differs')
    manifest = {'schema_version': VERSION, 'dictionary_sha256': sha(dictionary),
        'source_dictionary_sha256': source['dictionary_sha256'],
        'origin': {'path': str(knowledge.resolve()), 'manifest_sha256': sha(knowledge/'manifest.json'),
                   'graph_sha256': original['graph.sqlite']},
        'files': [{'path': n, 'sha256': sha(output/n), 'bytes': (output/n).stat().st_size} for n in FILES],
        'counts': counts, 'compiler_sha256': sha(__file__), 'canonical_approval': False,
        'audit_retained_at_origin': True, 'runtime_requires_origin': False}
    write(output/'manifest.json', manifest)
    verify(output)
    return manifest
