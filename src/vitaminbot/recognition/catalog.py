from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Final, Protocol
from urllib.parse import parse_qsl, unquote, urlparse

CATALOG_CONTRACT_VERSION: Final = "1.0.0"
CATALOG_LABEL_CONFLICT: Final = "catalog_label_conflict"
INCOMPLETE_RECORD_FLAG: Final = "incomplete_record"


class CatalogContractError(ValueError):
    """Raised when a KIR-118 catalog adapter violates the project-owned contract."""


class CatalogProviderError(RuntimeError):
    """Base class for expected provider failures that must degrade without blocking entry."""


class ProviderUnavailableError(CatalogProviderError):
    pass


class ProviderRateLimitedError(CatalogProviderError):
    pass


class ProviderAccessDeniedError(CatalogProviderError):
    pass


class ProviderMalformedResponseError(CatalogProviderError):
    pass


class ScanKind(StrEnum):
    LINEAR_BARCODE = "linear_barcode"
    QR = "qr"
    DATA_MATRIX = "data_matrix"
    MANUAL_IDENTIFIER = "manual_identifier"


class IdentifierType(StrEnum):
    GTIN_8 = "gtin_8"
    GTIN_12 = "gtin_12"
    GTIN_13 = "gtin_13"
    GTIN_14 = "gtin_14"
    GS1_DIGITAL_LINK = "gs1_digital_link"
    UNKNOWN = "unknown"


class ProviderClass(StrEnum):
    AUTHORITATIVE_IDENTITY = "authoritative_identity"
    PRODUCT_MASTER_DATA = "product_master_data"
    OPEN_COMMUNITY_CATALOG = "open_community_catalog"
    COMMERCIAL_AGGREGATOR = "commercial_aggregator"
    RESOLVER = "resolver"


class QueryMode(StrEnum):
    EXACT_IDENTIFIER = "exact_identifier"
    DIGITAL_LINK_RESOLUTION = "digital_link_resolution"


class ProviderResultState(StrEnum):
    NO_MATCH = "no_match"
    SINGLE_EXACT_MATCH = "single_exact_match"
    MULTIPLE_MATCHES = "multiple_matches"
    PARTIAL_MATCH = "partial_match"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    ACCESS_DENIED = "access_denied"
    MALFORMED_RESPONSE = "malformed_response"


class VerificationState(StrEnum):
    EXTERNAL_UNVERIFIED = "external_unverified"


class FreshnessState(StrEnum):
    PROVIDER_TIMESTAMP_CURRENT_UNKNOWN_SEMANTICS = "provider_timestamp_current_unknown_semantics"
    PROVIDER_TIMESTAMP_MISSING = "provider_timestamp_missing"
    CATALOG_LABEL_CONFLICT = "catalog_label_conflict"
    POSSIBLE_OLD_PACKAGE = "possible_old_package"
    PROVIDER_MARKS_OBSOLETE = "provider_marks_obsolete"
    FRESHNESS_UNRESOLVED = "freshness_unresolved"


class DiscoveryState(StrEnum):
    IDENTIFIER_UNRESOLVED = "identifier_unresolved"
    CATALOG_CANDIDATE_FOUND = "catalog_candidate_found"
    CATALOG_AMBIGUOUS = "catalog_ambiguous"
    CATALOG_INCOMPLETE_OR_STALE = "catalog_incomplete_or_stale"
    CATALOG_LABEL_CONFLICT = "catalog_label_conflict"
    NO_CATALOG_MATCH = "no_catalog_match"
    LOOKUP_DEGRADED = "lookup_degraded"


class RecommendedAction(StrEnum):
    CONFIRM_IDENTITY = "confirm_identity"
    PHOTO_OR_MANUAL = "photo_or_manual"


class FallbackRoute(StrEnum):
    LABEL_PHOTO = "label_photo"
    MANUAL_ENTRY = "manual_entry"


_FAILURE_STATES: Final[frozenset[ProviderResultState]] = frozenset(
    {
        ProviderResultState.PROVIDER_UNAVAILABLE,
        ProviderResultState.RATE_LIMITED,
        ProviderResultState.ACCESS_DENIED,
        ProviderResultState.MALFORMED_RESPONSE,
    }
)


def _require_nonblank(value: str, field_name: str) -> None:
    if not value.strip():
        raise CatalogContractError(f"{field_name} must not be blank")


def _require_optional_nonblank(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_nonblank(value, field_name)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CatalogContractError(f"{field_name} must be timezone-aware")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True)
class GS1Qualifier:
    ai: str
    value: str

    def __post_init__(self) -> None:
        _require_nonblank(self.ai, "qualifier ai")
        _require_nonblank(self.value, "qualifier value")


@dataclass(frozen=True, slots=True)
class LookupRequest:
    request_id: str
    raw_scan: str
    scan_kind: ScanKind
    normalized_identifier: str
    identifier_type: IdentifierType
    check_digit_valid: bool | None
    requested_at: datetime
    digital_link_uri: str | None = None
    gs1_primary_key: str | None = None
    gs1_qualifiers: tuple[GS1Qualifier, ...] = ()
    market_context: str | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.request_id, "request_id")
        _require_nonblank(self.raw_scan, "raw_scan")
        _require_nonblank(self.normalized_identifier, "normalized_identifier")
        _require_aware(self.requested_at, "requested_at")
        if self.market_context is not None:
            _require_nonblank(self.market_context, "market_context")
        if self.identifier_type is IdentifierType.GS1_DIGITAL_LINK:
            if self.digital_link_uri is None or self.gs1_primary_key is None:
                raise CatalogContractError(
                    "GS1 Digital Link requests require URI and primary key provenance"
                )
        elif self.digital_link_uri is not None or self.gs1_primary_key is not None:
            raise CatalogContractError(
                "digital_link_uri and gs1_primary_key are valid only for Digital Link"
            )

    @property
    def lookup_permitted(self) -> bool:
        return (
            self.identifier_type is not IdentifierType.UNKNOWN
            and self.check_digit_valid is not False
        )


@dataclass(frozen=True, slots=True)
class ConfirmedLabelFact:
    field_name: str
    raw_value: str
    source_reference: str

    def __post_init__(self) -> None:
        _require_nonblank(self.field_name, "field_name")
        _require_nonblank(self.raw_value, "raw_value")
        _require_nonblank(self.source_reference, "source_reference")


@dataclass(frozen=True, slots=True)
class SourcedCandidateField:
    field_name: str
    raw_value: str
    provider_key: str
    source_path: str
    retrieved_at: datetime
    normalized_candidate: str | None = None
    provider_record_id: str | None = None
    provider_updated_at: datetime | None = None
    source_url: str | None = None
    license_class: str | None = None
    rights_note: str | None = None
    verification_state: VerificationState = VerificationState.EXTERNAL_UNVERIFIED
    conflicts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("field_name", self.field_name),
            ("raw_value", self.raw_value),
            ("provider_key", self.provider_key),
            ("source_path", self.source_path),
        ):
            _require_nonblank(value, field_name)
        _require_aware(self.retrieved_at, "retrieved_at")
        if self.normalized_candidate is not None:
            _require_nonblank(self.normalized_candidate, "normalized_candidate")
        if self.provider_record_id is not None:
            _require_nonblank(self.provider_record_id, "provider_record_id")
        if self.provider_updated_at is not None:
            _require_aware(self.provider_updated_at, "provider_updated_at")
        _require_optional_nonblank(self.source_url, "source_url")
        _require_optional_nonblank(self.license_class, "license_class")
        _require_optional_nonblank(self.rights_note, "rights_note")
        if any(not conflict.strip() for conflict in self.conflicts):
            raise CatalogContractError("field conflicts must not contain blank values")


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    reference: str
    provider_key: str
    retrieved_at: datetime
    related_identifier: str
    provider_record_id: str | None = None
    image_role: str | None = None
    rights_note: str | None = None
    cache_display_permission: str = "unknown"
    package_match_state: str = "unknown"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("reference", self.reference),
            ("provider_key", self.provider_key),
            ("related_identifier", self.related_identifier),
            ("cache_display_permission", self.cache_display_permission),
            ("package_match_state", self.package_match_state),
        ):
            _require_nonblank(value, field_name)
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_optional_nonblank(self.provider_record_id, "provider_record_id")
        _require_optional_nonblank(self.image_role, "image_role")
        _require_optional_nonblank(self.rights_note, "rights_note")


@dataclass(frozen=True, slots=True)
class CatalogCandidate:
    provider_key: str
    identifiers: tuple[str, ...]
    freshness_state: FreshnessState
    fields: tuple[SourcedCandidateField, ...] = ()
    images: tuple[ImageCandidate, ...] = ()
    provider_record_id: str | None = None
    provider_quality_flags: tuple[str, ...] = ()
    candidate_conflicts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank(self.provider_key, "provider_key")
        if not self.identifiers:
            raise CatalogContractError("catalog candidate requires at least one identifier")
        if any(not identifier.strip() for identifier in self.identifiers):
            raise CatalogContractError("candidate identifiers must not be blank")
        if self.provider_record_id is not None:
            _require_nonblank(self.provider_record_id, "provider_record_id")
        field_names = [field.field_name for field in self.fields]
        if len(field_names) != len(set(field_names)):
            raise CatalogContractError(
                "catalog candidate cannot silently choose between duplicate field names"
            )
        for sourced_field in self.fields:
            if sourced_field.provider_key != self.provider_key:
                raise CatalogContractError("field provider_key must match candidate provider")
            if self.provider_record_id is not None and sourced_field.provider_record_id not in (
                None,
                self.provider_record_id,
            ):
                raise CatalogContractError(
                    "field provider_record_id must match candidate provider record"
                )
        for image in self.images:
            if image.provider_key != self.provider_key:
                raise CatalogContractError("image provider_key must match candidate provider")
        if any(not flag.strip() for flag in self.provider_quality_flags):
            raise CatalogContractError("provider quality flags must not be blank")
        if any(not conflict.strip() for conflict in self.candidate_conflicts):
            raise CatalogContractError("candidate conflicts must not be blank")


@dataclass(frozen=True, slots=True)
class ProviderLookupResult:
    provider_key: str
    provider_class: ProviderClass
    adapter_version: str
    query_mode: QueryMode
    queried_identifier: str
    retrieved_at: datetime
    result_state: ProviderResultState
    candidates: tuple[CatalogCandidate, ...] = ()
    raw_response_reference_or_hash: str | None = None
    provider_error: str | None = None
    license_class: str | None = None
    rights_note: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("provider_key", self.provider_key),
            ("adapter_version", self.adapter_version),
            ("queried_identifier", self.queried_identifier),
        ):
            _require_nonblank(value, field_name)
        _require_aware(self.retrieved_at, "retrieved_at")
        _require_optional_nonblank(
            self.raw_response_reference_or_hash,
            "raw_response_reference_or_hash",
        )
        _require_optional_nonblank(self.provider_error, "provider_error")
        _require_optional_nonblank(self.license_class, "license_class")
        _require_optional_nonblank(self.rights_note, "rights_note")

        if self.result_state is ProviderResultState.NO_MATCH and self.candidates:
            raise CatalogContractError("no_match provider result cannot contain candidates")
        if self.result_state is ProviderResultState.SINGLE_EXACT_MATCH:
            if len(self.candidates) != 1:
                raise CatalogContractError("single_exact_match requires exactly one candidate")
        if self.result_state is ProviderResultState.MULTIPLE_MATCHES:
            if len(self.candidates) < 2:
                raise CatalogContractError("multiple_matches requires at least two candidates")
        if self.result_state is ProviderResultState.PARTIAL_MATCH and not self.candidates:
            raise CatalogContractError("partial_match requires at least one candidate")
        if self.result_state in _FAILURE_STATES:
            if self.candidates:
                raise CatalogContractError("provider failure cannot contain candidates")
            if self.provider_error is None:
                raise CatalogContractError("provider failure requires provider_error")
        elif self.provider_error is not None:
            raise CatalogContractError("provider_error is valid only for failure states")

        for candidate in self.candidates:
            if candidate.provider_key != self.provider_key:
                raise CatalogContractError("candidate provider_key must match provider result")


class CatalogLookupProvider(Protocol):
    provider_key: str
    provider_class: ProviderClass
    adapter_version: str
    license_class: str | None
    rights_note: str | None

    def lookup(self, request: LookupRequest) -> ProviderLookupResult:
        """Return provider-native observations mapped to the KIR-118 contract."""


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    candidate_id: str
    candidate: CatalogCandidate

    def __post_init__(self) -> None:
        _require_nonblank(self.candidate_id, "candidate_id")


@dataclass(frozen=True, slots=True)
class CatalogDiscoveryOutcome:
    request: LookupRequest
    discovery_state: DiscoveryState
    provider_results: tuple[ProviderLookupResult, ...]
    candidates: tuple[DiscoveryCandidate, ...]
    recommended_action: RecommendedAction
    fallback_routes: tuple[FallbackRoute, ...]
    nutrition_confirmation_required: bool
    detail: str

    def __post_init__(self) -> None:
        _require_nonblank(self.detail, "detail")
        if not self.nutrition_confirmation_required:
            raise CatalogContractError("catalog discovery can never waive nutrition confirmation")


def _gtin_type(value: str) -> IdentifierType:
    return {
        8: IdentifierType.GTIN_8,
        12: IdentifierType.GTIN_12,
        13: IdentifierType.GTIN_13,
        14: IdentifierType.GTIN_14,
    }.get(len(value), IdentifierType.UNKNOWN)


def gtin_check_digit_valid(value: str) -> bool:
    if not value.isdigit() or len(value) not in (8, 12, 13, 14):
        return False
    body = value[:-1]
    total = 0
    weight = 3
    for character in reversed(body):
        total += int(character) * weight
        weight = 1 if weight == 3 else 3
    expected = (10 - (total % 10)) % 10
    return expected == int(value[-1])


def _compact_linear_scan(raw_scan: str) -> str | None:
    allowed = set("0123456789 -")
    if not raw_scan or any(character not in allowed for character in raw_scan):
        return None
    compact = raw_scan.replace(" ", "").replace("-", "")
    return compact if compact else None


def _digital_link_parts(raw_scan: str) -> tuple[str, tuple[GS1Qualifier, ...]] | None:
    parsed = urlparse(raw_scan)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    primary_index: int | None = None
    for index in range(0, len(segments) - 1):
        if segments[index] == "01":
            primary_index = index
            break
    if primary_index is None:
        return None

    gtin = segments[primary_index + 1]
    if len(gtin) != 14 or not gtin.isdigit():
        return None

    qualifiers: list[GS1Qualifier] = []
    remaining = segments[primary_index + 2 :]
    if len(remaining) % 2 != 0:
        return None
    for index in range(0, len(remaining), 2):
        qualifiers.append(GS1Qualifier(ai=remaining[index], value=remaining[index + 1]))
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        qualifiers.append(GS1Qualifier(ai=key, value=value))
    return gtin, tuple(qualifiers)


def parse_lookup_request(
    *,
    request_id: str,
    raw_scan: str,
    scan_kind: ScanKind,
    requested_at: datetime,
    market_context: str | None = None,
) -> LookupRequest:
    raw_value = raw_scan.strip()
    _require_nonblank(raw_value, "raw_scan")
    _require_aware(requested_at, "requested_at")

    digital_link = _digital_link_parts(raw_value)
    if digital_link is not None:
        gtin, qualifiers = digital_link
        return LookupRequest(
            request_id=request_id,
            raw_scan=raw_scan,
            scan_kind=scan_kind,
            normalized_identifier=gtin,
            identifier_type=IdentifierType.GS1_DIGITAL_LINK,
            check_digit_valid=gtin_check_digit_valid(gtin),
            requested_at=requested_at,
            digital_link_uri=raw_value,
            gs1_primary_key=f"01:{gtin}",
            gs1_qualifiers=qualifiers,
            market_context=market_context,
        )

    compact = _compact_linear_scan(raw_value)
    if compact is not None:
        identifier_type = _gtin_type(compact)
        if identifier_type is not IdentifierType.UNKNOWN:
            return LookupRequest(
                request_id=request_id,
                raw_scan=raw_scan,
                scan_kind=scan_kind,
                normalized_identifier=compact,
                identifier_type=identifier_type,
                check_digit_valid=gtin_check_digit_valid(compact),
                requested_at=requested_at,
                market_context=market_context,
            )

    return LookupRequest(
        request_id=request_id,
        raw_scan=raw_scan,
        scan_kind=scan_kind,
        normalized_identifier=raw_value,
        identifier_type=IdentifierType.UNKNOWN,
        check_digit_valid=None,
        requested_at=requested_at,
        market_context=market_context,
    )


def _query_mode(request: LookupRequest) -> QueryMode:
    if request.identifier_type is IdentifierType.GS1_DIGITAL_LINK:
        return QueryMode.DIGITAL_LINK_RESOLUTION
    return QueryMode.EXACT_IDENTIFIER


def _provider_failure_result(
    provider: CatalogLookupProvider,
    request: LookupRequest,
    *,
    state: ProviderResultState,
    detail: str,
    retrieved_at: datetime,
) -> ProviderLookupResult:
    return ProviderLookupResult(
        provider_key=provider.provider_key,
        provider_class=provider.provider_class,
        adapter_version=provider.adapter_version,
        query_mode=_query_mode(request),
        queried_identifier=request.normalized_identifier,
        retrieved_at=retrieved_at,
        result_state=state,
        provider_error=detail,
        license_class=provider.license_class,
        rights_note=provider.rights_note,
    )


def _candidate_payload(candidate: CatalogCandidate) -> Mapping[str, object]:
    return {
        "provider_key": candidate.provider_key,
        "provider_record_id": candidate.provider_record_id,
        "identifiers": list(candidate.identifiers),
        "freshness_state": candidate.freshness_state.value,
        "fields": [
            {
                "field_name": field.field_name,
                "raw_value": field.raw_value,
                "normalized_candidate": field.normalized_candidate,
                "provider_key": field.provider_key,
                "provider_record_id": field.provider_record_id,
                "source_path": field.source_path,
                "retrieved_at": field.retrieved_at.isoformat(),
                "provider_updated_at": (
                    field.provider_updated_at.isoformat()
                    if field.provider_updated_at is not None
                    else None
                ),
                "source_url": field.source_url,
                "license_class": field.license_class,
                "rights_note": field.rights_note,
                "verification_state": field.verification_state.value,
                "conflicts": list(field.conflicts),
            }
            for field in candidate.fields
        ],
        "images": [
            {
                "reference": image.reference,
                "provider_key": image.provider_key,
                "retrieved_at": image.retrieved_at.isoformat(),
                "related_identifier": image.related_identifier,
                "provider_record_id": image.provider_record_id,
                "image_role": image.image_role,
                "rights_note": image.rights_note,
                "cache_display_permission": image.cache_display_permission,
                "package_match_state": image.package_match_state,
            }
            for image in candidate.images
        ],
        "provider_quality_flags": list(candidate.provider_quality_flags),
        "candidate_conflicts": list(candidate.candidate_conflicts),
    }


def _project_candidate_id(request: LookupRequest, candidate: CatalogCandidate) -> str:
    canonical = json.dumps(
        {
            "contract_version": CATALOG_CONTRACT_VERSION,
            "request_id": request.request_id,
            "scan_identifier": request.normalized_identifier,
            "candidate": _candidate_payload(candidate),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"catalog-candidate-v1:{sha256(canonical).hexdigest()}"


def _comparison_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _apply_confirmed_label_conflicts(
    candidate: CatalogCandidate,
    confirmed_label_facts: Mapping[str, ConfirmedLabelFact],
) -> CatalogCandidate:
    fields: list[SourcedCandidateField] = []
    conflict_found = False
    for sourced_field in candidate.fields:
        label_fact = confirmed_label_facts.get(sourced_field.field_name)
        if label_fact is None:
            fields.append(sourced_field)
            continue
        catalog_value = sourced_field.normalized_candidate or sourced_field.raw_value
        if _comparison_text(catalog_value) == _comparison_text(label_fact.raw_value):
            fields.append(sourced_field)
            continue

        conflict_found = True
        conflicts = sourced_field.conflicts
        if CATALOG_LABEL_CONFLICT not in conflicts:
            conflicts = conflicts + (CATALOG_LABEL_CONFLICT,)
        fields.append(replace(sourced_field, conflicts=conflicts))

    if not conflict_found:
        return candidate

    candidate_conflicts = candidate.candidate_conflicts
    if CATALOG_LABEL_CONFLICT not in candidate_conflicts:
        candidate_conflicts = candidate_conflicts + (CATALOG_LABEL_CONFLICT,)
    return replace(
        candidate,
        fields=tuple(fields),
        freshness_state=FreshnessState.CATALOG_LABEL_CONFLICT,
        candidate_conflicts=candidate_conflicts,
    )


class CatalogDiscoveryService:
    def __init__(
        self,
        *,
        providers: tuple[CatalogLookupProvider, ...],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        provider_keys = [provider.provider_key for provider in providers]
        if any(not key.strip() for key in provider_keys):
            raise CatalogContractError("provider_key must not be blank")
        if len(provider_keys) != len(set(provider_keys)):
            raise CatalogContractError("configured provider keys must be unique")
        self._providers = providers
        self._clock = clock

    def discover(
        self,
        request: LookupRequest,
        *,
        confirmed_label_facts: tuple[ConfirmedLabelFact, ...] = (),
    ) -> CatalogDiscoveryOutcome:
        if not request.lookup_permitted:
            return self._fallback_outcome(
                request=request,
                state=DiscoveryState.IDENTIFIER_UNRESOLVED,
                provider_results=(),
                detail="identifier is unrecognized or has an invalid GTIN check digit",
            )

        label_facts = self._label_fact_map(confirmed_label_facts)
        provider_results: list[ProviderLookupResult] = []

        for provider in self._providers:
            result = self._lookup_provider(provider, request)
            provider_results.append(result)
            if result.result_state is ProviderResultState.NO_MATCH:
                continue
            if result.result_state in _FAILURE_STATES:
                continue
            return self._candidate_outcome(
                request=request,
                result=result,
                provider_results=tuple(provider_results),
                label_facts=label_facts,
            )

        if not provider_results or any(
            result.result_state in _FAILURE_STATES for result in provider_results
        ):
            return self._fallback_outcome(
                request=request,
                state=DiscoveryState.LOOKUP_DEGRADED,
                provider_results=tuple(provider_results),
                detail="catalog lookup did not yield a usable candidate",
            )
        return self._fallback_outcome(
            request=request,
            state=DiscoveryState.NO_CATALOG_MATCH,
            provider_results=tuple(provider_results),
            detail="configured providers returned no catalog match",
        )

    @staticmethod
    def _label_fact_map(
        facts: tuple[ConfirmedLabelFact, ...],
    ) -> dict[str, ConfirmedLabelFact]:
        mapped: dict[str, ConfirmedLabelFact] = {}
        for fact in facts:
            if fact.field_name in mapped:
                raise CatalogContractError(
                    "confirmed label facts must contain at most one value per field"
                )
            mapped[fact.field_name] = fact
        return mapped

    def _lookup_provider(
        self,
        provider: CatalogLookupProvider,
        request: LookupRequest,
    ) -> ProviderLookupResult:
        try:
            result = provider.lookup(request)
            self._validate_provider_result(provider, request, result)
            return result
        except ProviderUnavailableError as exc:
            state = ProviderResultState.PROVIDER_UNAVAILABLE
            detail = str(exc)
        except ProviderRateLimitedError as exc:
            state = ProviderResultState.RATE_LIMITED
            detail = str(exc)
        except ProviderAccessDeniedError as exc:
            state = ProviderResultState.ACCESS_DENIED
            detail = str(exc)
        except (ProviderMalformedResponseError, CatalogContractError) as exc:
            state = ProviderResultState.MALFORMED_RESPONSE
            detail = str(exc)

        retrieved_at = self._clock()
        _require_aware(retrieved_at, "clock value")
        return _provider_failure_result(
            provider,
            request,
            state=state,
            detail=detail or state.value,
            retrieved_at=retrieved_at,
        )

    @staticmethod
    def _validate_provider_result(
        provider: CatalogLookupProvider,
        request: LookupRequest,
        result: ProviderLookupResult,
    ) -> None:
        if result.provider_key != provider.provider_key:
            raise CatalogContractError("provider result key does not match configured provider")
        if result.provider_class is not provider.provider_class:
            raise CatalogContractError("provider result class does not match configured provider")
        if result.adapter_version != provider.adapter_version:
            raise CatalogContractError(
                "provider result adapter_version does not match configured provider"
            )
        if result.queried_identifier != request.normalized_identifier:
            raise CatalogContractError("provider result queried_identifier mismatch")
        if result.query_mode is not _query_mode(request):
            raise CatalogContractError("provider result query_mode mismatch")

        if result.result_state is ProviderResultState.SINGLE_EXACT_MATCH:
            candidate = result.candidates[0]
            if request.normalized_identifier not in candidate.identifiers:
                raise CatalogContractError(
                    "single_exact_match candidate must preserve the queried identifier"
                )

    def _candidate_outcome(
        self,
        *,
        request: LookupRequest,
        result: ProviderLookupResult,
        provider_results: tuple[ProviderLookupResult, ...],
        label_facts: Mapping[str, ConfirmedLabelFact],
    ) -> CatalogDiscoveryOutcome:
        candidates = tuple(
            _apply_confirmed_label_conflicts(candidate, label_facts)
            for candidate in result.candidates
        )
        discovery_candidates = tuple(
            DiscoveryCandidate(
                candidate_id=_project_candidate_id(request, candidate),
                candidate=candidate,
            )
            for candidate in candidates
        )

        if result.result_state is ProviderResultState.MULTIPLE_MATCHES:
            return self._fallback_outcome(
                request=request,
                state=DiscoveryState.CATALOG_AMBIGUOUS,
                provider_results=provider_results,
                candidates=discovery_candidates,
                detail="multiple catalog candidates require explicit user or label resolution",
            )

        if any(candidate.candidate_conflicts for candidate in candidates):
            return self._fallback_outcome(
                request=request,
                state=DiscoveryState.CATALOG_LABEL_CONFLICT,
                provider_results=provider_results,
                candidates=discovery_candidates,
                detail="catalog candidate conflicts with confirmed current-label evidence",
            )

        if result.result_state is ProviderResultState.PARTIAL_MATCH or any(
            self._candidate_requires_freshness_fallback(candidate) for candidate in candidates
        ):
            return self._fallback_outcome(
                request=request,
                state=DiscoveryState.CATALOG_INCOMPLETE_OR_STALE,
                provider_results=provider_results,
                candidates=discovery_candidates,
                detail="catalog candidate is incomplete or freshness remains unresolved",
            )

        return CatalogDiscoveryOutcome(
            request=request,
            discovery_state=DiscoveryState.CATALOG_CANDIDATE_FOUND,
            provider_results=provider_results,
            candidates=discovery_candidates,
            recommended_action=RecommendedAction.CONFIRM_IDENTITY,
            fallback_routes=(FallbackRoute.LABEL_PHOTO, FallbackRoute.MANUAL_ENTRY),
            nutrition_confirmation_required=True,
            detail=(
                "catalog identity candidate found; identity confirmation does not confirm "
                "serving or nutrition facts"
            ),
        )

    @staticmethod
    def _candidate_requires_freshness_fallback(candidate: CatalogCandidate) -> bool:
        if INCOMPLETE_RECORD_FLAG in candidate.provider_quality_flags:
            return True
        return candidate.freshness_state is not (
            FreshnessState.PROVIDER_TIMESTAMP_CURRENT_UNKNOWN_SEMANTICS
        )

    @staticmethod
    def _fallback_outcome(
        *,
        request: LookupRequest,
        state: DiscoveryState,
        provider_results: tuple[ProviderLookupResult, ...],
        detail: str,
        candidates: tuple[DiscoveryCandidate, ...] = (),
    ) -> CatalogDiscoveryOutcome:
        return CatalogDiscoveryOutcome(
            request=request,
            discovery_state=state,
            provider_results=provider_results,
            candidates=candidates,
            recommended_action=RecommendedAction.PHOTO_OR_MANUAL,
            fallback_routes=(FallbackRoute.LABEL_PHOTO, FallbackRoute.MANUAL_ENTRY),
            nutrition_confirmation_required=True,
            detail=detail,
        )
