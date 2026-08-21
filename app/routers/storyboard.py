from fastapi import APIRouter, HTTPException
from app.db import get_db
from app.models import SegmentCreate, ShotBeatCreate
import uuid
from datetime import datetime

router = APIRouter(tags=["storyboard"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/segments")
def list_segments(project_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM segments WHERE project_id=? ORDER BY sort_order", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/projects/{project_id}/segments")
def create_segment(project_id: str, s: SegmentCreate):
    db = get_db()
    sid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO segments (id,project_id,sort_order,summary,start_transition,end_transition,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (sid, project_id, s.sort_order, s.summary, s.start_transition, s.end_transition, 'draft', ts, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"segment_id": sid}}

@router.get("/segments/{segment_id}/beats")
def list_beats(segment_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM shot_beats WHERE segment_id=? ORDER BY sort_order", (segment_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/segments/{segment_id}/beats")
def create_beat(segment_id: str, b: ShotBeatCreate):
    db = get_db()
    bid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO shot_beats (id,segment_id,sort_order,start_ms,end_ms,shot_size,camera_movement,character_action,scene_change,lighting,composition,style,emotion,transition,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (bid, segment_id, b.sort_order, b.start_ms, b.end_ms, b.shot_size, b.camera_movement, b.character_action, b.scene_change, b.lighting, b.composition, b.style, b.emotion, b.transition, ts, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"beat_id": bid}}

@router.delete("/beats/{beat_id}")
def delete_beat(beat_id: str):
    db = get_db()
    db.execute("DELETE FROM shot_beats WHERE id=?", (beat_id,))
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}
