"""executor test conftest — add worktree root to sys.path."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent  # .worktrees/plugin-bootstrap
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
