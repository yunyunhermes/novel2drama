from fastapi import APIRouter
from app.db import get_db
from app.models import ExportCreate
import uuid, json
from typing import Optional
from datetime import datetime

router = APIRouter(tags=["export"])

def now():
    return datetime.utcnow().isoformat()


# ============ 导出接口 (接线) ============
from fastapi import Body
import json as _json
import uuid as _uuid
from datetime import datetime as _dt

def _now():
    return _dt.utcnow().isoformat()

@router.post("/projects/{project_id}/exports")
def create_export(project_id: str, payload: dict = Body(default={})):
    """创建导出任务 (触发 ffmpeg 拼接)"""
    db = get_db()
    episode_id = payload.get("episode_id")
    segment_ids = payload.get("segment_ids", [])
    if not segment_ids:
        # 默认取当前集所有已确认段
        rows = db.execute(
            "SELECT id FROM segments WHERE project_id=? AND status='confirmed' AND (? IS NULL OR episode_id=?) ORDER BY sort_order",
            (project_id, episode_id, episode_id)).fetchall()
        segment_ids = [r[0] for r in rows]
    if not segment_ids:
        db.close()
        return {"success": False, "error": {"code": "NO_SEGMENTS", "message": "没有可导出的已确认段"}}
    eid = str(_uuid.uuid4())
    ts = _now()
    title = payload.get("title", f"导出_{ts[:10]}")
    db.execute(
        "INSERT INTO exports (id,project_id,episode_id,title,segment_ids_json,resolution,fps,status,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (eid, project_id, episode_id, title, _json.dumps(segment_ids),
         payload.get("resolution","1280x720"), payload.get("fps",24), "draft", ts, ts))
    # 触发 ffmpeg job
    jid = str(_uuid.uuid4())
    db.execute("INSERT INTO jobs (id,project_id,episode_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (jid, project_id, episode_id, "ffmpeg_export", "export", eid, _json.dumps(payload), 'queued', ts))
    db.execute("UPDATE exports SET status='queued', updated_at=? WHERE id=?", (ts, eid))
    db.commit()
    db.close()
    return {"success": True, "data": {"export_id": eid, "job_id": jid, "status": "queued", "segment_count": len(segment_ids)}}


@router.get("/exports/{export_id}")
def get_export(export_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM exports WHERE id=?", (export_id,)).fetchone()
    db.close()
    if not row:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "export not found"}}
    return {"success": True, "data": dict(row)}


@router.get("/projects/{project_id}/exports")
def list_exports(project_id: str, episode_id: Optional[str] = None):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM exports WHERE project_id=? AND (? IS NULL OR episode_id=?) ORDER BY created_at DESC",
        (project_id, episode_id, episode_id),
    ).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}
