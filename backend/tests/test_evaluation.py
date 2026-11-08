import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from evaluation import evaluate as evaluation
from auditor.spec_input import SpecError, validate_structure

CORPUS, MANIFEST = evaluation.load_corpus()


def test_frozen_corpus_identity_and_development_separation():
    assert MANIFEST["sha256"] == "7f2eb935e58d042484bd70d11a39745262a172f21487e41c85255f5ebd781665"
    assert len(CORPUS["cases"]) == 90
    assert all(case["split"] == "additional_evaluation" for case in CORPUS["cases"])
    assert all(case["old"]["info"]["title"] != "Original Example Orders API" for case in CORPUS["cases"] if "info" in case["old"])
    assert len(MANIFEST["ai_case_ids"]) == 6 and MANIFEST["ai_attempts_per_case"] == 1


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["id"])
def test_frozen_policy_case(case):
    row = evaluation.score_case(case, repeats=1)
    assert row["status"] == "passed", row


def test_checksum_prevents_silent_label_edits(tmp_path):
    (tmp_path / "manifest.json").write_bytes((ROOT / "evaluation/manifest.json").read_bytes())
    (tmp_path / "corpus.json").write_bytes((ROOT / "evaluation/corpus.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        evaluation.load_corpus(tmp_path)


def test_authoring_is_independent_of_engine_predictions():
    # Authoring is deterministic standard-library data construction, never a model oracle.
    from evaluation.author_corpus import build
    authored = build()
    assert evaluation.canonical(authored) == evaluation.canonical(CORPUS["cases"])
    source = (ROOT / "evaluation/author_corpus.py").read_text(encoding="utf-8")
    assert "from auditor" not in source and "analyze_pair(" not in source


def test_metric_denominators_and_wrong_severity_are_not_hidden():
    case = next(case for case in CORPUS["cases"] if case["id"] == "request-enum-narrow")
    expected = copy.deepcopy(case["expected"]["findings"])
    wrong = copy.deepcopy(expected)
    wrong[0]["severity"] = "informational"
    row = {"kind": "comparison", "status": "failed", "expected": expected, "predicted": wrong, "compatible_control": False,
           "latency_ms": [1], "evidence_checks": 2, "evidence_errors": []}
    summary = evaluation.aggregate([row])
    assert summary["exact_signature_micro"] == {"tp": 0, "fp": 1, "fn": 1, "precision": 0, "recall": 0}
    row["expected"] = []
    row["predicted"] = []
    summary = evaluation.aggregate([row])
    assert summary["exact_signature_micro"]["precision"] is None
    assert summary["exact_signature_micro"]["recall"] is None


def test_evidence_checks_distinguish_null_missing_and_numeric_boolean():
    finding = {"id": "test", "before": {"present": True, "pointer": "#/x", "value": None},
               "after": {"present": False, "pointer": None, "value": None, "expected_pointer": "#/x", "context_pointer": "#"}}
    result = {"comparison": {"findings": [finding]}}
    sources = {"old": {"x": None}, "new": {}}
    assert evaluation.evidence_checks(result, sources) == (2, [])
    finding["before"]["value"] = True; sources["old"]["x"] = 1
    assert len(evaluation.evidence_checks(result, sources)[1]) == 1
    finding["before"]["value"] = 1; sources["new"]["x"] = None
    assert len(evaluation.evidence_checks(result, sources)[1]) == 1


def test_recorded_baselines_and_label_erratum_are_preserved():
    prior = ROOT / "evaluation/archive/parcel-v1"
    _, old_manifest = evaluation.load_corpus(prior)
    assert old_manifest["sha256"] == MANIFEST["prior_corpus_sha256"]
    first = json.loads((ROOT / "docs/section-6-baseline.json").read_text(encoding="utf-8"))
    corrected = json.loads((ROOT / "docs/section-6-corrected-labels-baseline.json").read_text(encoding="utf-8"))
    assert first["summary"]["passed"] == 87 and first["summary"]["cases"] == 88
    assert corrected["summary"]["passed"] == 89 and corrected["summary"]["cases"] == 90
    assert corrected["engine_version"] == "1.0.0"


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize("field", ["schemas", "responses", "parameters", "examples", "requestBodies", "headers", "securitySchemes", "links", "callbacks"])
def test_component_key_regex_is_consistent_between_openapi_families(version, field):
    document = {"openapi": version, "info": {"title": "Test", "version": "1"}, "paths": {}, "components": {field: {"bad/name~key": {}}}}
    with pytest.raises(SpecError) as error:
        validate_structure(document)
    assert error.value.detail["code"] == "invalid_openapi"
    assert error.value.detail["pointer"] == "#/components/" + field


def test_component_extension_keys_are_not_mistaken_for_fixed_maps():
    document = {"openapi": "3.1.0", "info": {"title": "Test", "version": "1"}, "paths": {}, "components": {"x-custom": {"arbitrary/key": "value"}}}
    validate_structure(document)


def test_unexpected_engine_errors_are_reported_as_failures_without_private_text(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("private diagnostic must not enter report")
    monkeypatch.setattr(evaluation, "analyze_pair", broken)
    row = evaluation.score_case(CORPUS["cases"][0], repeats=2)
    assert row["status"] == "failed"
    assert "valid comparison rejected" in row["issues"]
    assert "private diagnostic" not in json.dumps(row)


def test_ai_summary_retains_failed_cases_and_verifies_review_lineage():
    from evaluation.summarize import summarize
    raw = (ROOT / "docs/section-6-ai.json").read_bytes()
    review = json.loads((ROOT / "docs/section-6-ai-review.json").read_text(encoding="utf-8"))
    rubric = (ROOT / "evaluation/ai-rubric.json").read_bytes()
    result = summarize(raw, review, MANIFEST, rubric)
    assert result["attempted"] == 6 and result["accepted_structural_outputs"] == 5
    assert result["not_generated"] == 1
    assert result["grounded_denominator_all_attempts"] == {"numerator": 1, "denominator": 6}
    changed = copy.deepcopy(review)
    changed["cases"].pop()
    with pytest.raises(ValueError, match="omitted or duplicated"):
        summarize(raw, changed, MANIFEST, rubric)
    with pytest.raises(ValueError, match="does not match"):
        summarize(raw + b" ", review, MANIFEST, rubric)
