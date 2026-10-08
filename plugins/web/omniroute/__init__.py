"""OmniRoute aggregated web search provider plugin."""
from __future__ import annotations


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
