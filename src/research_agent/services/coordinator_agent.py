"""Coordinator Agent Service.

This module provides the LangChain agent instance for the Coordinator Agent,
using OpenAI's models with web search tools and research planning capabilities.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.graph.state import CompiledStateGraph
from typing import Optional

from research_agent.infrastructure.llm.base_models import gpt_4_1, gpt_5_mini, gpt_5 
from research_agent.infrastructure.storage.postgres.langgraph_persistence import get_persistence
from research_agent.infrastructure.llm.builtin_tools import openai_search_tool
from research_agent.tools.web_search_tools import search_web, extract_from_urls, map_website, search_wikipedia
from research_agent.tools.coordinator_tools import (
    create_research_plan,
    get_research_plan,
    list_research_plans,
)
from research_agent.graphs.state.coordinator_agent_state import CoordinatorAgentState


# System prompt for the Coordinator Agent
COORDINATOR_SYSTEM_PROMPT = """You are a Research Planning Coordinator, an expert assistant that helps research administrators design and plan comprehensive research missions.

## Your Role

You collaborate with research administrators to:
1. **Understand and clarify** research objectives, scope, and requirements
2. **Investigate and gather** preliminary information about target entities (companies, products, people, topics)
3. **Design comprehensive research plans** with clear stages, substages, and specialized agent instances
4. **Optimize plans** within budget and time constraints
5. **Present plans** for administrator review and approval

## Your Capabilities

**Web Research Tools:**
- `search_web`: Search the web for information (companies, products, news, market research)
- `extract_from_urls`: Extract and analyze content from specific URLs (product pages, documentation, company sites)
- `map_website`: Discover all pages and structure of a website (useful for catalog/documentation discovery)
- `search_wikipedia`: Search Wikipedia for background information (companies, people, concepts)

**Planning Tools:**
- `create_research_plan`: Create a structured research plan with stages, substages, and agent instances
- `get_research_plan`: Retrieve a previously created plan from the conversation state
- `list_research_plans`: List all plans created in this conversation

## Your Planning Process

### Phase 1: Discovery & Clarification (CRITICAL)
Before creating any plan, you MUST:
1. **Ask clarifying questions** to understand:
   - What entities are we researching? (companies, products, people, topics)
   - What are the key questions we need to answer?
   - What's the end goal? (due diligence, competitive analysis, market research, etc.)
   - What are the budget/time constraints?
   - What level of depth is needed?

2. **Gather preliminary information**:
   - Use your web search tools to learn about the target entities
   - Understand the competitive landscape, industry context
   - Identify potential data sources and research challenges

### Phase 2: Plan Design
After Phase 1, create a research plan that includes:

**Stages & Substages:**
- Break research into logical stages (e.g., "Discovery", "Deep Analysis", "Synthesis")
- Within each stage, define substages for specific research activities
- Consider dependencies between stages

**Agent Instances:**
- For each substage, specify agent instances (specialized research agents)
- Examples: "Company Profile Agent", "Product Claims Agent", "Competitive Analysis Agent"
- Assign clear purposes, target entities, and key questions to each agent
- Estimate costs (low/medium/high or specific amounts)

**Objectives & Success Criteria:**
- Define clear, measurable objectives
- Specify how we'll know each objective is achieved

**Budget Optimization:**
- Respect the administrator's budget constraints
- Optimize for speed, cost, depth, or balanced approach
- Provide cost/duration estimates

### Phase 3: Presentation & Iteration
- Present the plan clearly using the `create_research_plan` tool
- Be ready to iterate based on administrator feedback
- Adjust scope, depth, or approach as needed

## Guidelines

- **ALWAYS clarify first** - Don't rush to create a plan without understanding requirements
- **Be specific** - Vague plans are not helpful
- **Be realistic** - Provide honest estimates and acknowledge limitations
- **Be thorough** - Research plans should cover all aspects of the research question
- **Be budget-conscious** - Respect constraints and optimize accordingly
- **Be collaborative** - This is a conversation with the administrator, not a monologue

## Output Modes

Most search tools support `output_mode`:
- `"summary"`: Returns LLM-compressed summaries with citations (recommended for initial research)
- `"raw"`: Returns formatted raw results with URLs preserved (useful when you need specific URLs/details)

Use summary mode for exploratory research, switch to raw mode when you need URLs or detailed data.

Remember: You are a planning assistant, not a research executor. Your job is to create excellent plans in collaboration with the research administrator."""


# Global agent instance (initialized once during app startup)
_coordinator_agent: Optional[CompiledStateGraph] = None


async def initialize_coordinator_agent() -> CompiledStateGraph:
    """Initialize the Coordinator Agent during app startup.
    
    This should be called once during FastAPI lifespan startup.
    Uses Postgres for persistence (store and checkpointer).
    
    Returns:
        CompiledStateGraph instance (LangGraph agent) configured with:
        - Web search tools (Tavily search, extract, map)
        - Wikipedia search
        - OpenAI's built-in web search
        - Research plan creation tool
    """
    global _coordinator_agent
    
    if _coordinator_agent is not None:
        return _coordinator_agent
    
    # Get Postgres store and checkpointer
    store, checkpointer = await get_persistence()
    
    # Use GPT-4.1 for the coordinator (can switch to gpt_5 or gpt_5_mini if needed)
    model = gpt_4_1
    
    # Define coordinator tools
    coordinator_tools = [
        # Web search tools (Tavily-powered)
        search_web,           # Main web search
        extract_from_urls,    # Extract content from specific URLs
        map_website,          # Discover website structure
        
        # Wikipedia search
        search_wikipedia,     # Background information from Wikipedia
        
        # Research planning
        create_research_plan, # Create structured research plans
        get_research_plan,    # Retrieve a specific research plan from state
        list_research_plans,  # List all plans in the conversation
    ]
    
    # Bind OpenAI's built-in search as a model-bound tool (optional fallback)
    model_with_builtin = model.bind_tools([openai_search_tool])
    
    # Create HITL middleware for research plan approval
    hitl_middleware = HumanInTheLoopMiddleware(
        interrupt_on={
            # Require approval for research plan creation
            "create_research_plan": {
                "allowed_decisions": ["approve", "edit", "reject"],
                "description": lambda tool_call, state, runtime: (
                    f"Research Plan: {tool_call.get('arguments', {}).get('mission_title', 'Untitled')}\n\n"
                    f"The coordinator has created a research plan and requires your approval "
                    f"before proceeding."
                )
            },
            # Other tools auto-approved (no interrupt)
            "search_web": False,
            "extract_from_urls": False,
            "map_website": False,
            "search_wikipedia": False,
            "get_research_plan": False,
            "list_research_plans": False,
        },
        description_prefix="Tool execution requires approval",
    )
    
    # Create the agent using create_agent
    # This returns a CompiledStateGraph (LangGraph agent)
    agent = create_agent(
        model=model_with_builtin,
        tools=coordinator_tools,
        system_prompt=COORDINATOR_SYSTEM_PROMPT,
        state_schema=CoordinatorAgentState,  # Custom state with research_plans tracking
        middleware=[hitl_middleware],  # Add HITL middleware for research plan approval
        store=store,
        checkpointer=checkpointer,  # Required for HITL interrupts
    )
    
    _coordinator_agent = agent
    return agent


def get_coordinator_agent() -> CompiledStateGraph:
    """Get the initialized Coordinator Agent.
    
    Returns the agent instance that was initialized during app startup.
    
    Returns:
        CompiledStateGraph instance
        
    Raises:
        RuntimeError: If agent hasn't been initialized yet
    """
    if _coordinator_agent is None:
        raise RuntimeError(
            "Coordinator agent not initialized. "
            "Call initialize_coordinator_agent() during app startup."
        )
    return _coordinator_agent


def generate_thread_title(first_message: str, max_length: int = 50) -> str:
    """Generate a title for a thread based on the first message.
    
    Args:
        first_message: The first user message in the thread
        max_length: Maximum length of the generated title
        
    Returns:
        A concise title for the thread
    """
    # Simple title generation - truncate and clean up
    title = first_message.strip()
    
    # Remove newlines and extra whitespace
    title = " ".join(title.split())
    
    # Truncate if too long
    if len(title) > max_length:
        title = title[:max_length - 3] + "..."
    
    # If still empty, use default
    if not title:
        title = "New Conversation"
    
    return title
