"""Use prefixes inside one existing Managed Folder; create no DSS objects."""
from pathlib import PurePosixPath


class PrefixFolder:
    def __init__(self, folder, prefix):
        self.folder = folder
        self.prefix = self.clean(prefix).strip('/')+'/'

    @staticmethod
    def clean(path):
        if not isinstance(path,str) or not path or path.startswith('/') or '\\' in path or '..' in PurePosixPath(path).parts:
            raise ValueError('RELATIVE_STORAGE_PATH_REQUIRED')
        return path

    def list_paths_in_partition(self):
        names = [p.lstrip('/') for p in self.folder.list_paths_in_partition()]
        return ['/'+p[len(self.prefix):] for p in names if p.startswith(self.prefix)]

    def get_download_stream(self, name):
        return self.folder.get_download_stream(self.prefix+self.clean(name.lstrip('/')))

    def upload_stream(self, name, stream):
        return self.folder.upload_stream(self.prefix+self.clean(name),stream)


def open_folder(cfg, role):
    import dataiku
    return PrefixFolder(dataiku.Folder(cfg['params']['CODE_FOLDER_ID'],ignore_flow=True),cfg['storage'][role])
