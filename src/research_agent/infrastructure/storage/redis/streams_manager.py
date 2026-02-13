from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple, Type

import redis.asyncio as redis

try:
    from pydantic import BaseModel
except ImportError:  # if you don't want pydantic dependency here
    BaseModel = object  # type: ignore


ChannelGroup = str
ChannelType = str
StreamKey = str
EventType = str

Handler = Callable[["StreamEvent"], Awaitable[None]]


@dataclass(frozen=True)
class StreamAddress:
    group: ChannelGroup
    channel: ChannelType
    key: StreamKey

    def stream_name(self) -> str:
        return f"{self.group}:{self.channel}:{self.key}"


class StreamEvent(BaseModel):  # pydantic model (nice for validation/intellisense)
    v: int = 1
    ts: float
    group: str
    channel: str
    key: str
    event_type: str
    data: Dict[str, Any] = {}
    meta: Dict[str, Any] = {}

    # Redis metadata
    id: Optional[str] = None  # stream entry id


class EventSpec(BaseModel):
    """
    Declares how to validate & handle a specific event_type in a (group, channel).
    """
    data_model: Optional[Type[Any]] = None  # typically a pydantic model
    handlers: List[Handler] = []


class EventRouter:
    """
    Registry + routing:
      (group, channel, event_type) -> EventSpec
    """
    def __init__(self) -> None:
        self._specs: Dict[Tuple[str, str, str], EventSpec] = {}

    def register(
        self,
        *,
        group: str,
        channel: str,
        event_type: str,
        data_model: Optional[Type[Any]] = None,
        handlers: Optional[List[Handler]] = None,
    ) -> None:
        self._specs[(group, channel, event_type)] = EventSpec(
            data_model=data_model,
            handlers=handlers or [],
        )

    def add_handler(
        self,
        *,
        group: str,
        channel: str,
        event_type: str,
        handler: Handler,
    ) -> None:
        key = (group, channel, event_type)
        if key not in self._specs:
            self._specs[key] = EventSpec(data_model=None, handlers=[])
        self._specs[key].handlers.append(handler)

    def resolve(self, event: StreamEvent) -> Optional[EventSpec]:
        return self._specs.get((event.group, event.channel, event.event_type))


class RedisStreamsManager:
    def __init__(
        self,
        r: redis.Redis,
        *,
        router: EventRouter,
        ttl_seconds: int = 86400,
        maxlen: int = 2000,
    ) -> None:
        self.r = r
        self.router = router
        self.ttl_seconds = ttl_seconds
        self.maxlen = maxlen

    # -------------------------
    # Publish
    # -------------------------
    async def publish(
        self,
        addr: StreamAddress,
        *,
        event_type: str,
        data: Mapping[str, Any],
        meta: Optional[Mapping[str, Any]] = None,
        v: int = 1,
    ) -> str:
        payload = {
            "v": v,
            "ts": time.time(),
            "group": addr.group,
            "channel": addr.channel,
            "key": addr.key,
            "event_type": event_type,
            "data": dict(data),
            "meta": dict(meta or {}),
        }

        stream = addr.stream_name()
        msg_id = await self.r.xadd(
            stream,
            {"payload": json.dumps(payload, default=str)},
            maxlen=self.maxlen,
            approximate=True,
        )

        # sliding TTL is usually ok; change to "set only if no TTL" if you prefer
        await self.r.expire(stream, self.ttl_seconds)
        return msg_id

    # -------------------------
    # Read (pull)
    # -------------------------
    async def read(
        self,
        addr: StreamAddress,
        *,
        last_id: str = "0",
        block_ms: int = 5000,
        count: int = 100,
    ) -> List[StreamEvent]:
        stream = addr.stream_name()
        result = await self.r.xread({stream: last_id}, count=count, block=block_ms)
        if not result:
            return []

        events: List[StreamEvent] = []
        for _stream_name, msgs in result:
            for msg_id, fields in msgs:
                raw = fields.get("payload", "{}")
                payload = json.loads(raw)

                evt = StreamEvent(**payload, id=msg_id)
                events.append(evt)

        return events

    # -------------------------
    # Dispatch (validate + route)
    # -------------------------
    async def dispatch(self, event: StreamEvent) -> None:
        spec = self.router.resolve(event)
        if not spec:
            return  # unknown event_type => ignore (or log)

        # Validate/parse data if a model exists
        if spec.data_model is not None:
            # If it's a Pydantic model: instantiate it
            try:
                parsed = spec.data_model(**event.data)  # type: ignore[arg-type]
                # Replace dict with canonical data (optional)
                if hasattr(parsed, "model_dump"):
                    event.data = parsed.model_dump()
            except Exception:
                # If validation fails, you can re-route to an error handler
                # or raise; for now we raise (strict mode)
                raise

        # Fan-out to handlers (sequential; can be parallel if you want)
        for h in spec.handlers:
            await h(event)

    # -------------------------
    # Subscribe loop (tail + dispatch)
    # -------------------------
    async def subscribe(
        self,
        addr: StreamAddress,
        *,
        start_id: str = "0",   # "0" replay, "$" new only
        block_ms: int = 2000,
        count: int = 50,
        stop_on_event_types: Optional[set[str]] = None,
    ) -> None:
        last_id = start_id

        while True:
            events = await self.read(
                addr,
                last_id=last_id,
                block_ms=block_ms,
                count=count,
            )

            for evt in events:
                last_id = evt.id or last_id
                await self.dispatch(evt)

                if stop_on_event_types and evt.event_type in stop_on_event_types:
                    return


