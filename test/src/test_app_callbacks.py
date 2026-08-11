import importlib.util
import sys
import unittest
from pathlib import Path

# app/app.py uses `from src.plotting import ...` (not `from app.src...` or
# relative imports) - it's designed to run with the `app/` directory itself on
# sys.path (as `python app/app.py` does), not as a submodule of the `app`
# namespace package the rest of the test suite imports from (`app.src.*`).
# A plain `import app.app` collides with that already-imported namespace
# package, so load app/app.py directly from its file path instead, under a
# name that can't collide with the `app` package.
_APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _import_app_entrypoint():
    sys.path.insert(0, str(_APP_DIR))
    try:
        spec = importlib.util.spec_from_file_location("app_entrypoint", _APP_DIR / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(_APP_DIR))


class TestAppImport(unittest.TestCase):
    def test_app_module_imports_cleanly(self):
        # Regression test: app.py used to import save_to_redis/load_from_redis/
        # list_keys from a commented-out block while calling them live in 3
        # callbacks, which would raise NameError the first time those
        # callbacks fired. Loading the module must succeed and expose the
        # restored Redis functions.
        app_module = _import_app_entrypoint()

        self.assertTrue(callable(app_module.save_to_redis))
        self.assertTrue(callable(app_module.load_from_redis))
        self.assertTrue(callable(app_module.list_keys))
        self.assertTrue(callable(app_module.load_session_data))


if __name__ == "__main__":
    unittest.main()
