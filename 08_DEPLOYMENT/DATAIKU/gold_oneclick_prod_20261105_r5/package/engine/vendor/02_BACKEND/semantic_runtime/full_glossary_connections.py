"""Read bounded source definitions and lexical links without approving meanings."""
import hashlib
import json


class ConnectionReader:
    def __init__(self, dbs, card):
        self.dbs, self.card = dbs, card
        self._resolved, self._aliases = {}, {}

    @staticmethod
    def _page(limit, offset=0):
        if type(limit) is not int or not 1 <= limit <= 12 or type(offset) is not int or offset < 0:
            raise ValueError("invalid bounded connection page")

    def _resolve(self, source, node):
        if source == "dictionary":
            exists = self.dbs[source].execute("SELECT 1 FROM entry WHERE id=?", (node,)).fetchone()
            return (node if exists else None), []
        key = source, node
        if key not in self._resolved:
            rows = [dict(r) for r in self.dbs["identity"].execute(
                "SELECT * FROM uri_alias WHERE source=? AND alias_uri=? "
                "ORDER BY canonical_uri,evidence_id", key)]
            targets = {r["canonical_uri"] for r in rows if r["status"] == "SOURCE_URI_ALIAS"}
            resolved = None if self._alias_conflict(rows) else next(iter(targets)) if len(targets) == 1 else node
            if resolved and not self.dbs["graph"].execute(
                    "SELECT 1 FROM node WHERE source=? AND id=?", (source, resolved)).fetchone():
                resolved = None
            self._resolved[key] = resolved, rows
        return self._resolved[key]

    @staticmethod
    def _alias_conflict(receipts):
        return any(r["status"] == "CONFLICT" for r in receipts) or len({
            r["canonical_uri"] for r in receipts if r["status"] == "SOURCE_URI_ALIAS"}) > 1

    def _names(self, source, node):
        """Incoming source edges may use a declared URI alias instead of node ID."""
        key = source, node
        if key not in self._aliases:
            aliases = self.dbs["identity"].execute(
                "SELECT DISTINCT alias_uri FROM uri_alias WHERE source=? AND canonical_uri=? "
                "AND status='SOURCE_URI_ALIAS' ORDER BY alias_uri", key)
            self._aliases[key] = [node] + [r[0] for r in aliases
                if r[0] != node and self._resolve(source, r[0])[0] == node]
        return self._aliases[key]

    @staticmethod
    def _allowed(row):
        return row["status"] not in {"REVIEWED_DIFFERENT", "DEFERRED"}

    def linked_entries(self, source, node, limit=12):
        self._page(limit)
        resolved, receipts = self._resolve(source, node)
        if resolved is None:
            return []
        if source == "dictionary":
            return [{"entry_id": resolved, "status": "SOURCE_IDENTITY", "reason": "SAME_SOURCE_ENTRY"}]
        rows = self.dbs["identity"].execute(
            "SELECT * FROM concept_mapping WHERE source=? AND node_id=? "
            "AND status NOT IN ('REVIEWED_DIFFERENT','DEFERRED') ORDER BY id LIMIT ?",
            (source, resolved, limit))
        return [{"entry_id": r["entry_id"], "status": r["status"], "reason": r["reason"],
                 "mapping_id": r["id"], "alias_receipts": receipts} for r in rows]

    @staticmethod
    def _text(value):
        value = value or ""
        return {"text": value[:1200], "text_truncated": len(value) > 1200,
                "text_sha256": hashlib.sha256(value.encode()).hexdigest()}

    def _definitions(self, source, node, end):
        db = self.dbs["dictionary"]
        if source == "dictionary":
            entry = db.execute("SELECT * FROM entry WHERE id=?", (node,)).fetchone()
            if not entry:
                return []
            if entry["source"] == "moleg":
                rows = db.execute("SELECT d.*,c.match_kind FROM definition_candidate c "
                    "JOIN definition_record d ON d.id=c.definition_id WHERE c.entry_id=? "
                    "AND d.content_type IN ('EXPLANATION','TRANSLATION') "
                    "ORDER BY d.content_type,d.id,c.match_kind LIMIT ?", (node, end))
                return [{k: r[k] for k in ("id", "source_id", "label", "kind", "content_type",
                        "request_id", "response_sha256", "match_kind")} | self._text(r["text"]) |
                        {"entry_id": node, "source_fields": json.loads(r["payload"]).get("fields", {}),
                         "status": "SOURCE_DEFINITION_CANDIDATE", "canonical_approval": False} for r in rows]
            if not entry["definition"]:
                return []
            result = self._text(entry["definition"]) | {"id": "entry-definition:" + node,
                "entry_id": node, "origin_source": entry["source"], "provenance": json.loads(entry["provenance"]),
                "status": "SOURCE_SCOPED_HINT", "canonical_approval": False}
            if entry["source"] == "corpus_definition":
                scope = db.execute("SELECT c.*,d.name AS document_name,d.source_sha256 FROM corpus_definition c "
                    "JOIN corpus_document d ON d.document_id=c.document_id WHERE c.id=?", (node,)).fetchone()
                if scope:
                    result["scope"] = {k: scope[k] for k in scope.keys() if k not in {"source_text"}}
                    for key in ("scope_hint", "location", "reference_hints"):
                        result["scope"][key] = json.loads(result["scope"][key])
            return [result]
        rows = self.dbs["translations"].execute("SELECT * FROM unit WHERE source=? AND node_id=? "
            "AND kind='DEFINITION' ORDER BY id LIMIT ?", (source, node, end)).fetchall()
        if rows:
            return [{k: r[k] for k in ("id", "original_sha256", "status", "needs_review", "origin_locator")} |
                    {"original": (r["original"] or "")[:1200], "translation_ko": (r["translation_ko"] or "")[:1200],
                     "original_truncated": len(r["original"] or "") > 1200,
                     "translation_truncated": len(r["translation_ko"] or "") > 1200,
                     "canonical_approval": False} for r in rows]
        row = self.dbs["graph"].execute("SELECT payload FROM node WHERE source=? AND id=?", (source, node)).fetchone()
        return [self._text(str(value)) | {"id": f"{source}:{node}:definition:{i}",
                "status": "SOURCE_RECORDED", "origin_locator": {"field": "definitions", "index": i},
                "canonical_approval": False} for i, value in enumerate(
                json.loads(row[0]).get("definitions", [])[:end] if row else [])]

    def _neighbour(self, source, node, *, allowed=True):
        resolved, receipts = self._resolve(source, node)
        return {"neighbour": {"source": source, "node_id": resolved} if resolved and allowed else None,
                "alias_receipts": receipts, "navigation_status": "AVAILABLE" if resolved and allowed else "HELD",
                "node_missing": resolved is None and not self._alias_conflict(receipts),
                "alias_conflict": self._alias_conflict(receipts)}

    def _mappings(self, source, node, end):
        column, args = ("entry_id=?", (node,)) if source == "dictionary" else ("source=? AND node_id=?", (source, node))
        rows = self.dbs["identity"].execute("SELECT * FROM concept_mapping WHERE " + column + " ORDER BY id LIMIT ?", (*args, end))
        result = []
        for raw in rows:
            row = dict(raw)
            external = source == "dictionary"
            other_source, other = (row["source"], row["node_id"]) if external else ("dictionary", row["entry_id"])
            result.append(row | {"origin": "concept_mapping", "predicate": "concept_mapping_candidate",
                "subject": row["entry_id"], "target": row["node_id"], "subject_source": "dictionary",
                "target_source": row["source"], "direction": "OUTGOING" if external else "INCOMING"} |
                self._neighbour(other_source, other, allowed=self._allowed(row)))
        return result

    def _relations(self, source, node, end):
        result = self._mappings(source, node, end)
        db = self.dbs["identity"]
        if source == "dictionary":
            fields = ','.join('"'+r[1].replace('"','""')+'"' for r in db.execute('PRAGMA table_info(official_relation)') if r[1] != 'payload')
            rows = db.execute('SELECT '+fields+' FROM official_relation WHERE source_id=? UNION '
                'SELECT '+fields+' FROM official_relation WHERE target_id=? ORDER BY id LIMIT ?', (node, node, end))
            for raw in rows:
                row = dict(raw); row.pop("payload", None)
                outgoing = row["source_id"] == node
                result.append(row | {"origin": "official_relation", "predicate": row["code"],
                    "subject": row["source_id"], "target": row["target_id"], "status": "SOURCE_RECORDED",
                    "direction": "OUTGOING" if outgoing else "INCOMING"} |
                    self._neighbour("dictionary", row["target_id"] if outgoing else row["source_id"]))
        else:
            names = self._names(source, node)
            # Query indexed endpoints separately; never scan raw RDF graph edges.
            edges = {}
            for name in names:
                for column in ("subject", "target"):
                    for raw in db.execute("SELECT * FROM source_edge WHERE source=? AND " + column +
                            "=? ORDER BY id LIMIT ?", (source, name, end)):
                        edges[raw["id"]] = dict(raw)
            for row in edges.values():
                outgoing = row["subject"] in names
                current_endpoint = row["subject"] if outgoing else row["target"]
                relation = row | {"origin": "source_edge", "status": "SOURCE_RECORDED",
                    "direction": "OUTGOING" if outgoing else "INCOMING",
                    "anchor_alias_receipts": self._resolve(source, current_endpoint)[1]}
                result.append(relation | self._neighbour(source, row["target"] if outgoing else row["subject"]))
        return sorted(result, key=lambda row: (row["id"], row["origin"]))

    def inspect(self, source, node, limit=6, offset=0):
        self._page(limit, offset)
        resolved, receipts = self._resolve(source, node)
        card = self.card(source, resolved or node)
        if resolved is None:
            return card | {"definitions": [], "relations": [], "next_offset": None,
                           "navigation_status": "HELD", "alias_receipts": receipts, "canonical_approval": False,
                           "node_missing": not self._alias_conflict(receipts),
                           "alias_conflict": self._alias_conflict(receipts)}
        end = offset + limit + 1
        definitions, relations = self._definitions(source, resolved, end), self._relations(source, resolved, end)
        more_relations = len(relations) > offset + limit
        relations = relations[offset:offset + limit]
        for relation in relations:
            other = relation["neighbour"]
            if other:
                relation["neighbour"] = self.card(other["source"], other["node_id"])
        return card | {"definitions": definitions[offset:offset + limit],
                       "relations": relations, "alias_receipts": receipts,
                       "next_offset": offset + limit if len(definitions) > offset + limit or more_relations else None,
                       "node_missing": False, "alias_conflict": False, "canonical_approval": False}
