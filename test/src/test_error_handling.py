import unittest
import dash
from app.src.error_handling import log_and_prevent_update, log_and_surface_error


class TestLogAndPreventUpdate(unittest.TestCase):
    def test_returns_value_on_success(self):
        @log_and_prevent_update("test.logger")
        def ok(x):
            return x * 2

        self.assertEqual(ok(3), 6)

    def test_catches_exception_and_returns_fallback(self):
        @log_and_prevent_update("test.logger", fallback="fallback-value")
        def boom():
            raise RuntimeError("kaboom")

        self.assertEqual(boom(), "fallback-value")

    def test_default_fallback_is_dash_no_update(self):
        @log_and_prevent_update("test.logger")
        def boom():
            raise RuntimeError("kaboom")

        self.assertIs(boom(), dash.no_update)

    def test_prevent_update_propagates_unchanged(self):
        @log_and_prevent_update("test.logger")
        def raises_prevent_update():
            raise dash.exceptions.PreventUpdate

        with self.assertRaises(dash.exceptions.PreventUpdate):
            raises_prevent_update()


class TestLogAndSurfaceError(unittest.TestCase):
    def test_returns_value_on_success(self):
        @log_and_surface_error("test.logger")
        def ok():
            return "all good"

        self.assertEqual(ok(), "all good")

    def test_catches_exception_and_inserts_error_message(self):
        @log_and_surface_error(
            "test.logger", error_output_index=0, fallback=(False, dash.no_update)
        )
        def boom():
            raise ValueError("bad input")

        result = boom()
        self.assertEqual(result[0], "Error: bad input")
        self.assertEqual(result[1], False)
        self.assertIs(result[2], dash.no_update)

    def test_error_output_index_not_zero(self):
        @log_and_surface_error("test.logger", error_output_index=1, fallback=(dash.no_update,))
        def boom():
            raise ValueError("bad input")

        result = boom()
        self.assertIs(result[0], dash.no_update)
        self.assertEqual(result[1], "Error: bad input")

    def test_non_tuple_fallback_returns_bare_error_string(self):
        @log_and_surface_error("test.logger")
        def boom():
            raise ValueError("bad input")

        self.assertEqual(boom(), "Error: bad input")

    def test_prevent_update_propagates_unchanged(self):
        @log_and_surface_error("test.logger")
        def raises_prevent_update():
            raise dash.exceptions.PreventUpdate

        with self.assertRaises(dash.exceptions.PreventUpdate):
            raises_prevent_update()


if __name__ == "__main__":
    unittest.main()
