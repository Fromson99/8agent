"""New runs only: request-demand entities with inherited evidence and outbox contracts."""
from .tiers_repository import TiersRepository
from ..contracts import digest
class ObligationRepository(TiersRepository):
    VERSION = 5
    DDL = 'journal-v5.sql'
    def dependency_hash(self):
        return digest({'parent':super().dependency_hash(),'plans':self.heads('question_plan'),
                       'obligation_reviews':self.heads('obligation_review')})
