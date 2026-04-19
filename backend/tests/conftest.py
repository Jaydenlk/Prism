"""
pytest conftest — add backend/ to sys.path so that `import app.*` works
without Docker or a full Prism installation.
"""
import sys
from pathlib import Path

# Ensure the `backend` directory is on the Python path so that
# `from app.services.im_feishu import FeishuAdapter` resolves correctly.
_BACKEND_DIR = Path(__file__).parent.parent  # .../PrismV3/backend
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
