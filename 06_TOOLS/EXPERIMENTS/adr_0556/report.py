"""Run the frozen first scorer with compatibility for an archived diagnostic.

The old report formatter expected MAIN to be pinned. ADR0556 deliberately does
not pin it. This read adapter supplies the historical pointer hash only for that
diagnostic lookup; it never adds the mutable pointer to the enforced input map.
No question, rubric, metric, model output, or experimental input is changed.
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name('summarize.py')
spec = importlib.util.spec_from_file_location('frozen_routing_scorer', SCRIPT)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)
original_read = scorer.read
POINTER = '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'


class Hashes(dict):
    def __missing__(self, key):
        if key != POINTER:
            raise KeyError(key)
        previous = original_read(scorer.R / '04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing/artifacts/frozen-design.json')
        return previous['file_hashes'][key]


def compatible_read(path):
    value = original_read(path)
    if path == scorer.A / 'artifacts/frozen-design.json':
        value['file_hashes'] = Hashes(value['file_hashes'])
    return value


if __name__ == '__main__':
    scorer.read = compatible_read
    scorer.main()
