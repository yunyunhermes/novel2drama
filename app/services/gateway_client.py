"""
GPU Gateway 客户端 - 调用 GPU 服务器的 OpenAI 兼容网关
Z-Image: /v1/images/generations (同步)
H3: /v1/videos (异步 task_id 轮询)
"""
import json
import urllib.request
import urllib.error
import urllib.parse
import time
import uuid
from typing import Optional, Dict, Any, List
from .config import (GPU_GATEWAY_BASE_URL, GPU_GATEWAY_KEY, GPU_GATEWAY_TIMEOUT,
                     Z_IMAGE_MODEL, H3_MODEL)


class GatewayError(Exception):
    pass


def _request(method: str, path: str, payload: Optional[Dict] = None,
             form_fields: Optional[Dict[str, str]] = None,
             form_files: Optional[List[tuple]] = None,  # [(field_name, filename, bytes, content_type)]
             timeout: int = GPU_GATEWAY_TIMEOUT) -> Dict[str, Any]:
    url = f"{GPU_GATEWAY_BASE_URL.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {GPU_GATEWAY_KEY}"}
    data = None
    if form_fields is not None or form_files is not None:
        # multipart/form-data
        boundary = uuid.uuid4().hex
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        parts = []
        if form_fields:
            for k, v in form_fields.items():
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        if form_files:
            for field, fname, fbytes, ctype in form_files:
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
                parts.append(fbytes)
                parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
    elif payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise GatewayError(f"HTTP {e.code}: {body[:500]}")
    except Exception as e:
        raise GatewayError(f"Gateway request failed: {e}")


def _download(url_path: str, timeout: int = 300) -> bytes:
    """从网关下载文件内容 (相对路径或绝对URL)"""
    if url_path.startswith("http"):
        url = url_path
    else:
        url = f"{GPU_GATEWAY_BASE_URL.rstrip('/')}{url_path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {GPU_GATEWAY_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        raise GatewayError(f"Download failed {url}: {e}")


# ============ Z-Image 文生图 ============
def z_image_generate(prompt: str, negative_prompt: Optional[str] = None,
                     size: str = "1024x1024", seed: Optional[int] = None) -> Dict[str, Any]:
    """
    调用 Z-Image 生成图片 (同步, 返回图URL/data)
    返回网关原始响应, 通常含 data[0].url 或 data[0].b64_json
    """
    payload = {
        "model": Z_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed is not None:
        payload["seed"] = seed
    return _request("POST", "/v1/images/generations", payload=payload)


def z_image_download(result: Dict[str, Any]) -> bytes:
    """从 z_image_generate 结果中提取图片字节"""
    data = result.get("data", [])
    if not data:
        raise GatewayError(f"empty data in z-image result: {result}")
    item = data[0]
    if "b64_json" in item:
        import base64
        return base64.b64decode(item["b64_json"])
    if "url" in item:
        return _download(item["url"])
    raise GatewayError(f"no url or b64_json in z-image result: {item}")


# ============ H3 视频生成 (异步) ============
def h3_video_create(prompt: str, first_frame_path: Optional[str] = None,
                    seconds: int = 15, size: str = "1280x720",
                    seed: Optional[int] = None,
                    negative_prompt: Optional[str] = None) -> str:
    """
    创建 H3 视频生成任务
    - 如果有 first_frame_path: 走 i2v (multipart)
    - 否则: 走 t2v (multipart, 仅 prompt)
    返回 task_id
    """
    fields = {
        "model": H3_MODEL,
        "prompt": prompt,
        "seconds": str(seconds),
        "size": size,
    }
    if negative_prompt:
        fields["negative_prompt"] = negative_prompt
    if seed is not None:
        fields["seed"] = str(seed)

    files = None
    if first_frame_path:
        with open(first_frame_path, "rb") as f:
            img_bytes = f.read()
        files = [("input_reference[]", first_frame_path.split("/")[-1], img_bytes, "image/png")]

    r = _request("POST", "/v1/videos", form_fields=fields, form_files=files)
    task_id = r.get("id") or r.get("task_id") or (r.get("data") or {}).get("id")
    if not task_id:
        raise GatewayError(f"no task_id in h3 create response: {r}")
    return task_id


def h3_video_status(task_id: str) -> Dict[str, Any]:
    """查询 H3 任务状态. 返回原始响应 (含 status/progress/url 等)"""
    return _request("GET", f"/v1/videos/{task_id}")


def h3_video_download(task_id: str) -> bytes:
    """下载 H3 视频"""
    return _download(f"/v1/videos/{task_id}/content")


def h3_video_wait(task_id: str, timeout: int = 1800, poll_interval: int = 10) -> Dict[str, Any]:
    """轮询直到 H3 任务完成或失败"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = h3_video_status(task_id)
        status = (st.get("status") or "").lower()
        if status in ("succeeded", "completed", "success", "done"):
            return st
        if status in ("failed", "error", "cancelled", "canceled"):
            raise GatewayError(f"H3 task {task_id} failed: {st}")
        time.sleep(poll_interval)
    raise GatewayError(f"H3 task {task_id} timeout after {timeout}s")


# ============ 健康检查 ============
def list_models() -> Dict[str, Any]:
    return _request("GET", "/v1/models")
