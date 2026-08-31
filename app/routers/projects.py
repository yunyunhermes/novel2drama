from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.db import get_db
from app.models import ProjectCreate
import uuid
from datetime import datetime

router = APIRouter(prefix="/projects", tags=["projects"])

def now():
    return datetime.utcnow().isoformat()

@router.get("")
def list_projects():
    db = get_db()
    rows = db.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY updated_at DESC").fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("")
def create_project(p: ProjectCreate):
    db = get_db()
    pid = str(uuid.uuid4())
    ts = now()
    data_dir = f"data/projects/{pid}"
    db.execute("INSERT INTO projects (id,name,description,status,target_duration_seconds,style_prompt,data_dir,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (pid, p.name, p.description, 'draft', p.target_duration_seconds, p.style_prompt, data_dir, ts, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"project_id": pid, "status": "draft"}}

@router.get("/{project_id}")
def get_project(project_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return {"success": True, "data": dict(row)}

@router.patch("/{project_id}")
def update_project(project_id: str, p: ProjectCreate):
    db = get_db()
    ts = now()
    db.execute("UPDATE projects SET name=?,description=?,target_duration_seconds=?,style_prompt=?,updated_at=? WHERE id=?",
               (p.name, p.description, p.target_duration_seconds, p.style_prompt, ts, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"project_id": project_id}}

@router.delete("/{project_id}")
def delete_project(project_id: str):
    db = get_db()
    ts = now()
    db.execute("UPDATE projects SET deleted_at=? WHERE id=?", (ts, project_id))
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}


# ==================== AI 助手现状聚合（item② 省 token） ====================
@router.get("/{project_id}/context")
def get_project_context(project_id: str, episode_id: str = None, page: str = None):
    """一键聚合项目/分集/当前集/版本/段落/资产现状，供 agent 开场用，替代逐个 find/cat。"""
    db = get_db()
    proj = db.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    if not proj:
        db.close()
        raise HTTPException(404, "Project not found")

    # 分集（按集号排序）
    eps = db.execute(
        "SELECT id,episode_no,title FROM episodes WHERE project_id=? AND deleted_at IS NULL ORDER BY episode_no",
        (project_id,)).fetchall()
    eps_list = [dict(r) for r in eps]

    # 当前集：episode_id 参数优先，否则默认第 1 集
    current_episode = episode_id or (eps_list[0]["id"] if eps_list else None)

    # 小说版本
    nv_rows = db.execute("SELECT COUNT(*) c FROM novel_versions WHERE project_id=?", (project_id,)).fetchone()
    nv_load = db.execute(
        "SELECT id,title,source_text,is_active FROM novel_versions WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)).fetchall()
    active = [r for r in nv_load if r["is_active"]]
    active_row = active[0] if active else None
    novel_versions = {
        "count": nv_rows["c"],
        "active_version_id": active_row["id"] if active_row else None,
        "active_title": active_row["title"] if active_row else None,
        "active_text_length": len(active_row["source_text"]) if active_row else 0,
    }

    # 段落（当前集内，摘要截断；最多返回 100 条防 token 爆炸）
    seg_rows = db.execute(
        "SELECT sort_order,summary,status FROM segments WHERE project_id=? AND episode_id=? "
        "ORDER BY sort_order LIMIT 100",
        (project_id, current_episode)).fetchall()
    seg_list = [{"sort_order": r["sort_order"], "status": r["status"],
                 "summary": (r["summary"] or "")[:100]} for r in seg_rows]

    # 资产
    char_c = db.execute("SELECT COUNT(*) c FROM assets WHERE project_id=? AND asset_type='character'",
                        (project_id,)).fetchone()["c"]
    scene_c = db.execute("SELECT COUNT(*) c FROM assets WHERE project_id=? AND asset_type='scene'",
                         (project_id,)).fetchone()["c"]

    # 项目级字段
    project = {k: proj[k] for k in ("id", "name", "status", "description",
                                    "target_duration_seconds", "style_prompt")}

    db.close()
    return {"success": True, "data": {
        "project": project,
        "episodes": eps_list,
        "current_episode": current_episode,
        "novel_versions": novel_versions,
        "segments": {"count": len(seg_list), "list": seg_list},
        "assets": {"characters": char_c, "scenes": scene_c},
        "page": page,
    }}


# ==================== 项目数据版本号（item③ 多人实时刷新的打底） ====================
@router.get("/{project_id}/version")
def get_project_version(project_id: str):
    from app.services import agent_store as astore
    return {"success": True, "data": {"version": astore.get_version(project_id)}}


# ==================== SSE 事件总线（item③ 实时增强，进程内广播） ====================
@router.get("/{project_id}/events")
async def project_events(project_id: str):
    from app.services.events import subscribe, unsubscribe
    from app.services import agent_store as astore
    q = subscribe(project_id)

    async def gen():
        try:
            yield sse({"type": "hello", "project_id": project_id,
                       "version": astore.get_version(project_id)})
            while True:
                ev = await q.get()
                yield sse(ev)
        finally:
            unsubscribe(project_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Content-Type": "text/event-stream; charset=utf-8"})


def sse(obj: dict) -> str:
    import json
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
