"""Best-effort self-update for the OmniRoute Hermes plugins.

Runs once per process at plugin-load time, gated by a TTL so it does not hit
the network on every launch. Replaces the four omniroute plugin dirs under the
profile's ``plugins/`` root with the latest state of the plugin repo. It never
blocks or fails plugin loading: any problem is printed as a warning and skipped.

The replacement takes effect on the NEXT process start (this process already
imported the old code).

Env overrides:
  OMNIROUTE_SELF_UPDATE_URL   plugin repo URL (default: jinnnyang/omniroute-hermes-plugin)
  OMNIROUTE_SELF_UPDATE_TTL   seconds between checks (default 86400; 0 = check every load, -1 = disabled)
  OMNIROUTE_SELF_UPDATE_OFF   set to 1/true/yes to disable
  OMNIROUTE_GIT               git executable to use (default: first `git` on PATH)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

DEFAULT_PLUGIN_URL = "https://github.com/jinnnyang/omniroute-hermes-plugin.git"
DEFAULT_BRANCH = "aptapi"
DEFAULT_TTL_SECONDS = 86400  # 24h
PLUGIN_DIRS = (
    "model-providers/omniroute",
    "image_gen/omniroute",
    "web/omniroute",
    "update-config",
    "update-skills",
    "_omniroute_common",
)
STAMP_NAME = ".omniroute-self-update.stamp"
LOCK_NAME = ".omniroute-self-update.lock"
LOCK_STALE_SECONDS = 600  # a lock older than this is considered dead
CLONE_TIMEOUT = 30

# one real update attempt per process, even if several providers load in parallel
_guard = threading.Lock()
_done = False


def _warn(message: str) -> None:
    print(f"[omniroute] {message}", file=sys.stderr)


def _profile_plugin_root() -> Path | None:
    """Locate the profile's plugins/ root (HERMES_HOME/plugins)."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()) / "plugins"
    except Exception:
        home = os.environ.get("HERMES_HOME")
        if home:
            return Path(home) / "plugins"
    return None


def _ttl_seconds() -> int:
    raw = os.environ.get("OMNIROUTE_SELF_UPDATE_TTL", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_TTL_SECONDS


def _enabled() -> bool:
    if os.environ.get("OMNIROUTE_SELF_UPDATE_OFF", "").strip().lower() in ("1", "true", "yes"):
        return False
    return _ttl_seconds() >= 0


def _git_exe() -> str | None:
    explicit = os.environ.get("OMNIROUTE_GIT", "").strip()
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    return shutil.which("git")


def _acquire_lock(plugin_root: Path) -> Path | None:
    """Cross-process lock (O_EXCL) with stale-lock takeover. Returns lock path or None."""
    lock_path = plugin_root / LOCK_NAME
    for _ in range(2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                return None
            if age > LOCK_STALE_SECONDS:
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    return None
            return None
        try:
            os.write(fd, f"pid={os.getpid()} time={time.time()}\n".encode("utf-8"))
        finally:
            os.close(fd)
        return lock_path
    return None


def _apply_update(plugin_root: Path, url: str, stamp: Path) -> None:
    staged = Path(tempfile.mkdtemp(prefix="omniroute-selfupdate-", dir=str(plugin_root.parent)))
    git = _git_exe()
    if git is None:
        _warn("self-update skipped: no git executable found on PATH (set OMNIROUTE_GIT)")
        return
    branch = os.environ.get("OMNIROUTE_SELF_UPDATE_BRANCH", "").strip() or DEFAULT_BRANCH
    try:
        subprocess.run(
            [git, "clone", "--depth", "1", "--branch", branch, "--quiet", url, str(staged)],
            check=True, capture_output=True, text=True, timeout=CLONE_TIMEOUT)
        src = staged / "plugins"
        if not src.is_dir():
            _warn(f"self-update skipped: cloned repo has no plugins/ dir ({url})")
            return
        replaced: list[str] = []
        for rel in PLUGIN_DIRS:
            src_dir = src / rel
            if not src_dir.is_dir():
                continue
            dst = plugin_root / rel
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src_dir, dst)
            replaced.append(rel)
        stamp.write_text(f"time={time.time()}\n", encoding="utf-8")
        _warn(f"self-update: refreshed {len(replaced)} dir(s) from {url} (effective next launch)")
    except (subprocess.SubprocessError, OSError) as exc:
        _warn(f"self-update skipped: {exc}")
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def _fmt_ttl(ttl: int) -> str:
    """Human-readable TTL, e.g. 86400 -> '24h'."""
    if ttl % 3600 == 0:
        return f"{ttl // 3600}h"
    if ttl % 60 == 0:
        return f"{ttl // 60}m"
    return f"{ttl}s"


def maybe_self_update() -> None:
    """TTL-gated, best-effort refresh of the omniroute plugin dirs (once/process).

    Never raises: any failure degrades to a stderr note. Every outcome prints a
    status line so a launch always shows the self-update state.
    """
    global _done
    if _done:
        return
    with _guard:
        if _done:
            return
        _done = True  # marked attempted; no retry within this process
    if not _enabled():
        _warn("self-update: disabled (OMNIROUTE_SELF_UPDATE_OFF set or TTL < 0)")
        return
    plugin_root = _profile_plugin_root()
    if plugin_root is None or not plugin_root.is_dir():
        _warn("self-update: skipped (plugins root not found)")
        return
    stamp = plugin_root / STAMP_NAME
    ttl = _ttl_seconds()
    try:
        if ttl > 0 and stamp.exists():
            age = time.time() - stamp.stat().st_mtime
            if age < ttl:
                last = time.strftime("%m-%d %H:%M", time.localtime(stamp.stat().st_mtime))
                nxt = time.strftime("%m-%d %H:%M", time.localtime(stamp.stat().st_mtime + ttl))
                _warn(f"self-update: skipped (last check {last}, TTL {_fmt_ttl(ttl)}, next check {nxt})")
                return
    except OSError:
        pass
    url = os.environ.get("OMNIROUTE_SELF_UPDATE_URL", "").strip() or DEFAULT_PLUGIN_URL
    lock = _acquire_lock(plugin_root)
    if lock is None:
        _warn("self-update: skipped (another process holds the update lock)")
        return
    try:
        _apply_update(plugin_root, url, stamp)
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
