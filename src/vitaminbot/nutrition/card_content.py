from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

_STATIC_DAILY_MEASUREMENT = re.compile(
    r"(?i)\b\d+(?:[.,]\d+)?\s*(?:mg|g|ug|µg|mcg|iu)"
    r"(?:\s*/\s*day|\s+per\s+day)\b"
)


class ClaimType(StrEnum):
    IDENTITY = "identity"
    FUNCTION = "function"
    FOOD_SOURCE = "food_source"
    ADMINISTRATION_INFO = "administration_info"
    LIMITATION = "limitation"


class ContentLifecycle(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class ApprovedSource:
    source_key: str
    authority: str
    jurisdiction_scope: str
    title: str
    source_url: str
    source_version: str

    def __post_init__(self) -> None:
        for value in (
            self.source_key,
            self.authority,
            self.jurisdiction_scope,
            self.title,
            self.source_url,
            self.source_version,
        ):
            if not value.strip():
                raise ValueError("approved source fields must not be blank")


@dataclass(frozen=True, slots=True)
class ApprovedClaim:
    claim_id: str
    claim_type: ClaimType
    plain_text: str
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.plain_text.strip():
            raise ValueError("approved claim identity/text must not be blank")
        if not self.source_refs:
            raise ValueError("approved scientific claim requires provenance")
        if _STATIC_DAILY_MEASUREMENT.search(self.plain_text):
            raise ValueError(
                "static scientific claim must not own a daily reference/safety measurement; "
                "resolve reference/safety numbers from KIR-115"
            )


@dataclass(frozen=True, slots=True)
class NutrientCardContent:
    content_id: str
    content_version: str
    locale: str
    substance_key: str
    display_name: str
    identity_claim_id: str
    function_claim_ids: tuple[str, ...]
    food_source_claim_ids: tuple[str, ...]
    administration_claim_ids: tuple[str, ...]
    limitation_claim_ids: tuple[str, ...]
    reference_subject_keys: tuple[str, ...]
    status: ContentLifecycle = ContentLifecycle.ACTIVE
    supersedes_content_id: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.content_id,
            self.content_version,
            self.locale,
            self.substance_key,
            self.display_name,
        ):
            if not value.strip():
                raise ValueError("card content identity fields must not be blank")
        if not self.reference_subject_keys:
            raise ValueError("card content requires at least one governed reference subject")


@dataclass(frozen=True, slots=True)
class CardContentRegistry:
    sources: tuple[ApprovedSource, ...]
    claims: tuple[ApprovedClaim, ...]
    contents: tuple[NutrientCardContent, ...]
    aliases: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        source_keys = [source.source_key for source in self.sources]
        claim_ids = [claim.claim_id for claim in self.claims]
        content_ids = [content.content_id for content in self.contents]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("approved source keys must be unique")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("approved claim IDs must be unique")
        if len(content_ids) != len(set(content_ids)):
            raise ValueError("content IDs must be unique")

        source_set = set(source_keys)
        claim_set = set(claim_ids)
        for claim in self.claims:
            missing_sources = set(claim.source_refs) - source_set
            if missing_sources:
                raise ValueError(f"claim {claim.claim_id} has unknown sources: {missing_sources}")
        active_keys: set[tuple[str, str]] = set()
        for content in self.contents:
            if content.status is ContentLifecycle.ACTIVE:
                key = (content.substance_key, content.locale)
                if key in active_keys:
                    raise ValueError(
                        "only one active card content version is allowed per substance/locale"
                    )
                active_keys.add(key)

        for content in self.contents:
            used = (
                (content.identity_claim_id,)
                + content.function_claim_ids
                + content.food_source_claim_ids
                + content.administration_claim_ids
                + content.limitation_claim_ids
            )
            missing_claims = set(used) - claim_set
            if missing_claims:
                raise ValueError(
                    f"content {content.content_id} has unknown claims: {missing_claims}"
                )

    def source(self, source_key: str) -> ApprovedSource | None:
        return next((source for source in self.sources if source.source_key == source_key), None)

    def claim(self, claim_id: str) -> ApprovedClaim | None:
        return next((claim for claim in self.claims if claim.claim_id == claim_id), None)

    def content_by_id(self, content_id: str) -> NutrientCardContent | None:
        return next(
            (content for content in self.contents if content.content_id == content_id),
            None,
        )

    def current(self, substance_key: str, *, locale: str = "en") -> NutrientCardContent | None:
        return next(
            (
                content
                for content in self.contents
                if content.substance_key == substance_key
                and content.locale == locale
                and content.status is ContentLifecycle.ACTIVE
            ),
            None,
        )

    def resolve_substance(self, value: str) -> str | None:
        normalized = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
        aliases = dict(self.aliases)
        return aliases.get(normalized)


def _source(
    key: str,
    title: str,
    url: str,
    version: str,
    *,
    authority: str = "NIH Office of Dietary Supplements",
    jurisdiction: str = "authoritative public-health context; not EU reference authority",
) -> ApprovedSource:
    return ApprovedSource(
        source_key=key,
        authority=authority,
        jurisdiction_scope=jurisdiction,
        title=title,
        source_url=url,
        source_version=version,
    )


SOURCES: Final[tuple[ApprovedSource, ...]] = (
    _source(
        "ODS-VD",
        "Vitamin D — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/VITAMIND/HealthProfessional/",
        "updated 2025-06-27; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-VC",
        "Vitamin C — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/VitaminC-HealthProfessional/",
        "updated 2025-07-31; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-MG",
        "Magnesium — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/magnesium-healthProfessional/",
        "updated 2026-01-06; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-ZN",
        "Zinc — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/",
        "updated 2026-01-06; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-SE",
        "Selenium — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/Selenium-HealthProfessional/",
        "updated 2025-09-04; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-B6",
        "Vitamin B6 — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/VitaminB6-HealthProfessional/",
        "updated 2023-06-16; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-B12",
        "Vitamin B12 — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/VitaminB12-HealthProfessional/",
        "updated 2025-07-02; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-FOL",
        "Folate — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/Folate-HealthProfessional/",
        "updated 2022-11-30; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-FE",
        "Iron — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
        "updated 2025-09-04; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-CA",
        "Calcium — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/",
        "updated 2026-06-22; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "ODS-O3",
        "Omega-3 Fatty Acids — Health Professional Fact Sheet",
        "https://ods.od.nih.gov/factsheets/Omega3FattyAcids-HealthProfessional/",
        "updated 2025-08-22; KIR-145 retrieved 2026-09-20",
    ),
    _source(
        "KIR-144",
        "Independent validation of supplement scheduling rule candidates",
        "https://linear.app/kirillkorn/issue/KIR-144",
        "accepted 2026-09-20",
        authority="VitaminBot independent safety validation",
        jurisdiction="governed VitaminBot scheduling wording",
    ),
    _source(
        "KIR-145",
        "Nutrient information-card content and source contract",
        "https://linear.app/kirillkorn/document/"
        "eng2kir-145-nutrient-information-card-content-and-source-contract-ca8bb628228c",
        "accepted 2026-09-20",
        authority="VitaminBot Nutrition Engine / Scientific Data",
        jurisdiction="accepted card content contract",
    ),
    _source(
        "KIR-153",
        "EFSA 2026 DHA SAFE_LEVEL independent validation",
        "https://linear.app/kirillkorn/document/"
        "kir-153-eng4-efsa-2026-dha-safe-level-validation-ee8f0179285c",
        "accepted 2026-09-20",
        authority="VitaminBot independent safety validation",
        jurisdiction="DHA/omega-3 rendering and applicability",
    ),
)


def _claim(
    claim_id: str,
    claim_type: ClaimType,
    text: str,
    *sources: str,
    limitations: tuple[str, ...] = (),
) -> ApprovedClaim:
    return ApprovedClaim(
        claim_id=claim_id,
        claim_type=claim_type,
        plain_text=text,
        source_refs=tuple(sources),
        limitations=limitations,
    )


CLAIMS: Final[tuple[ApprovedClaim, ...]] = (
    _claim(
        "vd.identity.v1",
        ClaimType.IDENTITY,
        "A fat-soluble vitamin; the body can also produce vitamin D in skin after UV exposure.",
        "ODS-VD",
    ),
    _claim(
        "vd.function.v1",
        ClaimType.FUNCTION,
        "Supports intestinal calcium absorption and normal calcium/phosphate balance needed "
        "for bone mineralization. It also has roles in neuromuscular and immune function.",
        "ODS-VD",
    ),
    _claim(
        "vd.food.v1",
        ClaimType.FOOD_SOURCE,
        "Fatty fish and fish-liver oils are among the richest natural sources; egg yolk and "
        "some cheeses contain smaller amounts; UV-exposed mushrooms provide vitamin D2; "
        "many foods are fortified.",
        "ODS-VD",
    ),
    _claim(
        "vd.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 permits a soft preference for taking known oral vitamin D with a meal/snack "
        "containing some dietary fat because fat enhances absorption; this is not a "
        "hard requirement and creates no Morning/Evening rule.",
        "KIR-144",
        "ODS-VD",
    ),
    _claim(
        "vd.limit.v1",
        ClaimType.LIMITATION,
        "Vitamin D form/equivalence semantics are substance-specific; IU must never be "
        "handled by a generic converter. Medication or special-population questions require "
        "separately governed rules.",
        "KIR-145",
    ),
    _claim(
        "vc.identity.v1",
        ClaimType.IDENTITY,
        "Vitamin C (L-ascorbic acid) is an essential water-soluble vitamin.",
        "ODS-VC",
    ),
    _claim(
        "vc.function.v1",
        ClaimType.FUNCTION,
        "Required for collagen, L-carnitine and certain neurotransmitter biosynthesis; "
        "also functions as a physiological antioxidant.",
        "ODS-VC",
    ),
    _claim(
        "vc.food.v1",
        ClaimType.FOOD_SOURCE,
        "Fruits and vegetables are the main sources, including citrus fruits, peppers, "
        "kiwifruit, broccoli, strawberries and Brussels sprouts. Cooking and long storage "
        "can reduce vitamin C content.",
        "ODS-VC",
    ),
    _claim(
        "vc.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 does not authorize a generic meal or time-of-day rule. Vitamin C can "
        "enhance non-heme iron absorption, but forced vitamin-C-plus-iron supplement "
        "grouping is not authorized for MVP.",
        "KIR-144",
    ),
    _claim(
        "vc.limit.v1",
        ClaimType.LIMITATION,
        "Do not turn common-cold or other condition evidence into a generic treatment claim.",
        "KIR-145",
    ),
    _claim(
        "mg.identity.v1",
        ClaimType.IDENTITY,
        "An essential mineral and cofactor in hundreds of enzyme systems.",
        "ODS-MG",
    ),
    _claim(
        "mg.function.v1",
        ClaimType.FUNCTION,
        "Participates in energy production, protein synthesis, muscle and nerve function, "
        "DNA/RNA synthesis and bone structure.",
        "ODS-MG",
    ),
    _claim(
        "mg.food.v1",
        ClaimType.FOOD_SOURCE,
        "Green leafy vegetables, legumes, nuts, seeds and whole grains are common sources; "
        "water can also contribute depending on source.",
        "ODS-MG",
    ),
    _claim(
        "mg.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        'No validated generic "magnesium at night" rule exists. KIR-144 explicitly rejects '
        "automatic evening placement; clock time is user preference unless another governed "
        "rule applies.",
        "KIR-144",
    ),
    _claim(
        "mg.limit.v1",
        ClaimType.LIMITATION,
        'Compound mass is not elemental magnesium. A label such as "magnesium citrate 500 mg" '
        "must not be assumed to mean 500 mg elemental magnesium.",
        "KIR-145",
    ),
    _claim(
        "zn.identity.v1",
        ClaimType.IDENTITY,
        "An essential mineral used by many enzymes and cellular processes.",
        "ODS-ZN",
    ),
    _claim(
        "zn.function.v1",
        ClaimType.FUNCTION,
        "Supports protein and DNA synthesis, immune function, cell division, wound healing, "
        "growth and development, and taste.",
        "ODS-ZN",
    ),
    _claim(
        "zn.food.v1",
        ClaimType.FOOD_SOURCE,
        "Meat, fish and other seafood are rich sources; eggs and dairy also contribute. "
        "Beans, nuts and whole grains contain zinc, but phytate can reduce its bioavailability.",
        "ODS-ZN",
    ),
    _claim(
        "zn.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 authorizes a conditional avoid-same-event preference only when the "
        "source-native supplemental elemental iron trigger is confirmed. Compound iron mass "
        "and fortified-food iron do not qualify. No universal hour gap is established.",
        "KIR-144",
    ),
    _claim(
        "zn.limit.v1",
        ClaimType.LIMITATION,
        'Do not infer "safe together" when no interaction/scheduling rule is available.',
        "KIR-145",
    ),
    _claim(
        "se.identity.v1",
        ClaimType.IDENTITY,
        "An essential mineral incorporated into selenoproteins.",
        "ODS-SE",
    ),
    _claim(
        "se.function.v1",
        ClaimType.FUNCTION,
        "Selenoproteins contribute to thyroid-hormone metabolism, DNA synthesis, reproduction "
        "and protection from oxidative damage.",
        "ODS-SE",
    ),
    _claim(
        "se.food.v1",
        ClaimType.FOOD_SOURCE,
        "Seafood, meat, poultry and organ meats are rich sources; Brazil nuts can contain "
        "very high amounts. Plant-food selenium can vary with soil conditions.",
        "ODS-SE",
    ),
    _claim(
        "se.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "No validated Morning/Day/Evening rule or universal meal requirement is authorized "
        "for the MVP.",
        "KIR-144",
    ),
    _claim(
        "se.limit.v1",
        ClaimType.LIMITATION,
        "Food selenium content can vary substantially by source; a food list is illustrative, "
        "not a precise intake estimate.",
        "KIR-145",
    ),
    _claim(
        "b6.identity.v1",
        ClaimType.IDENTITY,
        "A water-soluble vitamin family of related vitamers; "
        "PLP and PMP are active coenzyme forms.",
        "ODS-B6",
    ),
    _claim(
        "b6.function.v1",
        ClaimType.FUNCTION,
        "Participates in more than 100 enzyme reactions, especially amino-acid/protein "
        "metabolism; it also contributes to neurotransmitter synthesis, glycogen/glucose "
        "metabolism, immune function and hemoglobin formation.",
        "ODS-B6",
    ),
    _claim(
        "b6.food.v1",
        ClaimType.FOOD_SOURCE,
        "Fish, organ meats, potatoes and other starchy vegetables, non-citrus fruits, poultry "
        "and fortified cereals are common sources.",
        "ODS-B6",
    ),
    _claim(
        "b6.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        'KIR-144 rejects a generic "B vitamins in the morning" or "B6 at bedtime" '
        "scientific rule. "
        "Time-of-day placement is user preference unless another governed rule applies.",
        "KIR-144",
    ),
    _claim(
        "b6.limit.v1",
        ClaimType.LIMITATION,
        "A study using bedtime B6 for a specific research outcome does not create a general "
        "timing recommendation.",
        "KIR-145",
    ),
    _claim(
        "b12.identity.v1",
        ClaimType.IDENTITY,
        "A water-soluble vitamin; compounds with B12 activity are called cobalamins.",
        "ODS-B12",
    ),
    _claim(
        "b12.function.v1",
        ClaimType.FUNCTION,
        "Required for central-nervous-system development/function, normal red-blood-cell "
        "formation and DNA synthesis.",
        "ODS-B12",
    ),
    _claim(
        "b12.food.v1",
        ClaimType.FOOD_SOURCE,
        "Naturally present mainly in animal foods such as fish, meat, poultry, eggs and dairy. "
        "Plant foods do not naturally contain B12 unless fortified; fortified cereals and "
        "nutritional yeast can provide B12.",
        "ODS-B12",
    ),
    _claim(
        "b12.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "No governed KIR-144 clock-time rule exists for B12; Morning/Day/Evening placement "
        "should remain user-preference only.",
        "KIR-144",
    ),
    _claim(
        "b12.limit.v1",
        ClaimType.LIMITATION,
        "Absorption can depend on gastrointestinal physiology and medication/medical context; "
        "the card must not diagnose deficiency or recommend treatment.",
        "KIR-145",
    ),
    _claim(
        "fol.identity.v1",
        ClaimType.IDENTITY,
        '"Folate" is the vitamin family; folic acid is one form used in fortified foods and '
        "many supplements. 5-MTHF is another supplemental form.",
        "ODS-FOL",
    ),
    _claim(
        "fol.function.v1",
        ClaimType.FUNCTION,
        "Functions in one-carbon transfer reactions used for DNA/RNA synthesis, amino-acid "
        "metabolism and normal cell division.",
        "ODS-FOL",
    ),
    _claim(
        "fol.food.v1",
        ClaimType.FOOD_SOURCE,
        "Dark-green leafy vegetables, beans/peas, fruits, nuts, asparagus and Brussels sprouts "
        "are useful food sources; fortified grain products can contain folic acid.",
        "ODS-FOL",
    ),
    _claim(
        "fol.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 keeps food/fasting bioavailability differences informational only; they are "
        "not an automatic fasting rule.",
        "KIR-144",
    ),
    _claim(
        "fol.limit.v1",
        ClaimType.LIMITATION,
        "Do not convert U.S. DFE conversion conventions into an EU timing or dosing instruction.",
        "KIR-145",
    ),
    _claim(
        "fe.identity.v1",
        ClaimType.IDENTITY,
        "An essential mineral found in heme and non-heme forms in the diet.",
        "ODS-FE",
    ),
    _claim(
        "fe.function.v1",
        ClaimType.FUNCTION,
        "A component of hemoglobin and myoglobin for oxygen transport/use; also supports "
        "growth, neurological development, cellular function and some hormone synthesis.",
        "ODS-FE",
    ),
    _claim(
        "fe.food.v1",
        ClaimType.FOOD_SOURCE,
        "Heme iron is found in meat and seafood. Non-heme iron is found in legumes, nuts, "
        "vegetables and fortified grain products; its bioavailability is more affected by "
        "other meal components.",
        "ODS-FE",
    ),
    _claim(
        "fe.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 keeps generic fasting/tolerability advice informational only. Calcium/iron "
        "may receive a different-event preference, and a separate zinc rule exists only for "
        "confirmed source-native elemental supplemental iron conditions. No universal numeric "
        "gap is authorized.",
        "KIR-144",
    ),
    _claim(
        "fe.limit.v1",
        ClaimType.LIMITATION,
        "Therapeutic/prescribed iron and clinician instructions are not overridden by the "
        "generic planner.",
        "KIR-145",
    ),
    _claim(
        "ca.identity.v1",
        ClaimType.IDENTITY,
        "The most abundant mineral in the body.",
        "ODS-CA",
    ),
    _claim(
        "ca.function.v1",
        ClaimType.FUNCTION,
        "Provides structure to bones and teeth and participates in muscle function, nerve "
        "transmission, blood clotting, vascular contraction/dilation and hormone secretion.",
        "ODS-CA",
    ),
    _claim(
        "ca.food.v1",
        ClaimType.FOOD_SOURCE,
        "Milk, yogurt and cheese are rich sources. Nondairy sources include sardines/salmon "
        "with bones, kale, broccoli, bok choy and fortified foods.",
        "ODS-CA",
    ),
    _claim(
        "ca.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 authorizes a soft with-meal preference only for confirmed calcium carbonate; "
        "calcium citrate does not inherit that rule. KIR-144 also allows a constrained "
        "split-event rearrangement preference only for already-confirmed independently "
        "schedulable units; it must not create a dose or split an indivisible product.",
        "KIR-144",
    ),
    _claim(
        "ca.limit.v1",
        ClaimType.LIMITATION,
        "The calcium amount used for nutrition logic is elemental calcium, not total "
        "compound/tablet mass.",
        "KIR-145",
    ),
    _claim(
        "o3.identity.v1",
        ClaimType.IDENTITY,
        "Omega-3s are polyunsaturated fatty acids. ALA is an essential fatty acid; EPA and "
        "DHA are long-chain omega-3s.",
        "ODS-O3",
    ),
    _claim(
        "o3.function.v1",
        ClaimType.FUNCTION,
        "Omega-3s are components of cell-membrane phospholipids; DHA is especially "
        "concentrated in retina, brain and sperm. Omega-3 fatty acids also serve as "
        "precursors for signaling molecules.",
        "ODS-O3",
    ),
    _claim(
        "o3.food.v1",
        ClaimType.FOOD_SOURCE,
        "ALA occurs in flaxseed, soybean and canola oils, chia seeds and walnuts. EPA/DHA "
        "are found mainly in fish/seafood and marine/algal sources.",
        "ODS-O3",
    ),
    _claim(
        "o3.admin.v1",
        ClaimType.ADMINISTRATION_INFO,
        "KIR-144 explicitly does not authorize a generic omega-3 fat-meal rule based only on "
        '"ethyl ester"; delivery-system technology can change food dependence. Without the '
        "exact validated formulation/delivery-system applicability, no automatic meal rule is "
        "shown. There is no validated generic Morning/Day/Evening rule.",
        "KIR-144",
    ),
    _claim(
        "o3.limit.v1",
        ClaimType.LIMITATION,
        "Total fish-oil mass is not EPA+DHA or DHA mass. Product reformulation or corrected "
        "EPA/DHA data must invalidate stale applicability.",
        "KIR-145",
        "KIR-153",
    ),
)


def _content(
    key: str,
    name: str,
    prefix: str,
    reference_subject_keys: tuple[str, ...],
) -> NutrientCardContent:
    return NutrientCardContent(
        content_id=f"card:{key}:v1",
        content_version="kir145.accepted.v1",
        locale="en",
        substance_key=key,
        display_name=name,
        identity_claim_id=f"{prefix}.identity.v1",
        function_claim_ids=(f"{prefix}.function.v1",),
        food_source_claim_ids=(f"{prefix}.food.v1",),
        administration_claim_ids=(f"{prefix}.admin.v1",),
        limitation_claim_ids=(f"{prefix}.limit.v1",),
        reference_subject_keys=reference_subject_keys,
    )


CONTENTS: Final[tuple[NutrientCardContent, ...]] = (
    _content("vitamin_d", "Vitamin D", "vd", ("vitamin_d",)),
    _content("vitamin_c", "Vitamin C", "vc", ("vitamin_c",)),
    _content("magnesium", "Magnesium", "mg", ("magnesium",)),
    _content("zinc", "Zinc", "zn", ("zinc",)),
    _content("selenium", "Selenium", "se", ("selenium",)),
    _content("vitamin_b6", "Vitamin B6", "b6", ("vitamin_b6",)),
    _content("vitamin_b12", "Vitamin B12 / cobalamin", "b12", ("vitamin_b12",)),
    _content("folate", "Folate / folic acid", "fol", ("folate_dfe", "folic_acid")),
    _content("iron", "Iron", "fe", ("iron",)),
    _content("calcium", "Calcium", "ca", ("calcium",)),
    _content("omega_3", "Omega-3 / EPA / DHA", "o3", ("epa_plus_dha",)),
    _content("dha", "DHA", "o3", ("dha",)),
)


ALIASES: Final[tuple[tuple[str, str], ...]] = (
    ("vitamin d", "vitamin_d"),
    ("d", "vitamin_d"),
    ("vitamin c", "vitamin_c"),
    ("c", "vitamin_c"),
    ("magnesium", "magnesium"),
    ("mg", "magnesium"),
    ("zinc", "zinc"),
    ("selenium", "selenium"),
    ("vitamin b6", "vitamin_b6"),
    ("b6", "vitamin_b6"),
    ("vitamin b12", "vitamin_b12"),
    ("b12", "vitamin_b12"),
    ("cobalamin", "vitamin_b12"),
    ("folate", "folate"),
    ("folic acid", "folate"),
    ("iron", "iron"),
    ("calcium", "calcium"),
    ("omega 3", "omega_3"),
    ("omega3", "omega_3"),
    ("epa dha", "omega_3"),
    ("epa + dha", "omega_3"),
    ("dha", "dha"),
)


APPROVED_CARD_CONTENT: Final = CardContentRegistry(
    sources=SOURCES,
    claims=CLAIMS,
    contents=CONTENTS,
    aliases=ALIASES,
)
