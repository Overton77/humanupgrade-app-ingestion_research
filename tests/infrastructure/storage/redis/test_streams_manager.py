"""
Tests for Redis Streams Manager with entity discovery events.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from research_agent.infrastructure.storage.redis.streams_manager import (
    RedisStreamsManager,
    StreamAddress,
    StreamEvent,
    EventRouter,
)
from research_agent.infrastructure.storage.redis.event_registry import (
    create_event_router,
    GROUP_GRAPH,
    CHANNEL_ENTITY_DISCOVERY,
    EVENT_TYPE_START,
    EVENT_TYPE_COMPLETE,
    EVENT_TYPE_ERROR,
)
from research_agent.infrastructure.storage.redis.entity_candidate_run_events import (
    EntityCandidateRunStart,
    EntityCandidateRunComplete,
    EntityCandidateRunError,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock(return_value="1234567890-0")
    redis_mock.expire = AsyncMock()
    redis_mock.xread = AsyncMock(return_value=[])
    return redis_mock


@pytest.fixture
def event_router():
    """Create an event router with registered events."""
    return create_event_router()


@pytest.fixture
def streams_manager(mock_redis, event_router):
    """Create a streams manager with mock Redis."""
    return RedisStreamsManager(
        mock_redis,
        router=event_router,
        ttl_seconds=86400,
        maxlen=2000,
    )


@pytest.fixture
def stream_addr():
    """Create a stream address for testing."""
    return StreamAddress(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        key="test-run-id-123",
    )


class TestStreamAddress:
    """Test StreamAddress functionality."""
    
    def test_stream_name_format(self, stream_addr):
        """Test that stream name is formatted correctly."""
        expected = "graph:entity_discovery:test-run-id-123"
        assert stream_addr.stream_name() == expected
    
    def test_stream_address_immutable(self, stream_addr):
        """Test that StreamAddress is frozen/immutable."""
        with pytest.raises(Exception):  # dataclass frozen=True raises FrozenInstanceError
            stream_addr.group = "new_group"


class TestEventRouter:
    """Test EventRouter registration and resolution."""
    
    def test_router_registers_all_events(self, event_router):
        """Test that all entity discovery events are registered."""
        # Create test events
        start_event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_START,
            data={},
        )
        
        complete_event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_COMPLETE,
            data={},
        )
        
        error_event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_ERROR,
            data={},
        )
        
        # Verify all events can be resolved
        assert event_router.resolve(start_event) is not None
        assert event_router.resolve(complete_event) is not None
        assert event_router.resolve(error_event) is not None
    
    def test_router_resolves_correct_model(self, event_router):
        """Test that router resolves to correct data model."""
        start_event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_START,
            data={},
        )
        
        spec = event_router.resolve(start_event)
        assert spec.data_model == EntityCandidateRunStart
    
    def test_router_returns_none_for_unknown_event(self, event_router):
        """Test that unknown events return None."""
        unknown_event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group="unknown_group",
            channel="unknown_channel",
            key="test-run-id",
            event_type="unknown_type",
            data={},
        )
        
        assert event_router.resolve(unknown_event) is None
    
    def test_add_handler_to_event(self, event_router):
        """Test adding a handler to an existing event."""
        async def test_handler(event: StreamEvent):
            pass
        
        event_router.add_handler(
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            event_type=EVENT_TYPE_START,
            handler=test_handler,
        )
        
        start_event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_START,
            data={},
        )
        
        spec = event_router.resolve(start_event)
        assert len(spec.handlers) == 1
        assert spec.handlers[0] == test_handler


class TestStreamsManagerPublish:
    """Test publishing events with the streams manager."""
    
    @pytest.mark.asyncio
    async def test_publish_start_event(self, streams_manager, stream_addr, mock_redis):
        """Test publishing a start event."""
        data = {
            "query": "test query",
            "thread_id": "thread-123",
            "checkpoint_ns": "ns-123",
        }
        
        msg_id = await streams_manager.publish(
            stream_addr,
            event_type=EVENT_TYPE_START,
            data=data,
        )
        
        # Verify Redis was called correctly
        assert msg_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        
        # Verify stream name
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "graph:entity_discovery:test-run-id-123"
        
        # Verify payload structure
        payload_json = call_args[0][1]["payload"]
        payload = json.loads(payload_json)
        
        assert payload["group"] == GROUP_GRAPH
        assert payload["channel"] == CHANNEL_ENTITY_DISCOVERY
        assert payload["event_type"] == EVENT_TYPE_START
        assert payload["data"] == data
        
        # Verify TTL was set
        mock_redis.expire.assert_called_once_with(
            "graph:entity_discovery:test-run-id-123",
            86400,
        )
    
    @pytest.mark.asyncio
    async def test_publish_complete_event(self, streams_manager, stream_addr, mock_redis):
        """Test publishing a complete event."""
        data = {
            "intel_run_id": "intel-123",
            "pipeline_version": "v1",
            "has_candidates": True,
        }
        
        msg_id = await streams_manager.publish(
            stream_addr,
            event_type=EVENT_TYPE_COMPLETE,
            data=data,
        )
        
        assert msg_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        
        # Verify payload
        call_args = mock_redis.xadd.call_args
        payload_json = call_args[0][1]["payload"]
        payload = json.loads(payload_json)
        
        assert payload["event_type"] == EVENT_TYPE_COMPLETE
        assert payload["data"] == data
    
    @pytest.mark.asyncio
    async def test_publish_error_event(self, streams_manager, stream_addr, mock_redis):
        """Test publishing an error event."""
        data = {
            "error": "Something went wrong",
            "error_type": "ValueError",
        }
        
        msg_id = await streams_manager.publish(
            stream_addr,
            event_type=EVENT_TYPE_ERROR,
            data=data,
        )
        
        assert msg_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        
        # Verify payload
        call_args = mock_redis.xadd.call_args
        payload_json = call_args[0][1]["payload"]
        payload = json.loads(payload_json)
        
        assert payload["event_type"] == EVENT_TYPE_ERROR
        assert payload["data"] == data


class TestStreamsManagerRead:
    """Test reading events with the streams manager."""
    
    @pytest.mark.asyncio
    async def test_read_events(self, streams_manager, stream_addr, mock_redis):
        """Test reading events from a stream."""
        # Mock Redis XREAD response
        mock_redis.xread.return_value = [
            (
                "graph:entity_discovery:test-run-id-123",
                [
                    (
                        "1234567890-0",
                        {
                            "payload": json.dumps({
                                "v": 1,
                                "ts": 1234567890.0,
                                "group": GROUP_GRAPH,
                                "channel": CHANNEL_ENTITY_DISCOVERY,
                                "key": "test-run-id-123",
                                "event_type": EVENT_TYPE_START,
                                "data": {
                                    "query": "test query",
                                    "thread_id": "thread-123",
                                    "checkpoint_ns": "ns-123",
                                },
                                "meta": {},
                            }),
                        },
                    ),
                ],
            ),
        ]
        
        events = await streams_manager.read(
            stream_addr,
            last_id="0",
            block_ms=5000,
            count=100,
        )
        
        assert len(events) == 1
        event = events[0]
        
        assert event.id == "1234567890-0"
        assert event.group == GROUP_GRAPH
        assert event.channel == CHANNEL_ENTITY_DISCOVERY
        assert event.event_type == EVENT_TYPE_START
        assert event.data["query"] == "test query"
    
    @pytest.mark.asyncio
    async def test_read_no_events(self, streams_manager, stream_addr, mock_redis):
        """Test reading when no events are available."""
        mock_redis.xread.return_value = []
        
        events = await streams_manager.read(
            stream_addr,
            last_id="0",
            block_ms=5000,
            count=100,
        )
        
        assert len(events) == 0


class TestStreamsManagerDispatch:
    """Test event dispatching and validation."""
    
    @pytest.mark.asyncio
    async def test_dispatch_validates_start_event(self, streams_manager):
        """Test that dispatching validates data against EntityCandidateRunStart."""
        event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_START,
            data={
                "query": "test query",
                "thread_id": "thread-123",
                "checkpoint_ns": "ns-123",
            },
        )
        
        # Should not raise any validation errors
        await streams_manager.dispatch(event)
    
    @pytest.mark.asyncio
    async def test_dispatch_validates_complete_event(self, streams_manager):
        """Test that dispatching validates data against EntityCandidateRunComplete."""
        event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_COMPLETE,
            data={
                "intel_run_id": "intel-123",
                "pipeline_version": "v1",
                "has_candidates": True,
            },
        )
        
        # Should not raise any validation errors
        await streams_manager.dispatch(event)
    
    @pytest.mark.asyncio
    async def test_dispatch_validates_error_event(self, streams_manager):
        """Test that dispatching validates data against EntityCandidateRunError."""
        event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_ERROR,
            data={
                "error": "Something went wrong",
                "error_type": "ValueError",
            },
        )
        
        # Should not raise any validation errors
        await streams_manager.dispatch(event)
    
    @pytest.mark.asyncio
    async def test_dispatch_fails_invalid_data(self, streams_manager):
        """Test that dispatching fails with invalid data."""
        event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_START,
            data={
                # Missing required fields
                "query": "test query",
                # Missing thread_id and checkpoint_ns
            },
        )
        
        # Should raise validation error
        with pytest.raises(Exception):  # Pydantic validation error
            await streams_manager.dispatch(event)
    
    @pytest.mark.asyncio
    async def test_dispatch_calls_handlers(self, streams_manager, event_router):
        """Test that dispatching calls registered handlers."""
        handler_called = False
        handler_event = None
        
        async def test_handler(event: StreamEvent):
            nonlocal handler_called, handler_event
            handler_called = True
            handler_event = event
        
        # Add handler to router
        event_router.add_handler(
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            event_type=EVENT_TYPE_START,
            handler=test_handler,
        )
        
        event = StreamEvent(
            v=1,
            ts=1234567890.0,
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key="test-run-id",
            event_type=EVENT_TYPE_START,
            data={
                "query": "test query",
                "thread_id": "thread-123",
                "checkpoint_ns": "ns-123",
            },
        )
        
        await streams_manager.dispatch(event)
        
        assert handler_called is True
        assert handler_event == event


class TestStreamsManagerSubscribe:
    """Test subscribing to streams with auto-dispatch."""
    
    @pytest.mark.asyncio
    async def test_subscribe_stops_on_complete(self, streams_manager, stream_addr, mock_redis):
        """Test that subscribe stops when receiving a complete event."""
        # Mock Redis to return complete event
        mock_redis.xread.return_value = [
            (
                "graph:entity_discovery:test-run-id-123",
                [
                    (
                        "1234567890-0",
                        {
                            "payload": json.dumps({
                                "v": 1,
                                "ts": 1234567890.0,
                                "group": GROUP_GRAPH,
                                "channel": CHANNEL_ENTITY_DISCOVERY,
                                "key": "test-run-id-123",
                                "event_type": EVENT_TYPE_COMPLETE,
                                "data": {
                                    "intel_run_id": "intel-123",
                                    "pipeline_version": "v1",
                                    "has_candidates": True,
                                },
                                "meta": {},
                            }),
                        },
                    ),
                ],
            ),
        ]
        
        # Subscribe and stop on complete
        await streams_manager.subscribe(
            stream_addr,
            start_id="0",
            stop_on_event_types={EVENT_TYPE_COMPLETE, EVENT_TYPE_ERROR},
        )
        
        # Verify xread was called
        mock_redis.xread.assert_called()
    
    @pytest.mark.asyncio
    async def test_subscribe_stops_on_error(self, streams_manager, stream_addr, mock_redis):
        """Test that subscribe stops when receiving an error event."""
        # Mock Redis to return error event
        mock_redis.xread.return_value = [
            (
                "graph:entity_discovery:test-run-id-123",
                [
                    (
                        "1234567890-0",
                        {
                            "payload": json.dumps({
                                "v": 1,
                                "ts": 1234567890.0,
                                "group": GROUP_GRAPH,
                                "channel": CHANNEL_ENTITY_DISCOVERY,
                                "key": "test-run-id-123",
                                "event_type": EVENT_TYPE_ERROR,
                                "data": {
                                    "error": "Something went wrong",
                                    "error_type": "ValueError",
                                },
                                "meta": {},
                            }),
                        },
                    ),
                ],
            ),
        ]
        
        # Subscribe and stop on error
        await streams_manager.subscribe(
            stream_addr,
            start_id="0",
            stop_on_event_types={EVENT_TYPE_COMPLETE, EVENT_TYPE_ERROR},
        )
        
        # Verify xread was called
        mock_redis.xread.assert_called()
