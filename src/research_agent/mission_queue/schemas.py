from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskType(str, Enum):
    INSTANCE_RUN = "INSTANCE_RUN"
    SUBSTAGE_REDUCE = "SUBSTAGE_REDUCE"
    STAGE_REDUCE = "STAGE_REDUCE"       # reserved for later
    MISSION_REDUCE = "MISSION_REDUCE"   # reserved for later


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class TaskDefinition:
    """
    A normalized DAG task created by the mission DAG builder.
    This is the "source of truth" for the scheduler about what a task is.
    """
    task_id: str
    mission_id: str
    task_type: TaskType
    task_key: str  # human-readable path-like key (useful for logs/debug)
    inputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunnableTaskMessage:
    """
    What gets enqueued into Redis Streams "runnable" stream.
    Keep it small: routing + minimal inputs.
    """
    mission_id: str
    task_id: str
    task_type: TaskType
    task_key: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    attempt: int = 1

    def to_redis_fields(self) -> Dict[str, str]:
        """
        Flatten into Redis Stream fields (strings).
        The producer/consumer layer can JSON-encode inputs.
        """
        # NOTE: we intentionally leave JSON encoding to the Redis bus utility,
        # so this module doesn't depend on json serialization choices.
        return {
            "mission_id": self.mission_id,
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "task_key": self.task_key,
            "attempt": str(self.attempt),
        }


@dataclass(frozen=True)
class MissionEventMessage:
    """
    Events emitted by workers.
    Scheduler listens to these to unlock dependents.
    """
    mission_id: str
    task_id: str
    event_type: str  # TASK_STARTED / TASK_SUCCEEDED / TASK_FAILED / etc.
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MissionDAG:
    """
    The fully built DAG structure for one mission.
    - tasks: registry of task_id -> TaskDefinition
    - deps_remaining: how many unmet dependencies per task_id
    - dependents: adjacency list parent -> [children]
    - parents: adjacency list child -> [parents] (debugging + validation)
    - initial_ready: tasks with deps_remaining==0 at build time
    """
    mission_id: str
    tasks: Dict[str, TaskDefinition]
    deps_remaining: Dict[str, int]
    dependents: Dict[str, List[str]]
    parents: Dict[str, List[str]]
    initial_ready: List[str]

    def summarize(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for t in self.tasks.values():
            by_type[t.task_type.value] = by_type.get(t.task_type.value, 0) + 1

        return {
            "mission_id": self.mission_id,
            "num_tasks": len(self.tasks),
            "by_type": by_type,
            "num_edges": sum(len(v) for v in self.dependents.values()),
            "initial_ready": len(self.initial_ready),
        }
