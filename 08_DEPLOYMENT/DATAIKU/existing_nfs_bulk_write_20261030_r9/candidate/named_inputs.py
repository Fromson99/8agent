"""Explicit input names chosen for this field run; other S3 objects are retained."""
SELECTED_INPUT_NAMES = (
    'RAW_INPUT.zip', 'RAW_INPUT.zip.receipt.json',
    'PIPELINE_SUPPORT.zip', 'PIPELINE_SUPPORT.zip.receipt.json',
)


class SelectedInputFolder:
    def __init__(self, folder):
        self.folder = folder

    def list_paths_in_partition(self):
        found = {}
        for path in self.folder.list_paths_in_partition():
            name = path.lstrip('/')
            if name in SELECTED_INPUT_NAMES:
                if name in found:
                    raise ValueError('SELECTED_INPUT_DUPLICATE: ' + name)
                found[name] = path
        missing = sorted(set(SELECTED_INPUT_NAMES) - set(found))
        if missing:
            raise ValueError('SELECTED_INPUT_MISSING: ' + ', '.join(missing))
        return [found[name] for name in SELECTED_INPUT_NAMES]

    def get_download_stream(self, path):
        if path.lstrip('/') not in SELECTED_INPUT_NAMES:
            raise ValueError('UNSELECTED_INPUT_READ')
        return self.folder.get_download_stream(path)


def install_input_selection(runtime):
    original = runtime.input_receipts
    if getattr(original, '_selection_revision', None) == 'named-inputs-20261027-r2':
        return

    def selected_receipts(folder):
        # Keep the original receipt parser, archive name/size/hash checks and all
        # downstream download/unpack validation. Narrow only the visible names.
        result = original(SelectedInputFolder(folder))
        for name in ('RAW_INPUT.zip', 'PIPELINE_SUPPORT.zip'):
            item = result[name]
            print('INPUT_SELECTED', name, 'bytes=', item['bytes'], 'sha256=', item['sha256'], flush=True)
        return result

    selected_receipts._selection_revision = 'named-inputs-20261027-r2'
    runtime.input_receipts = selected_receipts
