"""OmniRoute aggregated web search provider plugin."""
from __future__ import annotations

import json


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

try:
    from plugins.web.omniroute.provider import OmniRouteWebSearchProvider
except ModuleNotFoundError:  # pragma: no cover - local file-loading fallback
    import importlib.util
    from pathlib import Path

    provider_path = Path(__file__).with_name("provider.py")
    spec = importlib.util.spec_from_file_location("omniroute_web_provider", provider_path)
    provider_module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(provider_module)
    OmniRouteWebSearchProvider = provider_module.OmniRouteWebSearchProvider


def register(ctx) -> None:
    """Register the OmniRoute web search provider with Hermes."""
    ctx.register_web_search_provider(OmniRouteWebSearchProvider())

    # 标准通道 web_search(query, limit) 固定签名，选不了 upstream；另注册一个
    # 自定义工具让 agent 按需指定 provider（实测支持 tavily/firecrawl/duckduckgo）。
    schema = {
        "description": (
            "Search the web via OmniRoute, choosing the upstream search engine. "
            "Use this instead of web_search when the choice of engine matters. "
            "Providers: tavily (high-quality LLM-oriented results, default choice), "
            "firecrawl (server default), duckduckgo (keyless free). "
            "Returns JSON {\"success\": bool, \"data\": {\"web\": [{title, url, description, position}]}} "
            "or {\"success\": false, \"error\": ...}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-50, default 5)",
                    "default": 5,
                },
                "provider": {
                    "type": "string",
                    "description": "Upstream engine: tavily | firecrawl | duckduckgo (default: server default)",
                },
            },
            "required": ["query"],
        },
    }

    provider = OmniRouteWebSearchProvider()

    def handle_omniroute_search(params, **kwargs):
        del kwargs
        query = params.get("query", "")
        limit = params.get("limit", 5)
        search_provider = (params.get("provider") or "").strip()
        return json.dumps(
            provider.search(query, limit, provider=search_provider),
            indent=2,
            ensure_ascii=False,
        )

    ctx.register_tool(
        name="omniroute_search",
        toolset="web",
        schema=schema,
        handler=handle_omniroute_search,
    )
