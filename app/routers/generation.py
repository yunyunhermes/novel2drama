from fastapi import APIRouter
from typing import Optional
from app.db import get_db
from app.models import JobCreate
import uuid
from datetime import datetime

router = APIRouter(tags=["generation"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: str, episode_id: Optional[str] = None):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM jobs WHERE project_id=? AND (? IS NULL OR episode_id=?) ORDER BY created_at DESC",
        (project_id, episode_id, episode_id),
    ).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/projects/{project_id}/jobs")
def create_job(project_id: str, j: JobCreate):
    db = get_db()
    jid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO jobs (id,project_id,episode_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (jid, project_id, j.episode_id, j.job_type, j.target_type, j.target_id, j.payload_json, 'queued', ts))
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


# ============ 生成触发接口 (接线) ============
from fastapi import Body
from typing import Optional
import json as _json

@router.post("/segments/{segment_id}/keyframes/generate")
def gen_keyframes(segment_id: str, payload: dict = Body(default={})):
    """触发 Z-Image 段首图生成, 返回 job_id"""
    db = get_db()
    jid = str(uuid.uuid4())
    ts = now()
    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not seg:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "segment not found"}}
    project_id = dict(seg)["project_id"]
    episode_id = dict(seg).get("episode_id")
    db.execute("INSERT INTO jobs (id,project_id,episode_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (jid, project_id, episode_id, "z_image_keyframe", "segment", segment_id, _json.dumps(payload), 'queued', ts))
    db.execute("UPDATE segments SET status='keyframe_generating', updated_at=? WHERE id=?", (ts, segment_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"job_id": jid, "status": "queued"}}


@router.get("/segments/{segment_id}/keyframes")
def list_keyframes(segment_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM keyframes WHERE segment_id=? ORDER BY created_at DESC", (segment_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("/keyframes/{keyframe_id}/select")
def select_keyframe(keyframe_id: str):
    db = get_db()
    ts = now()
    kf = db.execute("SELECT * FROM keyframes WHERE id=?", (keyframe_id,)).fetchone()
    if not kf:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "keyframe not found"}}
    kf = dict(kf)
    db.execute("UPDATE keyframes SET status='generated' WHERE segment_id=?", (kf["segment_id"],))
    db.execute("UPDATE keyframes SET status='selected' WHERE id=?", (keyframe_id,))
    db.execute("UPDATE segments SET selected_keyframe_id=?, status='keyframe_confirmed', updated_at=? WHERE id=?",
               (keyframe_id, ts, kf["segment_id"]))
    db.commit()
    db.close()
    return {"success": True, "data": {"selected": True}}


@router.post("/segments/{segment_id}/h3-generations")
def gen_h3(segment_id: str, payload: dict = Body(default={})):
    """触发 H3 15s 段生成, payload.quality 支持 preview/high"""
    quality = str(payload.get("quality", "preview")).lower()
    if quality not in ("preview", "high"):
        return {"success": False, "error": {"code": "INVALID_QUALITY", "message": "quality must be preview or high"}}
    payload = dict(payload)
    payload["quality"] = quality
    db = get_db()
    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not seg:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "segment not found"}}
    seg = dict(seg)
    if not seg.get("selected_keyframe_id"):
        db.close()
        return {"success": False, "error": {"code": "NO_KEYFRAME", "message": "请先选定段首图"}}
    jid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO jobs (id,project_id,episode_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (jid, seg["project_id"], seg.get("episode_id"), "h3_segment", "segment", segment_id, _json.dumps(payload), 'queued', ts))
    db.execute("UPDATE segments SET status='h3_generating', updated_at=? WHERE id=?", (ts, segment_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"job_id": jid, "status": "queued"}}


@router.get("/segments/{segment_id}/h3-generations")
def list_h3(segment_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM h3_generations WHERE segment_id=? ORDER BY created_at DESC", (segment_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("/h3-generations/{generation_id}/select")
def select_h3(generation_id: str):
    db = get_db()
    ts = now()
    g = db.execute("SELECT * FROM h3_generations WHERE id=?", (generation_id,)).fetchone()
    if not g:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "generation not found"}}
    g = dict(g)
    db.execute("UPDATE h3_generations SET status='generated' WHERE segment_id=?", (g["segment_id"],))
    db.execute("UPDATE h3_generations SET status='selected', updated_at=? WHERE id=?", (ts, generation_id))
    db.execute("UPDATE segments SET selected_h3_generation_id=?, status='confirmed', updated_at=? WHERE id=?",
               (generation_id, ts, g["segment_id"]))
    db.commit()
    db.close()
    return {"success": True, "data": {"selected": True}}
