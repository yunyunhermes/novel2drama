from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os

app = FastAPI(title="novel2drama", version="0.1.0")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

from app.routers import projects, novels, storyboard, assets, generation, review, export

app.include_router(projects.router, prefix="/api/v1")
app.include_router(novels.router, prefix="/api/v1")
app.include_router(storyboard.router, prefix="/api/v1")
app.include_router(assets.router, prefix="/api/v1")
app.include_router(generation.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("projects.html", {"request": request})

@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str):
    return templates.TemplateResponse("project_detail.html", {"request": request, "project_id": project_id})

@app.get("/projects/{project_id}/novels", response_class=HTMLResponse)
async def novel_edit(request: Request, project_id: str):
    return templates.TemplateResponse("novel_edit.html", {"request": request, "project_id": project_id})

@app.get("/projects/{project_id}/storyboard", response_class=HTMLResponse)
async def storyboard_edit(request: Request, project_id: str):
    return templates.TemplateResponse("storyboard_edit.html", {"request": request, "project_id": project_id})

@app.get("/projects/{project_id}/assets", response_class=HTMLResponse)
async def asset_review(request: Request, project_id: str):
    return templates.TemplateResponse("asset_review.html", {"request": request, "project_id": project_id})

@app.get("/projects/{project_id}/export", response_class=HTMLResponse)
async def export_page(request: Request, project_id: str):
    return templates.TemplateResponse("export.html", {"request": request, "project_id": project_id})
