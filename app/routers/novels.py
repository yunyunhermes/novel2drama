from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.db import get_db
from app.models import NovelVersionCreate
from app.services.chapter_parser import parse_chapters
import uuid
from datetime import datetime

router = APIRouter(tags=["novels"])

def now():
    return datetime.utcnow().isoformat()


# ============ 版本管理 ============

@router.get("/projects/{project_id}/novel-versions")
def list_novel_versions(project_id: str, episode_id: Optional[str] = None):
    db = get_db()
    rows = db.execute(
        "SELECT id, project_id, episode_id, title, version_no, is_active, created_at, "
        "length(source_text) AS text_length, "
        "substr(source_text, 1, 200) AS text_preview "
        "FROM novel_versions WHERE project_id=? AND (? IS NULL OR episode_id=?) "
        "ORDER BY version_no DESC",
        (project_id, episode_id, episode_id),
    ).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.get("/novel-versions/{version_id}")
def get_novel_version(version_id: str):
    """返回完整版本（含 source_text 全文）。前端"原文展示"用。"""
    db = get_db()
    row = db.execute("SELECT * FROM novel_versions WHERE id=?", (version_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "version not found")
    return {"success": True, "data": dict(row)}


@router.post("/projects/{project_id}/novel-versions")
def create_novel_version(project_id: str, v: NovelVersionCreate):
    db = get_db()
    vid = str(uuid.uuid4())
    ts = now()
    # version_no 按集递增
    where = "project_id=?"
    params = [project_id]
    if v.episode_id:
        where += " AND episode_id=?"
        params.append(v.episode_id)
    max_ver = db.execute(
        f"SELECT MAX(version_no) FROM novel_versions WHERE {where}", params
    ).fetchone()[0] or 0
    # 如果当前集还没有任何 active 版本，把新版本自动设为 active
    has_active = db.execute(
        f"SELECT COUNT(*) FROM novel_versions WHERE {where} AND is_active=1", params
    ).fetchone()[0]
    is_active = 0 if has_active else 1
    db.execute(
        "INSERT INTO novel_versions (id,project_id,episode_id,title,source_text,version_no,is_active,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (vid, project_id, v.episode_id, v.title, v.source_text, max_ver + 1, is_active, ts),
    )
    # 同步当前集的 current_novel_version_id（保持一致性）
    if is_active:
        db.execute(
            "UPDATE projects SET current_novel_version_id=?, updated_at=? WHERE id=?",
            (vid, ts, project_id),
        )
        if v.episode_id:
            db.execute(
                "UPDATE episodes SET current_novel_version_id=?, updated_at=? WHERE id=?",
                (vid, ts, v.episode_id),
            )
    db.commit()
    db.close()
    return {"success": True, "data": {"version_id": vid, "is_active": bool(is_active)}}


@router.post("/projects/{project_id}/novel-versions/{version_id}/activate")
def activate_novel_version(project_id: str, version_id: str, episode_id: Optional[str] = None):
    db = get_db()
    ts = now()
    # 校验版本属于该项目
    row = db.execute(
        "SELECT id FROM novel_versions WHERE id=? AND project_id=?",
        (version_id, project_id),
    ).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "version not found in this project")
    # 取消当前集（或项目）的其他 active
    where = "project_id=?"
    params = [project_id]
    if episode_id:
        where += " AND episode_id=?"
        params.append(episode_id)
    db.execute(f"UPDATE novel_versions SET is_active=0 WHERE {where}", params)
    db.execute("UPDATE novel_versions SET is_active=1 WHERE id=?", (version_id,))
    db.execute(
        "UPDATE projects SET current_novel_version_id=?, updated_at=? WHERE id=?",
        (version_id, ts, project_id),
    )
    if episode_id:
        db.execute(
            "UPDATE episodes SET current_novel_version_id=?, updated_at=? WHERE id=?",
            (version_id, ts, episode_id),
        )
    db.commit()
    db.close()
    return {"success": True, "data": {"activated": True}}


# ============ 章节管理 ============

@router.get("/novel-versions/{version_id}/chapters")
def list_chapters(version_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT id, novel_version_id, title, sort_order, included, "
        "length(content) AS text_length, substr(content, 1, 120) AS content_preview, "
        "created_at, updated_at "
        "FROM novel_chapters WHERE novel_version_id=? ORDER BY sort_order ASC",
        (version_id,),
    ).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.get("/chapters/{chapter_id}")
def get_chapter(chapter_id: str):
    """返回单章完整内容。"""
    db = get_db()
    row = db.execute("SELECT * FROM novel_chapters WHERE id=?", (chapter_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "chapter not found")
    return {"success": True, "data": dict(row)}


@router.post("/novel-versions/{version_id}/parse-chapters")
def parse_version_chapters(version_id: str):
    """触发章节解析：从 source_text 切出章节，写入 novel_chapters。
    幂等：先删除旧章节再重新写入。"""
    db = get_db()
    row = db.execute(
        "SELECT source_text FROM novel_versions WHERE id=?", (version_id,)
    ).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "version not found")
    source_text = row["source_text"]

    chapters = parse_chapters(source_text)
    ts = now()
    # 幂等：删旧写新
    db.execute("DELETE FROM novel_chapters WHERE novel_version_id=?", (version_id,))
    for ch in chapters:
        db.execute(
            "INSERT INTO novel_chapters (id,novel_version_id,title,content,sort_order,included,created_at,updated_at) "
            "VALUES (?,?,?,?,?,1,?,?)",
            (str(uuid.uuid4()), version_id, ch.title, ch.content, ch.sort_order, ts, ts),
        )
    db.commit()
    db.close()
    return {"success": True, "data": {"parsed": len(chapters)}}


class ChapterPatch(BaseModel):
    title: Optional[str] = None
    included: Optional[bool] = None
    content: Optional[str] = None


@router.patch("/chapters/{chapter_id}")
def patch_chapter(chapter_id: str, p: ChapterPatch):
    """编辑章节：标题/是否参与分镜/内容。"""
    db = get_db()
    row = db.execute("SELECT id FROM novel_chapters WHERE id=?", (chapter_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "chapter not found")
    updates = []
    params = []
    if p.title is not None:
        updates.append("title=?")
        params.append(p.title)
    if p.included is not None:
        updates.append("included=?")
        params.append(1 if p.included else 0)
    if p.content is not None:
        updates.append("content=?")
        params.append(p.content)
    if not updates:
        db.close()
        return {"success": True, "data": {"updated": 0}}
    updates.append("updated_at=?")
    params.append(now())
    params.append(chapter_id)
    db.execute(f"UPDATE novel_chapters SET {', '.join(updates)} WHERE id=?", params)
    db.commit()
    db.close()
    return {"success": True, "data": {"updated": 1}}


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: str):
    db = get_db()
    db.execute("DELETE FROM novel_chapters WHERE id=?", (chapter_id,))
    db.commit()
    db.close()
    return {"success": True, "data": {"deleted": True}}
