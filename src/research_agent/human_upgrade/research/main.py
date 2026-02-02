import asyncio
from research_mission.models import ResearchPlan, StagePlan, SubStagePlan, SubAgentTypeConfig, ConnectedCandidates
from research_mission.mission_graph import run_mission

def demo_plan() -> ResearchPlan:
    return ResearchPlan(
        mode="entities_standard",
        mission_id="human_upgrade_demo_company",
        connected=ConnectedCandidates(
            businesses=[{"name": "DemoCo"}],
            people=[{"name": "Founder A"}],
            products=[{"name": "Product X"}],
            compounds=[{"name": "Glutathione"}],
        ),
        curated_sources=[],
        tool_recommendations=[],
        stages=[
            StagePlan(
                id="S1",
                name="Entity & Structure Overview",
                substages=[
                    SubStagePlan(
                        id="1.1",
                        name="BusinessIdentityAndLeadership",
                        agents=[
                            SubAgentTypeConfig(
                                agent_type="BusinessIdentityAndLeadershipAgent",
                                count=1,
                                tool_names=["web_search", "file_write"],
                                objectives=["Produce org bio, leadership snapshot, timeline anchors."],
                            )
                        ],
                    ),
                    SubStagePlan(
                        id="1.2",
                        name="People & Roles",
                        depends_on=["1.1"],
                        agents=[
                            SubAgentTypeConfig(
                                agent_type="PersonBioAndAffiliationsAgent",
                                count=2,  # pretend 2 key people
                                slice_on="person",
                                slice_ids=["Founder A", "Advisor B"],
                                tool_names=["web_search", "file_write"],
                                objectives=["Write a bio + affiliations + credibility anchors."],
                            )
                        ],
                    ),
                ],
            ),
            StagePlan(
                id="S2",
                name="Products, Offerings & Claims",
                depends_on=["S1"],
                substages=[
                    SubStagePlan(
                        id="2.1",
                        name="ProductSpec",
                        agents=[
                            SubAgentTypeConfig(
                                agent_type="ProductSpecAgent",
                                count=1,
                                slice_on="product",
                                slice_ids=["Product X"],
                                tool_names=["web_search", "file_write"],
                                objectives=["Extract price, variants, ingredients/specs, warnings, manuals."],
                            )
                        ],
                    )
                ],
            ),
        ],
    )

async def main():
    plan = demo_plan()
    out = await run_mission(plan)
    print("DONE. Logs:")
    for line in out.get("logs", []):
        print("-", line)

if __name__ == "__main__":
    asyncio.run(main())
