"""Bind one notebook workspace to its remote receipt; never silently reset it."""
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
from prod_config import ROOT, ENGINE, STAGES


def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True).encode()


def read_folder(folder,path):
    names = {p.lstrip('/') for p in folder.list_paths_in_partition()}
    if path not in names: return None
    with folder.get_download_stream(path) as f: raw=f.read(32*1024**2+1)
    if len(raw)>32*1024**2: raise ValueError('REMOTE_STATE_LIMIT')
    return json.loads(raw)


def initialize(cfg,root,remote):
    root.mkdir(parents=True,exist_ok=True)
    path = root/'workspace.json'
    binding = hashlib.sha256(dump({k:v for k,v in cfg.items() if k!='scenario'})).hexdigest()
    saved = read_folder(remote,'workspace.json')
    local = json.loads(path.read_text()) if path.exists() else None
    if saved is not None and local!=saved:
        raise ValueError('CHECKPOINT_WORKSPACE_MISSING_OR_CHANGED: 이전 WORK_DIR와 체크포인트를 복구하세요. 새 INSERT/임베딩 없음.')
    if local is not None and local['binding']!=binding: raise ValueError('WORKSPACE_CONFIG_CHANGED')
    if local is None:
        local={'binding':binding,'token':uuid.uuid4().hex,'root':str(root),'created':time.time()}
        path.write_bytes(dump(local))
    if saved is None:
        remote.upload_stream('workspace.json',io.BytesIO(dump(local)))
        if read_folder(remote,'workspace.json')!=local:raise ValueError('WORKSPACE_READBACK_MISMATCH')
    return local

