"""Compatibility entry for the retired Socket.IO app.

Old code-serving Run commands importing ``main_integrated:app`` now use the
existing direct /chat JSON app. New revisions should run ``main_router.py``.
"""
from main import app
