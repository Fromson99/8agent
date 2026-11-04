"""Replay exact glossary evidence without storing the occurrence/candidate product.

The retained rows are immutable validated spans, finalized catalogue candidates
and the original label-match pairs. Views reconstruct all accepted/held evidence
and origins with the same rules as LinkProjector's materialized audit.
"""
from .contracts import sha

PROFILE = 'factorized-v1'
SCHEMA = 'term-navigation-storage-v4'
TABLES = {'link_catalogue', 'link_occurrence', 'audit_term', 'audit_source', 'audit_legacy_origin'}
VIEWS = {'occurrence_evidence', 'occurrence_origin'}


def create(db):
    # NO_ACCEPTED_CATALOGUE_CANDIDATE is the sole post-validation span mutation.
    # Reverse it when replaying the evidence computed before that mutation.
    accepted = "(o.status='ACCEPTED' OR o.reason='NO_ACCEPTED_CATALOGUE_CANDIDATE')"
    scope = "json_extract(c.json,'$.scope_document_id')"
    db.executescript(f"""
      CREATE TABLE construction.audit_term(key INTEGER PRIMARY KEY,id TEXT NOT NULL UNIQUE);
      CREATE TABLE construction.audit_source(key INTEGER PRIMARY KEY,id TEXT NOT NULL UNIQUE);
      CREATE TABLE construction.audit_legacy_origin(term_key INTEGER NOT NULL,source_key INTEGER NOT NULL,
        PRIMARY KEY(term_key,source_key)) WITHOUT ROWID;
      CREATE VIEW construction.occurrence_evidence AS
        SELECT o.id AS occurrence_id,c.id AS catalogue_id,c.term_id,o.source_id,
          CASE WHEN {accepted} AND c.status='ACCEPTED' AND
            ({scope} IS NULL OR {scope}=o.document_id) THEN 'ACCEPTED' ELSE 'HELD' END AS status,
          CASE WHEN NOT {accepted} THEN o.reason WHEN c.status!='ACCEPTED' THEN c.reason
            WHEN {scope}!=o.document_id THEN 'DEFINITION_DOCUMENT_SCOPE'
            ELSE 'VERIFIED_SOURCE_LABEL_CANDIDATE' END AS reason
        FROM link_occurrence o JOIN link_catalogue c ON c.key=o.key;
      CREATE VIEW construction.occurrence_origin AS
        SELECT t.id AS term_id,s.id AS source_id,'LEGACY_LABEL_MATCH' AS origin
        FROM audit_legacy_origin l JOIN audit_term t ON t.key=l.term_key
          JOIN audit_source s ON s.key=l.source_key
        UNION ALL
        SELECT DISTINCT term_id,source_id,'VERIFIED_GLOSSARY_LINK'
        FROM occurrence_evidence WHERE status='ACCEPTED';
    """)


def finish(projector, execute):
    db = projector.db.db
    before = db.execute('SELECT count(*) FROM occurrence').fetchone()[0]
    db.execute('INSERT INTO construction.audit_term SELECT rowid,id FROM term')
    db.execute('INSERT INTO construction.audit_source SELECT rowid,id FROM source')
    db.execute('INSERT INTO construction.audit_legacy_origin SELECT term_key,source_key FROM occurrence_keys')
    if db.execute('SELECT count(*) FROM construction.audit_legacy_origin').fetchone()[0] != before:
        raise ValueError('Legacy origin snapshot changed')
    # Do not materialize the join, its indexes, or a second text-ID origin copy.
    execute("UPDATE link_occurrence SET status='HELD',reason='NO_ACCEPTED_CATALOGUE_CANDIDATE' "
        "WHERE status='ACCEPTED' AND NOT EXISTS(SELECT 1 FROM link_catalogue c "
        "WHERE c.key=link_occurrence.key AND c.status='ACCEPTED' AND "
        "(json_extract(c.json,'$.scope_document_id') IS NULL OR "
        "json_extract(c.json,'$.scope_document_id')=link_occurrence.document_id))")
    # The runtime occurrence view enforces its integer coordinates as before.
    execute("INSERT OR IGNORE INTO occurrence SELECT term_id,source_id "
            "FROM occurrence_evidence WHERE status='ACCEPTED'")
    added = db.execute('SELECT count(*) FROM occurrence').fetchone()[0] - before
    return projector.finish_counts(execute, added, factorized=True)


def evidence_counts(db, qualified='occurrence_evidence'):
    # A two-counter aggregate streams the join; GROUP BY would sort every pair.
    accepted, held = db.execute('SELECT coalesce(sum(status=\'ACCEPTED\'),0),'
                               'coalesce(sum(status=\'HELD\'),0) FROM ' + qualified).fetchone()
    return {status: n for status, n in [('ACCEPTED', accepted), ('HELD', held)] if n}


def verify_relations(db, manifest):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    views = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    if tables != TABLES or views != VIEWS:
        raise ValueError('Factorized audit physical coverage changed')
    if manifest.get('audit_profile') != PROFILE:
        raise ValueError('Factorized audit profile mismatch')
    for kind in ('term', 'source'):
        if db.execute(f'SELECT 1 FROM audit_legacy_origin l LEFT JOIN audit_{kind} d '
                      f'ON d.key=l.{kind}_key WHERE d.key IS NULL LIMIT 1').fetchone():
            raise ValueError('Factorized audit legacy coordinate missing')


def policy():
    return {'audit_profile': PROFILE, 'replay_schema': 'glossary-evidence-replay-v1',
            'replay_compiler_sha256': sha(__file__),
            'physical_tables': sorted(TABLES), 'logical_views': sorted(VIEWS),
            'materialized_candidate_product': False}
