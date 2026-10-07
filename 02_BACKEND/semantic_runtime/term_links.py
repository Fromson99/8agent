"""Verified projection of frozen glossary spans into source navigation IDs."""
import hashlib
import time
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

from .contracts import digest, sha


def normalized(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


def compact(text):
    return re.sub(r"\s+", "", text)


def concept_id(source, node):
    return "concept:" + hashlib.sha256((source + "\0" + node).encode()).hexdigest()[:24]


def ro(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


class LinkProjector:
    def __init__(self, db, store, links, glossary, report, knowledge=None, *, direct_audit=False):
        self.db, self.store = db, store
        self.direct_audit = direct_audit
        if direct_audit:
            from .navigation_build import AuditSQL
            self.db = AuditSQL(db)
        self.paths = [Path(links), Path(glossary)]
        self.pins = {str(p): sha(p) for p in self.paths}
        value = json.loads(Path(report).read_text()) if not isinstance(report, dict) else report
        identity = value["identity"]
        if value["files"]["links.sqlite"] != self.pins[str(self.paths[0])]:
            raise ValueError("linkage SQLite binding mismatch")
        if identity["source_sha256"] not in {store.manifest["store_sha256"], store.manifest.get("source_store_sha256")}:
            raise ValueError("linkage belongs to another source generation")
        if identity.get("source_mode") == "immutable-input-reference":
            if "source.sqlite" in value["files"]:
                raise ValueError("unexpected linked source copy")
        elif value["files"].get("source.sqlite") != identity["source_sha256"]:
            raise ValueError("linkage source copy binding mismatch")
        if identity["glossary"]["dictionary_sha256"] != self.pins[str(self.paths[1])]:
            raise ValueError("linkage belongs to another glossary")
        self.binding = {"report_sha256": digest(value), "links_sha256": self.pins[str(self.paths[0])],
                        "glossary_sha256": self.pins[str(self.paths[1])], "source_sha256": identity["source_sha256"],
                        "helper_sha256": sha(__file__), "knowledge_manifest_sha256": None}
        self.links, self.glossary, self.lookup = ro(links), ro(glossary), None
        tables = {r[0] for r in self.links.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"occurrence", "catalogue_link", "knowledge_catalogue_link", "entry", "surface"} <= tables:
            self.close()
            raise ValueError("current glossary link schema required")
        expected = identity["glossary"].get("knowledge")
        if bool(knowledge) != bool(expected):
            self.close()
            raise ValueError("knowledge binding must be explicit")
        if knowledge:
            path = Path(knowledge)
            manifest = json.loads((path / "manifest.json").read_text())
            mh = sha(path / "manifest.json")
            if mh != expected["manifest_sha256"] or manifest["dictionary_sha256"] != expected["dictionary_sha256"]:
                self.close()
                raise ValueError("knowledge manifest binding mismatch")
            payloads = {r["path"]: r for r in manifest["files"]}
            lp = path / "lookup.sqlite"
            if sha(lp) != payloads["lookup.sqlite"]["sha256"]:
                self.close()
                raise ValueError("knowledge lookup binding mismatch")
            self.paths.extend([lp, path / "manifest.json"])
            self.pins.update({str(lp): payloads["lookup.sqlite"]["sha256"], str(path / "manifest.json"): mh})
            self.lookup = ro(lp)
            self.binding["knowledge_manifest_sha256"] = mh
        self.visited = set()
        if direct_audit and db.execute("SELECT 1 FROM sqlite_master WHERE name='term_surface'").fetchone():
            self.visited = {r[0] for r in db.execute("SELECT item FROM navigation_checkpoint WHERE stage='document'")}
            return
        self.db.executescript("""
          CREATE TABLE term_surface(term_id TEXT,key TEXT,text TEXT,kind TEXT,
            PRIMARY KEY(term_id,key,text,kind));
          CREATE INDEX term_surface_key ON term_surface(key);
          CREATE TABLE link_catalogue(id TEXT PRIMARY KEY,kind TEXT,key TEXT,term_id TEXT,
            status TEXT,reason TEXT,json TEXT);
          CREATE INDEX link_catalogue_key ON link_catalogue(key);
          CREATE TABLE link_occurrence(id TEXT PRIMARY KEY,key TEXT,document_id TEXT,block_id TEXT,
            unit_id TEXT,start INTEGER,end INTEGER,source_id TEXT,source_text_sha256 TEXT,
            source_artifact_sha256 TEXT,matched_text TEXT,status TEXT,reason TEXT);
          CREATE INDEX link_occurrence_key ON link_occurrence(key);
          CREATE TABLE occurrence_evidence(occurrence_id TEXT,catalogue_id TEXT,term_id TEXT,
            source_id TEXT,status TEXT,reason TEXT,PRIMARY KEY(occurrence_id,catalogue_id));
          CREATE TABLE occurrence_origin(term_id TEXT,source_id TEXT,origin TEXT,
            PRIMARY KEY(term_id,source_id,origin));
          CREATE TABLE source_literal(id TEXT PRIMARY KEY,document_id TEXT,text TEXT);
          CREATE INDEX source_literal_scope ON source_literal(document_id);
        """)
        self._catalogue()
        self._review_relations()

    def close(self):
        for name in ("links", "glossary", "lookup"):
            db = getattr(self, name, None)
            if db is not None:
                db.close()

    def _term(self, ident, label, source, node, surfaces):
        value = {"id": ident, "label": label, "source": source, "node_id": node,
                 "status": "SOURCE_TERM_NOT_CANONICAL_MEANING", "canonical_approval": False}
        self.db.execute("INSERT OR IGNORE INTO term VALUES (?,?)", (ident, json.dumps(value, ensure_ascii=False)))
        self.db.executemany("INSERT OR IGNORE INTO term_surface VALUES (?,?,?,?)",
                           [(ident, r["key"], r["text"], r["kind"]) for r in surfaces])

    def _catalogue(self):
        # Include source entries even without corpus hits so query resolution stays complete.
        for incoming, origin in [(self.glossary, "dictionary"), (self.links, "local_definition")]:
            surfaces = {}
            for r in incoming.execute("SELECT * FROM surface ORDER BY entry_id,key,kind"):
                surfaces.setdefault(r["entry_id"], []).append(dict(r))
            for row in incoming.execute("SELECT id,label,source,provenance FROM entry ORDER BY id"):
                self._term(row["id"], row["label"], row["source"], row["id"], surfaces.get(row["id"], []))
                if row['source'] == 'corpus_definition':
                    scoped = json.loads(row['provenance']).get('document_id') or '__UNRESOLVED_DOCUMENT__'
                    value = json.loads(self.db.execute('SELECT json FROM term WHERE id=?', (row['id'],)).fetchone()[0])
                    value['scope_document_id'] = scoped
                    self.db.execute('UPDATE term SET json=? WHERE id=?', (json.dumps(value,ensure_ascii=False),row['id']))
        for incoming in (self.glossary, self.links):
            for row in incoming.execute('SELECT id,document_id FROM corpus_definition'):
                current = self.db.execute('SELECT json FROM term WHERE id=?', (row['id'],)).fetchone()
                value = json.loads(current[0]); value['scope_document_id'] = row['document_id']
                self.db.execute('UPDATE term SET json=? WHERE id=?', (json.dumps(value,ensure_ascii=False),row['id']))
        for table, kind in [("catalogue_link", "dictionary"), ("knowledge_catalogue_link", "knowledge")]:
            for raw in self.links.execute("SELECT * FROM " + table + " ORDER BY key"):
                row = dict(raw); valid = False
                if kind == "dictionary":
                    tid = row["entry_id"]
                    valid = bool(self.glossary.execute("SELECT 1 FROM surface WHERE key=? AND entry_id=?",
                                                       (row["key"], tid)).fetchone())
                    scope = self.glossary.execute("SELECT document_id FROM corpus_definition WHERE id=?", (tid,)).fetchone()
                    if scope:row["scope_document_id"] = scope[0]
                    else:
                        term = json.loads(self.db.execute('SELECT json FROM term WHERE id=?', (tid,)).fetchone()[0])
                        if term.get('scope_document_id'):row['scope_document_id'] = term['scope_document_id']
                else:
                    tid = concept_id(row["source"], row["node_id"])
                    valid = bool(self.lookup and self.lookup.execute("SELECT 1 FROM surface WHERE key=? AND source=? "
                        "AND node_id=? AND label=? AND kind=?", tuple(row[k] for k in ("key", "source", "node_id", "label", "kind"))).fetchone())
                    if valid:
                        self._term(tid, row["label"], row["source"], row["node_id"],
                                   [{"key": row["key"], "text": row["label"], "kind": row["kind"]}])
                self._candidate(kind, row, tid, valid)
        for row in self.links.execute("SELECT s.*,d.document_id FROM surface s JOIN corpus_definition d ON d.id=s.entry_id"):
            self._candidate("local_definition", dict(row) | {"scope_document_id": row["document_id"]}, row["entry_id"], True)

    def _review_relations(self):
        tables = {r[0] for r in self.glossary.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'sense_assertion', 'sense_candidate'} <= tables:
            return
        query = """SELECT a.*,l.entry_id AS left_entry,r.entry_id AS right_entry
                   FROM sense_assertion a JOIN sense_candidate l ON l.id=a.source
                   JOIN sense_candidate r ON r.id=a.target WHERE a.status='PROPOSED'
                   AND (a.axis='RELATION' OR (a.axis='IDENTITY' AND a.value='SAME'))"""
        for row in self.glossary.execute(query):
            if row['left_entry'] == row['right_entry'] or not json.loads(row['evidence_json']):
                continue
            if any(not self.db.execute('SELECT 1 FROM term WHERE id=?', (row[k],)).fetchone()
                   for k in ('left_entry', 'right_entry')):
                continue
            value = {'id': row['id'], 'source': row['left_entry'], 'target': row['right_entry'],
                     'code': row['value'], 'status': 'MODEL_REVIEWED_PROPOSAL',
                     'source_sense': row['source'], 'target_sense': row['target'],
                     'scope_key': row['scope_key'], 'job_id': row['job_id'],
                     'canonical_approval': False, 'reason': 'EVIDENCE_BOUND_NAVIGATION_HINT',
                     'evidence': json.loads(row['evidence_json'])}
            self.db.execute('INSERT OR IGNORE INTO edge VALUES (?,?)',
                            (value['id'], json.dumps(value, ensure_ascii=False)))

    def _candidate(self, kind, row, tid, valid):
        self.db.execute("INSERT INTO link_catalogue VALUES (?,?,?,?,?,?,?)", (
            digest([kind, row]), kind, row["key"], tid, "VALID" if valid else "HELD",
            "SOURCE_LABEL_CANDIDATE" if valid else "CATALOGUE_MEMBERSHIP_MISMATCH", json.dumps(row, ensure_ascii=False)))

    def document(self, did, blocks, block_sources):
        self.visited.add(did)
        values = []
        block_hashes = {}
        for raw in self.links.execute("SELECT * FROM occurrence WHERE document_id=? ORDER BY block_id,start,end,key", (did,)):
            row = dict(raw); block = blocks.get(str(row["block_id"]))
            sid = block_sources.get(str(row["block_id"]))
            reason, matched, block_hash, artifact_hash = "VERIFIED_EXACT_SOURCE_SPAN", "", None, None
            if not block or not sid:
                reason = "SOURCE_BLOCK_MISSING"
            else:
                text = block["text"]
                bid = str(row["block_id"])
                if bid not in block_hashes:
                    block_hashes[bid] = hashlib.sha256(text.encode()).hexdigest()
                block_hash = block_hashes[bid]
                artifact_hash = block["source_artifact_sha256"]
                if row["unit_id"] != block["unit_id"]:
                    reason = "SOURCE_UNIT_MISMATCH"
                elif type(row["start"]) is not int or type(row["end"]) is not int or not 0 <= row["start"] < row["end"] <= len(text):
                    reason = "INVALID_SOURCE_SPAN"
                else:
                    matched = text[row["start"]:row["end"]]
                    if compact(matched) != row["key"]:
                        reason = "SPAN_SURFACE_MISMATCH"
            values.append((digest(row), row["key"], did, str(row["block_id"]), row["unit_id"], row["start"], row["end"],
                sid, block_hash, artifact_hash, matched, "ACCEPTED" if reason == "VERIFIED_EXACT_SOURCE_SPAN" else "HELD", reason))
            if len(values) >= 2048:
                self.db.executemany("INSERT INTO link_occurrence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
                values.clear()
        self.db.executemany("INSERT INTO link_occurrence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", values)

    def finish(self):
        sequence = 0
        def execute(sql, *args):
            nonlocal sequence
            sequence += 1
            started, cpu = time.monotonic(), time.thread_time()
            result = self.db.execute(sql, *args)
            print(f'NAVIGATION glossary-evidence.sql-{sequence} elapsed={time.monotonic()-started:.3f}s '
                  f'thread_cpu={time.thread_time()-cpu:.3f}s', flush=True)
            return result
        for did, in self.links.execute("SELECT DISTINCT document_id FROM occurrence"):
            if did not in self.visited:
                self.document(did, {}, {})
        if self.direct_audit:
            execute("CREATE INDEX link_occurrence_accepted ON link_occurrence(key,document_id) WHERE status='ACCEPTED'")
        execute("UPDATE link_catalogue SET status='HELD',reason='NO_VERIFIED_OCCURRENCE' WHERE status='VALID' "
            "AND NOT EXISTS(SELECT 1 FROM link_occurrence o WHERE o.key=link_catalogue.key AND o.status='ACCEPTED')")
        execute("UPDATE link_catalogue SET status='HELD',reason='DEFINITION_DOCUMENT_SCOPE' WHERE status='VALID' "
            "AND json_extract(json,'$.scope_document_id') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM link_occurrence o "
            "WHERE o.key=link_catalogue.key AND o.status='ACCEPTED' AND o.document_id=json_extract(link_catalogue.json,'$.scope_document_id'))")
        execute("UPDATE link_catalogue SET status='ACCEPTED' WHERE status='VALID'")
        execute("CREATE TEMP TABLE scoped_link_catalogue AS SELECT id,key,term_id,status,reason,"
                        "json_extract(json,'$.scope_document_id') AS scope_document_id FROM link_catalogue")
        execute("CREATE INDEX temp.scoped_link_catalogue_key ON scoped_link_catalogue(key)")
        execute("INSERT INTO occurrence_evidence SELECT o.id,c.id,c.term_id,o.source_id,"
            "CASE WHEN o.status='ACCEPTED' AND c.status='ACCEPTED' AND (c.scope_document_id IS NULL OR "
            "c.scope_document_id=o.document_id) THEN 'ACCEPTED' ELSE 'HELD' END,"
            "CASE WHEN o.status!='ACCEPTED' THEN o.reason WHEN c.status!='ACCEPTED' THEN c.reason "
            "WHEN c.scope_document_id!=o.document_id THEN 'DEFINITION_DOCUMENT_SCOPE' "
            "ELSE 'VERIFIED_SOURCE_LABEL_CANDIDATE' END FROM link_occurrence o JOIN scoped_link_catalogue c ON c.key=o.key")
        execute("DROP TABLE temp.scoped_link_catalogue")
        execute("CREATE INDEX evidence_accepted_catalogue ON occurrence_evidence(catalogue_id) WHERE status='ACCEPTED'")
        execute("UPDATE link_occurrence SET status='HELD',reason='NO_ACCEPTED_CATALOGUE_CANDIDATE' "
            "WHERE status='ACCEPTED' AND NOT EXISTS(SELECT 1 FROM occurrence_evidence e WHERE e.occurrence_id=link_occurrence.id AND e.status='ACCEPTED')")
        execute("INSERT OR IGNORE INTO occurrence_origin SELECT term_id,source_id,'LEGACY_LABEL_MATCH' FROM occurrence")
        execute("INSERT OR IGNORE INTO occurrence_origin SELECT term_id,source_id,'VERIFIED_GLOSSARY_LINK' "
                        "FROM occurrence_evidence WHERE status='ACCEPTED'")
        before_pairs = self.db.execute('SELECT count(*) FROM occurrence').fetchone()[0] if self.direct_audit else 0
        added = execute("INSERT OR IGNORE INTO occurrence SELECT term_id,source_id FROM occurrence_evidence WHERE status='ACCEPTED'").rowcount
        if self.direct_audit:added = self.db.execute('SELECT count(*) FROM occurrence').fetchone()[0]-before_pairs
        counts = {}
        for table in ("link_occurrence", "link_catalogue", "occurrence_evidence"):
            counts[table] = dict(execute("SELECT status,count(*) FROM " + table + " GROUP BY status"))
        counts["candidate_kinds"] = {kind: n for kind, n in execute("SELECT kind,count(*) FROM link_catalogue GROUP BY kind")}
        counts["input_occurrences"] = self.links.execute("SELECT count(*) FROM occurrence").fetchone()[0]
        counts["added_term_source_pairs"] = added
        if execute("SELECT 1 FROM link_catalogue c WHERE c.status='ACCEPTED' AND NOT EXISTS "
                "(SELECT 1 FROM occurrence_evidence e WHERE e.catalogue_id=c.id AND e.status='ACCEPTED') LIMIT 1").fetchone():
            raise ValueError("accepted catalogue candidate has no accepted evidence")
        if sum(counts["link_occurrence"].values()) != counts["input_occurrences"]:
            raise ValueError("unaccounted glossary occurrence")
        for table, kind in [("catalogue_link", "dictionary"), ("knowledge_catalogue_link", "knowledge")]:
            if counts["candidate_kinds"].get(kind, 0) != self.links.execute("SELECT count(*) FROM " + table).fetchone()[0]:
                raise ValueError("unaccounted glossary catalogue link")
        for p in self.paths:
            if sha(p) != self.pins[str(p)]:
                raise ValueError("glossary input changed during compilation")
        return {"binding": self.binding, "counts": counts, "canonical_approval": False}
