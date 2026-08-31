from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os

app = FastAPI(title="novel2drama", version="0.1.0")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

from app.routers import projects, novels, storyboard, assets, generation, review, export, episodes

app.include_router(projects.router, prefix="/api/v1")
app.include_router(novels.router, prefix="/api/v1")
app.include_router(storyboard.router, prefix="/api/v1")
app.include_router(assets.router, prefix="/api/v1")
app.include_router(generation.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(episodes.router, prefix="/api/v1")


@app.on_event("startup")
def _migrate():
    """启动时幂等迁移：补 episodes 表 / episode_id 列 / 旧数据回填。"""
    from app.schema import migrate_episodes
    from app.db import get_db
    db = get_db()
    try:
        migrate_episodes(db)
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "projects.html")

@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str):
    return templates.TemplateResponse(request, "project_detail.html", {"project_id": project_id})

@app.get("/projects/{project_id}/novels", response_class=HTMLResponse)
async def novel_edit(request: Request, project_id: str):
    return templates.TemplateResponse(request, "novel_edit.html", {"project_id": project_id})

@app.get("/projects/{project_id}/storyboard", response_class=HTMLResponse)
async def storyboard_edit(request: Request, project_id: str):
    return templates.TemplateResponse(request, "storyboard_edit.html", {"project_id": project_id})

@app.get("/projects/{project_id}/assets", response_class=HTMLResponse)
async def asset_review(request: Request, project_id: str):
    return templates.TemplateResponse(request, "asset_review.html", {"project_id": project_id})

@app.get("/projects/{project_id}/export", response_class=HTMLResponse)
async def export_page(request: Request, project_id: str):
    return templates.TemplateResponse(request, "export.html", {"project_id": project_id})


# ============ 文件服务 ============
from fastapi.responses import FileResponse
from app.services.config import project_dir as _project_dir

@app.get("/api/v1/system/gpu-status")
async def gpu_status():
    """返回 ComfyUI、xDiT 和 gpu-gateway 的当前健康状态。"""
    from app.services import system_status
    return {"success": True, "data": system_status.get_gpu_status()}

@app.get("/files/{project_id}/{file_path:path}")
async def serve_file(project_id: str, file_path: str):
    """提供项目文件下载 (图片/视频/导出)"""
    import os as _os
    base = _project_dir(project_id)
    full = _os.path.join(base, file_path)
    # 防目录穿越
    if not _os.path.abspath(full).startswith(_os.path.abspath(base)):
        return {"success": False, "error": {"code": "FORBIDDEN", "message": "invalid path"}}
    if not _os.path.isfile(full):
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "file not found"}}
    return FileResponse(full)
