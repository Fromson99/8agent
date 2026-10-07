import hashlib

import pytest

from semantic_runtime import storage


def test_verified_immutable_source_is_not_rehashed_until_file_state_changes(tmp_path, monkeypatch):
    path = tmp_path / 'store.sqlite'
    path.write_bytes(b'original source')
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    real_sha = storage.sha
    calls = []
    monkeypatch.setattr(storage, 'sha', lambda file: (calls.append(file), real_sha(file))[1])

    storage.verify_store_binding(path, expected)
    storage.verify_store_binding(path, expected)
    assert len(calls) == 1

    path.write_bytes(b'altered source')
    with pytest.raises(ValueError, match='generation artifact hash mismatch'):
        storage.verify_store_binding(path, expected)
    assert len(calls) == 2
