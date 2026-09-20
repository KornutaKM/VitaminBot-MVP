from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from vitaminbot.application.kir116 import Button, Screen
from vitaminbot.nutrition.card_content import (
    APPROVED_CARD_CONTENT,
    CardContentRegistry,
    ContentLifecycle,
    NutrientCardContent,
)
from vitaminbot.nutrition.normalization import ComputedAmount
from vitaminbot.nutrition.reference_values import (
    EU_EFSA_REFERENCE_DATASET,
    ComparisonRelation,
    ComparisonResult,
    ComparisonStatus,
    ExposureContext,
    Jurisdiction,
    LookupResult,
    LookupStatus,
    PopulationProfile,
    ReferenceDataset,
    ReferenceLifecycle,
    ReferenceQuery,
    ReferenceRecord,
    ReferenceStatus,
    ReferenceType,
    SourceLifecycle,
    ValueSemantics,
    compare_amount_to_reference,
    lookup_reference,
)

_MAX_TELEGRAM_TEXT = 4096
_REFERENCE_ORDER = {
    ReferenceType.NRV: 0,
    ReferenceType.AR: 1,
    ReferenceType.PRI: 2,
    ReferenceType.AI: 3,
    ReferenceType.RI: 4,
    ReferenceType.UL: 5,
    ReferenceType.SAFE_LEVEL: 6,
}
_SAFETY_TYPES = frozenset({ReferenceType.UL, ReferenceType.SAFE_LEVEL})


class CardStatus(StrEnum):
    INFORMATION = "INFORMATION"
    CANNOT_ASSESS = "CANNOT_ASSESS"
    CAUTION = "CAUTION"
    POTENTIAL_REFERENCE_LIMIT_CONCERN = "POTENTIAL_REFERENCE_LIMIT_CONCERN"


@dataclass(frozen=True, slots=True)
class CardContext:
    profile: PopulationProfile
    exposure: ExposureContext
    jurisdiction: str
    context_revision: str
    locale: str = "en"
    dietary_phytate_mg_per_day: Decimal | None = None
    minimal_cutaneous_synthesis: bool | None = None
    confirmed_amount: ComputedAmount | None = None
    medication_context_material: bool = False
    medication_rule_available: bool | None = None
    presentation_hint: str | None = None

    def __post_init__(self) -> None:
        if not self.jurisdiction.strip():
            raise ValueError("jurisdiction must not be blank")
        if not self.context_revision.strip():
            raise ValueError("context_revision must not be blank")
        if not self.locale.strip():
            raise ValueError("locale must not be blank")

    @classmethod
    def unknown(
        cls,
        context_revision: str,
        *,
        locale: str = "en",
        jurisdiction: str = "EU",
    ) -> CardContext:
        return cls(
            profile=PopulationProfile(),
            exposure=ExposureContext(),
            jurisdiction=jurisdiction,
            context_revision=context_revision,
            locale=locale,
        )


@dataclass(frozen=True, slots=True)
class ProvenanceSnapshot:
    source_key: str
    title: str
    source_url: str
    source_version: str
    authority: str
    jurisdiction_scope: str


@dataclass(frozen=True, slots=True)
class ClaimSnapshot:
    claim_id: str
    claim_type: str
    plain_text: str
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceSnapshot:
    subject_key: str
    reference_type: str
    lookup_status: str
    display_line: str
    dataset_version: str
    context_revision: str
    record_id: str | None
    record_status: str | None
    source_key: str | None
    source_title: str | None
    source_url: str | None
    source_version: str | None
    source_locator: str | None
    applicability_status: str | None
    reasons: tuple[str, ...]
    candidate_record_ids: tuple[str, ...]
    comparison_status: str | None = None
    comparison_relation: str | None = None


@dataclass(frozen=True, slots=True)
class CardBinding:
    content_id: str
    content_version: str
    substance_key: str
    display_name: str
    locale: str
    dataset_version: str
    context_revision: str
    claims: tuple[ClaimSnapshot, ...]
    claim_sources: tuple[ProvenanceSnapshot, ...]
    references: tuple[ReferenceSnapshot, ...]


@dataclass(frozen=True, slots=True)
class CardEnvelope:
    status: CardStatus
    classification: str
    known_facts: tuple[str, ...]
    unknown_or_ambiguous: tuple[str, ...]
    withheld_conclusion: str | None
    provenance: tuple[str, ...]
    resolution_path: str | None
    escalation_path: str | None
    non_droppable_warnings: tuple[str, ...]
    comparison_context: tuple[str, ...]
    contributors: tuple[str, ...]
    evidence_state: str


@dataclass(frozen=True, slots=True)
class CardRender:
    screen: Screen
    binding: CardBinding | None
    envelope: CardEnvelope


class NutrientCardRenderer:
    """KIR-146 renderer over immutable KIR-145 copy and versioned KIR-115 data."""

    def __init__(
        self,
        *,
        registry: CardContentRegistry = APPROVED_CARD_CONTENT,
        dataset: ReferenceDataset = EU_EFSA_REFERENCE_DATASET,
    ) -> None:
        self._registry = registry
        self._dataset = dataset

    @property
    def registry(self) -> CardContentRegistry:
        return self._registry

    @property
    def dataset(self) -> ReferenceDataset:
        return self._dataset

    def render_current(
        self,
        substance_key: str,
        context: CardContext,
        *,
        max_chars: int = _MAX_TELEGRAM_TEXT,
    ) -> CardRender:
        content = self._registry.current(substance_key, locale=context.locale)
        if content is None:
            return self._missing_content_render(substance_key, context.locale)

        if context.jurisdiction != Jurisdiction.EU.value:
            return self._unsupported_jurisdiction_render(content, context)

        references = self._resolve_references(content, context)
        claims = self._claim_snapshots(content)
        claim_sources = self._claim_source_snapshots(claims)
        binding = CardBinding(
            content_id=content.content_id,
            content_version=content.content_version,
            substance_key=content.substance_key,
            display_name=content.display_name,
            locale=content.locale,
            dataset_version=self._dataset.version,
            context_revision=context.context_revision,
            claims=claims,
            claim_sources=claim_sources,
            references=references,
        )
        envelope = self._build_envelope(content, references, context, claim_sources)
        screen = self._compact_screen(binding, references, envelope, max_chars=max_chars)
        return CardRender(screen=screen, binding=binding, envelope=envelope)

    def render_historical(
        self,
        binding: CardBinding,
        *,
        max_chars: int = _MAX_TELEGRAM_TEXT,
    ) -> CardRender:
        envelope = self._build_historical_envelope(binding)
        screen = self._compact_screen(
            binding,
            binding.references,
            envelope,
            max_chars=max_chars,
            historical=True,
        )
        return CardRender(screen=screen, binding=binding, envelope=envelope)

    def reference_values_screen(self, render: CardRender) -> Screen:
        if render.binding is None:
            return render.screen

        lines = [
            "Reference values",
            "",
            "Typed governed records only; these are not personalized dose recommendations.",
            "",
        ]
        for snapshot in render.binding.references:
            lines.append(f"• {snapshot.subject_key} / {snapshot.display_line}")
            if snapshot.record_id is not None:
                lines.append(
                    f"  record={snapshot.record_id}; dataset={snapshot.dataset_version}; "
                    f"context={snapshot.context_revision}"
                )
            elif snapshot.reasons:
                lines.append(f"  applicability={', '.join(snapshot.reasons)}")
        lines.extend(
            [
                "",
                "A missing or non-matching record is not replaced with an adult/default value.",
            ]
        )
        return Screen(
            text=self._bounded_text(lines),
            rows=(
                (Button("Why / Sources", f"k146s:{render.binding.substance_key}"),),
                (Button("Back", f"k146c:{render.binding.substance_key}"),),
            ),
        )

    def sources_screen(self, render: CardRender) -> Screen:
        if render.binding is None:
            return render.screen

        lines = [
            "Why / Sources",
            "",
            f"content={render.binding.content_id} @ {render.binding.content_version}",
            f"dataset={render.binding.dataset_version}",
            f"context_revision={render.binding.context_revision}",
            "",
            "Approved claims:",
        ]
        for claim in render.binding.claims:
            lines.append(
                f"• {claim.claim_id} [{claim.claim_type}] → {', '.join(claim.source_refs)}"
            )
        lines.extend(["", "Approved content sources:"])
        for source in render.binding.claim_sources:
            lines.extend(
                [
                    f"• {source.source_key} — {source.title}",
                    f"  {source.authority}; {source.jurisdiction_scope}",
                    f"  version: {source.source_version}",
                    f"  {source.source_url}",
                ]
            )

        matched = tuple(
            snapshot for snapshot in render.binding.references if snapshot.record_id is not None
        )
        if matched:
            lines.extend(["", "Exact reference/safety records:"])
            for snapshot in matched:
                lines.extend(
                    [
                        (
                            f"• {snapshot.record_id} — {snapshot.reference_type}; "
                            f"status={snapshot.record_status}"
                        ),
                        (
                            f"  source={snapshot.source_key}; version={snapshot.source_version}; "
                            f"applicability={snapshot.applicability_status}"
                        ),
                        f"  locator={snapshot.source_locator}",
                        f"  {snapshot.source_url}",
                    ]
                )
        unresolved = tuple(
            snapshot for snapshot in render.binding.references if snapshot.record_id is None
        )
        if unresolved:
            lines.extend(["", "Unresolved reference/applicability state:"])
            for snapshot in unresolved:
                lines.append(
                    f"• {snapshot.subject_key}/{snapshot.reference_type}: "
                    f"{snapshot.lookup_status}; reasons={','.join(snapshot.reasons) or 'none'}"
                )
                if snapshot.candidate_record_ids:
                    lines.append(f"  candidate_records={','.join(snapshot.candidate_record_ids)}")
            lines.append("No unresolved value was replaced by a default.")
        return Screen(
            text=self._bounded_text(lines),
            rows=(
                (Button("Reference values", f"k146r:{render.binding.substance_key}"),),
                (Button("Back", f"k146c:{render.binding.substance_key}"),),
            ),
        )

    def is_stale(self, binding: CardBinding, *, context_revision: str) -> bool:
        if binding.context_revision != context_revision:
            return True
        if binding.dataset_version != self._dataset.version:
            return True

        current = self._registry.current(binding.substance_key, locale=binding.locale)
        if (
            current is None
            or current.content_id != binding.content_id
            or current.content_version != binding.content_version
            or current.display_name != binding.display_name
        ):
            return True

        for claim_snapshot in binding.claims:
            claim = self._registry.claim(claim_snapshot.claim_id)
            if (
                claim is None
                or claim.claim_type.value != claim_snapshot.claim_type
                or claim.plain_text != claim_snapshot.plain_text
                or claim.source_refs != claim_snapshot.source_refs
                or claim.limitations != claim_snapshot.limitations
            ):
                return True

        for source_snapshot in binding.claim_sources:
            source = self._registry.source(source_snapshot.source_key)
            if (
                source is None
                or source.source_version != source_snapshot.source_version
                or source.source_url != source_snapshot.source_url
            ):
                return True

        for snapshot in binding.references:
            if snapshot.record_id is None:
                continue
            record = self._dataset.get_record(snapshot.record_id)
            if record is None or record.lifecycle is not ReferenceLifecycle.ACTIVE:
                return True
            reference_source = self._dataset.get_source(record.source_key)
            if (
                reference_source is None
                or reference_source.lifecycle is not SourceLifecycle.ACTIVE
                or reference_source.version_label != snapshot.source_version
                or reference_source.source_url != snapshot.source_url
            ):
                return True
        return False

    def _resolve_references(
        self,
        content: NutrientCardContent,
        context: CardContext,
    ) -> tuple[ReferenceSnapshot, ...]:
        pairs: set[tuple[str, ReferenceType]] = set()
        for record in self._dataset.records:
            if (
                record.lifecycle is ReferenceLifecycle.ACTIVE
                and record.jurisdiction is Jurisdiction.EU
                and record.substance_key in content.reference_subject_keys
            ):
                pairs.add((record.substance_key, record.reference_type))

        snapshots: list[ReferenceSnapshot] = []
        for subject_key, reference_type in sorted(
            pairs,
            key=lambda item: (
                content.reference_subject_keys.index(item[0]),
                _REFERENCE_ORDER[item[1]],
            ),
        ):
            query = ReferenceQuery(
                substance_key=subject_key,
                reference_type=reference_type,
                profile=context.profile,
                exposure=context.exposure,
                jurisdiction=Jurisdiction.EU,
                dietary_phytate_mg_per_day=context.dietary_phytate_mg_per_day,
                minimal_cutaneous_synthesis=context.minimal_cutaneous_synthesis,
                context_revision=context.context_revision,
            )
            lookup = lookup_reference(self._dataset, query)
            snapshots.append(self._snapshot(subject_key, reference_type, lookup, context))
        return tuple(snapshots)

    def _snapshot(
        self,
        subject_key: str,
        reference_type: ReferenceType,
        lookup: LookupResult,
        context: CardContext,
    ) -> ReferenceSnapshot:
        typed_lookup = lookup
        status = typed_lookup.status
        if status is not LookupStatus.MATCHED or typed_lookup.match is None:
            reasons = tuple(reason.value for reason in typed_lookup.reasons)
            reason_text = ", ".join(reasons) if reasons else status.value
            return ReferenceSnapshot(
                subject_key=subject_key,
                reference_type=reference_type.value,
                lookup_status=status.value,
                display_line=(
                    f"{reference_type.value}: cannot assess for this context "
                    f"({reason_text}); no value was guessed."
                ),
                dataset_version=typed_lookup.dataset_version,
                context_revision=context.context_revision,
                record_id=None,
                record_status=None,
                source_key=None,
                source_title=None,
                source_url=None,
                source_version=None,
                source_locator=None,
                applicability_status=None,
                reasons=reasons,
                candidate_record_ids=typed_lookup.candidate_record_ids,
            )

        match = typed_lookup.match
        record = match.record
        source = match.source
        if source.lifecycle is not SourceLifecycle.ACTIVE:
            return ReferenceSnapshot(
                subject_key=subject_key,
                reference_type=reference_type.value,
                lookup_status="source_not_active",
                display_line=(
                    f"{reference_type.value}: cannot assess because the matched source is "
                    "superseded; no stale value was displayed."
                ),
                dataset_version=typed_lookup.dataset_version,
                context_revision=context.context_revision,
                record_id=None,
                record_status=None,
                source_key=source.source_key,
                source_title=source.title,
                source_url=source.source_url,
                source_version=source.version_label,
                source_locator=record.source_locator,
                applicability_status=match.applicability.status.value,
                reasons=("source_superseded",),
                candidate_record_ids=typed_lookup.candidate_record_ids,
            )

        display_line = self._matched_line(record)
        comparison_status: str | None = None
        comparison_relation: str | None = None
        if context.confirmed_amount is not None:
            comparison = compare_amount_to_reference(
                context.confirmed_amount,
                typed_lookup,
                context_revision=context.context_revision,
            )
            comparison_status = comparison.status.value
            comparison_relation = (
                comparison.relation.value if comparison.relation is not None else None
            )
            display_line += self._comparison_suffix(reference_type, comparison)

        return ReferenceSnapshot(
            subject_key=subject_key,
            reference_type=reference_type.value,
            lookup_status=status.value,
            display_line=display_line,
            dataset_version=typed_lookup.dataset_version,
            context_revision=context.context_revision,
            record_id=record.record_id,
            record_status=record.status.value,
            source_key=source.source_key,
            source_title=source.title,
            source_url=source.source_url,
            source_version=source.version_label,
            source_locator=record.source_locator,
            applicability_status=match.applicability.status.value,
            reasons=tuple(reason.value for reason in match.applicability.reasons),
            candidate_record_ids=typed_lookup.candidate_record_ids,
            comparison_status=comparison_status,
            comparison_relation=comparison_relation,
        )

    @staticmethod
    def _matched_line(record: ReferenceRecord) -> str:
        token = ""
        if record.value is not None:
            assert record.unit is not None
            token = f"{_decimal(record.value)} {record.unit.value}/day"
        elif record.value_min is not None and record.value_max is not None:
            assert record.unit is not None
            token = (
                f"{_decimal(record.value_min)}–{_decimal(record.value_max)} {record.unit.value}/day"
            )

        if record.value_semantics is ValueSemantics.INCREMENT and token:
            token = f"increment {token}; base record={record.base_reference_id}"
        elif record.value_semantics is ValueSemantics.RANGE_INCREMENT and token:
            token = f"range increment {token}; base record={record.base_reference_id}"

        applicability = NutrientCardRenderer._record_applicability(record)
        if record.reference_type is ReferenceType.SAFE_LEVEL:
            return (
                f"SAFE_LEVEL: {token} — separate safety concept; not a UL, target, dose, "
                f"personal maximum, or personal safety guarantee.{applicability}"
            )
        if record.reference_type is ReferenceType.UL and token:
            return (
                f"UL: {token} — safety upper-intake reference, not a target or recommended "
                "dose. Below it is not personal safety clearance; above it is not by itself "
                f"a toxicity diagnosis.{applicability}"
            )
        if token:
            return (
                f"{record.reference_type.value}: {token} — typed reference value, not a "
                f"personalized dose recommendation.{applicability}"
            )

        status = record.status
        if status is ReferenceStatus.NO_UL_INSUFFICIENT_DATA:
            return (
                "UL: not established because available evidence was insufficient to derive "
                f"one. This does not mean unlimited safety.{applicability}"
            )
        if status is ReferenceStatus.NO_NUMERIC_UL_NO_DEFINED_ADVERSE_EFFECTS:
            return (
                "UL: no numeric UL established from the available evidence. This does not "
                f"mean unlimited safety.{applicability}"
            )
        if status is ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED:
            return (
                "UL: not established for this matched exposure. A separate SAFE_LEVEL record "
                f"may apply; it is not a UL or dose.{applicability}"
            )
        return (
            f"{record.reference_type.value}: not established in this governed source. This "
            f"is not an unlimited-safety statement.{applicability}"
        )

    @staticmethod
    def _record_applicability(record: ReferenceRecord) -> str:
        parts = [f"exposure={record.exposure_basis.value}"]
        if record.dietary_phytate_mg_per_day is not None:
            parts.append(f"phytate={_decimal(record.dietary_phytate_mg_per_day)} mg/day")
        if record.allowed_source_classes:
            parts.append(
                "source_class="
                + "|".join(source_class.value for source_class in record.allowed_source_classes)
            )
        if record.allowed_dha_forms:
            parts.append("dha_form=" + "|".join(form.value for form in record.allowed_dha_forms))
        if record.epa_dha_ratio_max_exclusive is not None:
            parts.append(f"EPA/DHA <{_decimal(record.epa_dha_ratio_max_exclusive)}")
        if record.excludes_background_dietary_dha:
            parts.append("background dietary DHA excluded")
        if record.excludes_medical_supervision:
            parts.append("medical-supervision exposure excluded")
        return " Applicability: " + "; ".join(parts) + "."

    @staticmethod
    def _comparison_suffix(
        reference_type: ReferenceType,
        comparison: ComparisonResult,
    ) -> str:
        if comparison.status is not ComparisonStatus.COMPARABLE or comparison.relation is None:
            return ""
        relation = comparison.relation
        if reference_type is ReferenceType.SAFE_LEVEL:
            if relation is ComparisonRelation.BELOW:
                return (
                    " Confirmed comparable amount is below this SAFE_LEVEL; that is not "
                    "personal safety clearance."
                )
            if relation is ComparisonRelation.EQUAL:
                return (
                    " Confirmed comparable amount equals this SAFE_LEVEL; it is not a target "
                    "or prescribed dose."
                )
            return (
                " Confirmed comparable amount is above this SAFE_LEVEL; this value alone does "
                "not establish unsafe/toxic status or characterize the risk above it."
            )

        if reference_type is ReferenceType.UL:
            if relation is ComparisonRelation.ABOVE:
                return (
                    " Confirmed comparable amount is above this UL comparison; this is a "
                    "potential reference-limit concern, not a toxicity diagnosis."
                )
            if relation is ComparisonRelation.EQUAL:
                return (
                    " Confirmed comparable amount equals this UL comparison; the UL remains "
                    "a safety reference, not a target."
                )
            return (
                " Confirmed comparable amount is below this UL comparison; that is not "
                "personal safety clearance."
            )
        return ""

    def _build_envelope(
        self,
        content: NutrientCardContent,
        references: tuple[ReferenceSnapshot, ...],
        context: CardContext,
        claim_sources: tuple[ProvenanceSnapshot, ...],
    ) -> CardEnvelope:
        unresolved = tuple(
            (
                f"{snapshot.subject_key}/{snapshot.reference_type}: "
                + (", ".join(snapshot.reasons) if snapshot.reasons else snapshot.lookup_status)
            )
            for snapshot in references
            if snapshot.lookup_status != LookupStatus.MATCHED.value
        )
        medication_unknown: tuple[str, ...] = ()
        if context.medication_context_material and context.medication_rule_available is not True:
            medication_unknown = (
                "medication interaction evidence is unavailable or not governed for this card",
            )

        comparison_concern = any(
            snapshot.reference_type == ReferenceType.UL.value
            and snapshot.comparison_relation == ComparisonRelation.ABOVE.value
            for snapshot in references
        )
        safe_level_above = any(
            snapshot.reference_type == ReferenceType.SAFE_LEVEL.value
            and snapshot.comparison_relation == ComparisonRelation.ABOVE.value
            for snapshot in references
        )

        all_unknown = unresolved + medication_unknown
        if all_unknown:
            status = CardStatus.CANNOT_ASSESS
        elif comparison_concern:
            status = CardStatus.POTENTIAL_REFERENCE_LIMIT_CONCERN
        elif safe_level_above:
            status = CardStatus.CAUTION
        else:
            status = CardStatus.INFORMATION

        warnings = [
            "Reference and safety values are comparison concepts, not personalized dose advice.",
            "No supported scheduling rule or interaction result is proof of "
            "compatibility or safety.",
        ]
        if any(
            snapshot.reference_type == ReferenceType.SAFE_LEVEL.value
            and snapshot.record_id is not None
            for snapshot in references
        ):
            warnings.append(
                "SAFE_LEVEL remains distinct from UL and is not a target, dose, personal "
                "maximum, or personal safety guarantee."
            )
        if any(
            snapshot.reference_type == ReferenceType.UL.value
            and snapshot.record_status
            in {
                ReferenceStatus.NO_UL_INSUFFICIENT_DATA.value,
                ReferenceStatus.NO_NUMERIC_UL_NO_DEFINED_ADVERSE_EFFECTS.value,
                ReferenceStatus.NO_UL_SAFE_LEVEL_IDENTIFIED.value,
            }
            for snapshot in references
        ):
            warnings.append("A UL not being established does not mean unlimited safety.")
        if medication_unknown:
            warnings.append(
                "Interaction conclusion withheld because approved evidence is unavailable; "
                "this is not a 'no interaction' result."
            )

        claim_ids = self._content_claim_ids(content)
        provenance = tuple(
            sorted(
                {source.source_key for source in claim_sources}
                | {
                    snapshot.source_key
                    for snapshot in references
                    if snapshot.source_key is not None
                }
            )
        )

        return CardEnvelope(
            status=status,
            classification=(
                "reference_comparison"
                if comparison_concern or safe_level_above
                else ("insufficient_data" if all_unknown else "information")
            ),
            known_facts=claim_ids
            + tuple(
                snapshot.record_id for snapshot in references if snapshot.record_id is not None
            ),
            unknown_or_ambiguous=all_unknown,
            withheld_conclusion=(
                "Reference/safety conclusion withheld where governed applicability is "
                "unresolved; VitaminBot did not assume an adult/default context."
                if all_unknown
                else None
            ),
            provenance=provenance,
            resolution_path=(
                "Confirm the missing profile/form/exposure inputs or approved evidence; "
                "VitaminBot will not assume a default."
                if all_unknown
                else None
            ),
            escalation_path=(
                "Professional review may be appropriate for medication-specific questions; "
                "VitaminBot does not infer no interaction."
                if medication_unknown
                else None
            ),
            non_droppable_warnings=tuple(warnings),
            comparison_context=tuple(
                f"{snapshot.subject_key}/{snapshot.reference_type}/{snapshot.lookup_status}"
                for snapshot in references
            ),
            contributors=(),
            evidence_state="missing_or_ambiguous" if all_unknown else "supported",
        )

    def _build_historical_envelope(self, binding: CardBinding) -> CardEnvelope:
        unresolved = tuple(
            f"{snapshot.subject_key}/{snapshot.reference_type}: historical {snapshot.lookup_status}"
            for snapshot in binding.references
            if snapshot.lookup_status != LookupStatus.MATCHED.value
        )
        return CardEnvelope(
            status=CardStatus.CANNOT_ASSESS if unresolved else CardStatus.INFORMATION,
            classification="historical_snapshot",
            known_facts=tuple(
                snapshot.record_id
                for snapshot in binding.references
                if snapshot.record_id is not None
            ),
            unknown_or_ambiguous=unresolved,
            withheld_conclusion=(
                "Historical card preserved its original unresolved applicability state."
                if unresolved
                else None
            ),
            provenance=tuple(
                sorted(
                    {source.source_key for source in binding.claim_sources}
                    | {
                        snapshot.source_key
                        for snapshot in binding.references
                        if snapshot.source_key is not None
                    }
                )
            ),
            resolution_path=None,
            escalation_path=None,
            non_droppable_warnings=(
                "Historical rendering reproduces the content/source versions captured at the time.",
            ),
            comparison_context=tuple(
                f"{snapshot.subject_key}/{snapshot.reference_type}/{snapshot.lookup_status}"
                for snapshot in binding.references
            ),
            contributors=(),
            evidence_state="historical_snapshot",
        )

    def _compact_screen(
        self,
        binding: CardBinding,
        references: tuple[ReferenceSnapshot, ...],
        envelope: CardEnvelope,
        *,
        max_chars: int,
        historical: bool = False,
    ) -> Screen:
        def claim_text(claim_type: str) -> str:
            return " ".join(
                claim.plain_text for claim in binding.claims if claim.claim_type == claim_type
            )

        identity = claim_text("identity")
        functions = claim_text("function")
        foods = claim_text("food_source")
        administration = claim_text("administration_info")
        limitations = claim_text("limitation")

        reference_lines = tuple(
            snapshot.display_line
            for snapshot in references
            if snapshot.reference_type not in {item.value for item in _SAFETY_TYPES}
        )
        safety_lines = tuple(
            snapshot.display_line
            for snapshot in references
            if snapshot.reference_type in {item.value for item in _SAFETY_TYPES}
        )

        status = (
            f"Status: {envelope.status.value}\n{envelope.withheld_conclusion or ''}".rstrip()
            if envelope.status is not CardStatus.INFORMATION
            else ""
        )
        historical_label = "Historical snapshot\n" if historical else ""
        sections: dict[str, str] = {
            "header": f"{binding.display_name}\n{historical_label}{status}".strip(),
            "identity": f"What it is: {identity}",
            "function": f"What it does: {functions}",
            "food": f"Food sources: {foods}",
            "reference": (
                "Reference context:\n" + "\n".join(f"• {line}" for line in reference_lines)
                if reference_lines
                else "Reference context: no governed reference record is available."
            ),
            "safety": (
                "Safety context:\n" + "\n".join(f"• {line}" for line in safety_lines)
                if safety_lines
                else "Safety context: no governed safety record is available."
            ),
            "administration": f"Administration: {administration}",
            "important": f"Important: {limitations}",
            "resolution": (
                f"Next step: {envelope.resolution_path}"
                if envelope.resolution_path is not None
                else ""
            ),
            "escalation": (
                f"Escalation: {envelope.escalation_path}"
                if envelope.escalation_path is not None
                else ""
            ),
            "warnings": "\n".join(
                f"Important: {warning}" for warning in envelope.non_droppable_warnings
            ),
        }
        text = self._fit_sections(sections, max_chars=max_chars)
        return Screen(
            text=text,
            rows=(
                (Button("Reference values", f"k146r:{binding.substance_key}"),),
                (Button("Why / Sources", f"k146s:{binding.substance_key}"),),
                (Button("Back", "k146list"),),
            ),
        )

    def _fit_sections(self, sections: dict[str, str], *, max_chars: int) -> str:
        if max_chars < 256:
            raise ValueError("max_chars is too small for non-droppable safety content")
        order = (
            "header",
            "identity",
            "function",
            "food",
            "reference",
            "safety",
            "administration",
            "important",
            "resolution",
            "escalation",
            "warnings",
        )
        kept = {key for key in order}
        text = "\n\n".join(sections[key] for key in order if key in kept and sections[key])
        for removable in ("food", "function", "identity"):
            if len(text) <= max_chars:
                break
            kept.remove(removable)
            text = "\n\n".join(sections[key] for key in order if key in kept and sections[key])
        if len(text) > max_chars:
            raise ValueError(
                "card cannot fit without dropping a non-droppable safety/applicability qualifier"
            )
        return text

    def _claim_snapshots(
        self,
        content: NutrientCardContent,
    ) -> tuple[ClaimSnapshot, ...]:
        snapshots: list[ClaimSnapshot] = []
        for claim_id in self._content_claim_ids(content):
            claim = self._registry.claim(claim_id)
            if claim is None:
                raise ValueError(f"content references unavailable claim {claim_id}")
            snapshots.append(
                ClaimSnapshot(
                    claim_id=claim.claim_id,
                    claim_type=claim.claim_type.value,
                    plain_text=claim.plain_text,
                    source_refs=claim.source_refs,
                    limitations=claim.limitations,
                )
            )
        return tuple(snapshots)

    def _claim_source_snapshots(
        self,
        claims: tuple[ClaimSnapshot, ...],
    ) -> tuple[ProvenanceSnapshot, ...]:
        source_keys = {source_key for claim in claims for source_key in claim.source_refs}
        snapshots: list[ProvenanceSnapshot] = []
        for key in sorted(source_keys):
            source = self._registry.source(key)
            if source is None:
                raise ValueError(f"claim source {key} is unavailable")
            snapshots.append(
                ProvenanceSnapshot(
                    source_key=source.source_key,
                    title=source.title,
                    source_url=source.source_url,
                    source_version=source.source_version,
                    authority=source.authority,
                    jurisdiction_scope=source.jurisdiction_scope,
                )
            )
        return tuple(snapshots)

    @staticmethod
    def _content_claim_ids(content: NutrientCardContent) -> tuple[str, ...]:
        return (
            (content.identity_claim_id,)
            + content.function_claim_ids
            + content.food_source_claim_ids
            + content.administration_claim_ids
            + content.limitation_claim_ids
        )

    def _missing_content_render(self, substance_key: str, locale: str) -> CardRender:
        envelope = CardEnvelope(
            status=CardStatus.CANNOT_ASSESS,
            classification="insufficient_governed_data",
            known_facts=(),
            unknown_or_ambiguous=(
                f"approved governed card content is unavailable for {substance_key}/{locale}",
            ),
            withheld_conclusion="Nutrient card withheld; no substitute content was synthesized.",
            provenance=(),
            resolution_path="Use an approved content version/locale.",
            escalation_path=None,
            non_droppable_warnings=(
                "VitaminBot did not translate, summarize, or invent missing scientific copy.",
            ),
            comparison_context=(),
            contributors=(),
            evidence_state="missing",
        )
        return CardRender(
            screen=Screen(
                text=(
                    "Nutrient information unavailable\n\n"
                    "Approved governed content is not available for this nutrient/locale. "
                    "VitaminBot did not synthesize a substitute card."
                ),
                rows=((Button("Back", "k146list"),),),
            ),
            binding=None,
            envelope=envelope,
        )

    def _unsupported_jurisdiction_render(
        self,
        content: NutrientCardContent,
        context: CardContext,
    ) -> CardRender:
        envelope = CardEnvelope(
            status=CardStatus.CANNOT_ASSESS,
            classification="insufficient_governed_data",
            known_facts=(),
            unknown_or_ambiguous=(
                f"jurisdiction {context.jurisdiction} is not supported by the EU-first card",
            ),
            withheld_conclusion="Reference/safety context withheld for unsupported jurisdiction.",
            provenance=(),
            resolution_path="Use a governed jurisdiction-specific dataset/content contract.",
            escalation_path=None,
            non_droppable_warnings=(
                "VitaminBot did not silently substitute EU values for another jurisdiction.",
            ),
            comparison_context=(),
            contributors=(),
            evidence_state="unsupported",
        )
        return CardRender(
            screen=Screen(
                text=(
                    f"{content.display_name}\n\n"
                    "Status: CANNOT_ASSESS\n"
                    f"Jurisdiction {context.jurisdiction} is not supported by this EU-first "
                    "card. No EU reference/safety value was substituted."
                ),
                rows=((Button("Back", "k146list"),),),
            ),
            binding=None,
            envelope=envelope,
        )

    @staticmethod
    def _bounded_text(lines: list[str]) -> str:
        text = "\n".join(lines)
        if len(text) > _MAX_TELEGRAM_TEXT:
            raise ValueError("source/reference view exceeds Telegram regular-message limit")
        return text


ContextProvider = Callable[[int, str], CardContext]


class KIR146Controller:
    """Bot-native KIR-146 nutrient card controller."""

    def __init__(
        self,
        renderer: NutrientCardRenderer,
        *,
        context_provider: ContextProvider | None = None,
    ) -> None:
        self._renderer = renderer
        self._context_provider = context_provider or self._default_context

    def list_cards(self) -> Screen:
        active = sorted(
            (
                content
                for content in self._renderer.registry.contents
                if content.status is ContentLifecycle.ACTIVE
                and content.locale == "en"
                and content.substance_key != "dha"
            ),
            key=lambda content: content.display_name,
        )
        rows = tuple(
            (Button(content.display_name, f"k146c:{content.substance_key}"),) for content in active
        )
        rows += ((Button("DHA (specific scope)", "k146c:dha"),),)
        return Screen(
            text=(
                "Nutrient information\n\n"
                "Choose an approved educational card. Reference/safety values are shown only "
                "when the governed applicability context resolves; no adult/default context "
                "is guessed."
            ),
            rows=rows,
        )

    def open(self, telegram_user_id: int, query: str) -> Screen:
        key = self._renderer.registry.resolve_substance(query)
        if key is None:
            return Screen(
                text=(
                    "Nutrient information unavailable\n\n"
                    "No approved governed card matches that nutrient. VitaminBot did not "
                    "synthesize a substitute."
                ),
                rows=((Button("Available cards", "k146list"),),),
            )
        return self._current_render(telegram_user_id, key).screen

    def callback(self, telegram_user_id: int, data: str) -> Screen:
        if data == "k146list":
            return self.list_cards()
        parts = data.split(":", 1)
        if len(parts) != 2:
            return Screen(
                text="This nutrient-card action is not valid.",
                rows=((Button("Available cards", "k146list"),),),
            )
        action, key = parts
        if self._renderer.registry.current(key, locale="en") is None:
            return Screen(
                text=(
                    "This nutrient-card action is stale or unsupported. "
                    "No substitute scientific content was shown."
                ),
                rows=((Button("Available cards", "k146list"),),),
            )
        render = self._current_render(telegram_user_id, key)
        if action == "k146c":
            return render.screen
        if action == "k146r":
            return self._renderer.reference_values_screen(render)
        if action == "k146s":
            return self._renderer.sources_screen(render)
        return Screen(
            text="This nutrient-card action is not valid.",
            rows=((Button("Available cards", "k146list"),),),
        )

    def _current_render(self, telegram_user_id: int, key: str) -> CardRender:
        context = self._context_provider(telegram_user_id, key)
        return self._renderer.render_current(key, context)

    @staticmethod
    def _default_context(telegram_user_id: int, _key: str) -> CardContext:
        return CardContext.unknown(
            context_revision=f"telegram-user:{telegram_user_id}:scientific-context-unresolved"
        )


def _decimal(value: Decimal) -> str:
    return format(value, "f")
