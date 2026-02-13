from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import traceback
from typing import Any, Dict, Optional, Tuple

import redis.asyncio as redis
from langchain_core.runnables import RunnableConfig

from research_agent.human_upgrade.structured_outputs.research_plans_outputs import (
    AgentInstancePlanWithSources,
)
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference

from research_agent.human_upgrade.utils.research_tools_map import RESEARCH_TOOLS_MAP
from research_agent.human_upgrade.utils.default_tools_by_agent_type import (
    FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP,
)

from research_agent.human_upgrade.tools.utils.agent_workspace_root_helpers import workspace_for, workspace_root_for
from research_agent.human_upgrade.graphs.agent_instance_factory import (
    build_worker_agent,
    run_worker_once,
)

# If these output types exist and are importable, we’ll use them for reduce:
try:
    from research_agent.human_upgrade.graphs.outputs.agent_instance_output import AgentInstanceOutput
    from research_agent.human_upgrade.graphs.outputs.substage_output import SubStageOutput
except Exception:  # pragma: no cover
    AgentInstanceOutput = None  # type: ignore
    SubStageOutput = None  # type: ignore


# -----------------------------
# Redis configuration
# -----------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RUNNABLE_STREAM = os.getenv("RUNNABLE_STREAM", "mission:runnable")
EVENTS_STREAM = os.getenv("EVENTS_STREAM", "mission:events")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "workers")

WORKER_NAME = os.getenv("WORKER_NAME", f"worker-{socket.gethostname()}-{os.getpid()}")

XREAD_BLOCK_MS = int(os.getenv("XREAD_BLOCK_MS", "5000"))
XREAD_COUNT = int(os.getenv("XREAD_COUNT", "10"))

# Max concurrent tasks per worker process (simple)
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "3"))


def now_ms() -> int:
    return int(time.time() * 1000)


def to_str(x: Any) -> Any:
    if isinstance(x, (bytes, bytearray)):
        return x.decode()
    return x


def json_dumps_safe(obj: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, (bytes, bytearray)):
            return o.decode()
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
    return json.dumps(obj, default=default)


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
        "emitter": WORKER_NAME,
    }
    return await r.xadd(EVENTS_STREAM, fields)


async def ensure_consumer_group(r: redis.Redis) -> None:
    """
    Ensure group exists for workers on runnable stream.
    """
    try:
        await r.xgroup_create(
            name=RUNNABLE_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        print(f"[worker] created consumer group '{CONSUMER_GROUP}' on '{RUNNABLE_STREAM}'")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            return
        raise


# -----------------------------
# Tool selection helpers
# -----------------------------

def _select_tools(tool_names: list[str]) -> list[Any]:
    tools: list[Any] = []
    for name in tool_names:
        tool = RESEARCH_TOOLS_MAP.get(name)
        if tool is not None:
            tools.append(tool)
    return tools


def tools_for_agent_type(tool_map: dict[str, list[str]], agent_type: str) -> list[Any]:
    tool_names = tool_map.get(agent_type, []) or []
    return _select_tools(tool_names)


# -----------------------------
# Message parsing
# -----------------------------

def _decode_fields(fields: Dict[bytes, bytes]) -> Dict[str, Any]:
    decoded = {k.decode(): v.decode() for k, v in fields.items()}
    inputs_raw = decoded.get("inputs_json") or "{}"
    try:
        inputs = json.loads(inputs_raw)
    except Exception:
        inputs = {"_raw": inputs_raw}

    decoded["inputs"] = inputs
    return decoded


# -----------------------------
# Task handlers
# -----------------------------

async def handle_instance_run(
    r: redis.Redis,
    *,
    mission_id: str,
    task_id: str,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Runs one AgentInstancePlanWithSources through your real sub-agent factory.

    Inputs expected (from scheduler):
      - instance_plan: dict (AgentInstancePlanWithSources.model_dump())
      - stage_id, sub_stage_id, agent_type, instance_id (may be redundant)
      - upstream_final_reports: optional dict[instance_id -> (FileReference dict or text)]
    """
    if "instance_plan" not in inputs:
        raise ValueError("INSTANCE_RUN requires inputs['instance_plan'] (full instance plan dict)")

    inst = AgentInstancePlanWithSources.model_validate(inputs["instance_plan"])
    agent_type = inst.agent_type

    stage_id = inst.stage_id
    sub_stage_id = inst.sub_stage_id

    upstream_final_reports = inputs.get("upstream_final_reports") or {}

    # Workspace: use relative path string for state (prevents path duplication)
    # Use sub_stage_id as both id+name segment (we don't have substage_name in this message yet)
    workspace_root = workspace_root_for(
        mission_id,
        stage_id,
        f"{sub_stage_id}",
        f"{inst.agent_type}_{inst.instance_id}",
    )

    tools = tools_for_agent_type(FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP, inst.agent_type)

    agent_graph = build_worker_agent(
        tools=tools,
        agent_type=agent_type,
        # model defaults inside factory
        store=None,
        checkpointer=None,
    )

    # RunnableConfig thread_id helps isolate langgraph checkpoints
    cfg: RunnableConfig = {
        "configurable": {
            "thread_id": f"task__{task_id}",
            "mission_id": mission_id,
            "stage_id": stage_id,
            "sub_stage_id": sub_stage_id,
            "instance_id": inst.instance_id,
        }
    }

    # ---------
    # TEMP injection WITHOUT sub-agent factory changes:
    # We can’t change dynamic prompts easily right now, but we *can* put this into plan.notes
    # and into seed_context via the existing run_worker_once.
    #
    # We’ll append a short, bounded prefix to inst.notes for now.
    # Later: this becomes artifact plumbing + structured inputs.
    # ---------
    if upstream_final_reports:
        injected = json_dumps_safe(upstream_final_reports)
        prefix = (
            "\n\n[UPSTREAM_FINAL_REPORTS_INJECTED]\n"
            "You may use these upstream synthesized reports as context:\n"
            f"{injected}\n"
            "[/UPSTREAM_FINAL_REPORTS_INJECTED]\n"
        )
        inst.notes = (inst.notes or "") + prefix

    out = await run_worker_once(
        agent_graph=agent_graph,
        agent_instance_plan=inst,
        workspace_root=workspace_root,
        agent_type=agent_type,
        mission_id=mission_id,
        stage_id=stage_id,
        substage_id=sub_stage_id,
        substage_name="",  # optional
        config=cfg,
    )

    # Pull outputs (your after_agent writes final_report FileReference)
    final_report = out.get("final_report", None)
    file_refs = out.get("file_refs", []) or []

    # Normalize FileReference if it’s a pydantic object
    if hasattr(final_report, "model_dump"):
        final_report_payload = final_report.model_dump()
    else:
        final_report_payload = final_report

    normalized_file_refs = []
    for fr in file_refs:
        if hasattr(fr, "model_dump"):
            normalized_file_refs.append(fr.model_dump())
        else:
            normalized_file_refs.append(fr)

    return {
        "instance_id": inst.instance_id,
        "agent_type": inst.agent_type,
        "stage_id": stage_id,
        "sub_stage_id": sub_stage_id,
        "workspace_root": workspace_root,
        "final_report": final_report_payload,
        "file_refs": normalized_file_refs,
    }


async def handle_substage_reduce(
    r: redis.Redis,
    *,
    mission_id: str,
    task_id: str,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Simple reduce for now:
    - If scheduler included instance_outputs in inputs, use it.
    - Otherwise emit a minimal record listing instance_ids and mark missing_outputs=True.

    Inputs expected:
      - stage_id
      - sub_stage_id
      - instance_ids: list[str]
      - instance_outputs: optional dict (instance_id -> {final_report, file_refs, workspace_root...})
    """
    stage_id = inputs.get("stage_id")
    sub_stage_id = inputs.get("sub_stage_id")
    instance_ids = inputs.get("instance_ids") or []
    instance_outputs = inputs.get("instance_outputs")  # optional

    if instance_outputs is None:
        # Minimal placeholder output (scheduler can still unlock stage reduce later)
        return {
            "stage_id": stage_id,
            "sub_stage_id": sub_stage_id,
            "instance_ids": instance_ids,
            "missing_outputs": True,
            "notes": "SUBSTAGE_REDUCE ran without instance_outputs attached. Add in scheduler or switch to Mongo-backed fetch.",
        }

    # If your real SubStageOutput model is available, use it
    if SubStageOutput is not None and AgentInstanceOutput is not None:
        # Convert dict payloads back into AgentInstanceOutput if possible
        inst_out_objs = {}
        for iid, payload in instance_outputs.items():
            inst_out_objs[iid] = AgentInstanceOutput(
                instance_id=iid,
                agent_type=payload.get("agent_type"),
                final_report=payload.get("final_report"),
                file_refs=payload.get("file_refs", []),
                workspace_root=payload.get("workspace_root"),
            )

        substage_output = SubStageOutput(
            substage_id=sub_stage_id,
            substage_name=str(sub_stage_id),
            instance_ids=list(inst_out_objs.keys()),
            instance_outputs=inst_out_objs,
        )
        return {"substage_output": substage_output.model_dump()}

    # Otherwise: raw dict output
    return {
        "stage_id": stage_id,
        "sub_stage_id": sub_stage_id,
        "instance_ids": instance_ids,
        "instance_outputs": instance_outputs,
        "missing_outputs": False,
    }


# -----------------------------
# Router
# -----------------------------

async def run_one_task(
    r: redis.Redis,
    *,
    mission_id: str,
    task_id: str,
    task_type: str,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    # Normalize task_type (strip whitespace, handle case)
    task_type = task_type.strip() if task_type else ""
    
    print(f"[worker] run_one_task: task_type='{task_type}' task_id='{task_id}'")
    
    if task_type == "INSTANCE_RUN":
        return await handle_instance_run(r, mission_id=mission_id, task_id=task_id, inputs=inputs)
    if task_type == "SUBSTAGE_REDUCE":
        return await handle_substage_reduce(r, mission_id=mission_id, task_id=task_id, inputs=inputs)

    raise ValueError(f"Unsupported task_type='{task_type}' (received type: {type(task_type).__name__}, repr: {repr(task_type)})")


# -----------------------------
# Worker loop
# -----------------------------

async def worker_loop() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=False)
    await ensure_consumer_group(r)

    sem = asyncio.Semaphore(WORKER_CONCURRENCY)

    print(
        f"[worker] starting name={WORKER_NAME} "
        f"stream={RUNNABLE_STREAM} group={CONSUMER_GROUP} concurrency={WORKER_CONCURRENCY}"
    )

    async def _handle_message(msg_id: str, fields: Dict[bytes, bytes]) -> None:
        decoded = _decode_fields(fields)

        mission_id = decoded.get("mission_id")
        task_id = decoded.get("task_id")
        task_type = decoded.get("task_type")
        task_key = decoded.get("task_key")
        inputs = decoded.get("inputs") or {}

        if not (mission_id and task_id and task_type):
            # malformed
            await r.xack(RUNNABLE_STREAM, CONSUMER_GROUP, msg_id)
            return

        async with sem:
            await publish_event(r, mission_id, task_id, "TASK_STARTED", {"task_type": task_type, "task_key": task_key})
            start_time = time.time()

            try:
                # Add timeout for task execution (30 minutes default)
                task_timeout = int(os.getenv("TASK_TIMEOUT_SECONDS", "1800"))
                out_payload = await asyncio.wait_for(
                    run_one_task(
                        r,
                        mission_id=mission_id,
                        task_id=task_id,
                        task_type=task_type,
                        inputs=inputs,
                    ),
                    timeout=task_timeout,
                )
                elapsed = time.time() - start_time
                await publish_event(r, mission_id, task_id, "TASK_SUCCEEDED", out_payload)
                await r.xack(RUNNABLE_STREAM, CONSUMER_GROUP, msg_id)
                print(f"[worker] ✅ {task_type} {task_key} msg={msg_id} elapsed={elapsed:.1f}s")

            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                error_msg = f"Task timed out after {elapsed:.1f}s (limit: {task_timeout}s)"
                await publish_event(
                    r,
                    mission_id,
                    task_id,
                    "TASK_FAILED",
                    {"error": error_msg, "task_type": task_type, "task_key": task_key, "timeout": True},
                )
                await r.xack(RUNNABLE_STREAM, CONSUMER_GROUP, msg_id)
                print(f"[worker] ⏱️  TIMEOUT {task_type} {task_key} msg={msg_id} elapsed={elapsed:.1f}s")

            except Exception as e:
                elapsed = time.time() - start_time
                error_details = {
                    "error": repr(e),
                    "error_type": type(e).__name__,
                    "task_type": task_type,
                    "task_key": task_key,
                    "elapsed_seconds": elapsed,
                    "traceback": traceback.format_exc(),
                }
                await publish_event(
                    r,
                    mission_id,
                    task_id,
                    "TASK_FAILED",
                    error_details,
                )
                # Ack or not?
                # For prototype: ACK so it doesn't poison the group.
                # Later: move to DLQ stream or keep pending for retry.
                await r.xack(RUNNABLE_STREAM, CONSUMER_GROUP, msg_id)
                print(f"[worker] ❌ {task_type} {task_key} msg={msg_id} error={e!r} elapsed={elapsed:.1f}s")
                print(f"[worker] Traceback: {traceback.format_exc()}")

    try:
        while True:
            resp = await r.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=WORKER_NAME,
                streams={RUNNABLE_STREAM: ">"},
                count=XREAD_COUNT,
                block=XREAD_BLOCK_MS,
            )
            if not resp:
                continue

            # resp: [(stream_name, [(id, fields), ...])]
            for _stream_name, messages in resp:
                for msg_id_bytes, fields in messages:
                    msg_id = to_str(msg_id_bytes)
                    # fire-and-forget each message (bounded by semaphore)
                    asyncio.create_task(_handle_message(msg_id, fields))

    finally:
        await r.aclose()


def main() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
