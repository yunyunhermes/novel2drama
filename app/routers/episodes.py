from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.db import get_db
import uuid
from datetime import datetime

router = APIRouter(tags=["episodes"])


def now():
    return datetime.utcnow().isoformat()


class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    target_duration_seconds: Optional[int] = None
    status: Optional[str] = None


@router.get("/projects/{project_id}/episodes")
def list_episodes(project_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT id, project_id, episode_no, title, summary, status, "
        "current_novel_version_id, target_duration_seconds, created_at, updated_at "
        "FROM episodes WHERE project_id=? AND deleted_at IS NULL ORDER BY episode_no ASC",
        (project_id,),
    ).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.post("/projects/{project_id}/episodes")
def create_episode(project_id: str):
    db = get_db()
    # 校验项目存在
    if not db.execute(
        "SELECT id FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)
    ).fetchone():
        db.close()
        raise HTTPException(404, "project not found")
    pid = str(uuid.uuid4())
    ts = now()
    max_no = db.execute(
        "SELECT MAX(episode_no) FROM episodes WHERE project_id=?", (project_id,)
    ).fetchone()[0] or 0
    ep_no = max_no + 1
    db.execute(
        "INSERT INTO episodes (id,project_id,episode_no,title,status,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (pid, project_id, ep_no, f"第{ep_no}集", "draft", ts, ts),
    )
    db.commit()
    db.close()
    return {"success": True, "data": {"episode_id": pid, "episode_no": ep_no}}


@router.get("/episodes/{episode_id}")
def get_episode(episode_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "episode not found")
    return {"success": True, "data": dict(row)}


@router.patch("/episodes/{episode_id}")
def update_episode(episode_id: str, e: EpisodeUpdate):
    db = get_db()
    if not db.execute("SELECT id FROM episodes WHERE id=?", (episode_id,)).fetchone():
        db.close()
        raise HTTPException(404, "episode not found")
    updates = []
    params = []
    for f in ("title", "summary", "target_duration_seconds", "status"):
        v = getattr(e, f, None)
        if v is not None:
            updates.append(f"{f}=?")
            params.append(v)
    if not updates:
        db.close()
        return {"success": True, "data": {"episode_id": episode_id}}
    updates.append("updated_at=?")
    params.append(now())
    params.append(episode_id)
    db.execute(f"UPDATE episodes SET {', '.join(updates)} WHERE id=?", params)
    db.commit()
    db.close()
    return {"success": True, "data": {"episode_id": episode_id}}


@router.delete("/episodes/{episode_id}")
def delete_episode(episode_id: str):
    db = get_db()
    ts = now()
    db.execute(
        "UPDATE episodes SET deleted_at=?, updated_at=? WHERE id=?",
        (ts, ts, episode_id),
    )
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}
