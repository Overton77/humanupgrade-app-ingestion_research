from langchain.tools import tool, ToolRuntime  
from typing import Optional  
from research_agent.human_upgrade.structured_outputs.todos import TodoList, TodoItem
from research_agent.human_upgrade.logger import logger 



# NOTE: todo_create is not needed - todos are generated via LLM structured output
# in the generate_todos_node, not created individually by the agent 


@tool(
    description="Update an existing todo item's status or add notes.",
    parse_docstring=False,
)
async def todo_update(
    runtime: ToolRuntime,
    todo_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Update a todo item.
    
    Args:
        todo_id: ID of the todo to update
        status: New status (pending, in_progress, completed)
        notes: Notes to append about progress or findings
    
    Returns:
        Confirmation message
    """
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"📝 UPDATE TODO [{steps_taken}]: {todo_id}")
    
    # Get todo list from state (it's a TodoList Pydantic model)
    todo_list: TodoList| None = runtime.state.get("todo_list", None)
    if not todo_list:
        return f"Error: No todo list found in state. Create todos first."
    
    # Update the todo using TodoList method
    success = todo_list.update_todo(
        todo_id=todo_id,
        status=status,
        notes=notes,
    )
    
    if not success:
        logger.warning(f"⚠️  TODO NOT FOUND: {todo_id}")
        return f"Error: Todo not found: {todo_id}"
    
    # State is automatically updated since we modified the object in place
    # But let's explicitly set it to ensure it's tracked
    runtime.state["todo_list"] = todo_list
    
    status_msg = f" → {status}" if status else ""
    notes_msg = f" (notes added)" if notes else ""
    
    logger.info(f"✅ TODO UPDATED: {todo_id}{status_msg}{notes_msg} (Progress: {todo_list.completedCount}/{todo_list.totalTodos})")
    
    return f"Todo updated: {todo_id}{status_msg}{notes_msg}\nProgress: {todo_list.completedCount}/{todo_list.totalTodos} completed"


@tool(
    description="Read the current todo list to see what tasks are pending, in progress, or completed.",
    parse_docstring=False,
)
async def todo_read(
    runtime: ToolRuntime,
    status_filter: Optional[str] = None,
) -> str:
    """
    Read the todo list.
    
    Args:
        status_filter: Optional status to filter by (pending, in_progress, completed)
    
    Returns:
        Formatted todo list
    """
    # Get todo list from state (it's a TodoList Pydantic model)
    todo_list: TodoList| None = runtime.state.get("todo_list", None)
    if not todo_list:
        return "No todo list found. Generate todos first."
    
    if status_filter:
        # Filter todos by status
        filtered_todos = [t for t in todo_list.todos if t.status == status_filter]
        if not filtered_todos:
            return f"No todos with status: {status_filter}"
        
        lines = [f"Todos with status '{status_filter}' ({len(filtered_todos)}):"]
        for todo in filtered_todos:
            entity_info = f" [{todo.entityType}] {todo.entityName}" if todo.entityName else ""
            lines.append(f"  • {todo.id}: {todo.description}{entity_info}")
            if todo.notes:
                first_note = todo.notes.split('\n')[0][:100]  # Truncate long notes
                lines.append(f"    Notes: {first_note}")
        return "\n".join(lines)
    
    # Return full formatted list
    lines = [
        f"📋 Todo List Summary:",
        f"Total: {todo_list.totalTodos} | ✅ Completed: {todo_list.completedCount} | 🔄 In Progress: {todo_list.inProgressCount} | ⏳ Pending: {todo_list.pendingCount}",
        "",
        "All Todos:",
    ]
    
    for todo in todo_list.todos:
        status_emoji = {
            "completed": "✅",
            "in_progress": "🔄",
            "pending": "⏳",
        }.get(todo.status, "❓")
        
        priority_emoji = {
            "HIGH": "🔴",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }.get(todo.priority, "⚪")
        
        entity_info = f" [{todo.entityType}] {todo.entityName}" if todo.entityName else ""
        lines.append(f"  {status_emoji} {priority_emoji} {todo.id}: {todo.description}{entity_info}")
        
        if todo.notes:
            first_note = todo.notes.split('\n')[0][:80]  # Truncate long notes
            lines.append(f"      Notes: {first_note}")
    
    formatted = "\n".join(lines)
    logger.info(f"✅ TODO LIST READ: {todo_list.totalTodos} todos")
    
    return formatted


@tool(
    description="Get the next pending todo item to work on (highest priority first).",
    parse_docstring=False,
)
async def todo_get_next(
    runtime: ToolRuntime,
) -> str:
    """
    Get the next pending todo.
    
    Returns:
        Details of the next todo to work on, or message if no pending todos
    """
    # Get todo list from state (it's a TodoList Pydantic model)
    todo_list: TodoList | None = runtime.state.get("todo_list", None)
    if not todo_list:
        return "No todo list found. Generate todos first."
    
    # Use TodoList method to get next pending
    next_todo: Optional[TodoItem] = todo_list.get_next_pending()
    if not next_todo:
        logger.info("✅ No pending todos remaining!")
        return f"No pending todos. All tasks complete or in progress!\n✅ Completed: {todo_list.completedCount}/{todo_list.totalTodos}"
    
    priority_icon = {
        "HIGH": "🔴",
        "MEDIUM": "🟡",
        "LOW": "🟢",
    }.get(next_todo.priority, "⚪")
    
    entity_info = ""
    if next_todo.entityName:
        entity_info = f"\nEntity: [{next_todo.entityType}] {next_todo.entityName}"
    
    logger.info(f"🎯 NEXT TODO: {next_todo.id}")
    
    return (
        f"{priority_icon} Next Todo:\n"
        f"ID: {next_todo.id}\n"
        f"Description: {next_todo.description}{entity_info}\n"
        f"Priority: {next_todo.priority}\n"
        f"Progress: {todo_list.completedCount}/{todo_list.totalTodos} completed"
    )
