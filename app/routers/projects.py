from fastapi import APIRouter, HTTPException
from app.db import get_db
from app.models import ProjectCreate
import uuid
from datetime import datetime

router = APIRouter(prefix="/projects", tags=["projects"])

def now():
    return datetime.utcnow().isoformat()

@router.get("")
def list_projects():
    db = get_db()
    rows = db.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY updated_at DESC").fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("")
def create_project(p: ProjectCreate):
    db = get_db()
    pid = str(uuid.uuid4())
    ts = now()
    data_dir = f"data/projects/{pid}"
    db.execute("INSERT INTO projects (id,name,description,status,target_duration_seconds,style_prompt,data_dir,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (pid, p.name, p.description, 'draft', p.target_duration_seconds, p.style_prompt, data_dir, ts, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"project_id": pid, "status": "draft"}}

@router.get("/{project_id}")
def get_project(project_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return {"success": True, "data": dict(row)}

@router.patch("/{project_id}")
def update_project(project_id: str, p: ProjectCreate):
    db = get_db()
    ts = now()
    db.execute("UPDATE projects SET name=?,description=?,target_duration_seconds=?,style_prompt=?,updated_at=? WHERE id=?",
               (p.name, p.description, p.target_duration_seconds, p.style_prompt, ts, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"project_id": project_id}}

@router.delete("/{project_id}")
def delete_project(project_id: str):
    db = get_db()
    ts = now()
    db.execute("UPDATE projects SET deleted_at=? WHERE id=?", (ts, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}
