from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger
from scripts import rag_integrated_legal_research_golden_61 as subject


def _frozen_payload() -> dict:
    cases = []
    for number, case_id in enumerate(subject.CASE_IDS, 1):
        gold = [{
            "law": f"법령-{number}",
            "article": f"제{number}조",
            "doc_id": f"doc-{number}",
            "node": number,
            "corpus_status": "present",
            "evidence_role": "decisive",
        }]
        if number <= 29:  # 61 + 29 = frozen 90-coordinate contract
            gold.append({
                "law": f"법령-{number}-시행령",
                "article": f"제{number + 100}조",
                "doc_id": f"sub-{number}",
                "node": number + 100,
                "corpus_status": "present",
                "evidence_role": "decisive",
            })
        cases.append({
            "number": number,
            "id": case_id,
            "suite": "cm-core-51" if number <= 51 else "fsc-hard-10",
            "question": f"질문 {number}",
            "reference_answer": f"기준답변 {number}",
            "gold_articles": gold,
            "material": "complete",
            "mode": "A",
            "answer_as_of": None,
            "current_as_of": None,
        })
    return {"cases": cases}


def _cm_source() -> dict:
    """Synthetic CM source with the frozen 14-case/22-companion shape."""
    cases = []
    for number in range(1, 15):
        count = 2 if number <= 8 else 1
        cases.append({
            "id": f"cm-{number:03d}",
            "required_companions": [
                {
                    "law": f"동반법령-{number}-{offset}",
                    "article": f"제{200 + number + offset}조",
                    "doc_id": f"companion-{number}-{offset}",
                    "node": 200 + number + offset,
                    "corpus_status": "present",
                    "evidence_role": "required_companion",
                }
                for offset in range(count)
            ],
        })
    return {"cases": cases}


def _provider_call(kind: str) -> dict:
    return {
        "kind": kind,
        "class": "product",
        "requested_model": subject.MODEL,
        "backend": "anthropic",
        "system": "system",
        "user": "user",
        "schema": {"type": "object"},
        "max_tokens": 32,
        "effort": "high",
        "provider": {
            "model": subject.MODEL,
            "backend": "anthropic",
            "raw_response": "{}",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "dur_ms": 1,
            "error": "",
        },
        "structured_output": {},
    }


def _public_case(case_id: str = "cm-001") -> dict:
    return {
        "number": 1,
        "case_id": case_id,
        "suite": "cm-core-51",
        "question": "질문",
    }


def _empty_declared_capture(case_id: str, arm_id: str) -> dict:
    recorder = ledger.StageLedgerRecorder(
        case_id, arm_id, ledger.identity_canonicalizer
    )
    for spec in subject.STAGE_PLAN[arm_id]:
        recorder.record_stage(
            spec["stage_id"], spec["kind"], [],
            parent_stage_ids=spec["parent_stage_ids"],
        )
    return recorder.capture()


def _declared_capture_with_presented(
    case_id: str, arm_id: str, coordinates: list[tuple[str, int]],
) -> dict:
    recorder = ledger.StageLedgerRecorder(
        case_id, arm_id, ledger.identity_canonicalizer
    )
    for spec in subject.STAGE_PLAN[arm_id]:
        recorder.record_stage(
            spec["stage_id"], spec["kind"], coordinates,
            parent_stage_ids=spec["parent_stage_ids"],
        )
    return recorder.capture()


def _product_capture(case_id: str = "cm-001") -> dict:
    arms = {}
    for arm_id in subject.ARMS:
        retrieval_calls = [_provider_call(f"{arm_id}.retrieval")]
        answer_calls = [_provider_call(f"{arm_id}.answer")]
        calls = retrieval_calls + answer_calls
        arms[arm_id] = {
            "arm_id": arm_id,
            "status": "complete",
            "error": "",
            "baseline_retrieval_shared": arm_id == subject.CANDIDATE_ARM,
            "retrieval": {
                "sections": [],
                "meta": {},
                "stage_capture": _empty_declared_capture(case_id, arm_id),
            },
            "answer": {
                "answer": f"{arm_id} 답변",
                "answerable": True,
                "error": "",
                "refs": [],
                "wiki": [],
            },
            "execution_metrics": {
                "integrated_total_ms": 4.0 if arm_id == subject.CANDIDATE_ARM else 0.0,
                "planner_provider_ms": 1.0 if arm_id == subject.CANDIDATE_ARM else 0.0,
                "deterministic_planning_ms": 3.0 if arm_id == subject.CANDIDATE_ARM else 0.0,
                "closed_id_violations": [],
                "closed_id_violation_count": 0,
                "generation_violations": [],
                "generation_violation_count": 0,
                "verified_evidence_violations": [],
                "verified_evidence_violation_count": 0,
                "verified_evidence_count": 0,
                "presented_evidence_count": 0,
                "verified_rate": 0.0,
            },
            "provider_calls": calls,
            "retrieval_provider_calls": retrieval_calls,
            "answer_provider_calls": answer_calls,
            "usage": subject._usage(calls),
            "wall_ms": 5.0,
            "retrieval_wall_ms": 3.0,
            "answer_wall_ms": 2.0,
        }
    baseline_usage = arms[subject.BASELINE_ARM]["usage"]
    arms[subject.BASELINE_ARM]["accounting"] = {
        "marginal": {"usage": deepcopy(baseline_usage), "wall_ms": 5.0},
        "inclusive": {"usage": deepcopy(baseline_usage), "wall_ms": 5.0},
        "shared_baseline_retrieval_added": False,
        "baseline_answer_added": False,
    }
    candidate_usage = arms[subject.CANDIDATE_ARM]["usage"]
    baseline_retrieval_usage = subject._usage(
        arms[subject.BASELINE_ARM]["retrieval_provider_calls"]
    )
    arms[subject.CANDIDATE_ARM]["accounting"] = {
        "marginal": {"usage": deepcopy(candidate_usage), "wall_ms": 5.0},
        "inclusive": {
            "usage": subject._usage_add(candidate_usage, baseline_retrieval_usage),
            "wall_ms": 8.0,
        },
        "shared_baseline_retrieval_added": True,
        "shared_baseline_retrieval_usage": baseline_retrieval_usage,
        "shared_baseline_retrieval_wall_ms": 3.0,
        "baseline_answer_added": False,
        "criteria_accounting": "inclusive",
    }
    value = {
        "schema_version": "adr-0114-gold-free-product-capture-v1",
        "adr_id": subject.ADR_ID,
        "experiment_id": subject.EXPERIMENT_ID,
        "run_id": subject.RUN_ID,
        "number": 1,
        "case_id": case_id,
        "suite": "cm-core-51",
        "question": "질문",
        "model": subject.MODEL,
        "gold_visible_to_product": False,
        "authority_generation": "a" * 64,
        "authority_as_of": "20260829",
        "corpus_fingerprint": "b" * 64,
        "run_environment_hash": "c" * 64,
        "corpus_article_roots": 1,
        "arms": arms,
        "captured_at": "2026-08-29T00:00:00+00:00",
        "complete": True,
    }
    value["capture_sha256"] = subject._self_hash(value, "capture_sha256")
    subject.validate_product_capture(value)
    return value


class _Exchange:
    def __init__(self, output: dict):
        self.model = subject.MODEL
        self.parsed = deepcopy(output)
        self._output = output

    def dump(self):
        return {
            "kind": "test",
            "at": "2026-08-29T00:00:00Z",
            "model": subject.MODEL,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "end_turn",
            "images": 0,
            "dur_ms": 12,
            "ttft_ms": 3,
            "system": "system",
            "user": "user",
            "raw_response": json.dumps(self._output, ensure_ascii=False),
            "error": "",
        }


class _FakeLLM:
    def __init__(self, output: dict):
        self.model = subject.MODEL
        self.backend = "anthropic"
        self.output = output
        self.log = []

    def structured(self, *args, **kwargs):
        assert kwargs["model"] == subject.MODEL
        self.log.append(_Exchange(self.output))
        return deepcopy(self.output)


def test_input_lock_is_split_into_physically_separate_public_and_scoring_fixtures():
    public, scoring = subject.split_input_lock(_frozen_payload(), _cm_source())

    assert len(public["cases"]) == len(scoring["cases"]) == 61
    assert sum(len(row["gold_articles"]) for row in scoring["cases"]) == 90
    assert sum(len(row["required_companions"]) for row in scoring["cases"]) == 22
    assert sum(bool(row["required_companions"]) for row in scoring["cases"]) == 14
    assert [row["case_id"] for row in public["cases"]] == list(subject.CASE_IDS)
    public_text = json.dumps(public, ensure_ascii=False)
    scoring_text = json.dumps(scoring, ensure_ascii=False)
    assert "reference_answer" not in public_text
    assert "gold_articles" not in public_text
    assert "기준답변" not in public_text
    assert '"question"' not in scoring_text
    assert public["gold_visible_to_product"] is False


def test_real_adr0091_input_lock_hash_and_full_cm51_fsc10_contract():
    assert subject._sha256(subject.INPUT_LOCK) == subject.EXPECTED_INPUT_LOCK_SHA256
    assert subject._sha256(subject.CM_SOURCE) == subject.EXPECTED_CM_SOURCE_SHA256
    public, scoring = subject.split_input_lock(
        subject._read_json(subject.INPUT_LOCK),
        subject._read_json(subject.CM_SOURCE),
    )

    assert [row["case_id"] for row in public["cases"]] == list(subject.CASE_IDS)
    assert [row["case_id"] for row in scoring["cases"]] == list(subject.CASE_IDS)
    assert sum(len(row["gold_articles"]) for row in scoring["cases"]) == 90
    assert sum(len(row["required_companions"]) for row in scoring["cases"]) == 22
    assert sum(bool(row["required_companions"]) for row in scoring["cases"]) == 14


def test_split_rejects_post_freeze_sampling_or_wrong_case_order():
    payload = _frozen_payload()
    payload["cases"] = payload["cases"][:-1]
    with pytest.raises(ValueError, match=r"frozen CM51\+FSC10 order"):
        subject.split_input_lock(payload, _cm_source())


def test_runtime_adapter_passes_frozen_caps_and_shares_baseline_result():
    observed = {}

    def retrieve(
        index, question, *, llm, assertion_llm, cap,
        integrated_research_enabled, integrated_cap, baseline_result=None,
        shortcut_enabled=False, feedback_enabled=False,
        reachability_trace=None,
    ):
        observed.update({
            "index": index,
            "question": question,
            "llm": llm,
            "assertion_llm": assertion_llm,
            "cap": cap,
            "integrated_research_enabled": integrated_research_enabled,
            "integrated_cap": integrated_cap,
            "baseline_result": baseline_result,
            "shortcut_enabled": shortcut_enabled,
            "feedback_enabled": feedback_enabled,
            "trace": reachability_trace,
        })
        return ["candidate"], {"integrated_research": {}}

    baseline = (["baseline"], {"meta": True})
    sections, meta, shared = subject.call_candidate_retrieve(
        retrieve, "INDEX", "질문", llm="LLM", reachability_trace="TRACE",
        baseline_result=baseline,
    )

    assert sections == ["candidate"]
    assert meta == {"integrated_research": {}}
    assert shared is True
    assert observed["cap"] == 20
    assert observed["integrated_cap"] == 32
    assert observed["integrated_research_enabled"] is True
    assert observed["baseline_result"] == baseline
    assert observed["llm"] == observed["assertion_llm"] == "LLM"


def test_runtime_adapter_fails_closed_when_integrated_signature_is_absent():
    def legacy(index, question, *, llm, cap=20):
        return [], {}

    with pytest.raises(subject.RuntimeContractError, match="parameters missing"):
        subject.call_candidate_retrieve(
            legacy, None, "질문", llm=None, reachability_trace=None,
            baseline_result=None,
        )


def test_candidate_capture_requires_all_frozen_stages_in_exact_order():
    capture = _empty_declared_capture("cm-001", subject.CANDIDATE_ARM)
    assert subject.validate_declared_capture(
        capture, "cm-001", subject.CANDIDATE_ARM
    ) == capture

    recorder = ledger.StageLedgerRecorder(
        "cm-001", subject.CANDIDATE_ARM, ledger.identity_canonicalizer
    )
    recorder.record_stage("question-source", "source", [])
    with pytest.raises(subject.BoundaryError, match="frozen ADR-0114 plan"):
        subject.validate_declared_capture(
            recorder.capture(), "cm-001", subject.CANDIDATE_ARM
        )


def test_scoring_fixture_cannot_be_read_before_valid_product_seal(tmp_path, monkeypatch):
    public_path = tmp_path / "public.json"
    scoring_path = tmp_path / "scoring.json"
    capture_dir = tmp_path / "captures"
    seal_path = tmp_path / "seal.json"
    capture_dir.mkdir()
    public = {
        "schema_version": "adr-0114-public-questions-v1",
        "gold_visible_to_product": False,
        "cases": [_public_case()],
    }
    scoring = {
        "schema_version": "adr-0114-offline-scoring-fixture-v1",
        "cases": [{
            "case_id": "cm-001", "reference_answer": "기준답변",
            "gold_articles": [{"doc_id": "law", "node": 1}],
        }],
    }
    subject._write_json(public_path, public)
    subject._write_json(scoring_path, scoring)
    subject._write_json(capture_dir / "cm-001.json", _product_capture())

    opened = []
    original = subject._read_json

    def recording_read(path: Path):
        opened.append(Path(path))
        return original(path)

    monkeypatch.setattr(subject, "_read_json", recording_read)
    with pytest.raises(FileNotFoundError):
        subject.open_scoring_fixture(
            scoring_path, seal_path, public_path, capture_dir,
            case_ids=("cm-001",),
        )
    assert scoring_path not in opened

    subject.build_product_seal(
        public_path, capture_dir, seal_path, case_ids=("cm-001",)
    )
    monkeypatch.setattr(
        subject,
        "fixture_integrity_receipt",
        lambda **kwargs: {"ready": True},
    )
    opened.clear()
    result = subject.open_scoring_fixture(
        scoring_path, seal_path, public_path, capture_dir,
        case_ids=("cm-001",),
    )
    assert result == scoring
    assert opened.index(seal_path) < opened.index(scoring_path)


def test_product_seal_detects_capture_mutation(tmp_path):
    public_path = tmp_path / "public.json"
    capture_dir = tmp_path / "captures"
    seal_path = tmp_path / "seal.json"
    capture_dir.mkdir()
    subject._write_json(public_path, {
        "schema_version": "adr-0114-public-questions-v1",
        "gold_visible_to_product": False,
        "cases": [_public_case()],
    })
    target = capture_dir / "cm-001.json"
    capture = _product_capture()
    subject._write_json(target, capture)
    subject.build_product_seal(
        public_path, capture_dir, seal_path, case_ids=("cm-001",)
    )
    capture["question"] = "봉인 뒤 변경"
    capture["capture_sha256"] = subject._self_hash(capture, "capture_sha256")
    subject._write_json(target, capture)

    with pytest.raises(subject.BoundaryError, match="sealed product capture changed"):
        subject.validate_product_seal(
            seal_path, public_path, capture_dir, case_ids=("cm-001",)
        )


def test_metadata_only_seal_revalidation_uses_sealed_bytes_without_parsing_capture(
        tmp_path, monkeypatch):
    public_path = tmp_path / "public.json"
    capture_dir = tmp_path / "captures"
    seal_path = tmp_path / "seal.json"
    capture_dir.mkdir()
    subject._write_json(public_path, {
        "schema_version": "adr-0114-public-questions-v1",
        "gold_visible_to_product": False,
        "cases": [_public_case()],
    })
    capture_path = capture_dir / "cm-001.json"
    subject._write_json(capture_path, _product_capture())
    subject.build_product_seal(
        public_path, capture_dir, seal_path, case_ids=("cm-001",)
    )
    original = subject._read_json

    def reject_capture_parse(path: Path):
        if Path(path) == capture_path:
            raise AssertionError("sealed capture must not be reparsed")
        return original(path)

    monkeypatch.setattr(subject, "_read_json", reject_capture_parse)
    seal = subject.validate_product_seal(
        seal_path, public_path, capture_dir,
        case_ids=("cm-001",), metadata_only=True,
    )

    assert seal["case_count"] == 1


def test_single_paired_haiku_judge_cannot_mutate_product_answer():
    output = {
        "baseline": {
            "correct": False,
            "unsupported_definitive_conclusion": False,
            "failure_type": "retrieval_miss",
            "reason": "근거 누락",
        },
        "candidate": {
            "correct": True,
            "unsupported_definitive_conclusion": False,
            "failure_type": "none",
            "reason": "기준답변과 일치",
        },
        "paired_outcome": "candidate_only",
        "comparison_reason": "candidate만 필요한 규범을 반영",
    }
    product = _product_capture()
    before = deepcopy(product)
    receipt = subject.execute_judge_case(
        _public_case(),
        {
            "case_id": "cm-001",
            "reference_answer": "기준답변",
            "gold_articles": [{"doc_id": "law", "node": 1}],
        },
        product,
        _FakeLLM(output),
    )

    assert product == before
    assert receipt["derived_paired_outcome"] == "candidate_only"
    assert receipt["may_change_product_answer"] is False
    assert receipt["model"] == subject.MODEL
    assert receipt["usage"]["calls"] == 1
    assert len(receipt["provider_calls"]) == 1
    assert receipt["provider_calls"][0]["provider"]["raw_response"]
    subject.validate_judge_receipt(
        receipt, expected_case=_public_case(), product_capture=product
    )


def test_retrieval_only_grades_expected_subset_on_final_present_stage():
    product = _product_capture()
    product["corpus_article_roots"] = 100
    product["arms"][subject.BASELINE_ARM]["retrieval"]["stage_capture"] = (
        _declared_capture_with_presented(
            "cm-001", subject.BASELINE_ARM, [("law", 1), ("extra", 9)]
        )
    )
    product["arms"][subject.CANDIDATE_ARM]["retrieval"]["stage_capture"] = (
        _declared_capture_with_presented(
            "cm-001", subject.CANDIDATE_ARM,
            [("law", 1), ("law", 2), ("companion", 3), ("extra", 9)],
        )
    )
    score = {
        "case_id": "cm-001",
        "gold_articles": [
            {"doc_id": "law", "node": 1},
            {"doc_id": "law", "node": 2},
        ],
        "required_companions": [{"doc_id": "companion", "node": 3}],
    }

    row = subject.grade_retrieval_only_case(product, score)
    summary = subject._summarize_retrieval_only([row])

    baseline = row["arms"][subject.BASELINE_ARM]
    candidate = row["arms"][subject.CANDIDATE_ARM]
    assert baseline["all_expected_present"] is False
    assert baseline["missing_expected"] == [{"doc_id": "law", "node": 2}]
    assert candidate["all_expected_present"] is True
    assert candidate["all_companions_present"] is True
    assert candidate["additional_presented_count"] == 1
    assert row["paired_outcome"] == "candidate_only"
    assert summary["judge_calls"] == 0
    assert summary["by_arm"][subject.CANDIDATE_ARM]["golden_recall"] == 1.0
    assert summary["by_arm"][subject.CANDIDATE_ARM]["all_expected_cases"] == 1


def test_retrieval_only_cli_skips_judge_and_semantic_finalizer(
    tmp_path, monkeypatch,
):
    adr = tmp_path / "ADR"
    experiment_dir = adr / "실험"
    experiment_dir.mkdir(parents=True)
    subject._write_json(experiment_dir / "manifest.json", {
        "runs": [{"id": subject.RUN_ID, "status": "planned"}],
    })
    artifacts = adr / "artifacts"
    paths = {
        "public": artifacts / "public.json",
        "scoring": artifacts / "scoring.json",
        "captures": artifacts / "captures",
        "judges": artifacts / "judges",
        "finalize_shards": artifacts / "shards",
        "seal": artifacts / "seal.json",
        "run": artifacts / "run.json",
        "ledger": artifacts / "ledger.json",
        "retrieval_only": artifacts / "retrieval-only.json",
    }
    subject._write_json(paths["public"], {"cases": [_public_case()]})
    called = {"report": 0}

    monkeypatch.setattr(subject, "CASE_IDS", ("cm-001",))
    monkeypatch.setattr(subject, "_artifact_paths", lambda _adr: paths)
    monkeypatch.setattr(
        subject, "preflight_receipt", lambda **_kwargs: {"status": "ready"}
    )
    monkeypatch.setattr(
        subject, "runtime_adapter_contract", lambda: {"ready": True}
    )
    monkeypatch.setattr(subject, "run_products", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        subject, "open_scoring_fixture",
        lambda *_args, **_kwargs: {"cases": [{"case_id": "cm-001"}]},
    )

    def write_report(*_args, **_kwargs):
        called["report"] += 1
        return {"summary": {"judge_calls": 0}}

    def forbidden(*_args, **_kwargs):
        raise AssertionError("semantic judge/finalizer must be unreachable")

    monkeypatch.setattr(subject, "write_retrieval_only_report", write_report)
    monkeypatch.setattr(subject, "run_judges", forbidden)
    monkeypatch.setattr(subject, "finalize", forbidden)

    assert subject.main(["--adr", str(adr), "--retrieval-only"]) == 0
    assert called["report"] == 1


def test_recording_llm_rejects_any_non_haiku_role_before_call():
    real = _FakeLLM({"answer": "x"})
    recording = subject.RecordingLLM(real)

    with pytest.raises(RuntimeError, match="model policy mismatch"):
        recording.structured(
            "test", "system", "user", {"type": "object"},
            model="claude-opus-5",
        )
    assert real.log == []


def test_preflight_is_read_only_and_never_constructs_an_llm(tmp_path, monkeypatch):
    def retrieve(
        index, question, *, llm, integrated_research_enabled,
        integrated_cap, baseline_result=None,
    ):
        raise AssertionError("preflight must not call runtime")

    def forbidden_llm(*args, **kwargs):
        raise AssertionError("preflight constructed an LLM")

    adr = tmp_path / "ADR-0114"
    paths = subject._artifact_paths(adr)
    subject.prepare_fixtures(
        input_lock=subject.INPUT_LOCK,
        cm_source=subject.CM_SOURCE,
        public_path=paths["public"],
        scoring_path=paths["scoring"],
    )
    subject._write_json(adr / "실험" / "manifest.json", {
        "dataset": {"sha256": subject.EXPECTED_INPUT_LOCK_SHA256},
        "design": {
            "retrieval_stage_plan": {
                "stages_by_arm": {
                    arm: [
                        {
                            "stage_id": spec["stage_id"],
                            "kind": spec["kind"],
                            "parent_stage_ids": list(spec["parent_stage_ids"]),
                        }
                        for spec in subject.STAGE_PLAN[arm]
                    ]
                    for arm in subject.ARMS
                }
            }
        },
        "questions": [{"id": case_id} for case_id in subject.CASE_IDS],
    })
    monkeypatch.setattr(subject.llm_mod, "LLM", forbidden_llm)
    receipt = subject.preflight_receipt(adr=adr, retrieve=retrieve)

    assert receipt["status"] == "ready"
    assert receipt["provider_calls"] == 0
    assert receipt["llm_constructed"] is False
    assert receipt["cases"] == 61
    assert receipt["input_lock_sha256"] == subject.EXPECTED_INPUT_LOCK_SHA256
    assert receipt["runtime_adapter"]["baseline_result_sharing"] is True


def test_preflight_blocks_lexicon_compilation_mode(tmp_path, monkeypatch):
    adr = tmp_path / "ADR-0114"
    paths = subject._artifact_paths(adr)
    subject.prepare_fixtures(
        input_lock=subject.INPUT_LOCK,
        cm_source=subject.CM_SOURCE,
        public_path=paths["public"],
        scoring_path=paths["scoring"],
    )
    subject._write_json(adr / "실험" / "manifest.json", {
        "dataset": {"sha256": subject.EXPECTED_INPUT_LOCK_SHA256},
        "design": {"retrieval_stage_plan": {"stages_by_arm": {
            arm: [
                {
                    "stage_id": spec["stage_id"],
                    "kind": spec["kind"],
                    "parent_stage_ids": list(spec["parent_stage_ids"]),
                }
                for spec in subject.STAGE_PLAN[arm]
            ]
            for arm in subject.ARMS
        }}},
        "questions": [{"id": case_id} for case_id in subject.CASE_IDS],
    })
    monkeypatch.setenv("RAG_LEXICON_COMPILE_MISSING", "1")

    receipt = subject.preflight_receipt(
        adr=adr,
        retrieve=lambda index, question, *, llm, integrated_research_enabled,
                        integrated_cap, baseline_result=None: ([], {}),
    )

    assert receipt["status"] == "blocked"
    assert receipt["lexicon_compile_missing_disabled"] is False


def test_product_capture_validator_rejects_gold_or_incomplete_receipt():
    product = _product_capture()
    product["arms"][subject.BASELINE_ARM]["reference_answer"] = "누출"
    product["capture_sha256"] = subject._self_hash(product, "capture_sha256")
    with pytest.raises(subject.BoundaryError, match="gold-bearing field"):
        subject.validate_product_capture(product)

    product = _product_capture()
    bad_call = _provider_call("bad")
    del bad_call["provider"]["raw_response"]
    product["arms"][subject.BASELINE_ARM]["provider_calls"] = [bad_call]
    product["arms"][subject.BASELINE_ARM]["retrieval_provider_calls"] = [bad_call]
    product["arms"][subject.BASELINE_ARM]["answer_provider_calls"] = []
    product["arms"][subject.BASELINE_ARM]["usage"] = subject._usage([bad_call])
    product["capture_sha256"] = subject._self_hash(product, "capture_sha256")
    with pytest.raises(subject.BoundaryError, match="receipt missing"):
        subject.validate_product_capture(product)


def test_canonical_fixture_integrity_recomputes_exact_values_and_hashes(tmp_path):
    public_path = tmp_path / "public.json"
    scoring_path = tmp_path / "scoring.json"
    subject.prepare_fixtures(
        input_lock=subject.INPUT_LOCK,
        cm_source=subject.CM_SOURCE,
        public_path=public_path,
        scoring_path=scoring_path,
    )
    ready = subject.fixture_integrity_receipt(
        input_lock=subject.INPUT_LOCK,
        cm_source=subject.CM_SOURCE,
        public_path=public_path,
        scoring_path=scoring_path,
    )
    assert ready["ready"] is True
    assert ready["decisive_coordinates"] == 90
    assert ready["required_companion_cases"] == 14
    assert ready["required_companion_coordinates"] == 22

    mutated = subject._read_json(public_path)
    mutated["cases"][0]["question"] += " 변경"
    subject._write_json(public_path, mutated)
    rejected = subject.fixture_integrity_receipt(
        input_lock=subject.INPUT_LOCK,
        cm_source=subject.CM_SOURCE,
        public_path=public_path,
        scoring_path=scoring_path,
    )
    assert rejected["ready"] is False
    assert rejected["public_exact"] is False
    assert rejected["scoring_exact"] is True


def test_baseline_preflight_contract_matches_native_raw_stage_lifecycle():
    contract = subject.baseline_raw_stage_contract()
    assert contract["ready"] is True
    assert [row["stage_id"] for row in contract["observed"]] == [
        row["stage_id"] for row in subject.STAGE_PLAN[subject.BASELINE_ARM]
    ]


def test_candidate_inclusive_accounting_adds_retrieval_but_not_baseline_answer():
    product = _product_capture()
    baseline = product["arms"][subject.BASELINE_ARM]
    candidate = product["arms"][subject.CANDIDATE_ARM]
    inclusive = candidate["accounting"]["inclusive"]["usage"]

    assert inclusive == subject._usage_add(
        candidate["usage"], subject._usage(baseline["retrieval_provider_calls"])
    )
    assert inclusive != subject._usage_add(candidate["usage"], baseline["usage"])
    assert candidate["accounting"]["baseline_answer_added"] is False

    candidate["accounting"]["inclusive"]["usage"] = subject._usage_add(
        candidate["usage"], baseline["usage"]
    )
    product["capture_sha256"] = subject._self_hash(product, "capture_sha256")
    with pytest.raises(subject.BoundaryError, match="inclusive accounting mismatch"):
        subject.validate_product_capture(product)


def test_summary_uses_candidate_inclusive_receipts_for_frozen_cost_criteria():
    product = _product_capture()
    arms = {}
    for arm_id in subject.ARMS:
        arms[arm_id] = {
            "product": subject._summary_product_arm(product["arms"][arm_id]),
            "presented_count": 0,
            "gold_hits": 0,
            "gold_total": 1,
            "all_gold_hit": False,
            "companion_hits": 0,
            "companion_total": 1,
            "all_companions_hit": False,
            "gold_results": [{"doc_id": "gold", "node": 1, "hit": False}],
            "companion_results": [{"doc_id": "companion", "node": 2, "hit": False}],
            "judge": {
                "correct": False,
                "unsupported_definitive_conclusion": False,
                "failure_type": "retrieval_miss",
                "reason": "miss",
            },
        }
    judge_call = _provider_call("judge")
    judge_call["class"] = "offline_evaluator"
    row = {
        "corpus_article_roots": 100,
        "arms": arms,
        "paired_outcome": "both_wrong",
        "judge_receipt": {
            "provider_calls": [judge_call],
            "wall_ms": 1.0,
            "paired_outcome_disagreement": False,
        },
    }
    summary = subject._summarize([row], {"artifact_sha256": "ledger"})
    candidate_usage = summary["by_arm"][subject.CANDIDATE_ARM][
        "product_usage_inclusive"
    ]
    assert candidate_usage["calls"] == 3
    assert candidate_usage["input_tokens"] == 30
    assert summary["frozen_criteria_measurement"]["candidate_cost_basis"].startswith(
        "inclusive:"
    )


def test_summary_compaction_preserves_accounting_without_raw_provider_payloads():
    product = _product_capture()
    arm = product["arms"][subject.CANDIDATE_ARM]

    compact = subject._summary_product_arm(arm)

    assert subject._usage(compact["provider_calls"]) == arm["usage"]
    assert compact["accounting"] == arm["accounting"]
    assert compact["execution_metrics"] == arm["execution_metrics"]
    filter_stage = next(
        row for row in arm["retrieval"]["stage_capture"]["stages"]
        if row["kind"] == "filter"
    )
    assert compact["retrieval"] == {
        "stage_capture_sha256": arm["retrieval"]["stage_capture"]["capture_sha256"],
        "filter_before_count": filter_stage["before_count"],
        "filter_after_count": filter_stage["after_count"],
    }
    assert "stages" not in json.dumps(compact["retrieval"], ensure_ascii=False)
    assert "raw_response" not in json.dumps(compact, ensure_ascii=False)


def test_seal_rejects_any_product_arm_error(tmp_path):
    public_path = tmp_path / "public.json"
    capture_dir = tmp_path / "captures"
    seal_path = tmp_path / "seal.json"
    capture_dir.mkdir()
    subject._write_json(public_path, {
        "schema_version": "adr-0114-public-questions-v1",
        "gold_visible_to_product": False,
        "cases": [_public_case()],
    })
    capture = _product_capture()
    capture["arms"][subject.CANDIDATE_ARM]["status"] = "error"
    capture["arms"][subject.CANDIDATE_ARM]["error"] = "synthetic failure"
    capture["capture_sha256"] = subject._self_hash(capture, "capture_sha256")
    subject._write_json(capture_dir / "cm-001.json", capture)

    with pytest.raises(subject.BoundaryError, match="sealed product arm failed"):
        subject.build_product_seal(
            public_path, capture_dir, seal_path, case_ids=("cm-001",)
        )


def test_judge_resume_validation_rejects_stale_product_or_wrong_run():
    output = {
        "baseline": {
            "correct": False,
            "unsupported_definitive_conclusion": False,
            "failure_type": "retrieval_miss",
            "reason": "miss",
        },
        "candidate": {
            "correct": True,
            "unsupported_definitive_conclusion": False,
            "failure_type": "none",
            "reason": "hit",
        },
        "paired_outcome": "candidate_only",
        "comparison_reason": "candidate hit",
    }
    product = _product_capture()
    receipt = subject.execute_judge_case(
        _public_case(),
        {
            "case_id": "cm-001",
            "reference_answer": "기준답변",
            "gold_articles": [{"doc_id": "gold", "node": 1}],
        },
        product,
        _FakeLLM(output),
    )
    stale = deepcopy(product)
    stale["arms"][subject.CANDIDATE_ARM]["answer"]["answer"] = "changed"
    stale["capture_sha256"] = subject._self_hash(stale, "capture_sha256")
    with pytest.raises(subject.BoundaryError, match="current sealed product capture"):
        subject.validate_judge_receipt(
            receipt, expected_case=_public_case(), product_capture=stale
        )

    receipt["run_id"] = "run-999"
    receipt["receipt_sha256"] = subject._self_hash(receipt, "receipt_sha256")
    with pytest.raises(subject.BoundaryError, match="question/run/completeness"):
        subject.validate_judge_receipt(
            receipt, expected_case=_public_case(), product_capture=product
        )


def test_finalize_refuses_completed_run_before_writing_any_artifact(tmp_path):
    adr = tmp_path / "ADR-0114"
    paths = subject._artifact_paths(adr)
    subject._write_json(adr / "실험" / "manifest.json", {
        "runs": [{"id": subject.RUN_ID, "status": "complete"}],
        "questions": [],
    })
    with pytest.raises(subject.BoundaryError, match="immutable"):
        subject.finalize({}, {}, paths, adr=adr)
    assert not paths["run"].exists()
    assert not paths["ledger"].exists()


def test_execution_metric_uses_runtime_local_planning_not_cold_resource_wall():
    index = SimpleNamespace(
        docs={}, authority_generation="generation-1", authority_as_of="20260829"
    )
    metrics = subject.integrated_execution_metrics(
        index,
        [],
        {
            "integrated_research": {
                "enabled": True,
                "elapsed_ms": 30_000.0,
                "deterministic_planning_ms": 123.0,
                "planner": {"receipts": [{"provider": {"dur_ms": 2_000.0}}]},
                "authority_generation": "generation-1",
                "authority_as_of": "20260829",
                "entry_plans": [],
                "final_compilation": {
                    "unverified_coordinates": [],
                    "missing_mandatory_coordinates": [],
                },
                "direct_conclusion_allowed": False,
                "errors": [],
                "fallback": "",
            }
        },
    )

    assert metrics["integrated_total_ms"] == 30_000.0
    assert metrics["planner_provider_ms"] == 2_000.0
    assert metrics["deterministic_planning_ms"] == 123.0


def test_product_resume_rejects_a_different_runtime_environment():
    product = _product_capture()
    expected = {
        "authority_generation": product["authority_generation"],
        "authority_as_of": product["authority_as_of"],
        "corpus_fingerprint": "d" * 64,
        "run_environment_hash": product["run_environment_hash"],
    }
    with pytest.raises(subject.BoundaryError, match="corpus identity mismatch"):
        subject.validate_product_capture(product, expected_runtime=expected)


def test_run_lock_rejects_a_second_process_handle(tmp_path):
    first = subject._acquire_run_lock(tmp_path / "ADR-0114")
    try:
        with pytest.raises(subject.BoundaryError, match="process is active"):
            subject._acquire_run_lock(tmp_path / "ADR-0114")
    finally:
        first.close()
    replacement = subject._acquire_run_lock(tmp_path / "ADR-0114")
    replacement.close()


def test_failed_preseal_attempt_is_discovered_and_hash_verified(tmp_path):
    adr = tmp_path / "ADR-0114"
    attempt = adr / "artifacts" / "failed-attempts" / "run-001-attempt-001"
    capture = attempt / "product-captures" / "cm-001.json"
    subject._write_json(capture, {"partial": True})
    receipt = {
        "schema_version": "adr-0114-aborted-attempt-v1",
        "adr_id": subject.ADR_ID,
        "experiment_id": subject.EXPERIMENT_ID,
        "run_id": subject.RUN_ID,
        "attempt_id": attempt.name,
        "status": "aborted_before_product_seal",
        "gold_opened": False,
        "scoring_fixture_opened": False,
        "judge_calls": 0,
        "partial_captures": [{
            "case_id": "cm-001",
            "path": "product-captures/cm-001.json",
            "sha256": subject._sha256(capture),
        }],
    }
    subject._write_json(attempt / "receipt.json", receipt)

    rows = subject._failed_attempt_entries(adr)

    assert len(rows) == 2
    assert {Path(row["path"]).name for row in rows} == {"receipt.json", "cm-001.json"}
    assert any(row["contains_raw_prompts_and_outputs"] for row in rows)

    subject._write_json(capture, {"partial": "tampered"})
    with pytest.raises(subject.BoundaryError, match="hash mismatch"):
        subject._failed_attempt_entries(adr)


def test_artifact_merge_is_deterministic_and_rejects_append_only_conflict(tmp_path):
    target = tmp_path / "artifact.json"
    subject._write_json(target, {"value": 1})
    row = subject._artifact_entry(target, "first")
    same = {**row, "description": "same bytes, later description"}

    merged = subject._merge_artifact_entries([same], [row])

    assert merged == [same]
    conflict = {**row, "sha256": "0" * 64}
    with pytest.raises(subject.BoundaryError, match="append-only artifact conflict"):
        subject._merge_artifact_entries([row], [conflict])


def test_existing_manifest_entry_must_still_match_disk(tmp_path):
    target = tmp_path / "artifact.json"
    subject._write_json(target, {"value": 1})
    row = subject._artifact_entry(target, "immutable")
    manifest = {"files": [row, {"path": "TODO", "sha256": "PENDING"}]}
    assert subject._validated_existing_artifact_entries(manifest) == [row]

    subject._write_json(target, {"value": 2})
    with pytest.raises(subject.BoundaryError, match="changed"):
        subject._validated_existing_artifact_entries(manifest)


def test_question_result_atomically_replaces_only_the_todo_template(tmp_path):
    target = tmp_path / "question.md"
    target.write_text("# 질문\n\n- 실행 시각: TODO\n", encoding="utf-8")

    subject._write_question_result(target, "# completed\n")
    subject._write_question_result(target, "# completed\n")

    assert target.read_text(encoding="utf-8") == "# completed\n"
    with pytest.raises(subject.BoundaryError, match="completed question artifact differs"):
        subject._write_question_result(target, "# changed\n")


def test_completed_question_receipt_is_safe_to_reuse_on_finalize_resume(tmp_path):
    target = tmp_path / "question.md"
    target.write_text(
        "# 질문 001 — cm-001\n\n"
        "- product capture 상태: `sealed exact`\n",
        encoding="utf-8",
    )

    assert subject._completed_question_result(target, "cm-001") is True
    assert subject._completed_question_result(target, "cm-002") is False


def test_question_heading_recovery_is_exact_and_preserves_payload(tmp_path):
    source = tmp_path / "original.md"
    target = tmp_path / "repaired.md"
    source.write_text(
        "# 질문 001 — cm-001\n\n"
        "## 4. 제품 입력 원값과 회수·탈락 단계 원장\n\n"
        "PAYLOAD-4\n\n"
        "## 5. 제품 모델 호출 — system/user/schema/provider raw/structured/usage\n\n"
        "PAYLOAD-5\n\n"
        "## 6. 중간 LLM 호출\n\n"
        "PAYLOAD-6\n\n"
        "## 7. 채점 호출 — 단일 paired Haiku, 제품 수정 금지\n\n"
        "PAYLOAD-7\n",
        encoding="utf-8",
    )

    subject._rewrite_standard_question_headings(source, target)

    repaired = target.read_text(encoding="utf-8")
    for heading in (
        "## 4. 제품 입력을 구성한 원값",
        "### 회수·탈락 단계 원장 — run·arm별",
        "## 5. 제품 모델 호출 — run·arm별 실제 원문",
        "## 6. 중간 LLM 호출 — router/compiler/verifier/repair",
        "## 7. 채점 호출과 반복 판정",
    ):
        assert heading in repaired
    for payload in ("PAYLOAD-4", "PAYLOAD-5", "PAYLOAD-6", "PAYLOAD-7"):
        assert payload in repaired
