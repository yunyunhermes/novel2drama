"""Client for the local xDiT H3 service."""
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .config import XDIT_H3_BASE_URL, XDIT_H3_TIMEOUT


class XDitError(Exception):
    pass


_completed_responses: Dict[str, Dict[str, Any]] = {}


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None,
             timeout: int = XDIT_H3_TIMEOUT) -> Dict[str, Any]:
    url = f"{XDIT_H3_BASE_URL.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise XDitError(f"xDiT HTTP {exc.code}: {body[:500]}") from exc
    except Exception as exc:
        raise XDitError(f"xDiT request failed: {exc}") from exc


def health(timeout: int = 5) -> Dict[str, Any]:
    return _request("GET", "/health", timeout=timeout)


def is_available(timeout: int = 5) -> bool:
    try:
        response = health(timeout=timeout)
        return str(response.get("status", "")).lower() in {"ok", "healthy", "ready"}
    except XDitError:
        return False


def h3_video_create(prompt: str, first_frame_path: Optional[str] = None,
                    seconds: int = 15, size: str = "768x768",
                    seed: Optional[int] = None,
                    negative_prompt: Optional[str] = None) -> str:
    """Create an xDiT task and return its task ID."""
    try:
        width, height = (int(value) for value in size.lower().split("x", 1))
    except (ValueError, AttributeError) as exc:
        raise XDitError(f"invalid xDiT size: {size}") from exc
    payload: Dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "height": height,
        "width": width,
        "num_frames": max(1, int(seconds * 24)),
        "num_inference_steps": 4,
    }
    if first_frame_path:
        payload["first_frame_path"] = first_frame_path
    if seed is not None:
        payload["seed"] = seed
    response = _request("POST", "/generate", payload=payload)
    task_id = response.get("task_id") or response.get("id")
    if not task_id:
        raise XDitError(f"no task_id in xDiT response: {response}")
    task_id = str(task_id)
    if str(response.get("status") or "").lower() in {"succeeded", "completed", "success", "done"}:
        _completed_responses[task_id] = response
    return task_id


def h3_video_status(task_id: str) -> Dict[str, Any]:
    return _request("GET", f"/tasks/{task_id}")


def h3_video_wait(task_id: str, timeout: int = XDIT_H3_TIMEOUT,
                  poll_interval: int = 10) -> Dict[str, Any]:
    """Wait for xDiT completion; supports the current synchronous service too."""
    deadline = time.time() + timeout
    if task_id in _completed_responses:
        return _completed_responses.pop(task_id)
    while time.time() < deadline:
        status = h3_video_status(task_id)
        state = str(status.get("status") or "").lower()
        if state in {"succeeded", "completed", "success", "done"}:
            return status
        if state in {"failed", "error", "cancelled", "canceled"}:
            raise XDitError(f"xDiT task {task_id} failed: {status}")
        time.sleep(poll_interval)
    raise XDitError(f"xDiT task {task_id} timeout after {timeout}s")


def h3_video_download(task_id: str, status: Optional[Dict[str, Any]] = None) -> bytes:
    """Read the shared filesystem path returned by xDiT."""
    response = status or h3_video_status(task_id)
    video_path = response.get("video_path") or response.get("path")
    if not video_path:
        raise XDitError(f"no video_path in xDiT response: {response}")
    try:
        with open(video_path, "rb") as video_file:
            return video_file.read()
    except OSError as exc:
        raise XDitError(f"cannot read xDiT video {video_path}: {exc}") from exc
