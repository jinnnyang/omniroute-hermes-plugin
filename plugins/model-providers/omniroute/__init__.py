"""OmniRoute model provider — 自建 LLM 聚合网关接入（moirai 定制）。

OmniRoute（aptapi.dev 核心应用）聚合火山引擎（Agent Plan / Coding Plan / Ark）、
OpenCode Go 等上游，客户端统一走 OpenAI 兼容端点。本 provider 把 OmniRoute
注册为 hermes 的一等 LLM provider。

网关行为（2026-10-07 本机实测，omniroute 容器）：
- 实际 API 端口 20128（20129 空响应）；base_url 可用 $OMNIROUTE_BASE_URL 覆盖；
- POST /v1/chat/completions：任意 Bearer 放行（无 key 才 403）→ keyless，api_key 占位即可；
- POST /v1/responses：Codex/Responses 协议同样可用（火山 coding plan 官方推荐）；
- GET /v1/models：keyless 下 401 → fetch_models 走尝试+兜底（fallback_models）；
- 实测可用模型：volcengine-agent/glm-5.3-flash 等任意 model 字段（透传 combo 或模型 id）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Iterable

from providers import register_provider
from providers.base import ProviderProfile

try:
    from plugins._omniroute_common.config import (
        resolve_omniroute_api_key,
        resolve_omniroute_base_url,
        resolve_omniroute_endpoint,
    )
except ModuleNotFoundError:  # pragma: no cover - local file-loading fallback
    config_path = Path(__file__).resolve().parents[2] / "_omniroute_common" / "config.py"
    spec = importlib.util.spec_from_file_location("omniroute_common_config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(config_module)
    resolve_omniroute_api_key = config_module.resolve_omniroute_api_key
    resolve_omniroute_base_url = config_module.resolve_omniroute_base_url
    resolve_omniroute_endpoint = config_module.resolve_omniroute_endpoint

print("[omniroute] Model Provider plugin loaded.", file=sys.stderr)


def _maybe_self_update() -> None:
    """Best-effort self-update (TTL-gated); never blocks the plugin load."""
    try:
        from plugins._omniroute_common.self_update import maybe_self_update
    except ModuleNotFoundError:
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "omniroute_self_update",
            Path(__file__).resolve().parents[2] / "_omniroute_common" / "self_update.py")
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        maybe_self_update = module.maybe_self_update
    try:
        maybe_self_update()
    except Exception:  # pragma: no cover - best-effort, never fail the plugin load
        pass


_maybe_self_update()

# 实测可用模型（2026-10-07）；以 OmniRoute dashboard 注册/combos 为准，可增删
FALLBACK_MODELS = (
    "volcengine-agent/glm-5.3-flash",
    "glm-5.3",
    "volcengine-agent/doubao-seed-2.0-pro",
)


def _first_non_empty(values: Iterable[str | None]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _get_api_key() -> str:
    return resolve_omniroute_api_key()


def _manual_model() -> str:
    return _first_non_empty(
        (
            os.environ.get("OMNIROUTE_MODEL"),
            os.environ.get("OMNIROUTE_DEFAULT_MODEL"),
        )
    )


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _fallback_models() -> tuple[str, ...]:
    manual = _manual_model()
    return tuple(_unique(([manual] if manual else []) + list(FALLBACK_MODELS)))


class OmniRouteProviderProfile(ProviderProfile):
    """OmniRoute 聚合网关 model provider（codex_responses 默认；chat_completions 兼容保留）。"""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ):
        """尝试 /v1/models（keyless 下通常 401）；失败回退 fallback_models。"""
        if not api_key:
            api_key = _get_api_key()

        effective_base_url = (base_url or self.base_url).rstrip("/")
        url = f"{effective_base_url}/models"

        import json
        import urllib.request

        try:
            from providers.base import _profile_user_agent
            user_agent = _profile_user_agent()
        except Exception:
            user_agent = "hermes-cli"

        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", user_agent)

        fetched: list[str] = []
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            items = data if isinstance(data, list) else data.get("data", [])
            fetched = [m["id"] for m in items if isinstance(m, dict) and "id" in m]
        except Exception as exc:
            print(f"[omniroute] Live model fetch failed (falling back): {exc}", file=sys.stderr)

        merged = _unique(fetched + list(self.fallback_models))
        print(
            f"[omniroute] Live model fetch loaded {len(merged)} models "
            f"(including {len(fetched)} live endpoints).",
            file=sys.stderr,
        )
        return merged


_DEFAULT_MODEL = _manual_model() or FALLBACK_MODELS[0]
_BASE_URL = resolve_omniroute_base_url()

omniroute_provider = OmniRouteProviderProfile(
    name="omniroute",
    display_name="OmniRoute",
    description="OmniRoute — 自建 LLM 聚合网关（火山 coding plan + OpenCode Go 订阅）",
    aliases=("omni", "omniroute-ai"),
    api_mode="codex_responses",  # 火山 Coding Plan 官方推荐协议（Responses）；chat_completions 仅兼容保留
    env_vars=("OMNIROUTE_API_KEY", "OMNIROUTE_BASE_URL"),
    base_url=_BASE_URL,
    models_url=resolve_omniroute_endpoint("models"),
    auth_type="api_key",  # keyless 网关：任意 Bearer 放行，key 可占位
    supports_model_listing=False,  # keyless 下 GET /v1/models 401；fetch_models 兜底 fallback
    supports_health_check=False,  # 避免 doctor 对 /models 探测误报
    default_aux_model=_DEFAULT_MODEL,
    fallback_models=_fallback_models(),
)

register_provider(omniroute_provider)
print("[omniroute] Model Provider 'omniroute' successfully registered.", file=sys.stderr)
