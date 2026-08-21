"""
FFmpeg 服务 - 视频拼接导出
"""
import os
import subprocess
from typing import List, Optional
from .storage import project_subdir


class FFmpegError(Exception):
    pass


def _run(cmd: List[str], timeout: int = 600) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise FFmpegError(f"ffmpeg failed: {r.stderr[-500:]}")
        return r.stdout
    except FileNotFoundError:
        raise FFmpegError("ffmpeg not installed")


def concat_videos(project_id: str, video_paths: List[str],
                  output_filename: str,
                  resolution: Optional[str] = None,
                  fps: Optional[int] = None) -> str:
    """
    把多个视频按顺序拼接成一个
    video_paths: 绝对路径列表
    返回输出文件绝对路径
    """
    if not video_paths:
        raise FFmpegError("no videos to concat")
    # 创建 concat list 文件
    list_path = os.path.join(project_subdir(project_id, "temp"), "concat_list.txt")
    with open(list_path, "w") as f:
        for p in video_paths:
            f.write(f"file '{p}'\n")
    out_dir = project_subdir(project_id, "exports")
    out_path = os.path.join(out_dir, output_filename)

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
    # 统一转码 (如果源分辨率/编码不一致, 用 libx264 重编码)
    filters = []
    if resolution:
        w, h = resolution.split("x")
        filters.append(f"scale={w}:{h}")
    if fps:
        filters.append(f"fps={fps}")
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            out_path]
    _run(cmd, timeout=1800)
    return out_path


def get_video_info(path: str) -> dict:
    """获取视频基本信息 (时长/分辨率/帧率)"""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_format", "-show_streams", path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {r.stderr[-300:]}")
    import json
    return json.loads(r.stdout)


def extract_thumbnail(video_path: str, out_path: str, time_s: float = 0.5) -> str:
    """提取视频缩略图"""
    cmd = ["ffmpeg", "-y", "-ss", str(time_s), "-i", video_path,
           "-vframes", "1", "-q:v", "2", out_path]
    _run(cmd, timeout=60)
    return out_path
