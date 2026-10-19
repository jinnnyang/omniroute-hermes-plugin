"""Shared configuration helpers for OmniRoute Hermes plugins.

OmniRoute（aptapi.dev 核心应用）是自建 LLM 聚合网关：聚合火山引擎（Agent/Coding Plan）、
OpenCode Go 等上游，按 combo 路由 + 多策略负载。客户端端点统一走
`POST /v1/*`（OpenAI 兼容面），keyless（任意 Bearer 放行，无 key 才 403）。
"""
from __future__ import annotations

import os

# 本机 OmniRoute 容器实际 API 端口（20129 空响应不可用）；可用 OMNIROUTE_BASE_URL 覆盖
DEFAULT_BASE_URL = "http://localhost:20128/v1"


def _strip_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def resolve_omniroute_base_url() -> str:
    """Resolve the OmniRoute OpenAI-compatible base URL.

    Precedence:
    1. OMNIROUTE_BASE_URL, if explicitly provided.
    2. DEFAULT_BASE_URL (localhost:20128/v1).
    """
    explicit_base_url = os.environ.get("OMNIROUTE_BASE_URL", "").strip()
    if explicit_base_url:
        return _strip_trailing_slash(explicit_base_url)
    return _strip_trailing_slash(DEFAULT_BASE_URL)


def resolve_omniroute_endpoint(suffix: str) -> str:
    """Join the resolved base URL with an endpoint suffix."""
    return resolve_omniroute_base_url().rstrip("/") + "/" + suffix.lstrip("/")


def resolve_omniroute_api_key() -> str:
    """Resolve the API key for OmniRoute providers.

    OmniRoute 是 keyless 网关：任意 Bearer 放行、无 key 才 403。占位值即可；
    配置了真实 key 时（管理面/用量）也会被正确携带。
    """
    return os.environ.get("OMNIROUTE_API_KEY", "").strip()
