from fastapi import APIRouter, HTTPException, UploadFile, File, Form
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
    rows = db.execute(
        "SELECT a.*, c.image_path AS selected_image "
        "FROM assets a LEFT JOIN asset_candidates c ON c.id=a.selected_candidate_id "
        "WHERE a.project_id=? ORDER BY a.created_at DESC",
        (project_id,),
    ).fetchall()
    data = []
    for r in rows:
        d = dict(r)
        cands = db.execute(
            "SELECT id, image_path, status, generator FROM asset_candidates "
            "WHERE asset_id=? ORDER BY created_at DESC",
            (d["id"],),
        ).fetchall()
        d["candidates"] = [dict(c) for c in cands]
        data.append(d)
    db.close()
    return {"success": True, "data": data}

# 资产类型 -> 上传/存储子目录
ASSET_SUBDIR_MAP = {"character": "assets/characters", "scene": "assets/scenes", "item": "assets/items"}


@router.post("/projects/{project_id}/assets")
def create_asset(project_id: str, a: AssetCreate):
    if a.asset_type not in ("character", "scene", "item"):
        return {"success": False, "error": {"code": "INVALID_ASSET_TYPE",
                                            "message": "asset_type must be character/scene/item"}}
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
    """触发资产候选图生成 (image2 渠道), 返回 job_id。
    payload 支持: count/size/aspect/view_mode/use_ref/quality/resolution/prompt_override。"""
    db = get_db()
    a = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not a:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "asset not found"}}
    a = dict(a)
    # asset_type 白名单 (防御非法类型)
    if a["asset_type"] not in ("character", "scene", "item"):
        db.close()
        return {"success": False, "error": {"code": "INVALID_ASSET_TYPE",
                                            "message": f"unsupported asset_type: {a['asset_type']}"}}
    jid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO jobs (id,project_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
               (jid, a["project_id"], "image2_asset", "asset", asset_id, _json.dumps(payload), 'queued', ts))
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


# ============ 资产上传 (直接上传本地图片) ============
import os as _os
from app.services import storage

@router.post("/projects/{project_id}/assets/upload")
async def upload_asset(project_id: str,
    file: UploadFile = File(...),
    asset_type: str = Form("character"),
    name: str = Form(...),
    description: str = Form(None),
    appearance_anchor: str = Form(None),
    costume_anchor: str = Form(None),
    temperament_anchor: str = Form(None),
    time: str = Form(None), weather: str = Form(None),
    lighting: str = Form(None), color_tendency: str = Form(None),
    negative_prompt: str = Form(None)):
    """上传本地图片作为资产锚点素材，直接成为该资产的选定候选图。"""
    db = get_db()
    try:
        if not db.execute("SELECT id FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone():
            raise HTTPException(404, "project not found")
        if asset_type not in ASSET_SUBDIR_MAP:
            raise HTTPException(400, "asset_type must be character/scene/item")
        sub = ASSET_SUBDIR_MAP[asset_type]
        storage.ensure_project_dirs(project_id)
        ext = _os.path.splitext(file.filename or "")[1] or ".jpg"
        if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = ".jpg"
        fname = f"{uuid.uuid4()}{ext}"
        data = await file.read()
        abspath = storage.save_bytes(project_id, sub, fname, data)
        rel = storage.get_rel_path(project_id, abspath)
        aid = str(uuid.uuid4()); cid = str(uuid.uuid4()); ts = now()
        db.execute(
            "INSERT INTO assets (id,project_id,asset_type,name,description,appearance_anchor,costume_anchor,temperament_anchor,time,weather,lighting,color_tendency,negative_prompt,status,selected_candidate_id,preview_candidate_id,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, project_id, asset_type, name, description, appearance_anchor, costume_anchor, temperament_anchor, time, weather, lighting, color_tendency, negative_prompt, 'draft', None, None, ts, ts))
        db.execute(
            "INSERT INTO asset_candidates (id,asset_id,generator,prompt,negative_prompt,image_path,seed,status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, aid, 'user_upload', f"{name} · 用户上传素材", negative_prompt, rel, None, 'selected', ts))
        db.execute("UPDATE assets SET selected_candidate_id=?, updated_at=? WHERE id=?", (cid, ts, aid))
        db.commit()
        return {"success": True, "data": {"asset_id": aid, "candidate_id": cid, "image_path": rel, "status": "draft"}}
    finally:
        db.close()
