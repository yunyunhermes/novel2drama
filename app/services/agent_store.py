"""agent 会话/消息持久化 + 项目数据变更版本号。

全后端 SQLite（禁止 localStorage），多人在同一项目共享同一份状态。

会话/消息模型：
- agent_sessions(id, project_id, title, created_at, updated_at)：会话头，按项目共享。
- agent_messages(id, session_id, role, type, content_json, created_at)：消息逐条，
  content_json 存序列化的 user/assistant/tool/permission 内容。
- project_version(project_id, version, updated_at)：agent 写操作完成后 bump，
  前端轮询 /projects/{id}/version 或 SSE data_changed 感知变化。
"""
import json
import uuid
from datetime import datetime

from app.db import get_db


def now():
    return datetime.utcnow().isoformat()


# ---------- 会话 ----------
def create_session(project_id, title=None):
    """新建一个 UI 会话（按项目共享；title 可后续改）。"""
    db = get_db()
    sid = str(uuid.uuid4())
    ts = now()
    db.execute(
        "INSERT INTO agent_sessions(id,project_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
        (sid, project_id, title or "新会话", ts, ts),
    )
    db.commit()
    db.close()
    return {"id": sid, "project_id": project_id, "title": title or "新会话",
            "created_at": ts, "updated_at": ts}


def list_sessions(project_id):
    db = get_db()
    rows = db.execute(
        "SELECT id,project_id,title,created_at,updated_at FROM agent_sessions "
        "WHERE project_id=? ORDER BY updated_at DESC", (project_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_session(sid):
    db = get_db()
    r = db.execute("SELECT * FROM agent_sessions WHERE id=?", (sid,)).fetchone()
    db.close()
    return dict(r) if r else None


def touch_session(sid):
    db = get_db()
    db.execute("UPDATE agent_sessions SET updated_at=? WHERE id=?", (now(), sid))
    db.commit()
    db.close()


# ---------- 消息 ----------
def add_message(session_id, role, mtype, content):
    """追加一条消息。content 为 dict，序列化到 content_json。"""
    db = get_db()
    mid = str(uuid.uuid4())
    ts = now()
    db.execute(
        "INSERT INTO agent_messages(id,session_id,role,type,content_json,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (mid, session_id, role, mtype, json.dumps(content, ensure_ascii=False), ts),
    )
    db.commit()
    db.close()
    return mid


def list_messages(session_id):
    db = get_db()
    rows = db.execute(
        "SELECT id,role,type,content_json,created_at FROM agent_messages "
        "WHERE session_id=? ORDER BY created_at ASC, id ASC", (session_id,),
    ).fetchall()
    db.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["content"] = json.loads(d.pop("content_json"))
        except Exception:
            d["content"] = {}
        out.append(d)
    return out


# ---------- 项目数据版本号 ----------
def get_version(project_id):
    db = get_db()
    r = db.execute("SELECT version FROM project_version WHERE project_id=?", (project_id,)).fetchone()
    db.close()
    return r["version"] if r else 0


def bump_version(project_id):
    """agent 写操作完成后 bump 项目版本号并返回新值（调用方再广播 data_changed）。"""
    db = get_db()
    ts = now()
    db.execute(
        """INSERT INTO project_version(project_id,version,updated_at) VALUES(?,1,?)
           ON CONFLICT(project_id) DO UPDATE SET version=version+1, updated_at=excluded.updated_at""",
        (project_id, ts),
    )
    db.commit()
    v = db.execute("SELECT version FROM project_version WHERE project_id=?", (project_id,)).fetchone()["version"]
    db.close()
    return v
