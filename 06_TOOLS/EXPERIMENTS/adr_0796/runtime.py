from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0796/selected/snapshot'
p=C/'02_BACKEND/semantic_runtime/search_selection.py';s=p.read_text().replace("VERSION = 'filename-search-selection-v1'","VERSION = 'filename-search-selection-v1'\nLATEST_VERSION = 'filename-search-selection-v2'")
s=s.replace("self.value = None", "self.value = None\n        self.latest = {}",1)
s=s.replace("value.get('schema_version') != VERSION", "value.get('schema_version') not in {VERSION, LATEST_VERSION}")
s=s.replace("self.fingerprint = digest(value)","""if value['schema_version'] == LATEST_VERSION:
                marks = value.get('latest_documents')
                if not isinstance(marks, list) or any(not isinstance(r, dict) or not isinstance(r.get('document_id'), str) or type(r.get('is_latest')) is not bool for r in marks):
                    raise ValueError('invalid latest document marks')
                self.latest = {r['document_id']: r for r in marks}
                if len(self.latest) != len(marks) or {k for k, r in self.latest.items() if not r['is_latest']} != set(self.excluded):
                    raise ValueError('latest mark/exclusion mismatch')
            self.fingerprint = digest(value)""")
s=s.replace("    def check_unchanged(self):", """    def require_latest(self):
        self.check_unchanged()
        if self.value is None or self.value.get('schema_version') != LATEST_VERSION:
            raise ValueError('latest document selection required; run pipeline search-selection --latest before serving')

    def check_unchanged(self):""")
s=s.replace("        for row in self.value['excluded']:","""        if self.value['schema_version'] == LATEST_VERSION:
            from .filename_versions import inventory_generation, select, latest_marks
            rows, binding = inventory_generation(self.path.parent.parent / self.path.stem)
            if binding['metadata_sha256'] != self.value.get('metadata_sha256'):
                raise ValueError('latest metadata changed')
            decisions = select(rows, self.value['exceptions']['value'])
            if latest_marks(decisions) != self.value['latest_documents']:
                raise ValueError('latest marks do not match approved selection')
        for row in self.value['excluded']:""")
s=s.replace("if not self.excluded:\n            return", "if not self.excluded and not self.latest:\n            return")
s=s.replace("            objects = {", """            db.execute('CREATE TEMP TABLE latest_document(document_id TEXT PRIMARY KEY, mark TEXT) WITHOUT ROWID')
            db.executemany('INSERT INTO latest_document VALUES (?,?)', [(k, json.dumps(v, ensure_ascii=False)) for k, v in self.latest.items() if v['is_latest']])
            objects = {""")
s=s.replace("                for name in ('document', 'source_unit', 'source_block', 'block_payload'):\n                    view(name, visible)","""                if self.latest:
                    columns = [r[1] for r in db.execute('PRAGMA main.table_info(document)')]
                    projection = ','.join(('json_set(original.json, \'$.document_metadata.is_latest\', json(\'true\'), \'$.document_metadata.latest_selection\', json(m.mark)) AS json' if n == 'json' else 'original."'+n+'"') for n in columns)
                    # Unclassified/external documents do not acquire an internal latest mark.
                    projection = projection.replace('json_set(original.json,', 'CASE WHEN m.document_id IS NULL THEN original.json ELSE json_set(original.json,').replace('json(m.mark)) AS json', 'json(m.mark)) END AS json')
                    db.execute('CREATE TEMP VIEW document AS SELECT '+projection+' FROM main.document original LEFT JOIN temp.latest_document m ON m.document_id=original.document_id WHERE '+visible)
                else: view('document', visible)
                for name in ('source_unit', 'source_block', 'block_payload'):
                    view(name, visible)""")
s=s.replace("            db.commit()", """                if 'definition_reference' in objects:
                    view('definition_reference', 'original.definition_id IN (SELECT id FROM temp.definition) AND original.reference_id IN (SELECT id FROM temp.reference)')
            db.commit()""")
p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/filename_versions.py';s=p.read_text().replace("    if not result: raise ValueError('no classified internal document metadata found')\n",'');p.write_text(s)
