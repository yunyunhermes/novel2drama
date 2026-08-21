from fastapi import APIRouter, HTTPException, Body
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

@router.patch("/projects/{project_id}/segments/{segment_id}")
def update_segment(project_id: str, segment_id: str, payload: dict = Body(default={})):
    db = get_db()
    db.execute(
        "UPDATE segments SET summary=?, start_transition=?, end_transition=?, updated_at=? WHERE id=? AND project_id=?",
        (payload.get("summary", ""), payload.get("start_transition", ""),
         payload.get("end_transition", ""), now(), segment_id, project_id),
    )
    db.commit()
    db.close()
    return {"success": True, "data": {"segment_id": segment_id}}

@router.delete("/projects/{project_id}/segments/{segment_id}")
def delete_segment(project_id: str, segment_id: str):
    db = get_db()
    db.execute("DELETE FROM shot_beats WHERE segment_id=?", (segment_id,))
    db.execute("DELETE FROM segments WHERE id=? AND project_id=?", (segment_id, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}

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

@router.patch("/beats/{beat_id}")
def update_beat(beat_id: str, payload: dict = Body(default={} )):
    allowed = {"start_ms", "end_ms", "shot_size", "camera_movement", "character_action",
                "scene_change", "lighting", "composition", "style", "emotion", "transition"}
    fields = [key for key in payload if key in allowed]
    if not fields:
        return {"success": True, "data": {"beat_id": beat_id}}
    values = [payload[key] for key in fields]
    assignments = ", ".join(f"{key}=?" for key in fields)
    db = get_db()
    db.execute(f"UPDATE shot_beats SET {assignments}, updated_at=? WHERE id=?", (*values, now(), beat_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"beat_id": beat_id}}

@router.delete("/beats/{beat_id}")
def delete_beat(beat_id: str):
    db = get_db()
    db.execute("DELETE FROM shot_beats WHERE id=?", (beat_id,))
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}


# ============ 分镜生成接口 (接线) ============
from fastapi import Body
import json as _json
import uuid as _uuid
from datetime import datetime as _dt

def _now():
    return _dt.utcnow().isoformat()

@router.post("/projects/{project_id}/storyboard/generate")
def gen_storyboard(project_id: str, payload: dict = Body(default={})):
    """触发 LLM 分镜生成, 返回 job_id"""
    db = get_db()
    jid = str(_uuid.uuid4())
    ts = _now()
    db.execute("INSERT INTO jobs (id,project_id,job_type,target_type,target_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
               (jid, project_id, "llm_storyboard", "project", project_id, _json.dumps(payload), 'queued', ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"job_id": jid, "status": "queued"}}


@router.post("/segments/{segment_id}/keyframe-prompt/build")
def build_keyframe_prompt_api(segment_id: str):
    """用规则构建段首图 prompt 并写回 segment"""
    from app.services.prompt_builder import build_keyframe_prompt, build_negative_prompt
    db = get_db()
    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not seg:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "segment not found"}}
    seg = dict(seg)
    project_id = seg["project_id"]
    proj = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    style_prompt = dict(proj).get("style_prompt") if proj else None
    chars = [dict(r) for r in db.execute(
        "SELECT a.* FROM assets a JOIN segment_asset_refs r ON a.id=r.asset_id WHERE r.segment_id=? AND r.asset_type='character'",
        (segment_id,)).fetchall()]
    scenes = [dict(r) for r in db.execute(
        "SELECT a.* FROM assets a JOIN segment_asset_refs r ON a.id=r.asset_id WHERE r.segment_id=? AND r.asset_type='scene'",
        (segment_id,)).fetchall()]
    first_beat = db.execute("SELECT * FROM shot_beats WHERE segment_id=? ORDER BY start_ms LIMIT 1", (segment_id,)).fetchone()
    first_beat = dict(first_beat) if first_beat else None
    prompt = build_keyframe_prompt(seg, chars, scenes, style_prompt, first_beat)
    negative = build_negative_prompt(seg, chars, scenes)
    ts = _now()
    db.execute("UPDATE segments SET keyframe_prompt=?, negative_prompt=?, updated_at=? WHERE id=?",
               (prompt, negative, ts, segment_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"keyframe_prompt": prompt, "negative_prompt": negative}}


@router.post("/segments/{segment_id}/h3-prompt/build")
def build_h3_prompt_api(segment_id: str):
    """用规则构建 H3 连续 prompt 并写回 segment"""
    from app.services.prompt_builder import build_h3_prompt, build_negative_prompt
    db = get_db()
    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not seg:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "segment not found"}}
    seg = dict(seg)
    project_id = seg["project_id"]
    proj = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    style_prompt = dict(proj).get("style_prompt") if proj else None
    chars = [dict(r) for r in db.execute(
        "SELECT a.* FROM assets a JOIN segment_asset_refs r ON a.id=r.asset_id WHERE r.segment_id=? AND r.asset_type='character'",
        (segment_id,)).fetchall()]
    scenes = [dict(r) for r in db.execute(
        "SELECT a.* FROM assets a JOIN segment_asset_refs r ON a.id=r.asset_id WHERE r.segment_id=? AND r.asset_type='scene'",
        (segment_id,)).fetchall()]
    beats = [dict(r) for r in db.execute("SELECT * FROM shot_beats WHERE segment_id=? ORDER BY start_ms", (segment_id,)).fetchall()]
    prompt = build_h3_prompt(seg, beats, chars, scenes, style_prompt)
    negative = build_negative_prompt(seg, chars, scenes)
    ts = _now()
    db.execute("UPDATE segments SET h3_prompt=?, negative_prompt=?, updated_at=? WHERE id=?",
               (prompt, negative, ts, segment_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"h3_prompt": prompt, "negative_prompt": negative}}


@router.get("/projects/{project_id}/agent-patches")
def list_agent_patches(project_id: str):
    """列出项目的 Agent patch (待确认)"""
    db = get_db()
    rows = db.execute("SELECT * FROM agent_patches WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("/agent-patches/{patch_id}/apply")
def apply_agent_patch(patch_id: str):
    """应用 Agent patch (第一版: 只支持 create_segment)"""
    db = get_db()
    p = db.execute("SELECT * FROM agent_patches WHERE id=?", (patch_id,)).fetchone()
    if not p:
        db.close()
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "patch not found"}}
    p = dict(p)
    if p["status"] != "pending":
        db.close()
        return {"success": False, "error": {"code": "ALREADY_PROCESSED", "message": f"patch status: {p['status']}"}}
    patch = _json.loads(p["patch_json"])
    ops = patch.get("ops", [])
    applied = 0
    errors = []
    for op in ops:
        if op.get("type") != "create_segment":
            errors.append(f"unsupported op type: {op.get('type')}")
            continue
        data = op.get("data", {})
        sid = str(_uuid.uuid4())
        ts = _now()
        # 获取当前最大 sort_order
        max_so = db.execute("SELECT MAX(sort_order) FROM segments WHERE project_id=?",
                            (p["project_id"],)).fetchone()[0] or 0
        db.execute(
            "INSERT INTO segments (id,project_id,sort_order,summary,start_transition,end_transition,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, p["project_id"], max_so+1, data.get("summary",""),
             data.get("start_transition",""), data.get("end_transition",""),
             "draft", ts, ts))
        # 节拍
        for bi, beat in enumerate(data.get("beats", [])):
            bid = str(_uuid.uuid4())
            db.execute(
                "INSERT INTO shot_beats (id,segment_id,sort_order,start_ms,end_ms,shot_size,camera_movement,character_action,scene_change,lighting,composition,style,emotion,transition,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (bid, sid, bi+1, beat.get("start_ms",0), beat.get("end_ms",0),
                 beat.get("shot_size",""), beat.get("camera_movement",""),
                 beat.get("character_action",""), beat.get("scene_change",""),
                 beat.get("lighting",""), beat.get("composition",""),
                 beat.get("style",""), beat.get("emotion",""), beat.get("transition",""),
                 ts, ts))
        applied += 1
    ts = _now()
    db.execute("UPDATE agent_patches SET status='applied', applied_at=? WHERE id=?", (ts, patch_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"applied_segments": applied, "errors": errors}}


@router.post("/agent-patches/{patch_id}/reject")
def reject_agent_patch(patch_id: str):
    db = get_db()
    ts = _now()
    db.execute("UPDATE agent_patches SET status='rejected', applied_at=? WHERE id=?", (ts, patch_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"rejected": True}}
