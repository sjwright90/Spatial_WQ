import unittest
from unittest.mock import patch

from app.src import session_manager


class TestSessionManager(unittest.TestCase):
    def test_save_to_redis(self):
        with patch.object(session_manager, "r") as mock_r:
            session_manager.save_to_redis("user1", "key1", "value1")
            mock_r.hset.assert_called_once_with("session:user1", "key1", "value1")
            mock_r.expire.assert_called_once_with("session:user1", 604800)

    def test_load_from_redis(self):
        with patch.object(session_manager, "r") as mock_r:
            mock_r.hget.return_value = "value1"
            result = session_manager.load_from_redis("user1", "key1")
            mock_r.hget.assert_called_once_with("session:user1", "key1")
            self.assertEqual(result, "value1")

    def test_list_keys(self):
        with patch.object(session_manager, "r") as mock_r:
            mock_r.hkeys.return_value = ["key1", "key2"]
            result = session_manager.list_keys("user1")
            mock_r.hkeys.assert_called_once_with("session:user1")
            self.assertEqual(result, ["key1", "key2"])

    def test_delete_session(self):
        with patch.object(session_manager, "r") as mock_r:
            session_manager.delete_session("user1")
            mock_r.delete.assert_called_once_with("session:user1")

    def test_session_exists_true(self):
        with patch.object(session_manager, "r") as mock_r:
            mock_r.exists.return_value = 1
            self.assertTrue(session_manager.session_exists("user1"))

    def test_session_exists_false(self):
        with patch.object(session_manager, "r") as mock_r:
            mock_r.exists.return_value = 0
            self.assertFalse(session_manager.session_exists("user1"))

    def test_key_exists(self):
        with patch.object(session_manager, "r") as mock_r:
            mock_r.hexists.return_value = True
            result = session_manager.key_exists("user1", "key1")
            mock_r.hexists.assert_called_once_with("session:user1", "key1")
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
