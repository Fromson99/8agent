"""Explicit GENOS input root avoids unrelated local migration receipts."""
import hashlib,json
import pytest
from lawrag.core.ingest import collection_manifest,manifest_item_for

def test_bound_collection_preserves_manifest_and_never_uses_workspace(tmp_path,monkeypatch):
 import lawrag.core.ingest as module
 monkeypatch.setattr(module,'data_path',lambda *a:pytest.fail('global local workspace must not be consulted'))
 raw=tmp_path/'RAW';doc=raw/'internal'/'sample.docx';doc.parent.mkdir(parents=True);doc.write_bytes(b'original')
 manifest=raw/'manifest.json';manifest.write_text(json.dumps({'items':[{'id':'fixture','body_sha256':hashlib.sha256(b'original').hexdigest()}]}));before=manifest.read_bytes()
 assert collection_manifest(doc,collection_root=raw)==manifest
 assert manifest_item_for(doc,b'original',collection_root=raw)[0]['id']=='fixture'
 assert manifest_item_for(doc,b'changed',collection_root=raw)==(None,None)
 assert collection_manifest(tmp_path/'converted.docx',collection_root=raw) is None
 assert manifest.read_bytes()==before
 with pytest.raises(FileNotFoundError):collection_manifest(doc,collection_root=tmp_path/'missing')
