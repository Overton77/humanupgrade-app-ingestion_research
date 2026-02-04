from typing import Dict 
from research_agent.human_upgrade.constants.research_plans_prebuilt_models import PrebuiltResearchPlan
from research_agent.human_upgrade.constants.research_plans_prebuilt_full_entities_standard import FULL_ENTITIES_STANDARD_PLAN
from research_agent.human_upgrade.constants.research_plans_prebuilt_full_entities_basic import FULL_ENTITIES_BASIC_PLAN

PREBUILT_RESEARCH_PLANS: Dict[str, PrebuiltResearchPlan] = {
    "full_entities_standard": FULL_ENTITIES_STANDARD_PLAN,
    "full_entities_basic": FULL_ENTITIES_BASIC_PLAN,
    # Add more research plan modes here as they are defined
    # "full_entities_deep": FULL_ENTITIES_DEEP_PLAN,
}
