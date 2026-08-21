from fastapi import APIRouter
from app.db import get_db
from app.models import ExportCreate
import uuid, json
from datetime import datetime

router = APIRouter(tags=["export"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/exports")
def list_exports(project_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM exports WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/projects/{project_id}/exports")
def create_export(project_id: str, e: ExportCreate):
    db = get_db()
    eid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO exports (id,project_id,title,segment_ids_json,resolution,fps,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (eid, project_id, e.title, json.dumps(e.segment_ids), e.resolution, e.fps, 'draft', ts, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"export_id": eid}}
