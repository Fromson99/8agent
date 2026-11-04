"""Native v6 journal retains legal_agent's evidence, budget and publication contracts."""
from .obligation_repository import ObligationRepository


class UnifiedRepository(ObligationRepository):
    VERSION = 6
    DDL = 'journal-v6.sql'
