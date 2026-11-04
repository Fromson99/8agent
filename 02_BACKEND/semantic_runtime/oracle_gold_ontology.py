"""Read approved Gold ontology through the source request's ORDS SQL budget.

Reuse the existing publication, ACL, glossary and revocation checks. No DB-API
driver, writer connection, extra retry or global repository override is used.
"""
from contextlib import contextmanager
import json

from .physical_mapping import identifier
from .oracle_dp_io import DPError
from .ontology_work.repository import Repository
from .ontology_work.glossary_binding import GlossaryBinding
from .legal_agent.errors import ContractError

PORTS = {
    'publication': ('ONTL_POST', 'PUB_ID BNDL_ID REV_NO PKG_HASH_VAL PKG_JSON_CN',
                    'ONTL_POST_ID CNCP_GROP_ID WORK_VER_NO POST_CTNT_HASH_VALU POST_KNWL_CTNT'),
    'head': ('ONTL_HEAD', 'BNDL_ID PUB_ID CHG_SEQ_NO', 'CNCP_GROP_ID ONTL_POST_ID CHAN_NO'),
    'anchor': ('ONTL_ANC', 'PUB_ID ANC_HASH_VAL DOC_ID SRC_VER_ID UNIT_ID',
               'ONTL_POST_ID DOC_LCT_HASH_VALU DOC_ID DOC_HASH_VALU STRC_UNIT_ID'),
}


def repository(mapping, request, glossary):
    class Cursor:
        def execute(self, statement, params):
            if not statement.startswith('SELECT '):
                raise DPError('GOLD_ONTOLOGY_READ_ONLY')
            selected = statement.split(' FROM ', 1)[0][7:].split(',')
            self.columns = [identifier(c.strip().rsplit('.', 1)[-1]) for c in selected]
            self.binds = [(str(i+1), v, 'NUMBER' if isinstance(v, (int, float)) else
                           'CLOB' if isinstance(v, str) and len(v.encode()) > 4000 else 'VARCHAR2')
                          for i, v in enumerate(params)]
            self.statement, self.consumed = statement, False
            return self

        def fetchone(self):
            rows = self.fetchmany(1)
            return rows[0] if rows else None

        def fetchmany(self, count):
            if self.consumed:
                return []
            if type(count) is not int or not 1 <= count <= 1025:
                raise DPError('GOLD_ONTOLOGY_RESULT_BOUND')
            self.consumed = True
            limited = self.statement + ' FETCH FIRST ' + str(count) + ' ROWS ONLY'
            if count <= 100:
                return [tuple(row[c] for c in self.columns)
                        for row in request.sql.query(limited, self.binds, limit=count)]
            statement = ('SELECT JSON_ARRAYAGG(JSON_ARRAY(' + ','.join(self.columns) +
                         ' NULL ON NULL RETURNING CLOB) RETURNING CLOB) AS ROWS_JSON FROM (' + limited + ')')
            response = request.sql.query(statement, self.binds, limit=1)
            raw = response[0]['ROWS_JSON'] if response else None
            rows = [] if raw is None else json.loads(raw) if isinstance(raw, str) else raw
            if (not isinstance(rows, list) or len(rows) > count
                    or any(not isinstance(row, list) or len(row) != len(self.columns) for row in rows)):
                raise DPError('GOLD_ONTOLOGY_RESULT_SHAPE')
            return [tuple(row) for row in rows]

    class ReadRepository(Repository):
        @contextmanager
        def session(self, write=False):
            if write:
                raise DPError('GOLD_ONTOLOGY_READ_ONLY')
            yield Cursor()

        def execute(self, cursor, statement, params=()):
            return cursor.execute(statement, params)

        def initialize(self):
            raise DPError('GOLD_ONTOLOGY_PRECREATED_TABLES_REQUIRED')

        def checked_scope(self, scope):
            scope = frozenset(scope)
            if not scope <= request.sources.allowed:
                raise ContractError('Gold ontology cannot widen the authenticated document scope')
            return scope

        def lookup(self, anchor, allowed_documents):
            return super().lookup(anchor, self.checked_scope(allowed_documents))

        def current_publications(self, references, allowed_documents):
            return super().current_publications(references, self.checked_scope(allowed_documents))

    result = ReadRepository(None, dialect='oracle', owner=mapping.tables['ONTL_POST']['owner'])
    for key, (table, aliases, logical) in PORTS.items():
        fields = [mapping.tables[table]['columns'][name]['name'] + ' AS ' + alias
                  for alias, name in zip(aliases.split(), logical.split())]
        result.tables[key] = '(SELECT ' + ','.join(fields) + ' FROM ' + mapping.physical_table(table) + ')'

    def verify_glossary(refs):
        if not refs:
            return
        if glossary is None:
            raise ContractError('Gold ontology assembly requires the request glossary')
        port = GlossaryBinding(glossary, snapshot=request.snapshot.dataset_version)
        for ref in refs:
            if ref != port.restore(ref['source'], ref['node_id']):
                raise ContractError('published glossary snapshot changed')
    result.glossary_validator = verify_glossary
    return result
