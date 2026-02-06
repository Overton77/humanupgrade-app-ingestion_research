from research_agent.human_upgrade.structured_outputs.research_plans_outputs import ResearchMissionPlanFinal
from langchain_core.runnables import RunnableConfig
import asyncio
from research_agent.human_upgrade.graphs.research_mission_graph import build_mission_graph
from research_agent.human_upgrade.graphs.test_run_data.one_thousand_roads_research import MISSION_PLAN_JSON
import json


async def run_mission(plan: ResearchMissionPlanFinal, config: RunnableConfig | None = None):
    default_semaphore = 8 
    graph = build_mission_graph(plan, config or {}) 
    cfg: RunnableConfig = config or {"configurable": {"thread_id": f"mission__{plan.mission_id}"}}
    return await graph.ainvoke({"plan": plan, "default_semaphore": default_semaphore}, cfg)  


if __name__ == "__main__": 
    async def main():
        plan = ResearchMissionPlanFinal.model_validate(MISSION_PLAN_JSON)
        result = await run_mission(plan)
        print(json.dumps(result, indent=4)) 
        print(result.get("logs")) 
        print(result.get("output_registry")) 
        print(result.get("mission_output")) 
        print(result.get("stage_outputs")) 
        
    asyncio.run(main()) 