"""Config loader — reads config.toml, handles Python 3.11+ and older."""

import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        print("Install tomli for Python < 3.11:  pip install tomli")
        sys.exit(1)

_DEFAULTS = {
    "tracking": {
        "poll_interval": 1,
        "upload_interval": 300,
        "min_session_seconds": 2,
    },
    "server": {
        "timeout_seconds": 30,
        "verify_ssl": True,
    },
    "storage": {
        "db_path": "sessions.db",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str = "config.toml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        print(f"Config file not found: {config_path.resolve()}")
        print("Copy config.toml to the same folder as tracker.py and fill in your values.")
        sys.exit(1)
    with open(config_path, "rb") as f:
        user_config = tomllib.load(f)
    config = _deep_merge(_DEFAULTS, user_config)

    # Validate required keys.
    required = [("server", "url"), ("server", "api_key"), ("device", "name")]
    for section, key in required:
        if not config.get(section, {}).get(key):
            print(f"Config error: [{section}] {key} is required.")
            sys.exit(1)

    return config
