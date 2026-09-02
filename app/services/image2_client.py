"""
Image2 客户端 - 调用 smmmc gpt-image-2 生成资产图 (smmmc NewAPI /v1)。

资产生成统一走 image2 (不再用 Z-Image 出资产图)。Z-Image 仍由 gateway_client 负责段首图关键帧。

- 文生图: POST /images/generations (json)
- 参考图编辑: POST /images/edits (multipart form-data, image[] 重复字段)
- 响应可能是 b64_json 或 data[].url (CDN); 统一采集为 bytes, 并为 URL 分支带浏览器 UA + Referer 下载。
- 用纯标准库 (urllib) 实现, 不依赖 requests/PIL, 确保 GPU 侧零新增依赖可运行。
"""
import base64
import io
import json
import sys
import urllib.request
import urllib.error
import uuid
from typing import Optional, Dict, Any, List

from .config import (
    IMAGE2_BASE_URL, IMAGE2_API_KEY, IMAGE2_MODEL,
    IMAGE2_QUALITY, IMAGE2_RESOLUTION, IMAGE2_TIMEOUT,
    ASSET_DEFAULT_ASPECT,
)


class Image2Error(Exception):
    pass


def _key() -> str:
    if not IMAGE2_API_KEY:
        # 兜底: 解析 /root/.hermes/.env (宿主机形态), 不依赖环境注入
        for p in ("/root/.hermes/.env", "/etc/novel2drama.env"):
            try:
                for line in open(p):
                    line = line.strip()
                    for name in ("SMMMC_API_KEY", "LLM_API_KEY", "IMAGE2_API_KEY"):
                        if line.startswith(name + "="):
                            val = line.split("=", 1)[1].strip().strip("'\"")
                            if val:
                                return val
            except OSError:
                continue
    return IMAGE2_API_KEY


def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{IMAGE2_BASE_URL.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=IMAGE2_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Image2Error(f"HTTP {e.code}: {body[:500]}")
    except Exception as e:
        raise Image2Error(f"image2 request failed: {e}")


def _post_multipart_edits(prompt: str, size: str, refs: List[bytes],
                          n: int, quality: str, resolution: str,
                          model: str, reasoning_effort: str) -> Dict[str, Any]:
    """POST /images/edits multipart. 参考图用 image[] 重复字段, multipart 对载荷大小宽容。"""
    url = f"{IMAGE2_BASE_URL.rstrip('/')}/images/edits"
    boundary = uuid.uuid4().hex
    fields = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": str(n),
        "quality": quality,
        "resolution": resolution,
        "reasoning_effort": reasoning_effort,
    }
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for i, rb in enumerate(refs):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image[]\"; "
            f"filename=\"ref_{i}.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
        )
        parts.append(rb)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {_key()}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=IMAGE2_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise Image2Error(f"HTTP {e.code}: {err[:500]}")
    except Exception as e:
        raise Image2Error(f"image2 edits request failed: {e}")


def _download(url: str, timeout: int = 300) -> bytes:
    """下载 CDN 图片, 需浏览器 UA + Referer (探针实测 bwg.code2alita.com / adobe*.code2alita.com)。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Referer": IMAGE2_BASE_URL.rstrip("/") + "/",
        "Authorization": f"Bearer {_key()}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def extract_images(data: Dict[str, Any]) -> List[bytes]:
    """从响应提取图片字节 (b64_json 或 url)。"""
    out: List[bytes] = []
    items = data.get("data", []) or []
    if not isinstance(items, list):
        # 兼容 data 为 dict 的形态
        items = [data.get("data")] if data.get("data") else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "b64_json" in item:
            out.append(base64.b64decode(item["b64_json"]))
        elif "url" in item:
            out.append(_download(item["url"]))
    return out


def _normalize_size(size: str, aspect: Optional[str], view_mode: str) -> str:
    """
    决定传给 image2 的 size 字符串。
    - view_mode == "character_multi": 强制 16:9 (三格图)。
    - 否则用传入 size (像素) 或 aspect 比例 (默认 ASSET_DEFAULT_ASPECT)。
    """
    if view_mode == "character_multi":
        return "16:9"
    if size and size not in ("auto",):
        return size
    return aspect or ASSET_DEFAULT_ASPECT


def validate_result_images(images: List[bytes], want_size: str) -> Dict[str, Any]:
    """做本地像素校验 (无 vision): 读取尺寸/模式, 采样通道范围防纯白坏图。
    PIL 缺失时仅返回字节信息。返回 {size, mode, dims, bytes, problems}"""
    info: Dict[str, Any] = {"count": len(images), "images": []}
    try:
        from PIL import Image
        has_pil = True
    except ImportError:
        has_pil = False
    for b in images:
        d: Dict[str, Any] = {"bytes": len(b) // 1024}
        if has_pil:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(b))
                d["mode"] = img.mode
                d["w"], d["h"] = img.size
                # 通道范围采样防纯白/纯黑坏图
                small = img.convert("RGB").resize((80, 110))
                px = list(small.getdata())
                chans = [p[i] for p in px for i in range(3)]
                d["chan_min"] = min(chans)
                d["chan_max"] = max(chans)
                if d["chan_min"] > 245:
                    d["problem"] = "near-white/broken image"
                elif d["chan_max"] < 10:
                    d["problem"] = "near-black/broken image"
            except Exception as e:
                d["problem"] = f"PIL decode failed: {e}"
        info["images"].append(d)
    return info


def image2_generate(prompt: str, size: Optional[str] = None,
                    aspect: Optional[str] = None,
                    view_mode: str = "single",
                    n: int = 1, refs: Optional[List[bytes]] = None,
                    model: Optional[str] = None, quality: Optional[str] = None,
                    resolution: Optional[str] = None,
                    reasoning_effort: str = "low") -> List[bytes]:
    """生成资产图, 返回 bytes 列表。

    - refs 为空 → 文生图 /images/generations
    - refs 非空 → /images/edits multipart (image[] 重复字段)
    - size: 像素字符串 (如 1536x864) 或 "auto"; 为空时按 aspect (默认 ASSET_DEFAULT_ASPECT)。
    - 若上游返回 JPEG 字节 (CDN URL), 会用 PIL 转成真 PNG (PNG 名 + PNG 内容), 保证落盘格式一致。
    """
    size_str = _normalize_size(size or "", aspect, view_mode)
    model = model or IMAGE2_MODEL
    quality = quality or IMAGE2_QUALITY
    resolution = resolution or IMAGE2_RESOLUTION

    if refs:
        data = _post_multipart_edits(prompt, size_str, refs, n, quality,
                                     resolution, model, reasoning_effort)
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size_str,
            "n": n,
            "quality": quality,
            "resolution": resolution,
            "reasoning_effort": reasoning_effort,
        }
        data = _post_json("/images/generations", payload)
    images = extract_images(data)
    # 落盘前统一转真 PNG: URL 下载的常是 JPEG 字节, 用 PNG 名保存需真 PNG 内容
    return [_to_png(b) for b in images]


def _to_png(data: bytes) -> bytes:
    """若字节是 JPEG (非 PNG) 且有 PIL, 转成真 PNG; 否则原样返回。"""
    try:
        from PIL import Image
    except ImportError:
        return data
    try:
        marker = data[:4]
        if marker == b"\x89PNG":
            return data  # 已是 PNG
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return data
