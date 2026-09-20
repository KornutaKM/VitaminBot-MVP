from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import cast

from vitaminbot.recognition.contract import (
    FieldObservation,
    LabelExtraction,
    RecognitionValidationError,
    RecordState,
    validate_extraction_payload,
)
from vitaminbot.recognition.pipeline import iter_label_fields


class BenchmarkManifestError(ValueError):
    """Raised when a frozen KIR-147 corpus manifest is unsafe or inconsistent."""


class RightsState(StrEnum):
    PROJECT_OWNED_SYNTHETIC = "project_owned_synthetic"
    TEAM_CAPTURED_INTERNAL_USE = "team_captured_internal_use"
    PERMISSIVE_REDISTRIBUTION = "permissive_redistribution"
    PUBLIC_DOMAIN = "public_domain"
    RIGHTS_RESTRICTED_INTERNAL_ONLY = "rights_restricted_internal_only"
    RIGHTS_UNKNOWN_DO_NOT_USE = "rights_unknown_do_not_use"


class SourceClass(StrEnum):
    SYNTHETIC_PROJECT_OWNED = "synthetic_project_owned"
    TEAM_SELF_CAPTURED = "team_self_captured"
    PUBLIC_PERMISSIVE = "public_permissive"


class FieldRole(StrEnum):
    PRODUCT_NAME = "product_name"
    BRAND = "brand"
    SERVING_SIZE = "serving_size"
    SERVING_BASIS = "serving_basis"
    INGREDIENT_OR_NUTRIENT_NAME = "ingredient_or_nutrient_name"
    QUANTITY = "quantity"
    UNIT = "unit"
    CHEMICAL_FORM = "chemical_form"
    ELEMENTAL_OR_EQUIVALENT = "elemental_or_equivalent_amount"
    REFERENCE_VALUE = "reference_value"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class BenchmarkCaseManifest:
    case_id: str
    artifact_id: str
    source_class: SourceClass
    rights_state: RightsState
    external_provider_processing_allowed: bool
    image_path: str
    image_encoding: str
    image_sha256: str
    gold_path: str
    gold_sha256: str
    split: str
    quality_tags: tuple[str, ...]
    adversarial_tags: tuple[str, ...]
    field_roles: tuple[tuple[str, FieldRole], ...]
    duplicate_group_id: str | None = None
    near_duplicate_group_id: str | None = None
    variant_group_id: str | None = None
    transformation_source_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("case_id", self.case_id),
            ("artifact_id", self.artifact_id),
            ("image_path", self.image_path),
            ("gold_path", self.gold_path),
            ("split", self.split),
        ):
            if not value.strip():
                raise BenchmarkManifestError(f"{field_name} must not be blank")
        if self.rights_state is RightsState.RIGHTS_UNKNOWN_DO_NOT_USE:
            raise BenchmarkManifestError(
                "rights_unknown_do_not_use case cannot enter a frozen corpus"
            )
        if self.image_encoding not in {"base64", "raw"}:
            raise BenchmarkManifestError("image_encoding must be base64 or raw")
        _require_sha256(self.image_sha256, "image_sha256")
        _require_sha256(self.gold_sha256, "gold_sha256")
        field_ids = tuple(field_id for field_id, _ in self.field_roles)
        if len(set(field_ids)) != len(field_ids):
            raise BenchmarkManifestError("field_roles field IDs must be unique")


@dataclass(frozen=True, slots=True)
class FrozenCorpusManifest:
    corpus_id: str
    corpus_version: str
    frozen_at: str
    annotation_protocol_version: str
    recognition_contract_revision: str
    source_policy_revision: str
    cases: tuple[BenchmarkCaseManifest, ...]
    known_limitations: tuple[str, ...]
    provider_benchmark_eligible: bool

    def __post_init__(self) -> None:
        for field_name, value in (
            ("corpus_id", self.corpus_id),
            ("corpus_version", self.corpus_version),
            ("frozen_at", self.frozen_at),
            ("annotation_protocol_version", self.annotation_protocol_version),
            ("recognition_contract_revision", self.recognition_contract_revision),
            ("source_policy_revision", self.source_policy_revision),
        ):
            if not value.strip():
                raise BenchmarkManifestError(f"{field_name} must not be blank")
        if not self.cases:
            raise BenchmarkManifestError("frozen corpus must contain at least one case")
        case_ids = tuple(case.case_id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise BenchmarkManifestError("case IDs must be unique")
        _validate_split_leakage(self.cases)


@dataclass(frozen=True, slots=True)
class LoadedBenchmarkCase:
    manifest: BenchmarkCaseManifest
    image: bytes
    gold: LabelExtraction


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    schema_valid: bool
    schema_error: str | None
    raw_label_text_exact: bool
    missing_field_ids: tuple[str, ...]
    hallucinated_field_ids: tuple[str, ...]
    raw_text_mismatch_ids: tuple[str, ...]
    normalized_candidate_mismatch_ids: tuple[str, ...]
    source_region_missing_ids: tuple[str, ...]
    quantity_error_ids: tuple[str, ...]
    unit_error_ids: tuple[str, ...]
    serving_basis_error_ids: tuple[str, ...]
    chemical_form_error_ids: tuple[str, ...]
    expected_record_state_match: bool
    correct_abstention_routing: bool
    estimated_manual_field_actions: int


@dataclass(frozen=True, slots=True)
class BenchmarkRunMetadata:
    run_id: str
    corpus_id: str
    corpus_version: str
    case_id: str
    provider_arm_id: str
    provider_family: str
    provider_model_revision: str
    adapter_revision: str
    prompt_revision: str
    schema_revision: str
    preprocessing_revision: str
    image_sha256: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("run_id", self.run_id),
            ("corpus_id", self.corpus_id),
            ("corpus_version", self.corpus_version),
            ("case_id", self.case_id),
            ("provider_arm_id", self.provider_arm_id),
            ("provider_family", self.provider_family),
            ("provider_model_revision", self.provider_model_revision),
            ("adapter_revision", self.adapter_revision),
            ("prompt_revision", self.prompt_revision),
            ("schema_revision", self.schema_revision),
            ("preprocessing_revision", self.preprocessing_revision),
        ):
            if not value.strip():
                raise BenchmarkManifestError(f"{field_name} must not be blank")
        _require_sha256(self.image_sha256, "image_sha256")


@dataclass(frozen=True, slots=True)
class BenchmarkRunRecord:
    metadata: BenchmarkRunMetadata
    score: BenchmarkScore


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise BenchmarkManifestError(f"{field_name} must be a hexadecimal SHA-256 digest")


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise BenchmarkManifestError(f"{field_name} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise BenchmarkManifestError(f"{field_name} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkManifestError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise BenchmarkManifestError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{field_name} item") for item in _sequence(value, field_name))


def _enum_value[T: StrEnum](
    enum_type: type[T],
    value: object,
    field_name: str,
) -> T:
    raw = _string(value, field_name)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise BenchmarkManifestError(f"{field_name} has unsupported value {raw!r}") from exc


def _parse_field_roles(value: object) -> tuple[tuple[str, FieldRole], ...]:
    mapping = _mapping(value, "field_roles")
    pairs: list[tuple[str, FieldRole]] = []
    for field_id, raw_role in mapping.items():
        if not isinstance(field_id, str) or not field_id.strip():
            raise BenchmarkManifestError("field_roles keys must be non-empty strings")
        pairs.append(
            (
                field_id,
                _enum_value(FieldRole, raw_role, f"field_roles[{field_id!r}]"),
            )
        )
    return tuple(sorted(pairs))


def _parse_case(value: object) -> BenchmarkCaseManifest:
    payload = _mapping(value, "case")
    return BenchmarkCaseManifest(
        case_id=_string(payload.get("case_id"), "case_id"),
        artifact_id=_string(payload.get("artifact_id"), "artifact_id"),
        source_class=_enum_value(
            SourceClass,
            payload.get("source_class"),
            "source_class",
        ),
        rights_state=_enum_value(
            RightsState,
            payload.get("rights_state"),
            "rights_state",
        ),
        external_provider_processing_allowed=_boolean(
            payload.get("external_provider_processing_allowed"),
            "external_provider_processing_allowed",
        ),
        image_path=_string(payload.get("image_path"), "image_path"),
        image_encoding=_string(payload.get("image_encoding"), "image_encoding"),
        image_sha256=_string(payload.get("image_sha256"), "image_sha256"),
        gold_path=_string(payload.get("gold_path"), "gold_path"),
        gold_sha256=_string(payload.get("gold_sha256"), "gold_sha256"),
        split=_string(payload.get("split"), "split"),
        quality_tags=_string_tuple(payload.get("quality_tags", []), "quality_tags"),
        adversarial_tags=_string_tuple(
            payload.get("adversarial_tags", []),
            "adversarial_tags",
        ),
        field_roles=_parse_field_roles(payload.get("field_roles", {})),
        duplicate_group_id=_optional_string(
            payload.get("duplicate_group_id"),
            "duplicate_group_id",
        ),
        near_duplicate_group_id=_optional_string(
            payload.get("near_duplicate_group_id"),
            "near_duplicate_group_id",
        ),
        variant_group_id=_optional_string(
            payload.get("variant_group_id"),
            "variant_group_id",
        ),
        transformation_source_id=_optional_string(
            payload.get("transformation_source_id"),
            "transformation_source_id",
        ),
    )


def _validate_split_leakage(cases: tuple[BenchmarkCaseManifest, ...]) -> None:
    for attr in (
        "duplicate_group_id",
        "near_duplicate_group_id",
        "variant_group_id",
        "transformation_source_id",
    ):
        groups: dict[str, set[str]] = {}
        for case in cases:
            group = getattr(case, attr)
            if group is None:
                continue
            groups.setdefault(group, set()).add(case.split)
        leaked = sorted(group for group, splits in groups.items() if len(splits) > 1)
        if leaked:
            raise BenchmarkManifestError(f"{attr} groups cross corpus splits: {', '.join(leaked)}")


def load_frozen_corpus(
    manifest_path: Path,
) -> tuple[
    FrozenCorpusManifest,
    tuple[LoadedBenchmarkCase, ...],
]:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _mapping(raw, "manifest")
    cases = tuple(_parse_case(item) for item in _sequence(payload.get("cases"), "cases"))
    manifest = FrozenCorpusManifest(
        corpus_id=_string(payload.get("corpus_id"), "corpus_id"),
        corpus_version=_string(payload.get("corpus_version"), "corpus_version"),
        frozen_at=_string(payload.get("frozen_at"), "frozen_at"),
        annotation_protocol_version=_string(
            payload.get("annotation_protocol_version"),
            "annotation_protocol_version",
        ),
        recognition_contract_revision=_string(
            payload.get("recognition_contract_revision"),
            "recognition_contract_revision",
        ),
        source_policy_revision=_string(
            payload.get("source_policy_revision"),
            "source_policy_revision",
        ),
        cases=cases,
        known_limitations=_string_tuple(
            payload.get("known_limitations", []),
            "known_limitations",
        ),
        provider_benchmark_eligible=_boolean(
            payload.get("provider_benchmark_eligible"),
            "provider_benchmark_eligible",
        ),
    )

    root = manifest_path.parent
    loaded: list[LoadedBenchmarkCase] = []
    for case in manifest.cases:
        image_file = root / case.image_path
        gold_file = root / case.gold_path
        image_stored = image_file.read_bytes()
        image = (
            base64.b64decode(image_stored, validate=True)
            if case.image_encoding == "base64"
            else image_stored
        )
        gold_bytes = gold_file.read_bytes()
        if sha256(image).hexdigest() != case.image_sha256:
            raise BenchmarkManifestError(f"image checksum mismatch for case {case.case_id!r}")
        if sha256(gold_bytes).hexdigest() != case.gold_sha256:
            raise BenchmarkManifestError(f"gold checksum mismatch for case {case.case_id!r}")
        gold_raw = json.loads(gold_bytes.decode("utf-8"))
        gold_payload = _mapping(gold_raw, f"gold payload for {case.case_id}")
        try:
            gold = validate_extraction_payload(gold_payload)
        except RecognitionValidationError as exc:
            raise BenchmarkManifestError(
                f"invalid gold extraction for case {case.case_id!r}: {exc}"
            ) from exc
        loaded.append(
            LoadedBenchmarkCase(
                manifest=case,
                image=image,
                gold=gold,
            )
        )
    return manifest, tuple(loaded)


def _index_fields(extraction: LabelExtraction) -> dict[str, FieldObservation]:
    fields = iter_label_fields(extraction)
    ids = tuple(field.field_id for field in fields)
    if len(set(ids)) != len(ids):
        raise BenchmarkManifestError("extraction field IDs must be unique for scoring")
    return {field.field_id: field for field in fields}


def _role_errors(
    case: BenchmarkCaseManifest,
    error_ids: set[str],
    role: FieldRole,
) -> tuple[str, ...]:
    role_map = dict(case.field_roles)
    return tuple(sorted(field_id for field_id in error_ids if role_map.get(field_id) is role))



def require_external_processing_allowed(case: BenchmarkCaseManifest) -> None:
    """Fail closed before a benchmark case is sent to an external provider."""

    if not case.external_provider_processing_allowed:
        raise BenchmarkManifestError(
            f"case {case.case_id!r} is not authorized for external provider processing"
        )


def require_provider_benchmark_eligible(manifest: FrozenCorpusManifest) -> None:
    """Fail closed when a smoke/incomplete corpus is used as provider-selection evidence."""

    if not manifest.provider_benchmark_eligible:
        raise BenchmarkManifestError(
            "corpus is not authorized for provider benchmark/selection evidence"
        )


def score_extraction(
    case: LoadedBenchmarkCase,
    actual: LabelExtraction,
) -> BenchmarkScore:
    expected_fields = _index_fields(case.gold)
    actual_fields = _index_fields(actual)
    expected_ids = set(expected_fields)
    actual_ids = set(actual_fields)
    missing = tuple(sorted(expected_ids - actual_ids))
    hallucinated = tuple(sorted(actual_ids - expected_ids))

    raw_mismatches: set[str] = set()
    normalized_mismatches: set[str] = set()
    region_missing: set[str] = set()
    for field_id in sorted(expected_ids & actual_ids):
        expected = expected_fields[field_id]
        actual_field = actual_fields[field_id]
        if (
            expected.raw_text != actual_field.raw_text
            or expected.presence_state is not actual_field.presence_state
        ):
            raw_mismatches.add(field_id)
        if expected.normalized_candidate != actual_field.normalized_candidate:
            normalized_mismatches.add(field_id)
        if expected.source_regions and not actual_field.source_regions:
            region_missing.add(field_id)

    generic_errors = set(missing) | raw_mismatches | normalized_mismatches
    expected_needs_resolution = (
        case.gold.record_state
        in (RecordState.USER_RESOLUTION_REQUIRED, RecordState.MANUAL_ENTRY_REQUIRED)
        or case.gold.requires_user_resolution
    )
    actual_needs_resolution = (
        actual.record_state
        in (RecordState.USER_RESOLUTION_REQUIRED, RecordState.MANUAL_ENTRY_REQUIRED)
        or actual.requires_user_resolution
    )
    false_or_missing_abstention = expected_needs_resolution != actual_needs_resolution
    manual_actions = (
        len(missing)
        + len(hallucinated)
        + len(raw_mismatches)
        + (1 if false_or_missing_abstention else 0)
    )

    return BenchmarkScore(
        schema_valid=True,
        schema_error=None,
        raw_label_text_exact=case.gold.raw_label_text == actual.raw_label_text,
        missing_field_ids=missing,
        hallucinated_field_ids=hallucinated,
        raw_text_mismatch_ids=tuple(sorted(raw_mismatches)),
        normalized_candidate_mismatch_ids=tuple(sorted(normalized_mismatches)),
        source_region_missing_ids=tuple(sorted(region_missing)),
        quantity_error_ids=_role_errors(
            case.manifest,
            generic_errors,
            FieldRole.QUANTITY,
        ),
        unit_error_ids=_role_errors(
            case.manifest,
            generic_errors,
            FieldRole.UNIT,
        ),
        serving_basis_error_ids=_role_errors(
            case.manifest,
            generic_errors,
            FieldRole.SERVING_BASIS,
        ),
        chemical_form_error_ids=_role_errors(
            case.manifest,
            generic_errors,
            FieldRole.CHEMICAL_FORM,
        ),
        expected_record_state_match=case.gold.record_state is actual.record_state,
        correct_abstention_routing=not false_or_missing_abstention,
        estimated_manual_field_actions=manual_actions,
    )


def score_payload(
    case: LoadedBenchmarkCase,
    payload: Mapping[str, object],
) -> BenchmarkScore:
    try:
        actual = validate_extraction_payload(payload)
    except RecognitionValidationError as exc:
        expected_ids = tuple(sorted(field.field_id for field in iter_label_fields(case.gold)))
        return BenchmarkScore(
            schema_valid=False,
            schema_error=str(exc),
            raw_label_text_exact=False,
            missing_field_ids=expected_ids,
            hallucinated_field_ids=(),
            raw_text_mismatch_ids=(),
            normalized_candidate_mismatch_ids=(),
            source_region_missing_ids=(),
            quantity_error_ids=_role_errors(
                case.manifest,
                set(expected_ids),
                FieldRole.QUANTITY,
            ),
            unit_error_ids=_role_errors(
                case.manifest,
                set(expected_ids),
                FieldRole.UNIT,
            ),
            serving_basis_error_ids=_role_errors(
                case.manifest,
                set(expected_ids),
                FieldRole.SERVING_BASIS,
            ),
            chemical_form_error_ids=_role_errors(
                case.manifest,
                set(expected_ids),
                FieldRole.CHEMICAL_FORM,
            ),
            expected_record_state_match=False,
            correct_abstention_routing=False,
            estimated_manual_field_actions=len(expected_ids),
        )
    return score_extraction(case, actual)
