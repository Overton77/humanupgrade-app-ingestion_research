"""
TodoList management functions for research agents.

These functions provide base todo list operations that can be wrapped
into LangChain tools with runtime injection.
"""

from typing import Optional, List
from datetime import datetime
import json
from pathlib import Path 
from datetime import datetime, timezone 


# We'll import the models when used, avoiding circular imports
# from research_agent.human_upgrade.entity_fast_output_models import TodoItem, TodoList, TodoStatus

def utc_now() -> datetime:
    """Get the current UTC time."""
    return datetime.now(timezone.utc)

# ============================================================================
# TODO LIST OPERATIONS
# ============================================================================

def create_todo_list() -> dict:
    """
    Create a new empty todo list.
    
    Returns:
        Dict representation of an empty TodoList
    """
    return {
        "todos": [],
        "totalTodos": 0,
        "completedCount": 0,
        "inProgressCount": 0,
        "pendingCount": 0,
    }


def add_todo(
    todo_list: dict,
    todo_id: str,
    description: str,
    entity_type: Optional[str] = None,
    entity_name: Optional[str] = None,
    priority: str = "MEDIUM",
    status: str = "pending",
) -> dict:
    """
    Add a new todo item to the list.
    
    Args:
        todo_list: Current todo list dict
        todo_id: Unique identifier for the todo
        description: What needs to be done
        entity_type: Optional entity type (PERSON, BUSINESS, etc.)
        entity_name: Optional entity name
        priority: Priority level (HIGH, MEDIUM, LOW)
        status: Initial status (default: pending)
    
    Returns:
        Updated todo list dict
    """
    # Check if todo already exists
    existing_ids = {t["id"] for t in todo_list.get("todos", [])}
    if todo_id in existing_ids:
        return todo_list  # Already exists, don't duplicate
    
    now = utc_now().isoformat()
    
    new_todo = {
        "id": todo_id,
        "description": description,
        "status": status,
        "entityType": entity_type,
        "entityName": entity_name,
        "priority": priority,
        "notes": None,
        "createdAt": now,
        "updatedAt": now,
        "completedAt": None,
    }
    
    todo_list["todos"].append(new_todo)
    _update_counts(todo_list)
    
    return todo_list


def update_todo(
    todo_list: dict,
    todo_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[dict, bool]:
    """
    Update an existing todo item.
    
    Args:
        todo_list: Current todo list dict
        todo_id: ID of the todo to update
        status: New status (pending, in_progress, completed, blocked, skipped)
        notes: Notes to append (will be appended to existing notes)
    
    Returns:
        Tuple of (updated todo list dict, success boolean)
    """
    todo = _find_todo(todo_list, todo_id)
    if not todo:
        return todo_list, False
    
    if status:
        todo["status"] = status
        if status == "completed" and not todo["completedAt"]:
            todo["completedAt"] = utc_now().isoformat()
    
    if notes is not None:
        if todo["notes"]:
            todo["notes"] = f"{todo['notes']}\n{notes}"
        else:
            todo["notes"] = notes
    
    todo["updatedAt"] = utc_now().isoformat()
    _update_counts(todo_list)
    
    return todo_list, True


def get_todo(todo_list: dict, todo_id: str) -> Optional[dict]:
    """
    Get a specific todo by ID.
    
    Args:
        todo_list: Current todo list dict
        todo_id: ID of the todo to retrieve
    
    Returns:
        Todo dict if found, None otherwise
    """
    return _find_todo(todo_list, todo_id)


def get_all_todos(todo_list: dict) -> List[dict]:
    """
    Get all todos in the list.
    
    Args:
        todo_list: Current todo list dict
    
    Returns:
        List of all todo dicts
    """
    return todo_list.get("todos", [])


def get_todos_by_status(todo_list: dict, status: str) -> List[dict]:
    """
    Get todos filtered by status.
    
    Args:
        todo_list: Current todo list dict
        status: Status to filter by
    
    Returns:
        List of todo dicts with the given status
    """
    return [t for t in todo_list.get("todos", []) if t["status"] == status]


def get_next_pending_todo(todo_list: dict) -> Optional[dict]:
    """
    Get the next pending todo (highest priority first).
    
    Args:
        todo_list: Current todo list dict
    
    Returns:
        Next pending todo dict, or None if no pending todos
    """
    pending = get_todos_by_status(todo_list, "pending")
    if not pending:
        return None
    
    # Sort by priority (HIGH > MEDIUM > LOW)
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    pending.sort(key=lambda t: priority_order.get(t.get("priority", "MEDIUM"), 1))
    return pending[0]


def format_todo_list(todo_list: dict) -> str:
    """
    Format the todo list as a readable string.
    
    Args:
        todo_list: Current todo list dict
    
    Returns:
        Formatted string representation
    """
    lines = []
    lines.append("=" * 80)
    lines.append("TODO LIST SUMMARY")
    lines.append("=" * 80)
    lines.append(f"Total: {todo_list.get('totalTodos', 0)}")
    lines.append(f"Completed: {todo_list.get('completedCount', 0)}")
    lines.append(f"In Progress: {todo_list.get('inProgressCount', 0)}")
    lines.append(f"Pending: {todo_list.get('pendingCount', 0)}")
    lines.append("")
    
    todos = todo_list.get("todos", [])
    if not todos:
        lines.append("(no todos)")
        return "\n".join(lines)
    
    # Group by status
    for status in ["in_progress", "pending", "blocked", "completed", "skipped"]:
        status_todos = [t for t in todos if t["status"] == status]
        if not status_todos:
            continue
        
        status_label = status.replace("_", " ").title()
        lines.append(f"\n{status_label} ({len(status_todos)}):")
        lines.append("-" * 80)
        
        for todo in status_todos:
            priority_icon = {
                "HIGH": "🔴",
                "MEDIUM": "🟡",
                "LOW": "🟢",
            }.get(todo.get("priority", "MEDIUM"), "⚪")
            
            entity_info = ""
            if todo.get("entityName"):
                entity_info = f" [{todo.get('entityType', '')}] {todo['entityName']}"
            
            lines.append(f"{priority_icon} {todo['id']}: {todo['description']}{entity_info}")
            
            if todo.get("notes"):
                # Show first line of notes only
                first_note = todo["notes"].split("\n")[0]
                if len(first_note) > 60:
                    first_note = first_note[:57] + "..."
                lines.append(f"   Notes: {first_note}")
    
    lines.append("\n" + "=" * 80)
    return "\n".join(lines)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _find_todo(todo_list: dict, todo_id: str) -> Optional[dict]:
    """Find a todo by ID."""
    for todo in todo_list.get("todos", []):
        if todo["id"] == todo_id:
            return todo
    return None


def _update_counts(todo_list: dict) -> None:
    """Update the count fields based on current todos."""
    todos = todo_list.get("todos", [])
    todo_list["totalTodos"] = len(todos)
    todo_list["completedCount"] = sum(1 for t in todos if t["status"] == "completed")
    todo_list["inProgressCount"] = sum(1 for t in todos if t["status"] == "in_progress")
    todo_list["pendingCount"] = sum(1 for t in todos if t["status"] == "pending")


