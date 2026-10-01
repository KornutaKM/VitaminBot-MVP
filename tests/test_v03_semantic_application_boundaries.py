from vitaminbot.application.applicability import ApplicabilityController
from vitaminbot.application.intake import IntakeController
from vitaminbot.application.kir116 import KIR116Controller
from vitaminbot.application.kir120 import KIR120Controller
from vitaminbot.application.kir122 import KIR122Controller
from vitaminbot.application.kir174 import KIR174Controller
from vitaminbot.application.nutrition import NutrientReferenceController, NutritionController
from vitaminbot.application.supplements import SupplementController


def test_v03_semantic_controller_names_are_behavior_preserving_aliases() -> None:
    assert SupplementController is KIR116Controller
    assert IntakeController is KIR120Controller
    assert NutritionController is KIR122Controller
    assert NutrientReferenceController is KIR146Controller
    assert ApplicabilityController is KIR174Controller
