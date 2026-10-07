"""OmniRoute web search backend for Hermes web_search.

实测（2026-10-07）：`POST {base}/search` 返回 200，body {query, limit} →
`{id, provider, query, results: [{title, url, display_url, snippet, position, ...}]}`。
provider 当前为 duckduckgo-free（keyless）。
"""
from __future__ import annotations

import importlib.util
import logging
from typing import Any, Dict, List

import httpx

try:  # Hermes runtime
    from agent.web_search_provider import WebSearchProvider
except ModuleNotFoundError:  # Local plugin test/runtime outside Hermes source tree
    class WebSearchProvider:  # type: ignore[no-redef]
        @property
        def name(self) -> str:
            raise NotImplementedError

        @property
        def display_name(self) -> str:
            return self.name

        def is_available(self) -> bool:
            raise NotImplementedError

        def supports_search(self) -> bool:
            return True

        def supports_extract(self) -> bool:
            return False

        def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
            raise NotImplementedError

        def get_setup_schema(self) -> Dict[str, Any]:
            return {"name": self.display_name, "badge": "", "tag": "", "env_vars": []}


logger = logging.getLogger(__name__)

MAX_SEARCH_COUNT = 50


def _resolve_endpoint() -> str:
    try:
        from plugins._omniroute_common.config import resolve_omniroute_endpoint
    except ModuleNotFoundError:
        config_path = __import__("pathlib").Path(__file__).resolve().parents[2] / "_omniroute_common" / "config.py"
        spec = importlib.util.spec_from_file_location("omniroute_common_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(config_module)
        resolve_omniroute_endpoint = config_module.resolve_omniroute_endpoint
    return resolve_omniroute_endpoint("search")


def _get_api_key() -> str:
    try:
        from plugins._omniroute_common.config import resolve_omniroute_api_key
    except ModuleNotFoundError:
        config_path = __import__("pathlib").Path(__file__).resolve().parents[2] / "_omniroute_common" / "config.py"
        spec = importlib.util.spec_from_file_location("omniroute_common_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(config_module)
        resolve_omniroute_api_key = config_module.resolve_omniroute_api_key
    return resolve_omniroute_api_key()


class OmniRouteWebSearchProvider(WebSearchProvider):
    """Search-only provider for OmniRoute aggregated web search (/v1/search)."""

    @property
    def name(self) -> str:
        return "omniroute"

    @property
    def display_name(self) -> str:
        return "OmniRoute Search"

    def is_available(self) -> bool:
        # keyless 网关：无需 API key
        return True

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"success": False, "error": "Empty search query"}

        count = max(1, min(int(limit), MAX_SEARCH_COUNT))
        headers = {"Content-Type": "application/json"}
        api_key = _get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = httpx.post(
                _resolve_endpoint(),
                json={"query": query, "limit": count},
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("OmniRoute Search HTTP error: %s", exc)
            return {
                "success": False,
                "error": f"OmniRoute Search returned HTTP {exc.response.status_code}",
            }
        except httpx.RequestError as exc:
            logger.warning("OmniRoute Search request error: %s", exc)
            return {"success": False, "error": f"Could not reach OmniRoute Search: {exc}"}

        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("OmniRoute Search response parse error: %s", exc)
            return {
                "success": False,
                "error": "Could not parse OmniRoute Search response as JSON",
            }

        raw_results = (data.get("results") or [])[:count]
        web_results: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_results, start=1):
            if not isinstance(item, dict):
                continue
            web_results.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "description": str(item.get("snippet") or item.get("description") or ""),
                    "position": int(item.get("position") or index),
                }
            )

        return {"success": True, "data": {"web": web_results}}

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "OmniRoute Search",
            "badge": "free",
            "tag": "OmniRoute aggregated web search (当前 upstream: duckduckgo-free); search only.",
            "env_vars": [
                {
                    "key": "OMNIROUTE_BASE_URL",
                    "prompt": "OmniRoute base URL (default http://localhost:20128/v1)",
                }
            ],
        }
