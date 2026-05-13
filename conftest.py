import sys
import os

root = os.path.dirname(os.path.abspath(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

# Prevent tests/executor_v2/ from shadowing the source executor_v2 package.
# pytest's default import mode adds tests/ to sys.path; the test package named
# executor_v2 would shadow the real source package of the same name.
# Fix: remove tests/ from sys.path and evict any test-sourced executor_v2 entries.
tests_dir = os.path.join(root, "tests")
while tests_dir in sys.path:
    sys.path.remove(tests_dir)

for key in list(sys.modules.keys()):
    if key == "executor_v2" or key.startswith("executor_v2."):
        mod = sys.modules[key]
        mod_file = getattr(mod, "__file__", "") or ""
        if "tests" in mod_file.replace("\\", "/"):
            del sys.modules[key]

# Pre-load the source executor_v2 so sys.modules maps executor_v2 -> source
# before pytest collection imports tests/executor_v2/__init__.py.
import importlib as _il
_il.import_module("executor_v2")
