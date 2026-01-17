from pydantic import BaseModel, Field
from typing import Optional, List
from research_agent.human_upgrade.structured_outputs.enums_literals import EntityResearchType, PriorityLevel, TodoStatus
from datetime import datetime, timezone 


# ========================================================================
# LLM OUTPUT MODELS - Minimal fields for LLM to generate
# ======================================================================== 

def utc_now() -> datetime:
    """Get the current UTC time."""
    return datetime.now(timezone.utc)

class TodoItemOutput(BaseModel):
    """Minimal todo item for LLM generation - no dates or computed fields."""
    id: str = Field(
        ...,
        description="Unique identifier for this todo (e.g., 'biz_001_identity')"
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Clear description of what needs to be done"
    )
    entityType: Optional[EntityResearchType] = Field(
        default=None,
        description="Type of entity this todo relates to"
    )
    entityName: Optional[str] = Field(
        default=None,
        description="Name of the entity this todo relates to"
    )
    priority: Optional[PriorityLevel] = Field(
        default="MEDIUM",
        description="Priority level (HIGH, MEDIUM, LOW)"
    )


class TodoListOutput(BaseModel):
    """Minimal todo list for LLM generation - just the todo items."""
    todos: List[TodoItemOutput] = Field(
        default_factory=list,
        description="List of todo items to complete the research objective"
    )


# ========================================================================
# INTERNAL STATE MODELS - Full models with temporal data and methods
# ========================================================================

class TodoItem(BaseModel):
    """Full todo item with all tracking fields for internal state management."""
    id: str = Field(
        ...,
        description="Unique identifier for this todo (e.g., 'biz_001_identity')"
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Clear description of what needs to be done"
    )
    status: TodoStatus = Field(
        default="pending",
        description="Current status of this todo"
    )
    entityType: Optional[EntityResearchType] = Field(
        default=None,
        description="Type of entity this todo relates to"
    )
    entityName: Optional[str] = Field(
        default=None,
        description="Name of the entity this todo relates to"
    )
    priority: Optional[PriorityLevel] = Field(
        default="MEDIUM",
        description="Priority level"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about progress, blockers, or findings"
    )
    createdAt: datetime = Field(
        default_factory=utc_now,
        description="When this todo was created"
    )
    updatedAt: datetime = Field(
        default_factory=utc_now,
        description="When this todo was last updated"
    )
    completedAt: Optional[datetime] = Field(
        default=None,
        description="When this todo was completed"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TodoList(BaseModel):
    """Full todo list with computed counts and helper methods for internal state management."""
    todos: List[TodoItem] = Field(
        default_factory=list,
        description="List of todo items"
    )
    totalTodos: int = Field(
        default=0,
        ge=0,
        description="Total number of todos"
    )
    completedCount: int = Field(
        default=0,
        ge=0,
        description="Number of completed todos"
    )
    inProgressCount: int = Field(
        default=0,
        ge=0,
        description="Number of in-progress todos"
    )
    pendingCount: int = Field(
        default=0,
        ge=0,
        description="Number of pending todos"
    )
    
    def update_counts(self):
        """Update the count fields based on current todos."""
        self.totalTodos = len(self.todos)
        self.completedCount = sum(1 for t in self.todos if t.status == "completed")
        self.inProgressCount = sum(1 for t in self.todos if t.status == "in_progress")
        self.pendingCount = sum(1 for t in self.todos if t.status == "pending")
    
    def get_todo(self, todo_id: str) -> Optional[TodoItem]:
        """Get a todo by ID."""
        for todo in self.todos:
            if todo.id == todo_id:
                return todo
        return None
    
    def add_todo(self, todo: TodoItem) -> None:
        """Add a new todo item."""
        if not self.get_todo(todo.id):
            self.todos.append(todo)
            self.update_counts()
    
    def update_todo(
        self,
        todo_id: str,
        status: Optional[TodoStatus] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update a todo item. Returns True if found and updated."""
        todo = self.get_todo(todo_id)
        if not todo:
            return False
        
        if status:
            todo.status = status
            if status == "completed" and not todo.completedAt:
                todo.completedAt = utc_now()
        
        if notes is not None:
            if todo.notes:
                todo.notes = f"{todo.notes}\n{notes}"
            else:
                todo.notes = notes
        
        todo.updatedAt = utc_now()
        self.update_counts()
        return True
    
    def get_next_pending(self) -> Optional[TodoItem]:
        """Get the next pending todo (highest priority first)."""
        pending = [t for t in self.todos if t.status == "pending"]
        if not pending:
            return None
        
        # Sort by priority (HIGH > MEDIUM > LOW)
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        pending.sort(key=lambda t: priority_order.get(t.priority or "MEDIUM", 1))
        return pending[0]
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ========================================================================
# CONVERSION UTILITIES
# ========================================================================

def convert_output_to_state(output: TodoListOutput) -> TodoList:
    """
    Convert LLM-generated TodoListOutput to full TodoList for state management.
    Adds temporal data and initializes all counts.
    """
    now = utc_now()
    
    # Convert each TodoItemOutput to TodoItem with temporal data
    full_todos = [
        TodoItem(
            id=item.id,
            description=item.description,
            status="pending",  # All new todos start as pending
            entityType=item.entityType,
            entityName=item.entityName,
            priority=item.priority or "MEDIUM",
            notes=None,
            createdAt=now,
            updatedAt=now,
            completedAt=None,
        )
        for item in output.todos
    ]
    
    # Create TodoList and update counts
    todo_list = TodoList(todos=full_todos)
    todo_list.update_counts()
    
    return todo_list
