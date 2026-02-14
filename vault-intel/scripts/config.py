"""Config loader for vault-intel skill."""

import yaml
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.yaml"
DATA_DIR = SKILL_DIR / "data"
LOCK_FILE = DATA_DIR / "vault-intel.lock"

# Allowed parent directories for configured paths (resolved, lowercase for comparison)
_ALLOWED_PARENTS = [
    Path.home(),  # e.g. C:\Users\thisi or /Users/thisi
    Path.home() / "Documents",
]


def _validate_path(p: Path, field_name: str) -> Path:
    """Validate a configured path against traversal attacks.

    Rules:
      1. Must be absolute (no relative paths like ../../etc/passwd)
      2. Must exist on disk
      3. Must be under an allowed parent directory (user home tree)

    Raises ValueError with the offending path and field name on failure.
    """
    resolved = p.resolve()

    if not resolved.is_absolute():
        raise ValueError(f"Config '{field_name}' must be an absolute path, got: {p}")

    if not resolved.exists():
        raise ValueError(f"Config '{field_name}' path does not exist: {resolved}")

    if not any(
        resolved == allowed or allowed in resolved.parents
        for allowed in _ALLOWED_PARENTS
    ):
        raise ValueError(
            f"Config '{field_name}' path is outside allowed directories: {resolved}. "
            f"Must be under one of: {[str(a) for a in _ALLOWED_PARENTS]}"
        )

    return resolved


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load and validate config.yaml, returning a dict with Path objects for key paths."""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Convert string paths to Path objects and validate each one
    for field in ("vault_path", "portfolio_path", "thirteenf_path"):
        cfg[field] = _validate_path(Path(cfg[field]), field)

    # Ensure data dir exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    return cfg


def get_run_dir(run_id: str) -> Path:
    """Create and return a run-specific data directory."""
    run_dir = DATA_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
