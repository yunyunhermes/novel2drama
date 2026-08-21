from fastapi import APIRouter, HTTPException
from app.db import get_db
from app.models import NovelVersionCreate
import uuid
from datetime import datetime

router = APIRouter(tags=["novels"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/novel-versions")
def list_novel_versions(project_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM novel_versions WHERE project_id=? ORDER BY version_no DESC", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/projects/{project_id}/novel-versions")
def create_novel_version(project_id: str, v: NovelVersionCreate):
    db = get_db()
    vid = str(uuid.uuid4())
    ts = now()
    max_ver = db.execute("SELECT MAX(version_no) FROM novel_versions WHERE project_id=?", (project_id,)).fetchone()[0] or 0
    db.execute("INSERT INTO novel_versions (id,project_id,title,source_text,version_no,created_at) VALUES (?,?,?,?,?,?)",
               (vid, project_id, v.title, v.source_text, max_ver+1, ts))
    db.execute("UPDATE projects SET current_novel_version_id=?, updated_at=? WHERE id=?", (vid, ts, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"version_id": vid}}

@router.post("/projects/{project_id}/novel-versions/{version_id}/activate")
def activate_novel_version(project_id: str, version_id: str):
    db = get_db()
    ts = now()
    db.execute("UPDATE novel_versions SET is_active=0 WHERE project_id=?", (project_id,))
    db.execute("UPDATE novel_versions SET is_active=1 WHERE id=?", (version_id,))
    db.execute("UPDATE projects SET current_novel_version_id=?, updated_at=? WHERE id=?", (version_id, ts, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"activated": True}}
