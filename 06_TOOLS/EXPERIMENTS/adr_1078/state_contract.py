"""ADR1078 prospective multi-step contract; owner must freeze before running.

This independently authored pure-memory fixture imports no ADR1076 harness.
General techniques (isolated package aliases, typed diagnostic trees, paired
traces) are shared methodology, not newly claimed product behavior. Public API:
    run(baseline_root, optimized_root, matrix, output_dir) -> dict
No execution occurs at import. The owner supplies immutable roots and enforces
network/resource guards, source hashes, and selected-pointer immutability.
"""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import importlib
from itertools import permutations, product
import json
from pathlib import Path
import sys
import traceback
from types import ModuleType, SimpleNamespace


SCHEMA = "adr1078-prospective-state-sequences-v1"
TEXTS = {("D_A", "0"): "첫째 원문 가나다", ("D_B", "0"): "둘째 원문 라마바",
         ("D_C", "0"): "셋째 원문 사아자"}
ERRORS = {
    "acl_or_missing_source": ("ContractError", "delivered reference source outside current scope"),
    "source_blocks": ("ContractError", "delivered reference block outside source"),
    "span": ("ContractError", "delivered reference original span changed"),
    "source_timeout": ("TimeoutError", "synthetic state-sequence source timeout"),
}


def typed(value):
    """Keep primitive types, container types, and mapping/span order visible."""
    kind = type(value)
    if kind is dict:
        return ["dict", [[typed(k), typed(v)] for k, v in value.items()]]
    if kind in (list, tuple):
        return [kind.__name__, [typed(v) for v in value]]
    if kind in (set, frozenset):
        return [kind.__name__, sorted((typed(v) for v in value), key=_json)]
    if kind in (str, int, float, bool, type(None)):
        return [kind.__name__, value]
    raise TypeError("unexpected fixture diagnostic value: " + kind.__name__)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(_json(typed(value)).encode()).hexdigest()


def _runtime(root, role):
    root = Path(root).resolve()
    name = "_adr1078_" + role + "_" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    if name in sys.modules:
        raise RuntimeError("ADR1078 namespace already loaded; use a fresh runner process")
    path = root / "02_BACKEND/semantic_runtime"
    if not (path / "legal_agent/unit_relations.py").is_file():
        raise FileNotFoundError(path / "legal_agent/unit_relations.py")
    package = ModuleType(name)
    package.__package__ = name
    package.__path__ = [str(path)]
    sys.modules[name] = package
    sys.path.insert(0, str(root / "02_BACKEND"))
    return importlib.import_module(name + ".legal_agent.unit_relations")


class MemoryStore:
    """Immutable source adapter; failures are explicit, persistent test state."""

    def __init__(self, tag):
        self.tag = tag
        self.texts = deepcopy(TEXTS)
        self.reads = self.checks = 0
        self.failed_sources = set()
        self.check_unchanged = self._check

    def _check(self):
        self.checks += 1
        # Texts are never changed in these sequences. Identity and source
        # timeout are independent boundaries, not hidden text invalidation.

    def source(self, document_id, block_id):
        self.reads += 1
        checker = getattr(self, "check_unchanged", None)
        if callable(checker):
            checker()
        key = document_id, str(block_id)
        if key in self.failed_sources:
            raise TimeoutError(ERRORS["source_timeout"][1])
        return {"text": self.texts[key]}


def _span(text, lo=0, hi=None):
    hi = len(text) if hi is None else hi
    part = text[lo:hi]
    return {"block_id": "0", "start_cp": lo, "end_cp": hi, "text": part,
            "block_hash": hashlib.sha256(text.encode()).hexdigest(),
            "span_hash": hashlib.sha256(part.encode()).hexdigest()}


def _input(pattern, placement):
    sources, selected, delivered = {}, {}, {}
    for letter in "ABC":
        sid, did = "S_" + letter, "D_" + letter
        text = TEXTS[did, "0"]
        rows = [_span(text)]
        if pattern == "partition":
            rows = [_span(text, 0, 3), _span(text, 3)]
        elif pattern == "duplicate":
            rows = rows + deepcopy(rows)
        elif pattern != "full":
            raise ValueError(pattern)
        sources[sid] = {"document_id": did, "document_name": "문서 " + letter,
                        "blocks": [{"block_id": "0"}]}
        if placement == "last_delivered" and letter == "C":
            delivered[sid] = rows
        else:
            selected["R_" + letter] = {"source_id": sid, "evidence": [{"spans": rows}]}
    if placement not in ("all_selected", "last_delivered"):
        raise ValueError(placement)
    return sources, selected, delivered


class World:
    def __init__(self, rel, case):
        self.rel, self.case = rel, case
        self.trace = []
        self.view = 0
        self.prepared = self._new_preparation()
        self.stores = {"A": MemoryStore("store-A"), "B": MemoryStore("store-B")}
        sources, selected, delivered = _input(case.get("pattern", "full"),
                                               case.get("placement", "all_selected"))
        self.records = {slot: deepcopy(selected) for slot in "AB"}
        self.sessions = {}
        for slot in "AB":
            self.sessions[slot] = SimpleNamespace(
                tag="session-" + slot, scope={"D_A", "D_B", "D_C"},
                tools=SimpleNamespace(sources=deepcopy(sources)),
                profile={"candidate_navigation": {"investigation_control": True}},
                store=self.stores[slot], investigation_delivered_spans=deepcopy(delivered))
        topology = case.get("topology")
        if topology == "two_sessions_shared_store":
            self.sessions["B"].store = self.stores["A"]
        elif topology == "one_session_alternating_store":
            self.sessions["B"] = self.sessions["A"]
        elif topology not in (None, "two_sessions_equal_stores"):
            raise ValueError(topology)
        self.slot = "A"

    def _new_preparation(self):
        cls = getattr(self.rel, "CatalogReadPreparation", None)
        return cls() if cls is not None else None

    @property
    def session(self):
        return self.sessions[self.slot]

    @property
    def selected(self):
        return self.records[self.slot]

    def activate(self, slot):
        self.slot = slot
        if self.case.get("topology") == "one_session_alternating_store":
            self.session.store = self.stores[slot]

    def identity(self):
        return self.session.tag, self.session.store.tag

    def rows(self, letter):
        sid = "S_" + letter
        for record in self.selected.values():
            if record["source_id"] == sid:
                return record["evidence"][0]["spans"]
        return self.session.investigation_delivered_spans[sid]

    def gathered(self):
        spans = {}
        for record in self.selected.values():
            spans.setdefault(record["source_id"], []).extend(
                row for evidence in record["evidence"] for row in evidence["spans"])
        if self.session.profile["candidate_navigation"]["investigation_control"]:
            for sid, rows in self.session.investigation_delivered_spans.items():
                spans.setdefault(sid, []).extend(rows)
        return spans

    def state(self):
        return {"slot": self.slot, "sessions": {
            slot: {"identity": s.tag, "store": s.store.tag, "scope": s.scope,
                   "sources": s.tools.sources, "profile": s.profile,
                   "delivered": s.investigation_delivered_spans, "selected": self.records[slot]}
            for slot, s in self.sessions.items()}, "stores": {
            slot: {"identity": store.tag, "texts": store.texts,
                   "failed_sources": store.failed_sources,
                   "checker": callable(getattr(store, "check_unchanged", None))}
            for slot, store in self.stores.items()}}

    def call(self, label, policy, *, error=None, new_view=False):
        if new_view:
            self.view += 1
            self.prepared = self._new_preparation()
        before = fingerprint(self.state())
        reads = sum(store.reads for store in self.stores.values())
        checks = sum(store.checks for store in self.stores.values())
        if error is None:
            spans = self.gathered()
            # Every nonempty valid fixture pattern covers its one complete
            # block (full, two exact partitions, or duplicated full spans).
            # This oracle does not call any product coverage helper.
            blocks = {sid: {str(row["block_id"]) for row in rows} for sid, rows in spans.items()}
            expected = {"status": "success", "value": typed((blocks, spans))}
        else:
            expected = {"status": "error", "type": ERRORS[error][0], "message": ERRORS[error][1]}
        try:
            if self.prepared is None:
                value = self.rel.acquired_blocks(self.session, self.selected)
            else:
                value = self.rel.acquired_blocks(self.session, self.selected, preparation=self.prepared)
            actual = {"status": "success", "value": typed(value)}
        except Exception as exc:
            actual = {"status": "error", "type": type(exc).__name__, "message": str(exc)}
        self.trace.append({
            "label": label, "read_policy": policy, "view": self.view,
            "identity": list(self.identity()), "new_view": new_view,
            "input_sha256": before, "after_sha256": fingerprint(self.state()),
            "expected": expected, "actual": actual, "oracle_matches": actual == expected,
            "source_reads": sum(store.reads for store in self.stores.values()) - reads,
            "store_checks": sum(store.checks for store in self.stores.values()) - checks,
        })


def _identity_braid(w):
    previous, seen = None, set()
    for index, slot in enumerate(w.case["route"]):
        w.activate(slot)
        identity = w.identity()
        switched = previous is not None and identity != previous
        reset = switched and (w.case["boundary"] == "new_view_on_switch" or
            w.case["boundary"] == "new_view_on_return" and slot in seen)
        policy = "fresh" if previous is None or switched or reset else "reuse"
        w.call(f"route-{index}-{slot}", policy, new_view=reset)
        w.call(f"route-{index}-{slot}-repeat", "reuse")
        previous = identity
        seen.add(slot)


def _failure_cycles(w):
    letter = "A" if w.case["position"] == "first_source" else "C"
    sid, did = "S_" + letter, "D_" + letter
    row = w.rows(letter)[0]
    original_row = deepcopy(row)
    original_source = deepcopy(w.session.tools.sources[sid])
    fault = w.case["fault"]
    if fault == "span_text":
        row["text"] = "다른 원문"
        error = "span"
    elif fault == "span_bound_bool":
        row["start_cp"] = False
        error = "span"
    elif fault == "source_missing":
        del w.session.tools.sources[sid]
        error = "acl_or_missing_source"
    elif fault == "source_timeout":
        w.session.store.failed_sources.add((did, "0"))
        error = "source_timeout"
    else:
        raise ValueError(fault)
    w.call("fault_first_attempt", "failed", error=error)
    w.call("fault_identical_retry", "failed", error=error)
    row.clear(); row.update(deepcopy(original_row))
    if fault == "source_missing":
        w.session.tools.sources[sid] = original_source
    w.session.store.failed_sources.clear()
    w.call("repair_success", "fresh")
    w.call("repeat_success", "reuse")
    row["span_hash"] = "invalid-secondary-hash"
    w.call("second_span_hash_fault", "failed", error="span")
    w.call("second_identical_retry", "failed", error="span")
    row.clear(); row.update(deepcopy(original_row))
    w.call("second_repair_success", "fresh")
    w.call("second_repeat_success", "reuse")
    w.call("new_view_success", "fresh", new_view=True)
    w.call("new_view_repeat_success", "reuse")


def _layered_fault_orders(w):
    active = set()
    row = w.rows("C")[0]
    original_row = deepcopy(row)
    original_blocks = deepcopy(w.session.tools.sources["S_C"]["blocks"])

    def error():
        if "acl" in active:
            return "acl_or_missing_source"
        if "source_blocks" in active:
            return "source_blocks"
        return "span" if "span" in active else None

    def transition(component, restoring):
        if component == "acl":
            if restoring:
                w.session.scope.add("D_C")
            else:
                w.session.scope.remove("D_C")
        elif component == "source_blocks":
            w.session.tools.sources["S_C"]["blocks"] = deepcopy(original_blocks) if restoring else []
        elif component == "span":
            if restoring:
                row.clear(); row.update(deepcopy(original_row))
            elif w.case["span_fault"] == "start_bool":
                row["start_cp"] = False
            elif w.case["span_fault"] == "start_float":
                row["start_cp"] = 0.0
            elif w.case["span_fault"] == "span_hash":
                row["span_hash"] = "invalid-layered-hash"
            else:
                raise ValueError(w.case["span_fault"])
        else:
            raise ValueError(component)
        active.remove(component) if restoring else active.add(component)

    w.call("initial", "fresh")
    w.call("initial_repeat", "reuse")
    for component in w.case["application_order"]:
        transition(component, False)
        w.call("apply_" + component, "failed", error=error())
    w.call("fully_faulted_repeat", "failed", error=error())
    for component in w.case["restoration_order"]:
        transition(component, True)
        expected_error = error()
        w.call("restore_" + component, "failed" if expected_error else "fresh", error=expected_error)
    w.call("fully_restored_repeat", "reuse")
    w.call("adjacent_view", "fresh", new_view=True)
    w.call("adjacent_view_repeat", "reuse")


def _bypass_view_cycles(w):
    s = w.session
    saved = deepcopy(w.selected)
    bypass = w.case["bypass"]
    phase_reset = w.case["boundary"] == "new_view_each_phase"
    w.call("valid", "fresh")
    w.call("valid_repeat", "reuse")
    if bypass == "control_disabled":
        s.profile["candidate_navigation"]["investigation_control"] = False
    elif bypass == "checker_absent":
        del s.store.check_unchanged
    elif bypass == "empty_spans":
        for record in w.selected.values():
            record["evidence"][0]["spans"] = []
    else:
        raise ValueError(bypass)
    w.call("bypass", "bypass", new_view=phase_reset)
    w.call("bypass_repeat", "bypass")
    s.profile["candidate_navigation"]["investigation_control"] = True
    s.store.check_unchanged = s.store._check
    w.records[w.slot] = saved
    w.call("restore", "fresh", new_view=phase_reset)
    w.call("restore_repeat", "reuse")
    w.call("adjacent_view", "fresh", new_view=True)
    w.call("adjacent_view_repeat", "reuse")


FAMILIES = {"identity_braid": _identity_braid, "failure_cycles": _failure_cycles,
            "layered_fault_orders": _layered_fault_orders, "bypass_view_cycles": _bypass_view_cycles}


def cases(matrix):
    categories = matrix["categories"]
    for family in FAMILIES:
        spec = categories[family]
        if family == "identity_braid":
            keys = ("topology", "route", "boundary")
            values = product(*(spec[k] for k in keys))
        elif family == "failure_cycles":
            keys = ("fault", "placement", "position")
            values = product(*(spec[k] for k in keys))
        elif family == "layered_fault_orders":
            keys = ("application_order", "restoration_order", "span_fault", "placement")
            orders = list(permutations(spec["components"]))
            values = product(orders, orders, spec["span_fault"], spec["placement"])
        else:
            keys = ("bypass", "pattern", "boundary")
            values = product(*(spec[k] for k in keys))
        for number, values_row in enumerate(values, 1):
            yield {"id": family + "/" + f"{number:04d}", "category": family,
                   **dict(zip(keys, values_row))}


def _arm(rel, case):
    world = World(rel, case)
    try:
        FAMILIES[case["category"]](world)
        return {"status": "COMPLETE", "steps": world.trace, "final_state": typed(world.state())}
    except BaseException as exc:
        return {"status": "HARNESS_ERROR", "steps": world.trace,
                "final_state": typed(world.state()), "error_type": type(exc).__name__,
                "error": str(exc), "traceback": traceback.format_exc()}


def _pair_problems(case, baseline, optimized, matrix):
    problems = []
    if baseline["status"] != "COMPLETE" or optimized["status"] != "COMPLETE":
        return ["arm did not finish the declared sequence"]
    count = matrix["categories"][case["category"]]["calls_per_arm_per_case"]
    if len(baseline["steps"]) != count or len(optimized["steps"]) != count:
        problems.append("declared call count differs")
    if baseline["final_state"] != optimized["final_state"]:
        problems.append("final input states differ")
    for index, (left, right) in enumerate(zip(baseline["steps"], optimized["steps"])):
        label = f"step {index} ({left['label']})"
        for field in ("label", "read_policy", "view", "identity", "new_view", "input_sha256", "after_sha256", "expected", "actual"):
            if left[field] != right[field]:
                problems.append(label + ": unequal " + field)
        for role, observation in (("baseline", left), ("optimized", right)):
            if not observation["oracle_matches"]:
                problems.append(label + ": " + role + " violates the fixed coverage/error oracle")
            if observation["input_sha256"] != observation["after_sha256"]:
                problems.append(label + ": " + role + " mutated fixture inputs")
        policy = left["read_policy"]
        if policy in ("fresh", "failed", "bypass"):
            if left["source_reads"] != right["source_reads"]:
                problems.append(label + ": " + policy + " boundary skipped baseline reads")
            if left["store_checks"] != right["store_checks"]:
                problems.append(label + ": " + policy + " boundary changed store checks")
            if policy == "fresh" and left["source_reads"] <= 0:
                problems.append(label + ": fresh boundary did not read originals")
        elif policy == "reuse":
            if not (left["source_reads"] > 0 and right["source_reads"] == 0 and right["store_checks"] == 1):
                problems.append(label + ": eligible reuse did not preserve one immutable-store check")
        else:
            problems.append(label + ": unknown read policy")
    return problems


def run(baseline_root, optimized_root, matrix, output_dir):
    """Execute once in the owner's frozen, network-disabled, bounded process."""
    if matrix["schema_version"] != SCHEMA:
        raise ValueError("unexpected state matrix schema")
    if {key: tuple(value) for key, value in matrix["error_oracle"].items()} != ERRORS:
        raise ValueError("state matrix error oracle differs from implementation")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = output_dir / "state-pairs.jsonl.gz"
    failures_path = output_dir / "state-first-failure.json"
    counts = {family: 0 for family in FAMILIES}
    witnesses = {family: {"fresh": 0, "reuse": 0, "failed": 0, "bypass": 0, "new_view": 0}
                 for family in FAMILIES}
    call_count = 0
    current_pair = None
    with gzip.open(raw, "xt", encoding="utf-8") as stream:
        def emit(row):
            stream.write(_json(row) + "\n")
            stream.flush()

        try:
            emit({"kind": "manifest", "schema": SCHEMA, "matrix_sha256": fingerprint(matrix),
                  "baseline_root": str(Path(baseline_root).resolve()),
                  "optimized_root": str(Path(optimized_root).resolve()),
                  "scope": matrix["comparison_scope"]})
            baseline = _runtime(baseline_root, "baseline")
            optimized = _runtime(optimized_root, "optimized")
            if hasattr(baseline, "CatalogReadPreparation") or not hasattr(optimized, "CatalogReadPreparation"):
                raise ValueError("unexpected baseline/candidate preparation capabilities")
            for case in cases(matrix):
                left = _arm(baseline, case)
                right = _arm(optimized, case)
                problems = _pair_problems(case, left, right, matrix)
                current_pair = {"kind": "pair", "case": case, "baseline": left,
                                "optimized": right, "problems": problems}
                emit(current_pair)
                counts[case["category"]] += 1
                call_count += len(left["steps"])
                if problems:
                    raise AssertionError("state-sequence mismatch: " + case["id"] + ": " + problems[0])
                for step in right["steps"]:
                    witnesses[case["category"]][step["read_policy"]] += 1
                    witnesses[case["category"]]["new_view"] += int(step["new_view"])
            if any(counts[family] != matrix["counts"][family] or
                   counts[family] != matrix["categories"][family]["paired_cases"] for family in FAMILIES):
                raise AssertionError("category census differs from fixed matrix")
            if sum(counts.values()) != matrix["counts"]["total_pairs"] or call_count != matrix["counts"]["calls_per_arm"]:
                raise AssertionError("total pair/call census differs from fixed matrix")
            if any(w["fresh"] == 0 or w["reuse"] == 0 or w["new_view"] == 0 for w in witnesses.values()):
                raise AssertionError("missing declared reuse/fresh-view witness")
            result = {"status": "PASS", "paired_cases": sum(counts.values()), "counts": counts,
                      "failures": 0, "calls_per_arm": call_count,
                      "total_observed_product_calls": 2 * call_count,
                      "state_boundary_witnesses": witnesses, "raw_path": str(raw),
                      "real_data_loads": 0, "external_model_calls": 0,
                      "legal_quality_certified": False}
            emit({"kind": "summary", "result": result})
            return result
        except BaseException as exc:
            failure = {"status": "FAIL", "paired_cases": sum(counts.values()), "counts": counts,
                       "failures": 1, "calls_recorded_baseline": call_count, "raw_path": str(raw),
                       "error_type": type(exc).__name__, "error": str(exc),
                       "traceback": traceback.format_exc(), "first_failed_pair": current_pair}
            emit({"kind": "failure", "failure": failure})
            with failures_path.open("x", encoding="utf-8") as output:
                json.dump(failure, output, ensure_ascii=False, indent=2)
                output.write("\n")
            raise
