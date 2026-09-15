#!/usr/bin/env python3
"""Thin entrypoint: bundled immutable authoring runner or read-only progress."""
import runpy
import sys
from pathlib import Path

def main():
    here = Path(__file__).resolve().parent
    if len(sys.argv) < 2:
        print('Usage: ./genos.sh {prepare|run|status|retry|rework|handoff|load-handoff} [options]')
        return 2
    command, *args = sys.argv[1:]
    if command == 'status':
        sys.argv = [str(here/'genos_progress.py'), *args]
        runpy.run_path(str(here/'genos_progress.py'), run_name='__main__')
    else:
        if command == 'prepare':
            root = here.parents[1]
            for flag, value in [('--schema', root/'config/observation.schema.json'), ('--system', root/'config/authoring-system.txt')]:
                if not any(x == flag or x.startswith(flag+'=') for x in args):
                    args += [flag, str(value)]
        sys.argv = [str(here/'genos_authoring.py'), command, *args]
        runpy.run_path(str(here/'genos_authoring.py'), run_name='__main__')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
