"""Update only the synthetic transport decoder, retaining every assertion."""
from common import *
import sys
C=ROOT/read(ART/'stage.json')['roots']['candidate']
sys.argv=[__file__,'-q','--junitxml='+str(ART/'wire-fixture.xml'),str(C/'05_TESTS/CONTRACTS/test_reference_decision_continuity.py')+'::test_closed_skip_reaches_next_wire_and_completion_inspection']
source=Path(__file__).with_name('run_contracts.py').read_text()
needle="raise SystemExit(pytest.main(['-o','pythonpath=',*sys.argv[1:]]))"
patch="""import test_read_choice_input_preservation as fixture_wire
from semantic_runtime.legal_agent.navigation_input import expand_cards
raw_wire=fixture_wire.wire
fixture_wire.wire=lambda view: expand_cards(raw_wire(view))
"""
assert needle in source
exec(compile(source.replace(needle,patch+needle),__file__,'exec'))
