"""OmniRoute aggregated web search provider plugin."""
from __future__ import annotations

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
