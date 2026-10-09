"""OmniRoute config bootstrap — first-launch defaults for config.yaml and .env.

Runs once per process at plugin-load time, TTL-gated (24h). Only fills in
missing keys; never overwrites settings the user has already set.

Injected defaults (aptapi branch):
  - custom_providers.omniroute.base_url = https://aptapi.dev/v1
  - custom_providers.omniroute.api_mode = responses
  - web.search_backend = omniroute
  - image_gen.provider = omniroute
  - image_gen.model = doubao-seedream-5.0-pro
  - .env: OMNIROUTE_API_KEY=local (keyless gateway placeholder)

Env overrides:
  OMNICONFIG_TTL_SECONDS   seconds between checks (default 86400; 0 = every load, -1 = off)
  OMNICONFIG_OFF           set to 1/true/yes to disable entirely
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# --- constants ---------------------------------------------------------------

TTL_STAMP_NAME = ".omniroute-config-bootstrap.stamp"
DEFAULT_TTL = 86400  # 24h

DEFAULTS_CONFIG_YAML: dict = {
    "custom_providers": {
        "omniroute": {
            "base_url": "https://aptapi.dev/v1",
            "api_mode": "responses",
        }
    },
    "web": {
        "search_backend": "omniroute",
    },
    "image_gen": {
        "provider": "omniroute",
        "model": "doubao-seedream-5.0-pro",
    },
}

ENV_PLACEHOLDER = "OMNIROUTE_API_KEY=local\n"

_guard = threading.Lock()
_done = False


def _warn(msg: str) -> None:
    print(f"[omniroute-config] {msg}", file=sys.stderr)


def _profile_home() -> Path | None:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        home = os.environ.get("HERMES_HOME", "").strip()
        return Path(home) if home else None


def _ttl() -> int:
    raw = os.environ.get("OMNICONFIG_TTL_SECONDS", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_TTL


def _disabled() -> bool:
    return os.environ.get("OMNICONFIG_OFF", "").strip().lower() in ("1", "true", "yes")


# --- YAML helpers -------------------------------------------------------------

def _load_yaml(path: Path):
    """Load YAML, preferring ruamel.yaml (comments survive), falling back to PyYAML."""
    text = path.read_text(encoding="utf-8")
    try:
        from ruamel.yaml import YAML
        yaml = YAML()
        yaml.preserve_quotes = True
        return yaml, yaml.load(text)
    except ImportError:
        import yaml as pyyaml
        return pyyaml, pyyaml.safe_load(text) or {}


def _write_yaml(path: Path, yaml_obj, data) -> None:
    try:
        from ruamel.yaml import YAML as _  # noqa: F401
        yaml_obj.dump(data, path)
    except ImportError:
        import yaml as pyyaml
        pyyaml.safe_dump(data, path, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _deep_merge_missing(dst: dict, defaults: dict) -> bool:
    """Recursively set missing keys in dst from defaults. Returns True if anything changed."""
    changed = False
    for k, v in defaults.items():
        if k not in dst or dst[k] is None:
            dst[k] = v
            changed = True
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            if _deep_merge_missing(dst[k], v):
                changed = True
    return changed


# --- .env helper --------------------------------------------------------------

def _ensure_env_placeholder(home: Path) -> None:
    env_path = home / ".env"
    try:
        if not env_path.exists():
            env_path.write_text(ENV_PLACEHOLDER, encoding="utf-8")
            _warn(f"created .env with placeholder OMNIROUTE_API_KEY=local")
            return
        text = env_path.read_text(encoding="utf-8")
        if "OMNIROUTE_API_KEY" not in text:
            with env_path.open("a", encoding="utf-8") as f:
                f.write(ENV_PLACEHOLDER)
            _warn("appended OMNIROUTE_API_KEY=local to .env")
    except OSError as exc:
        _warn(f".env bootstrap skipped: {exc}")


# --- main entrypoint -----------------------------------------------------------

def bootstrap_config() -> None:
    """TTL-gated, best-effort config.yaml + .env bootstrap. Never raises."""
    global _done
    if _done:
        return
    with _guard:
        if _done:
            return
        _done = True

    if _disabled():
        return

    ttl = _ttl()
    if ttl < 0:
        return

    home = _profile_home()
    if home is None:
        return

    stamp = home / TTL_STAMP_NAME
    try:
        if ttl > 0 and stamp.exists() and time.time() - stamp.stat().st_mtime < ttl:
            return
    except OSError:
        pass

    # --- config.yaml ---
    cfg_path = home / "config.yaml"
    try:
        if not cfg_path.exists():
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            yaml_obj, data = None, {}
            # write fresh defaults
            try:
                from ruamel.yaml import YAML
                yaml = YAML()
                yaml.preserve_quotes = True
                yaml.dump(DEFAULTS_CONFIG_YAML, cfg_path)
            except ImportError:
                import yaml as pyyaml
                pyyaml.safe_dump(DEFAULTS_CONFIG_YAML, cfg_path,
                                 default_flow_style=False, allow_unicode=True, sort_keys=False)
            _warn(f"created config.yaml with OmniRoute defaults")
        else:
            yaml_obj, data = _load_yaml(cfg_path)
            if _deep_merge_missing(data, DEFAULTS_CONFIG_YAML):
                _write_yaml(cfg_path, yaml_obj, data)
                _warn("config.yaml: injected missing OmniRoute defaults (existing values preserved)")
    except Exception as exc:
        _warn(f"config.yaml bootstrap skipped: {exc}")

    # --- .env ---
    _ensure_env_placeholder(home)

    # stamp
    try:
        stamp.write_text(f"time={time.time()}\n", encoding="utf-8")
    except OSError:
        pass


# fire-and-forget at import time
bootstrap_config()
