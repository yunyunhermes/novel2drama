from fastapi import APIRouter
from app.db import get_db
from app.models import JobCreate
import uuid
from datetime import datetime

router = APIRouter(tags=["generation"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/projects/{project_id}/jobs")
def create_job(project_id: str, j: JobCreate):
    db = get_db()
    jid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO jobs (id,project_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
               (jid, project_id, j.job_type, j.target_type, j.target_id, j.payload_json, 'queued', ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"job_id": jid}}

@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    db.close()
    if not row:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found"}}
    return {"success": True, "data": dict(row)}
