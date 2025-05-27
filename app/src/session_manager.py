# class to manage storing and retrieving session data from Redis.
# for now keeping base functions in this script, but later we can move it to a separate file if needed.
import redis
import os

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,  # Default Redis database
    decode_responses=True,  # Decode responses to strings
)

r = redis.Redis(connection_pool=pool)


class SessionManager:
    """
    Class to manage storing and retrieving session data from Redis.
    """

    @staticmethod
    def set_session_data(session_id, key, value):
        """
        Set a value in the session data.
        """
        r.hset(session_id, key, value)

    @staticmethod
    def get_session_data(session_id, key):
        """
        Get a value from the session data.
        """
        return r.hget(session_id, key)

    @staticmethod
    def delete_session_data(session_id):
        """
        Delete all session data for a given session ID.
        """
        r.delete(session_id)
