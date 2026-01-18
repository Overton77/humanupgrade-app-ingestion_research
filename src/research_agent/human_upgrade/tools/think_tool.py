from langchain.tools import tool, ToolRuntime   
from research_agent.human_upgrade.logger import logger   
from langchain_core.messages import ToolMessage 
from langgraph.types import Command 


@tool( 
    description="Think about the current task and the best way to complete it.",
    parse_docstring=True,
)
def think_tool(
    runtime: ToolRuntime,
    reflection: str,
) -> Command:
    """
    Think about the current task and the best way to complete it.

    Args:
        runtime: The tool runtime context containing tool call information.
        reflection: A reflection on all the current context, the objectives, work done so far, and the best way to complete the task.

    Returns:
        A Command object containing the reflection as a ToolMessage in the messages update.
    """

    logger.info(f"🧠 THINKING: {reflection}") 
    

    return Command(  
        update={ 
            "messages": [ 
                ToolMessage(
                    content=reflection, 
                    tool_call_id=runtime.tool_call_id, 
                )
            ]
        }
    )