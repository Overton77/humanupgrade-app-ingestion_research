from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as redis

from research_agent.structured_outputs.research_plans_outputs import ResearchMissionPlanFinal
from research_agent.mission_queue.mission_dag_builder import build_mission_dag, format_dag_summary
from research_agent.mission_queue.schemas import MissionDAG, TaskDefinition, TaskStatus, TaskType


# -----------------------------
# Redis configuration
# -----------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RUNNABLE_STREAM = os.getenv("RUNNABLE_STREAM", "mission:runnable")
EVENTS_STREAM = os.getenv("EVENTS_STREAM", "mission:events")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "workers")  # workers consume runnable
SCHEDULER_NAME = os.getenv("SCHEDULER_NAME", "scheduler-1")

XREAD_BLOCK_MS = int(os.getenv("XREAD_BLOCK_MS", "5000"))
XREAD_COUNT = int(os.getenv("XREAD_COUNT", "50"))

# How often to print status
STATUS_PRINT_EVERY_S = float(os.getenv("STATUS_PRINT_EVERY_S", "5"))


def now_ms() -> int:
    return int(time.time() * 1000)


def to_str(x: Any) -> Any:
    if isinstance(x, (bytes, bytearray)):
        return x.decode()
    return x


def json_dumps_safe(obj: Any) -> str:
    """
    Safe JSON dump for event/task payloads (handles bytes).
    """
    def default(o: Any) -> Any:
        if isinstance(o, (bytes, bytearray)):
            return o.decode()
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
    return json.dumps(obj, default=default)


async def ensure_consumer_group(r: redis.Redis) -> None:
    """
    Ensure consumer group exists on runnable stream for workers.
    Scheduler doesn't consume runnable, but creating it here is convenient for dev.
    """
    try:
        await r.xgroup_create(
            name=RUNNABLE_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        print(f"[scheduler] created consumer group '{CONSUMER_GROUP}' on '{RUNNABLE_STREAM}'")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            # already exists
            return
        raise


async def publish_event(
    r: redis.Redis,
    mission_id: str,
    task_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
) -> str:
    safe_data = {k: to_str(v) for k, v in (data or {}).items()}
    fields = {
        "mission_id": mission_id,
        "task_id": task_id,
        "event_type": event_type,
        "ts_ms": str(now_ms()),
        "data": json_dumps_safe(safe_data),
        "emitter": SCHEDULER_NAME,
    }
    return await r.xadd(EVENTS_STREAM, fields)


# -----------------------------
# Scheduler state
# -----------------------------

@dataclass
class SchedulerState:
    dag: MissionDAG
    # Track task statuses locally
    status_by_task_id: Dict[str, TaskStatus] = field(default_factory=dict)

    # Store outputs from TASK_SUCCEEDED
    outputs_by_task_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Temporary: map instance_id -> final_report (whatever worker emits)
    instance_final_report_cache: Dict[str, Any] = field(default_factory=dict)

    # Failures
    failures_by_task_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # For debug summaries
    enqueued_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0

    def __post_init__(self) -> None:
        # default status
        for tid in self.dag.tasks.keys():
            self.status_by_task_id.setdefault(tid, TaskStatus.PENDING)

        # mark initial ready as READY (not yet enqueued)
        for tid in self.dag.initial_ready:
            self.status_by_task_id[tid] = TaskStatus.READY

    def mission_state_summary(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for st in self.status_by_task_id.values():
            counts[st.value] = counts.get(st.value, 0) + 1

        return {
            "mission_id": self.dag.mission_id,
            "counts": counts,
            "enqueued_count": self.enqueued_count,
            "succeeded_count": self.succeeded_count,
            "failed_count": self.failed_count,
            "remaining_blocked": sum(1 for v in self.dag.deps_remaining.values() if v > 0),
        }


# -----------------------------
# Enqueue logic
# -----------------------------

def _build_runnable_payload(
    task: TaskDefinition,
    *,
    include_full_instance_plan: bool,
    instance_plans_by_id: Dict[str, Any],
    upstream_final_reports: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Turn a TaskDefinition into Redis stream fields.

    We always include:
      - mission_id, task_id, task_type, task_key, attempt
      - inputs (JSON string)

    For INSTANCE_RUN tasks, optionally include the full instance plan JSON (prototype convenience).
    Also optionally include upstream_final_reports (temporary dependency injection).
    """
    base = {
        "mission_id": task.mission_id,
        "task_id": task.task_id,
        "task_type": task.task_type.value,
        "task_key": task.task_key,
        "attempt": "1",
    }

    inputs: Dict[str, Any] = dict(task.inputs or {})
    if task.task_type == TaskType.INSTANCE_RUN and include_full_instance_plan:
        instance_id = inputs.get("instance_id")
        if instance_id and instance_id in instance_plans_by_id:
            inputs["instance_plan"] = instance_plans_by_id[instance_id]

    if upstream_final_reports:
        inputs["upstream_final_reports"] = upstream_final_reports

    base["inputs_json"] = json_dumps_safe(inputs)
    return base


async def enqueue_task(
    r: redis.Redis,
    state: SchedulerState,
    task_id: str,
    *,
    include_full_instance_plan: bool,
    instance_plans_by_id: Dict[str, Any],
) -> None:
    """
    Enqueue a READY task exactly once.
    """
    status = state.status_by_task_id.get(task_id, TaskStatus.PENDING)
    if status not in (TaskStatus.READY,):
        return

    task = state.dag.tasks[task_id]

    # Temporary dependency injection:
    # If this INSTANCE_RUN depends on upstream instance outputs, attach whatever we have.
    upstream_reports: Dict[str, Any] = {}
    if task.task_type == TaskType.INSTANCE_RUN:
        # Look at parents in DAG to find upstream instance tasks, and attach their cached final_reports if present.
        for parent_id in state.dag.parents.get(task_id, []):
            parent_task = state.dag.tasks[parent_id]
            if parent_task.task_type == TaskType.INSTANCE_RUN:
                inst_id = parent_task.inputs.get("instance_id")
                if inst_id and inst_id in state.instance_final_report_cache:
                    upstream_reports[inst_id] = state.instance_final_report_cache[inst_id]

    payload = _build_runnable_payload(
        task,
        include_full_instance_plan=include_full_instance_plan,
        instance_plans_by_id=instance_plans_by_id,
        upstream_final_reports=upstream_reports if upstream_reports else None,
    )

    msg_id = await r.xadd(RUNNABLE_STREAM, payload)
    state.status_by_task_id[task_id] = TaskStatus.RUNNING  # "enqueued/running" for now
    state.enqueued_count += 1

    await publish_event(
        r,
        mission_id=task.mission_id,
        task_id=task.task_id,
        event_type="TASK_ENQUEUED",
        data={"redis_message_id": to_str(msg_id), "task_type": task.task_type.value},
    )

    print(f"[scheduler] ➕ enqueued {task.task_type.value} {task.task_key} msg={to_str(msg_id)}")


# -----------------------------
# Event handling / unlock logic
# -----------------------------

def _parse_event_fields(fields: Dict[bytes, bytes]) -> Dict[str, Any]:
    decoded = {k.decode(): v.decode() for k, v in fields.items()}
    data_raw = decoded.get("data") or "{}"
    try:
        data = json.loads(data_raw)
    except Exception:
        data = {"_raw": data_raw}

    return {
        "mission_id": decoded.get("mission_id"),
        "task_id": decoded.get("task_id"),
        "event_type": decoded.get("event_type"),
        "ts_ms": decoded.get("ts_ms"),
        "data": data,
        "emitter": decoded.get("emitter"),
    }


def _unlock_dependents(state: SchedulerState, completed_task_id: str) -> List[str]:
    """
    Decrement deps_remaining for children. Return list of newly READY task_ids.
    """
    newly_ready: List[str] = []
    for child_id in state.dag.dependents.get(completed_task_id, []):
        state.dag.deps_remaining[child_id] = max(0, state.dag.deps_remaining.get(child_id, 0) - 1)
        if state.dag.deps_remaining[child_id] == 0:
            # Only mark READY if not already succeeded/failed/running
            if state.status_by_task_id.get(child_id) in (TaskStatus.PENDING,):
                state.status_by_task_id[child_id] = TaskStatus.READY
                newly_ready.append(child_id)
    return newly_ready


def _extract_instance_final_report_if_present(
    state: SchedulerState,
    task: TaskDefinition,
    output_payload: Dict[str, Any],
) -> None:
    """
    Temporary: if this task is INSTANCE_RUN and emits a 'final_report' field,
    cache it by instance_id for downstream injection.
    """
    if task.task_type != TaskType.INSTANCE_RUN:
        return

    instance_id = task.inputs.get("instance_id")
    if not instance_id:
        return

    # Worker should include something like {"final_report": <FileReference dict or text>}
    if "final_report" in output_payload:
        state.instance_final_report_cache[instance_id] = output_payload["final_report"]


# -----------------------------
# Main scheduler loop
# -----------------------------

async def run_scheduler(
    plan: ResearchMissionPlanFinal,
    *,
    include_full_instance_plan: bool = True,
) -> None:
    r = redis.from_url(REDIS_URL, decode_responses=False)
    await ensure_consumer_group(r)

    dag = build_mission_dag(plan)
    print(format_dag_summary(dag))

    # Build a dict of instance_id -> JSON-able dict (for prototype convenience)
    instance_plans_by_id: Dict[str, Any] = {inst.instance_id: inst.model_dump() for inst in plan.agent_instances}

    state = SchedulerState(dag=dag)

    # Enqueue initial ready tasks
    for tid in dag.initial_ready:
        await enqueue_task(
            r,
            state,
            tid,
            include_full_instance_plan=include_full_instance_plan,
            instance_plans_by_id=instance_plans_by_id,
        )

    # Tail mission events
    last_event_id = "$"  # only new events
    last_status_print = time.time()

    print(f"[scheduler] listening to events stream='{EVENTS_STREAM}' starting from '$' ...")

    try:
        while True:
            # Print summary periodically
            if time.time() - last_status_print >= STATUS_PRINT_EVERY_S:
                summary = state.mission_state_summary()
                print(f"[scheduler] summary: {summary}")
                last_status_print = time.time()

                # Exit condition: all tasks succeeded or failed (no pending/ready/running)
                counts = summary["counts"]
                active = counts.get(TaskStatus.PENDING.value, 0) + counts.get(TaskStatus.READY.value, 0) + counts.get(TaskStatus.RUNNING.value, 0)
                if active == 0:
                    print("[scheduler] ✅ mission finished (no active tasks).")
                    break

            resp = await r.xread(
                streams={EVENTS_STREAM: last_event_id},
                count=XREAD_COUNT,
                block=XREAD_BLOCK_MS,
            )
            if not resp:
                continue

            for _stream_name, messages in resp:
                for msg_id, fields in messages:
                    last_event_id = msg_id
                    ev = _parse_event_fields(fields)

                    if ev.get("mission_id") != plan.mission_id:
                        # ignore other missions on shared stream
                        continue

                    task_id = ev.get("task_id")
                    event_type = ev.get("event_type")
                    data = ev.get("data") or {}

                    if not task_id or task_id not in state.dag.tasks:
                        continue

                    task = state.dag.tasks[task_id]

                    if event_type == "TASK_SUCCEEDED":
                        state.status_by_task_id[task_id] = TaskStatus.SUCCEEDED
                        state.outputs_by_task_id[task_id] = data
                        state.succeeded_count += 1

                        _extract_instance_final_report_if_present(state, task, data)

                        newly_ready = _unlock_dependents(state, task_id)
                        if newly_ready:
                            for child_id in newly_ready:
                                await enqueue_task(
                                    r,
                                    state,
                                    child_id,
                                    include_full_instance_plan=include_full_instance_plan,
                                    instance_plans_by_id=instance_plans_by_id,
                                )

                        print(f"[scheduler] ✅ succeeded {task.task_type.value} {task.task_key}")

                    elif event_type == "TASK_FAILED":
                        state.status_by_task_id[task_id] = TaskStatus.FAILED
                        state.failures_by_task_id[task_id] = data
                        state.failed_count += 1

                        print(f"[scheduler] ❌ failed {task.task_type.value} {task.task_key} data={data}")

                    else:
                        # Ignore other events for scheduling, but you still get them in stream.
                        # Useful for UI.
                        continue

    finally:
        await r.aclose()


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="In-memory mission scheduler (Redis Streams)")
    parser.add_argument("--plan-json-path", type=str, default=None, help="Path to a mission plan JSON file")
    parser.add_argument("--include-full-instance-plan", action="store_true", default=True, help="Include full instance_plan in runnable inputs_json (prototype convenience)")
    args = parser.parse_args()

    if not args.plan_json_path:
        raise SystemExit("Provide --plan-json-path to a ResearchMissionPlanFinal JSON file")

    plan_dict = json.loads(open(args.plan_json_path, "r", encoding="utf-8").read())
    plan = ResearchMissionPlanFinal.model_validate(plan_dict)

    asyncio.run(run_scheduler(plan, include_full_instance_plan=args.include_full_instance_plan))


if __name__ == "__main__":
    main()