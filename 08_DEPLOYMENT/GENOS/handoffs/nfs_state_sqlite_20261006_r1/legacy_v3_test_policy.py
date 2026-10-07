"""Explicitly select the v3 contract for the existing v3-only test fixtures.

The current product default is v4 capture. Older fixtures open cases-v3.sqlite
and expect its response schema; this test-only adapter selects that same scope.
It does not edit tests, product settings, release pointers or stored results.
"""
def pytest_runtest_call(item):
    if item.path.name not in {'test_unified_legal_agent.py', 'test_unified_memory_recovery.py'}:
        return
    fixture = item.funcargs.get('unified')
    if fixture:
        fixture[0].app.state.pipeline.contracts.pipeline['shortcut_v4'] = {'features': {'capture': False}}
