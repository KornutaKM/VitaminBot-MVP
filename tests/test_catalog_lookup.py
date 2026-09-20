from datetime import UTC, datetime

import pytest

from vitaminbot.recognition.catalog import (
    CATALOG_LABEL_CONFLICT,
    CatalogCandidate,
    CatalogContractError,
    CatalogDiscoveryService,
    ConfirmedLabelFact,
    DiscoveryState,
    FallbackRoute,
    FreshnessState,
    GS1Qualifier,
    IdentifierType,
    ImageCandidate,
    LookupRequest,
    ProviderClass,
    ProviderLookupResult,
    ProviderRateLimitedError,
    ProviderResultState,
    ProviderUnavailableError,
    QueryMode,
    RecommendedAction,
    ScanKind,
    SourcedCandidateField,
    VerificationState,
    gtin_check_digit_valid,
    parse_lookup_request,
)

NOW = datetime(2026, 9, 20, 11, 45, tzinfo=UTC)
GTIN = "4006381333931"
DIGITAL_LINK_GTIN = "09506000134352"


class MockProvider:
    provider_key = "mock"
    provider_class = ProviderClass.OPEN_COMMUNITY_CATALOG
    adapter_version = "mock-adapter-v1"
    license_class = "test-license"
    rights_note = "test-only synthetic catalog data"

    def __init__(
        self,
        *,
        result: ProviderLookupResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[LookupRequest] = []

    def lookup(self, request: LookupRequest) -> ProviderLookupResult:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class SecondProvider(MockProvider):
    provider_key = "second"
    provider_class = ProviderClass.PRODUCT_MASTER_DATA
    adapter_version = "second-adapter-v2"
    license_class = "second-license"
    rights_note = "second synthetic provider"


def _request(
    *,
    raw_scan: str = GTIN,
    scan_kind: ScanKind = ScanKind.LINEAR_BARCODE,
    request_id: str = "request-1",
) -> LookupRequest:
    return parse_lookup_request(
        request_id=request_id,
        raw_scan=raw_scan,
        scan_kind=scan_kind,
        requested_at=NOW,
        market_context="FI",
    )


def _field(
    *,
    provider_key: str = "mock",
    field_name: str = "product_name",
    raw_value: str = "Example Magnesium",
    normalized_candidate: str | None = "Example Magnesium",
    provider_record_id: str = "record-1",
    provider_updated_at: datetime | None = NOW,
) -> SourcedCandidateField:
    return SourcedCandidateField(
        field_name=field_name,
        raw_value=raw_value,
        normalized_candidate=normalized_candidate,
        provider_key=provider_key,
        provider_record_id=provider_record_id,
        source_path=f"product.{field_name}",
        retrieved_at=NOW,
        provider_updated_at=provider_updated_at,
        source_url="https://catalog.example/items/record-1",
        license_class="test-license",
        rights_note="synthetic fixture",
    )


def _candidate(
    *,
    provider_key: str = "mock",
    identifier: str = GTIN,
    name: str = "Example Magnesium",
    freshness: FreshnessState = (FreshnessState.PROVIDER_TIMESTAMP_CURRENT_UNKNOWN_SEMANTICS),
    flags: tuple[str, ...] = (),
    record_id: str = "record-1",
) -> CatalogCandidate:
    return CatalogCandidate(
        provider_key=provider_key,
        provider_record_id=record_id,
        identifiers=(identifier,),
        freshness_state=freshness,
        fields=(
            _field(
                provider_key=provider_key,
                raw_value=name,
                normalized_candidate=name,
                provider_record_id=record_id,
            ),
            _field(
                provider_key=provider_key,
                field_name="nutrition_text_candidate",
                raw_value="Magnesium citrate 500 mg",
                normalized_candidate=None,
                provider_record_id=record_id,
            ),
        ),
        images=(
            ImageCandidate(
                reference="https://images.example/record-1.jpg",
                provider_key=provider_key,
                retrieved_at=NOW,
                related_identifier=identifier,
                provider_record_id=record_id,
                image_role="front",
                rights_note="display permission unknown",
                cache_display_permission="unknown",
                package_match_state="unknown",
            ),
        ),
        provider_quality_flags=flags,
    )


def _result(
    *,
    provider_key: str = "mock",
    provider_class: ProviderClass = ProviderClass.OPEN_COMMUNITY_CATALOG,
    adapter_version: str = "mock-adapter-v1",
    state: ProviderResultState = ProviderResultState.SINGLE_EXACT_MATCH,
    candidates: tuple[CatalogCandidate, ...] | None = None,
    identifier: str = GTIN,
    query_mode: QueryMode = QueryMode.EXACT_IDENTIFIER,
) -> ProviderLookupResult:
    if candidates is None:
        candidates = (_candidate(provider_key=provider_key, identifier=identifier),)
    return ProviderLookupResult(
        provider_key=provider_key,
        provider_class=provider_class,
        adapter_version=adapter_version,
        query_mode=query_mode,
        queried_identifier=identifier,
        retrieved_at=NOW,
        result_state=state,
        candidates=candidates,
        raw_response_reference_or_hash="sha256:synthetic-response",
        license_class="test-license",
        rights_note="synthetic fixture",
    )


def test_gtin_parser_validates_supported_lengths_and_preserves_raw_scan() -> None:
    examples = (
        ("96385074", IdentifierType.GTIN_8),
        ("012345678905", IdentifierType.GTIN_12),
        ("4006381333931", IdentifierType.GTIN_13),
        ("12345678901231", IdentifierType.GTIN_14),
    )

    for value, identifier_type in examples:
        request = _request(raw_scan=value)
        assert request.raw_scan == value
        assert request.normalized_identifier == value
        assert request.identifier_type is identifier_type
        assert request.check_digit_valid is True
        assert request.lookup_permitted is True
        assert gtin_check_digit_valid(value) is True


def test_invalid_gtin_fails_closed_without_calling_provider() -> None:
    request = _request(raw_scan="4006381333932")
    provider = MockProvider(result=_result(identifier="4006381333932"))
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(request)

    assert request.check_digit_valid is False
    assert request.lookup_permitted is False
    assert provider.calls == []
    assert outcome.discovery_state is DiscoveryState.IDENTIFIER_UNRESOLVED
    assert outcome.recommended_action is RecommendedAction.PHOTO_OR_MANUAL
    assert outcome.fallback_routes == (
        FallbackRoute.LABEL_PHOTO,
        FallbackRoute.MANUAL_ENTRY,
    )


def test_gs1_digital_link_preserves_uri_primary_key_and_qualifiers() -> None:
    raw = "https://id.gs1.org/01/09506000134352/10/LOT-7?21=SERIAL-9&17=271231"
    request = _request(raw_scan=raw, scan_kind=ScanKind.QR)

    assert request.identifier_type is IdentifierType.GS1_DIGITAL_LINK
    assert request.normalized_identifier == DIGITAL_LINK_GTIN
    assert request.check_digit_valid is True
    assert request.digital_link_uri == raw
    assert request.gs1_primary_key == f"01:{DIGITAL_LINK_GTIN}"
    assert request.gs1_qualifiers == (
        GS1Qualifier(ai="10", value="LOT-7"),
        GS1Qualifier(ai="21", value="SERIAL-9"),
        GS1Qualifier(ai="17", value="271231"),
    )


def test_exact_match_remains_external_unverified_and_requires_identity_confirmation() -> None:
    request = _request()
    provider = MockProvider(result=_result())
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(request)

    assert outcome.discovery_state is DiscoveryState.CATALOG_CANDIDATE_FOUND
    assert outcome.recommended_action is RecommendedAction.CONFIRM_IDENTITY
    assert outcome.nutrition_confirmation_required is True
    assert outcome.fallback_routes == (
        FallbackRoute.LABEL_PHOTO,
        FallbackRoute.MANUAL_ENTRY,
    )
    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].candidate_id.startswith("catalog-candidate-v1:")
    assert all(
        field.verification_state is VerificationState.EXTERNAL_UNVERIFIED
        for field in outcome.candidates[0].candidate.fields
    )
    nutrition = next(
        field
        for field in outcome.candidates[0].candidate.fields
        if field.field_name == "nutrition_text_candidate"
    )
    assert nutrition.raw_value == "Magnesium citrate 500 mg"
    assert nutrition.normalized_candidate is None


def test_multiple_exact_candidates_are_never_auto_ranked() -> None:
    request = _request()
    candidates = (
        _candidate(name="Package A", record_id="record-a"),
        _candidate(name="Package B", record_id="record-b"),
    )
    provider = MockProvider(
        result=_result(
            state=ProviderResultState.MULTIPLE_MATCHES,
            candidates=candidates,
        )
    )
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(request)

    assert outcome.discovery_state is DiscoveryState.CATALOG_AMBIGUOUS
    assert outcome.recommended_action is RecommendedAction.PHOTO_OR_MANUAL
    assert [candidate.candidate.fields[0].raw_value for candidate in outcome.candidates] == [
        "Package A",
        "Package B",
    ]


@pytest.mark.parametrize(
    ("freshness", "flags"),
    [
        (FreshnessState.PROVIDER_TIMESTAMP_MISSING, ()),
        (FreshnessState.POSSIBLE_OLD_PACKAGE, ()),
        (
            FreshnessState.PROVIDER_TIMESTAMP_CURRENT_UNKNOWN_SEMANTICS,
            ("incomplete_record",),
        ),
    ],
)
def test_stale_or_incomplete_candidate_routes_to_photo_or_manual(
    freshness: FreshnessState,
    flags: tuple[str, ...],
) -> None:
    request = _request()
    provider = MockProvider(
        result=_result(candidates=(_candidate(freshness=freshness, flags=flags),))
    )
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(request)

    assert outcome.discovery_state is DiscoveryState.CATALOG_INCOMPLETE_OR_STALE
    assert outcome.recommended_action is RecommendedAction.PHOTO_OR_MANUAL


def test_no_universal_age_threshold_is_invented_for_provider_timestamp() -> None:
    old_timestamp = datetime(2020, 1, 1, tzinfo=UTC)
    candidate = CatalogCandidate(
        provider_key="mock",
        provider_record_id="record-old-date",
        identifiers=(GTIN,),
        freshness_state=FreshnessState.PROVIDER_TIMESTAMP_CURRENT_UNKNOWN_SEMANTICS,
        fields=(
            _field(
                provider_updated_at=old_timestamp,
                provider_record_id="record-old-date",
            ),
        ),
    )
    provider = MockProvider(result=_result(candidates=(candidate,)))
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(_request())

    assert outcome.discovery_state is DiscoveryState.CATALOG_CANDIDATE_FOUND
    assert outcome.recommended_action is RecommendedAction.CONFIRM_IDENTITY


def test_confirmed_current_label_wins_conflict_without_overwriting_catalog_candidate() -> None:
    request = _request()
    candidate = _candidate(name="Old Package Name")
    provider = MockProvider(result=_result(candidates=(candidate,)))
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)
    label_fact = ConfirmedLabelFact(
        field_name="product_name",
        raw_value="Current Package Name",
        source_reference="label-confirmation:revision-3",
    )

    outcome = service.discover(
        request,
        confirmed_label_facts=(label_fact,),
    )

    assert outcome.discovery_state is DiscoveryState.CATALOG_LABEL_CONFLICT
    assert outcome.recommended_action is RecommendedAction.PHOTO_OR_MANUAL
    discovered = outcome.candidates[0].candidate
    product_name = next(field for field in discovered.fields if field.field_name == "product_name")
    assert product_name.raw_value == "Old Package Name"
    assert CATALOG_LABEL_CONFLICT in product_name.conflicts
    assert CATALOG_LABEL_CONFLICT in discovered.candidate_conflicts
    assert discovered.freshness_state is FreshnessState.CATALOG_LABEL_CONFLICT
    assert label_fact.raw_value == "Current Package Name"


def test_no_match_is_normal_supported_fallback() -> None:
    result = ProviderLookupResult(
        provider_key="mock",
        provider_class=ProviderClass.OPEN_COMMUNITY_CATALOG,
        adapter_version="mock-adapter-v1",
        query_mode=QueryMode.EXACT_IDENTIFIER,
        queried_identifier=GTIN,
        retrieved_at=NOW,
        result_state=ProviderResultState.NO_MATCH,
        raw_response_reference_or_hash="sha256:no-match",
        license_class="test-license",
        rights_note="synthetic fixture",
    )
    provider = MockProvider(result=result)
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(_request())

    assert outcome.discovery_state is DiscoveryState.NO_CATALOG_MATCH
    assert outcome.provider_results[0].result_state is ProviderResultState.NO_MATCH
    assert outcome.candidates == ()
    assert outcome.recommended_action is RecommendedAction.PHOTO_OR_MANUAL


def test_rate_limited_provider_can_fall_through_to_next_configured_provider() -> None:
    first = MockProvider(error=ProviderRateLimitedError("429 retry later"))
    second_candidate = _candidate(
        provider_key="second",
        name="Second Provider Candidate",
    )
    second_result = _result(
        provider_key="second",
        provider_class=ProviderClass.PRODUCT_MASTER_DATA,
        adapter_version="second-adapter-v2",
        candidates=(second_candidate,),
    )
    second = SecondProvider(result=second_result)
    service = CatalogDiscoveryService(providers=(first, second), clock=lambda: NOW)

    outcome = service.discover(_request())

    assert outcome.discovery_state is DiscoveryState.CATALOG_CANDIDATE_FOUND
    assert [result.result_state for result in outcome.provider_results] == [
        ProviderResultState.RATE_LIMITED,
        ProviderResultState.SINGLE_EXACT_MATCH,
    ]
    assert outcome.candidates[0].candidate.provider_key == "second"
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_provider_outage_without_candidate_degrades_to_photo_or_manual() -> None:
    provider = MockProvider(error=ProviderUnavailableError("provider timeout"))
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(_request())

    assert outcome.discovery_state is DiscoveryState.LOOKUP_DEGRADED
    assert outcome.provider_results[0].result_state is (ProviderResultState.PROVIDER_UNAVAILABLE)
    assert outcome.provider_results[0].provider_error == "provider timeout"
    assert outcome.recommended_action is RecommendedAction.PHOTO_OR_MANUAL


def test_provider_contract_mismatch_is_treated_as_malformed_not_truth() -> None:
    mismatched = _result(provider_key="wrong-provider")
    provider = MockProvider(result=mismatched)
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(_request())

    assert outcome.discovery_state is DiscoveryState.LOOKUP_DEGRADED
    assert outcome.provider_results[0].result_state is ProviderResultState.MALFORMED_RESPONSE
    assert outcome.candidates == ()


def test_field_level_provenance_and_image_rights_are_preserved() -> None:
    provider = MockProvider(result=_result())
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(_request())

    result = outcome.provider_results[0]
    candidate = outcome.candidates[0].candidate
    product_name = next(field for field in candidate.fields if field.field_name == "product_name")
    image = candidate.images[0]

    assert result.raw_response_reference_or_hash == "sha256:synthetic-response"
    assert result.adapter_version == "mock-adapter-v1"
    assert result.license_class == "test-license"
    assert product_name.raw_value == "Example Magnesium"
    assert product_name.normalized_candidate == "Example Magnesium"
    assert product_name.provider_key == "mock"
    assert product_name.provider_record_id == "record-1"
    assert product_name.source_path == "product.product_name"
    assert product_name.retrieved_at == NOW
    assert product_name.provider_updated_at == NOW
    assert product_name.source_url == "https://catalog.example/items/record-1"
    assert product_name.license_class == "test-license"
    assert product_name.rights_note == "synthetic fixture"
    assert product_name.verification_state is VerificationState.EXTERNAL_UNVERIFIED
    assert image.rights_note == "display permission unknown"
    assert image.cache_display_permission == "unknown"
    assert image.package_match_state == "unknown"


def test_single_exact_match_must_preserve_queried_identifier() -> None:
    provider = MockProvider(result=_result(candidates=(_candidate(identifier="012345678905"),)))
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(_request())

    assert outcome.discovery_state is DiscoveryState.LOOKUP_DEGRADED
    assert outcome.provider_results[0].result_state is ProviderResultState.MALFORMED_RESPONSE


def test_duplicate_candidate_field_names_are_rejected_instead_of_silently_selected() -> None:
    duplicate = _field(field_name="product_name", raw_value="Another value")

    with pytest.raises(CatalogContractError, match="duplicate field names"):
        CatalogCandidate(
            provider_key="mock",
            provider_record_id="record-1",
            identifiers=(GTIN,),
            freshness_state=FreshnessState.FRESHNESS_UNRESOLVED,
            fields=(_field(), duplicate),
        )


def test_digital_link_provider_result_uses_resolution_query_mode() -> None:
    raw = "https://id.gs1.org/01/09506000134352/10/LOT-7"
    request = _request(raw_scan=raw, scan_kind=ScanKind.QR)
    candidate = _candidate(identifier=DIGITAL_LINK_GTIN)
    result = _result(
        identifier=DIGITAL_LINK_GTIN,
        query_mode=QueryMode.DIGITAL_LINK_RESOLUTION,
        candidates=(candidate,),
    )
    provider = MockProvider(result=result)
    service = CatalogDiscoveryService(providers=(provider,), clock=lambda: NOW)

    outcome = service.discover(request)

    assert outcome.discovery_state is DiscoveryState.CATALOG_CANDIDATE_FOUND
    assert outcome.provider_results[0].query_mode is QueryMode.DIGITAL_LINK_RESOLUTION
