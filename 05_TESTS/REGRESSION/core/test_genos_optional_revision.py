"""No live models: optional revision is not a GENOS prerequisite."""
import json
from pathlib import Path
import pytest
from lawrag.pipeline import genos_build as build, genos_batch as batch
from .test_genos_build import Fake, setup


@pytest.mark.parametrize('revision', ['', '   ', None])
def test_strict_no_revision_full_build_and_resume(setup, revision):
    args, _, out = setup
    args.model_revision = revision
    result = build.execute(args, provider_factory=Fake, emit=lambda _: None)
    assert result['ok']
    identity = json.loads((out / 'models.json').read_text())
    assert identity['model_revision'] is None and identity['model_revision_status'] == 'not_provided'
    queue = build.authoring().Queue(out / 'queue')
    assert queue.identity['model_revision'] == 'unspecified'
    assert queue.identity['model'] == 'fake-model'
    args.resume = True
    assert build.execute(args, provider_factory=Fake, emit=lambda _: None)['ok']
    assert not Fake.instances[-1].calls and not Fake.instances[-1].batches


def test_batch_no_revision_and_model_drift_still_checked(setup, monkeypatch):
    args, raw, out = setup
    args.model_revision = ''
    plan = build.inventory(raw, 'internal')
    report = {'errors': [], 'excluded': [], 'aliases': []}
    result = batch.execute(args, plan, report, provider_factory=Fake, emit=lambda _: None)
    assert result['ok']
    args.resume = True
    class Different(Fake):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.models['llm'] = 'changed-model'
    result = batch.execute(args, plan, report, provider_factory=Different, emit=lambda _: None)
    assert result['status'] == 'FAILED'
    assert 'endpoint/model changed' in result['records'][0]['error']
    assert not Fake.instances[-1].calls


def test_cli_default_and_optional_value(setup, monkeypatch):
    args, _, _ = setup
    monkeypatch.delenv('GENOS_LLM_REVISION', raising=False)
    assert build.parser().parse_args(['build', '--build-dir', 'test']).model_revision == ''
    args.model_revision = 'optional-user-note'
    build.execute(args, provider_factory=Fake, emit=lambda _: None)
    identity = json.loads((Path(args.build_dir) / 'models.json').read_text())
    assert identity['model_revision'] == 'optional-user-note'
    assert identity['model_revision_status'] == 'provided'
