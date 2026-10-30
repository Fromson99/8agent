"""A bounded port over the existing SQLite/Oracle Glossary; never a new dictionary."""
from copy import deepcopy
from ..contracts import digest
from ..full_glossary import concept_id
from ..legal_agent.errors import ContractError


class GlossaryBinding:
    def __init__(self, reader, *, snapshot):
        self.reader = reader
        self.binding = {'snapshot': snapshot, **deepcopy(reader.binding)}

    def check(self, binding=None):
        self.reader.check_unchanged()
        current = {'snapshot': self.binding['snapshot'], **self.reader.binding}
        if current != self.binding or (binding is not None and binding != current):
            raise ContractError('glossary snapshot drift; relinking review required')

    def restore(self, source, node_id):
        self.check()
        # Both existing SQLite and Oracle readers expose this bounded SQL port.
        row = self.reader.dbs['lookup'].execute(
            'SELECT source,node_id FROM label WHERE source=? AND node_id=? LIMIT 1', (source, node_id)).fetchone()
        if not row:
            raise ContractError('saved glossary source/node no longer exists')
        card = self.reader.card(source, node_id)
        if card['id'] != concept_id(source, node_id):
            raise ContractError('glossary concept identity mismatch')
        detail = self.reader.inspect(card['id'])
        links = self.reader.entry_links(card['id'])
        self.check()
        return {'concept_id': card['id'], 'source': source, 'node_id': node_id,
                'binding': deepcopy(self.binding), 'card': card, 'detail': detail, 'entry_links': links,
                'source_status': {'canonical_approval': card.get('canonical_approval'),
                                  'status': card.get('status')}, 'review_ref': card.get('review_ref')}

    def candidates(self, labels):
        self.check()
        if len(labels) > 16:
            raise ContractError('glossary query count limit')
        found = {}; pages = []
        for label in dict.fromkeys(labels):
            page = self.reader.lookup(label, limit=8)
            pages.append({'label': label, 'total': page['total'], 'next_offset': page['next_offset']})
            for card in page['concepts']:
                if card['id'] not in found:
                    found[card['id']] = self.restore(card['source'], card['node_id'])
        body = {'binding': deepcopy(self.binding), 'queries': pages,
                'candidates': [found[k] for k in sorted(found)],
                'unsearched': any(p['next_offset'] is not None for p in pages),
                'canonical_approval': False}
        return {**body, 'candidate_receipt': digest(body)}

    def verify_candidates(self, value):
        self.check(value['binding'])
        if value['candidate_receipt'] != digest({k: v for k, v in value.items() if k != 'candidate_receipt'}):
            raise ContractError('glossary candidate receipt changed')
        for row in value['candidates']:
            if row != self.restore(row['source'], row['node_id']):
                raise ContractError('stored glossary candidate changed')
        return value
