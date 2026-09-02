"""
存储服务 - 项目文件路径管理
所有生成文件统一放在 data/projects/{project_id}/ 下
"""
import os
import shutil
from typing import Optional
from .config import project_dir, project_subdir, PROJECTS_DATA_DIR


def ensure_project_dirs(project_id: str) -> None:
    """创建项目所有子目录"""
    for sub in ("novels", "storyboard",
                "assets/characters", "assets/scenes", "assets/items",
                "keyframes", "h3_segments", "exports", "temp"):
        project_subdir(project_id, sub)


def save_bytes(project_id: str, sub: str, filename: str, data: bytes) -> str:
    """保存字节到项目子目录, 返回绝对路径"""
    d = project_subdir(project_id, sub)
    path = os.path.join(d, filename)
    with open(path, "wb") as f:
        f.write(data)
    return path


def get_abs_path(project_id: str, rel_path: str) -> str:
    """把数据库存的相对路径转成绝对路径"""
    return os.path.join(project_dir(project_id), rel_path)


def get_rel_path(project_id: str, abs_path: str) -> str:
    """把绝对路径转成相对项目目录的路径 (用于存库)"""
    base = project_dir(project_id)
    if abs_path.startswith(base):
        return os.path.relpath(abs_path, base)
    return abs_path


def delete_project_files(project_id: str) -> None:
    """删除整个项目数据目录"""
    d = project_dir(project_id)
    if os.path.isdir(d):
        shutil.rmtree(d)


def list_files(project_id: str, sub: str, ext: Optional[str] = None) -> list:
    """列出项目子目录下的文件"""
    d = project_subdir(project_id, sub)
    files = []
    for f in sorted(os.listdir(d)):
        if ext and not f.endswith(ext):
            continue
        files.append(os.path.join(d, f))
    return files
