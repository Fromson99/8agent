#!/usr/bin/env python3
"""Stable entrypoint for explicit, hash-bound pipeline engines."""
import importlib.util
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
if __name__ == '__main__' and sys.argv[1:2] == ['oracle-query']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.oracle_query_publish import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['basis-batch']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.basis_batch import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['basis-links']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.basis_lifecycle import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['search-selection']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.search_selection import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['fulltext']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.fulltext_stage import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['unified-memory']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.unified_memory import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['action-memory']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.action_memory import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['task-harness']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.task_harness import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['golden']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.golden import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['document-release']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.document_release import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['reference-resolution']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    from lawrag.pipeline.reference_resolution import main
    raise SystemExit(main(sys.argv[2:]))
if __name__ == '__main__' and sys.argv[1:2] == ['build-all-legacy']:
    raise SystemExit('build-all-legacy is retired; use build-all --run-id NAME or build-data-stages --run-id NAME')
if __name__ == '__main__' and sys.argv[1:2] == ['build-all']:
    os.execv(sys.executable, [sys.executable, str(root / '06_TOOLS/COMMANDS/composed_build.py'), *sys.argv[2:]])
if __name__ == '__main__' and sys.argv[1:2] == ['glossary']:
    sys.path.insert(0, str(root / '02_BACKEND'))
    if sys.argv[2:3] == ['domain-control']:
        from lawrag.pipeline.unified_memory import main
        raise SystemExit(main(['catalogue-'+sys.argv[3],*sys.argv[4:]]))
    if sys.argv[2:3] == ['learn']:
        from lawrag.pipeline.glossary_learning import main
        raise SystemExit(main(sys.argv[3:]))
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
    if sys.argv[2:3] == ['abbreviation']:
        from lawrag.pipeline.glossary_abbreviation import main
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
if (__name__ == '__main__' and sys.argv[1:2] in (['check'], ['plan'], ['run'])
        and ('--profile' not in sys.argv or sys.argv[sys.argv.index('--profile')+1:sys.argv.index('--profile')+2] == ['legal-rag'])
        and '--engine' not in sys.argv):
    sys.path.insert(0, str(root))
    from importlib.util import spec_from_file_location, module_from_spec
    path = root / '02_BACKEND/PIPELINE/active_legal.py'
    spec = spec_from_file_location('active_legal_pipeline', path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    raise SystemExit(module.main(sys.argv[1:]))
path = root / '02_BACKEND/PIPELINE/engine_host.py'
spec = importlib.util.spec_from_file_location('pipeline_engine_host', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if __name__ == '__main__': module.main()
