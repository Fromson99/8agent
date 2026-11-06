"""Read existing root uploads; write only a scoped prefix in the code folder."""
from pathlib import PurePosixPath


class PrefixFolder:
    def __init__(self, folder, prefix=''):
        self.folder = folder
        self.prefix = self.clean(prefix).rstrip('/')+'/' if prefix else ''

    @staticmethod
    def clean(path):
        if (not isinstance(path,str) or not path or path.startswith('/') or
                '\\' in path or '\0' in path or '..' in PurePosixPath(path).parts):
            raise ValueError('RELATIVE_STORAGE_PATH_REQUIRED')
        return path

    def list_paths_in_partition(self):
        names = [p.lstrip('/') for p in self.folder.list_paths_in_partition()]
        return ['/'+p[len(self.prefix):] for p in names if p.startswith(self.prefix)]

    def get_download_stream(self, name):
        return self.folder.get_download_stream(self.prefix+self.clean(name.lstrip('/')))

    def upload_stream(self, name, stream):
        if not self.prefix:
            raise ValueError('INPUT_FOLDER_IS_READ_ONLY')
        return self.folder.upload_stream(self.prefix+self.clean(name),stream)


def open_folder(cfg, role):
    import dataiku
    if role not in {'input','result'}:raise ValueError('UNKNOWN_FOLDER_ROLE')
    key = cfg['input_folder'] if role=='input' else cfg['params']['CODE_FOLDER_ID']
    return PrefixFolder(dataiku.Folder(key,ignore_flow=True),cfg['storage'][role])
