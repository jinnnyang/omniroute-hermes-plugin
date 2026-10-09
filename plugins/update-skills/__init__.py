"""OmniRoute Agent Skills sync — pulls SKILL.md docs from aptapi.dev on launch.

Runs once per process, TTL-gated (24h). Fetches the skill index from
``GET https://aptapi.dev/api/agent-skills`` and downloads each SKILL.md via
``GET /api/agent-skills/{id}/raw`` into ``~/.hermes/skills/aptapi/<id>/SKILL.md``.

Existing files are overwritten (this directory is bootstrapper-managed).
Skills the user may have hand-edited elsewhere are untouched.

Env overrides:
  OMNISKILLS_TTL_SECONDS   seconds between checks (default 86400; 0 = every load, -1 = off)
  OMNISKILLS_OFF           set to 1/true/yes to disable
  OMNISKILLS_BASE_URL      override the API base (default: https://aptapi.dev)
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://aptapi.dev"
DEFAULT_TTL = 86400  # 24h
SKILLS_SUBDIR = Path("skills") / "aptapi"
STAMP_NAME = ".omniroute-skills-sync.stamp"
HTTP_TIMEOUT = 15

_guard = threading.Lock()
_done = False


def _warn(msg: str) -> None:
    print(f"[omniroute-skills] {msg}", file=sys.stderr)


def _profile_home() -> Path | None:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        home = os.environ.get("HERMES_HOME", "").strip()
        return Path(home) if home else None


def _ttl() -> int:
    raw = os.environ.get("OMNISKILLS_TTL_SECONDS", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_TTL


def _disabled() -> bool:
    return os.environ.get("OMNISKILLS_OFF", "").strip().lower() in ("1", "true", "yes")


def _base_url() -> str:
    return os.environ.get("OMNISKILLS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _http_get(url: str, timeout: int = HTTP_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json, text/markdown"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_index(raw: bytes) -> list[str]:
    """Extract skill IDs from the index response. Tolerates array-of-strings,
    array-of-objects ({id|name|slug}), or an object with an items/skills/list key."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (data.get("items") or data.get("skills") or data.get("list")
                 or data.get("data") or [])
        if not isinstance(items, list):
            return []
    else:
        return []

    ids: list[str] = []
    for it in items:
        if isinstance(it, str):
            ids.append(it)
        elif isinstance(it, dict):
            sid = it.get("id") or it.get("name") or it.get("slug")
            if sid:
                ids.append(str(sid))
    return ids


def _sync_one(base: str, skill_id: str, dest: Path) -> bool:
    url = f"{base}/api/agent-skills/{skill_id}/raw"
    try:
        content = _http_get(url)
    except Exception as exc:
        _warn(f"  skip {skill_id}: {exc}")
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return True
    except OSError as exc:
        _warn(f"  skip {skill_id}: write failed: {exc}")
        return False


def sync_skills() -> None:
    """TTL-gated, best-effort skills sync. Never raises."""
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

    stamp = home / STAMP_NAME
    try:
        if ttl > 0 and stamp.exists() and time.time() - stamp.stat().st_mtime < ttl:
            return
    except OSError:
        pass

    base = _base_url()
    dest_root = home / SKILLS_SUBDIR
    dest_root.mkdir(parents=True, exist_ok=True)

    # fetch index
    try:
        index_raw = _http_get(f"{base}/api/agent-skills")
    except Exception as exc:
        _warn(f"index fetch failed: {exc} — will retry next launch")
        return

    ids = _parse_index(index_raw)
    if not ids:
        _warn("index returned no skills; nothing to sync")
        return

    synced = 0
    for sid in ids:
        if _sync_one(base, sid, dest_root / sid / "SKILL.md"):
            synced += 1

    _warn(f"synced {synced}/{len(ids)} agent skills to {dest_root}")

    try:
        stamp.write_text(f"time={time.time()}\n", encoding="utf-8")
    except OSError:
        pass


# fire-and-forget at import time
sync_skills()
