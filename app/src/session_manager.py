# functions to manage storing and retrieving session data from Redis.
# for now keeping as functions, but could be refactored into a class later if needed.
import redis
import os

# Configure Redis connection pool (use service name 'redis' from Docker Compose)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Global connection pool
pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True,  # auto decode UTF-8 strings
)

# Shared Redis client
r = redis.Redis(connection_pool=pool)


def save_to_redis(session_id: str, key: str, value: str) -> None:
    """Save value under a hash for a specific session ID."""
    r.hset(f"session:{session_id}", key, value)
    # set TTL for 1 week (604800 seconds)
    r.expire(f"session:{session_id}", 604800)


def load_from_redis(session_id: str, key: str) -> str:
    """Load a specific key from a session hash."""
    return r.hget(f"session:{session_id}", key)


def list_keys(session_id: str) -> list:
    """List all keys for a session."""
    return r.hkeys(f"session:{session_id}")


def delete_session(session_id: str) -> None:
    """Delete all data under a session hash."""
    r.delete(f"session:{session_id}")


def session_exists(session_id: str) -> bool:
    """Check if any data exists for a session."""
    return r.exists(f"session:{session_id}") > 0


def key_exists(session_id: str, key: str) -> bool:
    """Check if a specific key exists in a session."""
    return r.hexists(f"session:{session_id}", key)
