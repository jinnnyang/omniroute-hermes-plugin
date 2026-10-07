"""OmniRoute Doubao Seedream image generation backend（经 OmniRoute 网关）.

实测（2026-10-07）：`POST {base}/images/generations`，model=`doubao-seedream-5.0-pro`
（裸名）或 `volcengine-agent/doubao-seedream-5.0-pro` 均返回 200 与火山 TOS 图片 URL；
`-lite` 变体未注册。网关 keyless，无需真实 API key。
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from typing import Any, Dict, List, Optional

import httpx

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)

logger = logging.getLogger(__name__)

# OmniRoute 图片生成端点（默认模型用户已确认 doubao-seedream-5.0-pro）
_MODELS: Dict[str, Dict[str, Any]] = {
    "doubao-seedream-5.0-pro": {
        "display": "Doubao Seedream 5.0 Pro",
        "speed": "~25s",
        "strengths": "5.0 大模型，高保真图像生成",
        "price": "paid",
    },
}

DEFAULT_MODEL = "doubao-seedream-5.0-pro"

# OmniRoute 网关实测（2026-10-07）：size 需 >= 921600 像素；
# 1024x1024 约 17s，2048x2048 约 56s（超网关 30s 内部直连超时，易 502）。
# 采用 1024 档分辨率保证稳定。
_SIZES = {
    "landscape": "1344x768",
    "square": "1024x1024",
    "portrait": "768x1344",
}

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)


def _get_base_url() -> str:
    try:
        from plugins._omniroute_common.config import resolve_omniroute_endpoint
    except ModuleNotFoundError:
        import importlib.util
        from pathlib import Path
        config_path = Path(__file__).resolve().parents[2] / "_omniroute_common" / "config.py"
        spec = importlib.util.spec_from_file_location("omniroute_common_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(config_module)
        resolve_omniroute_endpoint = config_module.resolve_omniroute_endpoint
    return resolve_omniroute_endpoint("images/generations")


def _get_api_key() -> str:
    try:
        from plugins._omniroute_common.config import resolve_omniroute_api_key
    except ModuleNotFoundError:
        import importlib.util
        from pathlib import Path
        config_path = Path(__file__).resolve().parents[2] / "_omniroute_common" / "config.py"
        spec = importlib.util.spec_from_file_location("omniroute_common_config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(config_module)
        resolve_omniroute_api_key = config_module.resolve_omniroute_api_key
    return resolve_omniroute_api_key()


class OmniRouteImageGenProvider(ImageGenProvider):
    """OmniRoute（火山 Seedream 5.0 Pro）图像生成 backend。

    AGENT GUIDANCE (指引):
    1. Typical Duration: Seedream 5.0 Pro 约 25 秒，同步生成。
    2. Access: 插件从 OmniRoute 返回的 URL 下载图片，解码后缓存到 profile cache 目录。
    3. Render: 用 `![description](file:///absolute/local/path.png)` 展示。
    """

    @property
    def name(self) -> str:
        return "omniroute"

    @property
    def display_name(self) -> str:
        return "OmniRoute (Seedream 5.0 Pro)"

    def is_available(self) -> bool:
        # keyless 网关：无需 API key 即可调用
        return True

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": mid, **meta}
            for mid, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text"],
            "max_reference_images": 0,
        }

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "OmniRoute (Seedream)",
            "badge": "paid",
            "tag": "Doubao Seedream via OmniRoute gateway — keyless local endpoint",
            "env_vars": [
                {
                    "key": "OMNIROUTE_BASE_URL",
                    "prompt": "OmniRoute base URL (default http://localhost:20128/v1)",
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        res = self._generate_core(prompt, aspect_ratio, **kwargs)
        if res.get("success"):
            image_ref = res.get("image")
            res["agent_guidance"] = (
                "[AGENT GUIDANCE]\n"
                "- 预计耗时 (Estimated Duration): Doubao Seedream 5.0 Pro 约 25s，同步生成。\n"
                "- 任务状态 (Task Status): 图像已成功生成并缓存到本地。\n"
                f"- 本地文件 (Local File): {image_ref}。请用绝对路径展示：![图片](file://{image_ref})。\n"
                "- 渲染/后续建议: 生成已全部成功，直接展示即可，无需重复调用。"
            )
        else:
            error = res.get("error", "Unknown error")
            res["agent_guidance"] = (
                "[AGENT GUIDANCE]\n"
                f"- 失败原因 (Failure Reason): {error}\n"
                "- 排查 (Verification): 确认 OMNIROUTE_BASE_URL 可达、模型在 OmniRoute dashboard 已注册。\n"
                "- 后续动作 (Next Steps): 修复后重新调用生成工具。"
            )
        return res

    def _generate_core(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)
        model = kwargs.get("model", DEFAULT_MODEL)

        if kwargs.get("image_url") or kwargs.get("reference_image_urls"):
            return error_response(
                error="OmniRoute Seedream is text-to-image only; image_url/reference_image_urls are not supported.",
                error_type="unsupported_modality",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        if model not in _MODELS:
            return error_response(
                error=f"Unsupported OmniRoute image model: {model}. Supported model: {DEFAULT_MODEL}",
                error_type="unsupported_model",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        print(f"[omniroute] Calling Image Generation: model={model}, aspect_ratio={aspect}", file=sys.stderr)
        print(f"[omniroute] Prompt: \"{prompt}\"", file=sys.stderr)

        if not prompt:
            return error_response(
                error="Prompt is required",
                error_type="invalid_argument",
                provider="omniroute",
                aspect_ratio=aspect,
            )

        size = _SIZES.get(aspect, _SIZES["square"])
        print(f"[omniroute] Mapped resolution size: {size}", file=sys.stderr)

        headers = {"Content-Type": "application/json"}
        api_key = _get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }

        try:
            resp = httpx.post(_get_base_url(), json=payload, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            res_data = resp.json()
        except httpx.HTTPStatusError as exc:
            error_msg = f"HTTP {exc.response.status_code}"
            try:
                err_body = exc.response.json()
                if "error" in err_body:
                    error_msg += f": {err_body['error'].get('message', str(err_body['error']))}"
            except Exception:
                error_msg += f": {exc.response.text[:200]}"
            print(f"[omniroute] API call failed: {error_msg}", file=sys.stderr)
            return error_response(
                error=f"API 调用失败: {error_msg}",
                error_type="api_error",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except httpx.RequestError as exc:
            print(f"[omniroute] Network error: {exc}", file=sys.stderr)
            return error_response(
                error=f"网络错误: {exc}",
                error_type="network_error",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except Exception as exc:
            print(f"[omniroute] Unexpected error: {exc}", file=sys.stderr)
            return error_response(
                error=f"图像生成失败: {exc}",
                error_type="api_error",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        data = res_data.get("data", [])
        if not data:
            return error_response(
                error="OmniRoute returned no image data",
                error_type="empty_response",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        first = data[0]
        b64 = first.get("b64_json")
        url = first.get("url")

        if b64:
            try:
                saved_path = save_b64_image(b64, prefix=f"omni_{model}")
            except Exception as exc:
                return error_response(
                    error=f"Could not save image to cache: {exc}",
                    error_type="io_error",
                    provider="omniroute",
                    model=model,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
            image_ref = str(saved_path)
        elif url:
            print(f"[omniroute] Downloading image from remote URL: {url}", file=sys.stderr)
            try:
                import base64
                resp = httpx.get(url, timeout=_TIMEOUT)
                resp.raise_for_status()
                image_bytes = resp.content
                b64_str = base64.b64encode(image_bytes).decode("utf-8")
                saved_path = save_b64_image(b64_str, prefix=f"omni_{model}")
                image_ref = str(saved_path)
                print(f"[omniroute] Image downloaded and saved to: {image_ref}", file=sys.stderr)
            except Exception as exc:
                print(f"[omniroute] Failed to download or save remote image: {exc}", file=sys.stderr)
                return error_response(
                    error=f"下载并缓存远程图片失败: {exc}",
                    error_type="io_error",
                    provider="omniroute",
                    model=model,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
        else:
            return error_response(
                error="Response contained neither b64_json nor URL",
                error_type="empty_response",
                provider="omniroute",
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        print(f"[omniroute] Image generation successful. Saved to: {image_ref}", file=sys.stderr)
        return success_response(
            image=image_ref,
            model=model,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="omniroute",
            extra={"size": size},
        )


def register(ctx) -> None:
    ctx.register_image_gen_provider(OmniRouteImageGenProvider())
    print("[omniroute] Image Gen provider registered successfully.", file=sys.stderr)
