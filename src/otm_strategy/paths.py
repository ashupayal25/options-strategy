"""Single place for project folders. Set OTM_HOME to override (for example on a server)."""
import os
from pathlib import Path


def _find_root() -> Path:
    env = os.environ.get("OTM_HOME")
    if env:
        return Path(env).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


ROOT = _find_root()
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"
