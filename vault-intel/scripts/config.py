"""Config loader for vault-intel skill."""

import yaml
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.yaml"
DATA_DIR = SKILL_DIR / "data"
LOCK_FILE = DATA_DIR / "vault-intel.lock"


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load and validate config.yaml, returning a dict with Path objects for key paths."""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Convert string paths to Path objects
    cfg["vault_path"] = Path(cfg["vault_path"])
    cfg["portfolio_path"] = Path(cfg["portfolio_path"])
    cfg["thirteenf_path"] = Path(cfg["thirteenf_path"])

    # Ensure data dir exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    return cfg


def get_run_dir(run_id: str) -> Path:
    """Create and return a run-specific data directory."""
    run_dir = DATA_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
