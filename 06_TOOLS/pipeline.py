#!/usr/bin/env python3
"""Stable entrypoint for explicit, hash-bound pipeline engines."""
import importlib.util
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
if __name__ == '__main__' and sys.argv[1:2] == ['build-all-legacy']:
    raise SystemExit('build-all-legacy is retired; use build-all --run-id NAME or build-data-stages --run-id NAME')
if __name__ == '__main__' and sys.argv[1:2] == ['build-all']:
    os.execv(sys.executable, [sys.executable, str(root / '06_TOOLS/COMMANDS/composed_build.py'), *sys.argv[2:]])
if __name__ == '__main__' and sys.argv[1:2] == ['glossary']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    if sys.argv[2:3] == ['knowledge']:
        from lawrag.pipeline.glossary_knowledge import main
        raise SystemExit(main(sys.argv[3:]))
    if sys.argv[2:3] == ['legal-relations']:
        from lawrag.pipeline.glossary_legal_relations import main
        raise SystemExit(main(sys.argv[3:]))
    if sys.argv[2:3] == ['review']:
        from lawrag.pipeline.glossary_review import main
        raise SystemExit(main(sys.argv[3:]))
    if sys.argv[2:3] == ['assemble']:
        from lawrag.pipeline.glossary_assembly import main
        raise SystemExit(main(sys.argv[3:]))
    from lawrag.pipeline.glossary_alignment import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['prepare-data']:
    os.execv(sys.executable, [sys.executable, str(root / '06_TOOLS/COMMANDS/prepare_data.py'), *sys.argv[2:]])
# Explicit offline data command, NOT an engine-host legal-authoring promotion.
# Both the main CLI and the GENOS wrapper execute the same maintained data runner.
if __name__ == '__main__' and sys.argv[1:2] in (['build-data'], ['build-data-stages']):
    script = root / '06_TOOLS/COMMANDS' / 'genos_data_stages.sh'
    os.execvp('bash', ['bash', str(script), *sys.argv[2:]])
path = root / '02_BACKEND/PIPELINE/engine_host.py'
spec = importlib.util.spec_from_file_location('pipeline_engine_host', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if __name__ == '__main__': module.main()
