"""Bounded source reads and exact literal suffix lookup for reference compilation."""
from collections import OrderedDict
import hashlib
import json
import re

_BOUNDARY = re.compile(r'[가-힣A-Za-z0-9]')


class LiteralSuffixIndex:
    """Equivalent to longest (?<![가-힣A-Za-z0-9])literal\\s*$ match.

    Traversal depends on the input suffix, never on the number of registered
    titles. Trying whitespace endings also preserves literal trailing spaces.
    """
    def __init__(self, keys):
        self.root = {}
        for ordinal,key in enumerate(keys):
            node = self.root
            for char in reversed(key):
                node = node.setdefault(char, {})
            node.setdefault(None, (key,ordinal))
        self.visits = 0

    def match(self, text):
        best = None
        end = len(text)
        self.visits = 0
        while True:
            node, start = self.root, end
            while True:
                terminal = node.get(None)
                key = terminal[0] if terminal is not None else None
                if key is not None and (start == 0 or not _BOUNDARY.fullmatch(text[start-1])):
                    if best is None or (len(key),-terminal[1]) > (len(best[0]),-best[1]):
                        best = terminal
                if not start:
                    break
                self.visits += 1
                node = node.get(text[start-1])
                if node is None:
                    break
                start -= 1
            if not end or not text[end-1].isspace():
                break
            end -= 1
        return best[0] if best is not None else None


class BuildSources:
    """Small metadata catalogue; source JSON decoded only when needed."""
    def __init__(self, db, max_bytes=8*1024*1024, max_entries=64):
        self.db, self.max_bytes, self.max_entries = db, max_bytes, max_entries
        self.cache, self.bytes = OrderedDict(), 0

    def __iter__(self):
        for row in self.db.execute('SELECT json FROM source ORDER BY id'):
            yield json.loads(row[0])

    def metadata(self):
        fields = ('id','document_id','document_name','heading','unit_id')
        query = 'SELECT '+','.join("json_extract(json,'$."+f+"')" for f in fields)+' FROM source ORDER BY id'
        for row in self.db.execute(query):
            yield dict(zip(fields,row))

    def blocks(self, did):
        for row in self.db.execute('SELECT json FROM source WHERE document_id=? ORDER BY id',(did,)):
            yield from json.loads(row[0])['blocks']

    def __getitem__(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key][0]
        row = self.db.execute('SELECT json FROM source WHERE id=?',(key,)).fetchone()
        if row is None:
            raise KeyError(key)
        # Budget serialized UTF-8 bytes; decoded objects carry Python overhead.
        size = len(row[0].encode())
        value = json.loads(row[0])
        if size <= self.max_bytes:
            while self.cache and (self.bytes+size > self.max_bytes or len(self.cache) >= self.max_entries):
                _,(_,old) = self.cache.popitem(last=False)
                self.bytes -= old
            self.cache[key] = (value,size)
            self.bytes += size
        return value


class ReferenceCheckpoint:
    """Source boundaries retain all block-local continuation state in one unit."""
    def __init__(self, db):
        self.db = db
        self.enabled = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='navigation_checkpoint'").fetchone())

    def counts(self):
        if self.enabled:
            row = self.db.execute("SELECT json FROM navigation_checkpoint WHERE stage='reference-counts' AND item='' ").fetchone()
            if row:return json.loads(row[0])
        return {'total':0,'unresolved':0}

    def sources(self, sources, counts):
        if not self.enabled:
            yield from sources
            return
        pending = 0
        for (sid,) in self.db.execute('SELECT id FROM source ORDER BY id'):
            if self.db.execute("SELECT 1 FROM navigation_checkpoint WHERE stage='reference-source' AND item=?",(sid,)).fetchone():
                continue
            yield sources[sid]
            self.db.execute("INSERT INTO navigation_checkpoint VALUES ('reference-source',?,'{}')",(sid,))
            self.db.execute("INSERT OR REPLACE INTO navigation_checkpoint VALUES ('reference-counts','',?)",(json.dumps(counts),))
            pending += 1
            if pending % 64 == 0:
                self.db.commit()
        self.db.commit()


class ReferenceWriter:
    def __init__(self, db):
        self.db = db
        self.shared = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='reference_payload'").fetchone())
        self.last_text = self.last_hash = self.last_role = None
        self.stored_hash = None

    def witness(self, text, role):
        if text != self.last_text:
            self.last_text = text
            self.last_hash = hashlib.sha256(text.encode()).hexdigest()
            self.last_role = role(text) if role is not None else None
        return self.last_hash, self.last_role

    def insert(self, value, *, ignore=True):
        if self.shared:
            value = dict(value)
            text = value.pop('source_text')
            key = value['source_text_sha256']
            if self.stored_hash != key:
                old = self.db.execute('SELECT text FROM reference_body WHERE sha256=?',(key,)).fetchone()
                if old and old[0] != text:raise ValueError('reference witness collision')
                self.db.execute('INSERT OR IGNORE INTO reference_body VALUES (?,?)',(key,text))
                self.stored_hash = key
            table = 'reference_payload'
        else:table = 'reference'
        self.db.execute(('INSERT OR IGNORE' if ignore else 'INSERT')+' INTO '+table+' VALUES (?,?,?)',
                        (value['id'],value['document_id'],json.dumps(value,ensure_ascii=False)))


def shared_reference_schema(db):
    db.execute('DROP TABLE reference')
    db.executescript('''
      CREATE TABLE reference_body(sha256 TEXT PRIMARY KEY,text TEXT NOT NULL);
      CREATE TABLE reference_payload(id TEXT PRIMARY KEY,document_id TEXT,json TEXT NOT NULL);
      CREATE INDEX reference_payload_document ON reference_payload(document_id);
      CREATE VIEW reference AS SELECT r.id,r.document_id,
        json_set(r.json,'$.source_text',b.text) AS json FROM reference_payload r
        JOIN reference_body b ON b.sha256=json_extract(r.json,'$.source_text_sha256');
      CREATE TRIGGER reference_insert INSTEAD OF INSERT ON reference BEGIN
        SELECT CASE WHEN json_type(NEW.json,'$.source_text') IS NOT 'text' OR
          json_type(NEW.json,'$.source_text_sha256') IS NOT 'text' THEN RAISE(ABORT,'invalid reference witness') END;
        SELECT CASE WHEN EXISTS(SELECT 1 FROM reference_body WHERE sha256=json_extract(NEW.json,'$.source_text_sha256')
          AND text!=json_extract(NEW.json,'$.source_text')) THEN RAISE(ABORT,'reference witness collision') END;
        INSERT OR IGNORE INTO reference_body VALUES(json_extract(NEW.json,'$.source_text_sha256'),json_extract(NEW.json,'$.source_text'));
        INSERT INTO reference_payload VALUES(NEW.id,NEW.document_id,json_remove(NEW.json,'$.source_text'));
      END;
      CREATE TRIGGER reference_update INSTEAD OF UPDATE ON reference BEGIN
        SELECT CASE WHEN json_type(NEW.json,'$.source_text') IS NOT 'text' OR
          json_type(NEW.json,'$.source_text_sha256') IS NOT 'text' THEN RAISE(ABORT,'invalid reference witness') END;
        SELECT CASE WHEN EXISTS(SELECT 1 FROM reference_body WHERE sha256=json_extract(NEW.json,'$.source_text_sha256')
          AND text!=json_extract(NEW.json,'$.source_text')) THEN RAISE(ABORT,'reference witness collision') END;
        INSERT OR IGNORE INTO reference_body VALUES(json_extract(NEW.json,'$.source_text_sha256'),json_extract(NEW.json,'$.source_text'));
        UPDATE reference_payload SET id=NEW.id,document_id=NEW.document_id,json=json_remove(NEW.json,'$.source_text') WHERE id=OLD.id;
      END;
      CREATE TRIGGER reference_delete INSTEAD OF DELETE ON reference BEGIN
        DELETE FROM reference_payload WHERE id=OLD.id;
      END;
    ''')
