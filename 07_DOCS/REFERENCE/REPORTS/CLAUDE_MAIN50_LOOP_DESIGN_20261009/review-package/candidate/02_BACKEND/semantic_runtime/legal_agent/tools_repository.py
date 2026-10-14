"""V2 journals reuse immutable source, physical-call and outbox storage primitives."""
from .repository import WorkRepository
from .errors import ProposalError


class ToolsRepository(WorkRepository):
    VERSION = 2
    DDL = 'journal-v2.sql'

    def visible(self, view_id, evidence_ids):
        for ident in evidence_ids:
            e = self.evidence(ident)
            if not self.db.execute('''SELECT 1 FROM presentation p JOIN model_attempt a USING(view_id)
                WHERE p.view_id=? AND p.evidence_id=? AND p.delivered_text_hash=? AND a.status='SUCCEEDED' ''',
                (view_id, ident, e['text_hash'])).fetchone():
                raise ProposalError('exact evidence not presented in this successful view: '+ident)
