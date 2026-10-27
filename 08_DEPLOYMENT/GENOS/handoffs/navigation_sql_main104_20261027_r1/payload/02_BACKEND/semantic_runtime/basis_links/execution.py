"""Request-scoped trusted identity propagation, never global mutable identity."""
from contextvars import ContextVar
CURRENT=ContextVar('basis_execution',default=None)
