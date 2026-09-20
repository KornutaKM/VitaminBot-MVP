import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from vitaminbot.recognition import RecordState, validate_extraction_payload
from vitaminbot.recognition.benchmark import (
    BenchmarkManifestError,
    FieldRole,
    load_frozen_corpus,
    require_external_processing_allowed,
    require_provider_benchmark_eligible,
    score_extraction,
)

CORPUS_DIR = Path(__file__).parent / "fixtures" / "recognition_benchmark" / "corpus_v0"


def test_smoke_corpus_loads_with_frozen_hashes_and_is_not_selection_evidence() -> None:
    manifest, cases = load_frozen_corpus(CORPUS_DIR / "manifest.json")

    assert manifest.corpus_id == "vitaminbot-label-smoke"
    assert manifest.corpus_version == "0.1.0"
    assert len(cases) == 2
    assert manifest.provider_benchmark_eligible is False
    with pytest.raises(BenchmarkManifestError):
        require_provider_benchmark_eligible(manifest)


def test_project_owned_synthetic_cases_are_explicitly_allowed_for_external_processing() -> None:
    _, cases = load_frozen_corpus(CORPUS_DIR / "manifest.json")

    for case in cases:
        require_external_processing_allowed(case.manifest)
        assert case.manifest.rights_state.value == "project_owned_synthetic"
        assert case.manifest.source_class.value == "synthetic_project_owned"


def test_frozen_corpus_detects_image_hash_tampering(tmp_path: Path) -> None:
    manifest_path = CORPUS_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    payload = cast(dict[str, object], manifest)
    cases = cast(list[object], payload["cases"])
    first = cast(dict[str, object], cases[0])
    first["image_sha256"] = "0" * 64

    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    for source in CORPUS_DIR.iterdir():
        if source.name == "manifest.json":
            continue
        (tmp_path / source.name).write_bytes(source.read_bytes())

    with pytest.raises(BenchmarkManifestError, match="image checksum mismatch"):
        load_frozen_corpus(target)


def test_scorer_keeps_hallucination_separate_from_generic_field_errors() -> None:
    _, cases = load_frozen_corpus(CORPUS_DIR / "manifest.json")
    case = next(case for case in cases if case.manifest.case_id == "vitamin-d-iu-clear")
    payload = case.gold.to_payload()
    rows = cast(list[object], payload["rows"])
    extra = {
        "row_id": "row:invented-calcium",
        "row_raw_text": "Calcium 500 mg",
        "printed_name": {
            "field_id": "row:invented:name",
            "source_kind": "label_image",
            "presence_state": "present",
            "raw_text": "Calcium",
            "normalized_candidate": "calcium",
        },
        "quantity": {
            "field_id": "row:invented:quantity",
            "source_kind": "label_image",
            "presence_state": "present",
            "raw_text": "500",
            "normalized_candidate": "500",
        },
        "unit": {
            "field_id": "row:invented:unit",
            "source_kind": "label_image",
            "presence_state": "present",
            "raw_text": "mg",
            "normalized_candidate": "mg",
        },
    }
    rows.append(extra)
    actual = validate_extraction_payload(payload)

    score = score_extraction(case, actual)

    assert score.missing_field_ids == ()
    assert score.raw_text_mismatch_ids == ()
    assert set(score.hallucinated_field_ids) == {
        "row:invented:name",
        "row:invented:quantity",
        "row:invented:unit",
    }
    assert score.estimated_manual_field_actions == 3


def test_ambiguous_magnesium_scores_correct_abstention_as_correct() -> None:
    _, cases = load_frozen_corpus(CORPUS_DIR / "manifest.json")
    case = next(case for case in cases if case.manifest.case_id == "magnesium-compound-ambiguous")

    score = score_extraction(case, case.gold)

    assert case.gold.record_state is RecordState.USER_RESOLUTION_REQUIRED
    assert score.correct_abstention_routing is True
    assert score.expected_record_state_match is True
    assert score.hallucinated_field_ids == ()


def test_missing_abstention_is_reported_independently() -> None:
    _, cases = load_frozen_corpus(CORPUS_DIR / "manifest.json")
    case = next(case for case in cases if case.manifest.case_id == "magnesium-compound-ambiguous")
    actual = replace(
        case.gold,
        record_state=RecordState.EXTRACTED_UNCONFIRMED,
        record_ambiguities=(),
        rows=(replace(case.gold.rows[0], ambiguity_codes=()),),
    )

    score = score_extraction(case, actual)

    assert score.correct_abstention_routing is False
    assert score.expected_record_state_match is False


def test_manifest_declares_safety_significant_field_roles() -> None:
    _, cases = load_frozen_corpus(CORPUS_DIR / "manifest.json")
    vitamin_d = next(case for case in cases if case.manifest.case_id == "vitamin-d-iu-clear")
    roles = dict(vitamin_d.manifest.field_roles)

    assert roles["row:d3:quantity"] is FieldRole.QUANTITY
    assert roles["row:d3:unit"] is FieldRole.UNIT
    assert roles["row:d3:form"] is FieldRole.CHEMICAL_FORM
