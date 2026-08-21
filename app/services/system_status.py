"""Health probes for GPU-side services."""
import json
import urllib.error
import urllib.request
from typing import Any, Dict

from .config import GPU_GATEWAY_BASE_URL, XDIT_H3_BASE_URL


def _probe(url: str, paths: tuple[str, ...], timeout: int = 3) -> Dict[str, Any]:
    last_error = None
    for path in paths:
        try:
            request = urllib.request.Request(f"{url.rstrip('/')}{path}", method="GET")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                try:
                    detail = json.loads(body)
                except json.JSONDecodeError:
                    detail = {"body": body[:200]}
                return {"status": "healthy", "http_status": response.status,
                        "endpoint": path, "detail": detail}
        except Exception as exc:
            last_error = str(exc)
    return {"status": "unavailable", "error": last_error}


def get_gpu_status() -> Dict[str, Dict[str, Any]]:
    """Probe all services independently so one down service never breaks this endpoint."""
    return {
        "comfyui": _probe("http://127.0.0.1:8188", ("/system_stats", "/health")),
        "xdit": _probe(XDIT_H3_BASE_URL, ("/health",)),
        "gpu_gateway": _probe(GPU_GATEWAY_BASE_URL, ("/health", "/v1/models")),
    }
