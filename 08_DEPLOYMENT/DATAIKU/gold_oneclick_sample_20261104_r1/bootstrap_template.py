import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile
import dataiku

ZIP_NAME = 'DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip'
ZIP_SHA256 = '@@ZIP_SHA@@'


def open_package():
    folder = dataiku.Folder(PARAMS['CODE_FOLDER_ID'])
    names = [p for p in folder.list_paths_in_partition() if PurePosixPath(p).name == ZIP_NAME]
    if len(names) != 1: raise ValueError('UPLOAD_ONE_CODE_ZIP:'+ZIP_NAME)
    with folder.get_download_stream(names[0]) as stream: raw = stream.read(16*1024**2+1)
    if len(raw)>16*1024**2 or hashlib.sha256(raw).hexdigest()!=ZIP_SHA256: raise ValueError('CODE_ZIP_HASH')
    root = Path(tempfile.gettempdir()) / ('gold-zip-flow-code-'+ZIP_SHA256[:16])
    root.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist(); manifest = json.loads(z.read('FLOW_MANIFEST.json'))
        if len(names)!=len(set(names)) or set(names)!=set(manifest['files'])|{'FLOW_MANIFEST.json'}:
            raise ValueError('CODE_ZIP_MEMBERS')
        if sum(i.file_size for i in z.infolist())>32*1024**2: raise ValueError('CODE_ZIP_SIZE')
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in item.filename or item.is_dir() or stat.S_ISLNK(item.external_attr>>16):
                raise ValueError('CODE_ZIP_PATH')
            dest = root.joinpath(*p.parts)
            if dest.is_symlink() or root.resolve() not in dest.resolve().parents: raise ValueError('CODE_PATH_ESCAPE')
            content = z.read(item)
            if item.filename!='FLOW_MANIFEST.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][item.filename]:
                raise ValueError('CODE_FILE_HASH')
            if dest.exists():
                if dest.read_bytes()!=content: raise ValueError('EXTRACTED_CODE_CHANGED')
            else:
                dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(content)
    sys.path.insert(0,str(root))
    return root


FLOW_PACKAGE = open_package()
