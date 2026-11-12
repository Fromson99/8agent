"""ADR-1504: every block read of the local store re-stat'ed the generation files, re-read the serving-path
config and re-hashed the manifest. The selection fingerprint (in memory) is compared on every call; the
file-system proof runs at most once a second for the same objects and still finds a changed file."""
from contextlib import closing

import pytest

from semantic_runtime import oracle_dp_io
from semantic_runtime.storage import Store
from test_code_search_selection import bound  # noqa: F401 - fixture


def test_file_proof_is_repeated_at_most_once_a_second(bound, monkeypatch):
    g, root, target, config = bound
    clock = [1000.0]
    monkeypatch.setattr(oracle_dp_io.time, 'monotonic', lambda: clock[0])
    with closing(Store(g, verify=False)) as store:
        calls = []
        real = Store.binding_signature
        monkeypatch.setattr(Store, 'binding_signature', lambda self: calls.append(1) or real(self))
        store.check_unchanged(); store.check_unchanged(); store.check_unchanged()
        assert len(calls) == 1, 'one full proof inside the second'
        config.write_bytes(config.read_bytes() + b' ')
        clock[0] += 1.0
        with pytest.raises(ValueError):
            store.check_unchanged()


def test_changed_fingerprint_is_refused_at_once(bound, monkeypatch):
    g, root, target, config = bound
    with closing(Store(g, verify=False)) as store:
        store.check_unchanged()
        monkeypatch.setattr(store.selection, 'fingerprint', 'changed')
        with pytest.raises(ValueError, match='source generation changed'):
            store.check_unchanged()
