from fastapi import APIRouter, HTTPException
from app.db import get_db
from app.models import AssetCreate
import uuid
from datetime import datetime

router = APIRouter(tags=["assets"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM assets WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/projects/{project_id}/assets")
def create_asset(project_id: str, a: AssetCreate):
    db = get_db()
    aid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO assets (id,project_id,asset_type,name,description,appearance_anchor,costume_anchor,temperament_anchor,time,weather,lighting,color_tendency,negative_prompt,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (aid, project_id, a.asset_type, a.name, a.description, a.appearance_anchor, a.costume_anchor, a.temperament_anchor, a.time, a.weather, a.lighting, a.color_tendency, a.negative_prompt, 'draft', ts, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"asset_id": aid}}

@router.post("/assets/{asset_id}/confirm")
def confirm_asset(asset_id: str):
    db = get_db()
    ts = now()
    db.execute("UPDATE assets SET status='confirmed', updated_at=? WHERE id=?", (ts, asset_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"confirmed": True}}
