"""Permanent-v2 pytest bootstrap.

The historical regression suite imports tool modules through the old ``scripts``
package name.  Keep that import surface test-only while resolving the modules
from the canonical tools root; production code must use ``06_TOOLS/run_tool.py``.
"""
from __future__ import annotations

import importlib.machinery
import os
import sys
import types
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_TOOL_ROOT = WORKSPACE_ROOT / "06_TOOLS" / "EXPERIMENTS"
EXPERIMENT_TOOL_DIRS = tuple(sorted(path for path in EXPERIMENT_TOOL_ROOT.rglob("*") if path.is_dir()))
TOOL_ROOTS = (
    WORKSPACE_ROOT / "06_TOOLS" / "COMMANDS",
    *EXPERIMENT_TOOL_DIRS,
)
REGRESSION_TESTS_ROOT = WORKSPACE_ROOT / "05_TESTS" / "REGRESSION"
# Stands in sys.path for all experiment tool directories; never a real directory.
EXPERIMENT_PATH_SLOT = str(EXPERIMENT_TOOL_ROOT / ".experiment-tool-directories")

os.environ.setdefault("LAWRAG_WORKSPACE_ROOT", str(WORKSPACE_ROOT))
os.environ.setdefault("LAWRAG_TOOL_WORKSPACE_ROOT", str(WORKSPACE_ROOT))


class ExperimentToolFinder:
    """Import experiment tool modules from their historical sys.path position.

    The ~1,400 experiment directories used to be separate sys.path entries, so
    every other import and every importlib.metadata.version() call scanned all
    of them.  They now occupy one placeholder entry.  Only a name that exists in
    some experiment directory is searched, with the placeholder expanded back
    into the directories, so resolution order is unchanged.
    """

    def __init__(self, directories):
        self.directories = [str(path) for path in directories]
        suffixes = tuple(importlib.machinery.all_suffixes())
        names = set()
        for directory in self.directories:
            for entry in os.scandir(directory):
                if entry.is_dir():
                    names.add(entry.name)  # regular packages and namespace portions
                    continue
                names.update(entry.name[:-len(suffix)] for suffix in suffixes if entry.name.endswith(suffix))
        self.names = frozenset(names)

    def find_spec(self, fullname, path=None, target=None):
        if path is not None or fullname not in self.names:
            return None
        try:
            slot = sys.path.index(EXPERIMENT_PATH_SLOT)
        except ValueError:
            return None
        search = [*sys.path[:slot], *self.directories, *sys.path[slot + 1:]]
        return importlib.machinery.PathFinder.find_spec(fullname, search, target)


def install_tool_paths():
    """Put tool roots on sys.path in the original order, experiments as one slot."""
    if EXPERIMENT_PATH_SLOT in sys.path:
        return
    present = set(sys.path)
    remaining = [path for path in EXPERIMENT_TOOL_DIRS if str(path) not in present]
    command_root = str(TOOL_ROOTS[0])
    slot = 0
    if command_root not in present:
        sys.path.insert(0, command_root)
        slot = 1
    sys.path.insert(slot, EXPERIMENT_PATH_SLOT)
    finder = ExperimentToolFinder(remaining)
    path_finder = next(index for index, item in enumerate(sys.meta_path) if item is importlib.machinery.PathFinder)
    sys.meta_path.insert(path_finder, finder)


install_tool_paths()

scripts = types.ModuleType("scripts")
scripts.__path__ = [str(path) for path in TOOL_ROOTS]
scripts.__package__ = "scripts"
sys.modules.setdefault("scripts", scripts)

tests = types.ModuleType("tests")
tests.__path__ = [str(REGRESSION_TESTS_ROOT)]
tests.__package__ = "tests"
sys.modules.setdefault("tests", tests)


import pytest

# Test databases are throwaway, but SQLite (PRAGMA synchronous=FULL in product code)
# and atomic file writes still fsync.  On this WSL disk one fsync often costs tens of
# milliseconds, which made a typical test file ~10x slower.  When pytest is started
# from the command line, restart it once under libeatmydata, which turns fsync into
# a no-op below Python: PRAGMA values, os.fsync calls and file contents are unchanged
# and a killed process still leaves its writes in the page cache.  Set
# LAWRAG_TEST_KEEP_FSYNC=1 to keep real fsync.
EATMYDATA_LIBRARY = "/usr/lib/x86_64-linux-gnu/libeatmydata.so"


def _started_as_pytest_command():
    main = sys.modules.get("__main__")
    spec_name = getattr(getattr(main, "__spec__", None), "name", "")
    return spec_name in ("pytest", "pytest.__main__") or Path(sys.argv[0]).name in ("pytest", "py.test")


def _restart_without_fsync_required():
    return (os.environ.get("LAWRAG_TEST_KEEP_FSYNC") != "1"
            and "libeatmydata" not in os.environ.get("LD_PRELOAD", "")
            and os.path.exists(EATMYDATA_LIBRARY)
            and _started_as_pytest_command())


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config):
    if not _restart_without_fsync_required():
        return None
    capture = config.pluginmanager.getplugin("capturemanager")
    if capture is not None:
        capture.stop_global_capturing()
    sys.stdout.flush()
    sys.stderr.flush()
    preload = os.environ.get("LD_PRELOAD", "")
    env = dict(os.environ, LD_PRELOAD=EATMYDATA_LIBRARY + (" " + preload if preload else ""))
    os.execve(sys.executable, sys.orig_argv, env)


# Shared small source-only serving fixture; never imports retired authoring runners.
import json
import sqlite3
from semantic_runtime.contracts import sha, write
from lawrag.pipeline import glossary_assembly as assembly, glossary_v1 as v1

@pytest.fixture
def term_glossary(tmp_path):
    path = tmp_path / 'dictionary'; path.mkdir()
    with sqlite3.connect(path / 'dictionary.sqlite') as db:
        assembly.tables(db)
        v1.add_entry(db, 'fixture:day', 'econedu', '영업일', '영업일은 은행이 영업하는 날을 말한다.', english='Business Day')
    knowledge = tmp_path / 'knowledge'; knowledge.mkdir()
    schemas = {
        'graph': 'CREATE TABLE label(source,node_id,normalized); CREATE TABLE node(source,id,payload);',
        'lookup': 'CREATE TABLE surface(key,source,node_id,label,kind);',
        'translations': 'CREATE TABLE unit(source,node_id,kind,id,original_sha256,status,needs_review,origin_locator,original,translation_ko);',
        'identity': 'CREATE TABLE concept_mapping(id,source,node_id,entry_id,status,reason); CREATE TABLE uri_alias(source,alias_uri,canonical_uri,status,evidence_id);',
        'legal': 'CREATE TABLE entry(id,label,homonym); CREATE TABLE edge(id,source_id,target_id,code,status,reason);',
    }
    for name, schema in schemas.items():
        with sqlite3.connect(knowledge / (name + '.sqlite')) as db:
            db.executescript(schema)
    with sqlite3.connect(knowledge / 'lookup.sqlite') as db:
        db.execute('INSERT INTO surface VALUES (?,?,?,?,?)', ('자금지원', 'fibo', 'loan', '자금지원', 'TRANSLATION'))
    with sqlite3.connect(knowledge / 'graph.sqlite') as db:
        db.execute('INSERT INTO node VALUES (?,?,?)', ('fibo', 'loan', json.dumps({'definitions': ['가상 자금지원 정의']})))
    manifest = {'schema_version': 'glossary-knowledge-bundle-v1', 'dictionary_sha256': sha(path / 'dictionary.sqlite'), 'counts': {},
                'files': [{'path': p.name, 'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(knowledge.glob('*.sqlite'))]}
    write(knowledge / 'manifest.json', manifest)
    write(path / 'report.json', {'schema_version': assembly.VERSION, 'dictionary_sha256': manifest['dictionary_sha256'],
                                'counts': {}, 'collection': {'complete': True},
                                'knowledge_binding': {'path': str(knowledge), 'manifest_sha256': sha(knowledge / 'manifest.json')}})
    return path
