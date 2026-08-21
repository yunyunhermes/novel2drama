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


# ============ 资产抽卡接口 (接线) ============
from fastapi import Body
import json as _json

@router.post("/assets/{asset_id}/candidates/generate")
def gen_asset_candidates(asset_id: str, payload: dict = Body(default={})):
    """触发 Z-Image 资产候选图生成, 返回 job_id"""
    db = get_db()
    a = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not a:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "asset not found"}}
    a = dict(a)
    jid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO jobs (id,project_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
               (jid, a["project_id"], "z_image_asset", "asset", asset_id, _json.dumps(payload), 'queued', ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"job_id": jid, "status": "queued"}}


@router.get("/assets/{asset_id}/candidates")
def list_asset_candidates(asset_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM asset_candidates WHERE asset_id=? ORDER BY created_at DESC", (asset_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("/asset-candidates/{candidate_id}/select")
def select_asset_candidate(candidate_id: str):
    from app.services import asset_pipeline
    db = get_db()
    try:
        asset_pipeline.select_candidate(db, candidate_id)
        db.close()
        return {"success": True, "data": {"selected": True}}
    except ValueError as e:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": str(e)}}
