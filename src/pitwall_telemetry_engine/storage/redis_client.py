import logging
import os
import redis.asyncio as aioredis
from pitwall_telemetry_engine.schemas.car_data import CarData

logger = logging.getLogger(__name__)

DEFAULT_STREAM_KEY = "f1:telemetry:raw"
DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


class RedisTelemetryBuffer:
    """High-throughput asynchronous Redis 7 Streams message buffer."""

    def __init__(self, redis_url: str = DEFAULT_REDIS_URL, maxlen: int = 5000) -> None:
        self.redis_url = redis_url
        self.maxlen = maxlen
        self.client: aioredis.Redis | None = None

    async def connect(self) -> bool:
        """Initializes the async Redis client connection and tests via ping()."""
        try:
            self.client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
            )
            await self.client.ping()
            print(f"🗄️  Connected to Redis Stream Buffer at {self.redis_url}")
            return True
        except Exception as e:
            print(f"⚠️  [REDIS NOTICE] Redis offline at {self.redis_url} ({e}). Engine running in standalone mode.")
            self.client = None
            return False

    async def publish_tick(
        self,
        tick: CarData,
        stream_key: str = DEFAULT_STREAM_KEY,
    ) -> str | None:
        """
        Publishes a CarData telemetry tick to the Redis Stream (XADD)
        with an approximate sliding window (MAXLEN ~ 5000).
        """
        if not self.client:
            return None

        payload = {
            "driver_number": str(tick.driver_number),
            "speed": str(tick.speed),
            "throttle": str(tick.throttle),
            "brake": str(tick.brake),
            "gear": str(tick.n_gear),
            "rpm": str(tick.rpm),
            "drs": str(tick.drs) if tick.drs is not None else "",
            "date": tick.date.isoformat(),
        }

        try:
            # XADD f1:telemetry:raw MAXLEN ~ 5000 * field value ...
            msg_id = await self.client.xadd(
                name=stream_key,
                fields=payload,
                maxlen=self.maxlen,
                approximate=True,
            )
            return msg_id
        except Exception as e:
            logger.warning(f"Failed to publish tick to Redis stream {stream_key}: {e}")
            return None

    async def read_ticks(
        self,
        stream_key: str = DEFAULT_STREAM_KEY,
        last_id: str = "0-0",
        count: int = 10,
    ) -> list[tuple[str, dict]]:
        """
        Reads a batch of entries from the Redis Stream using XREAD.
        Returns a list of (msg_id, fields_dict).
        """
        if not self.client:
            return []

        try:
            # XREAD COUNT count STREAMS stream_key last_id
            response = await self.client.xread(
                streams={stream_key: last_id},
                count=count,
            )
            if not response:
                return []

            # response format: [[stream_name, [(msg_id, fields), ...]]]
            _, messages = response[0]
            return messages
        except Exception as e:
            logger.warning(f"Failed to read from Redis stream {stream_key}: {e}")
            return []

    async def close(self) -> None:
        """Gracefully closes the Redis connection."""
        if self.client:
            await self.client.aclose()
            self.client = None