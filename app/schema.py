"""novel2drama schema migration helpers (idempotent).

Called on FastAPI startup so both dev (host) and GPU instances migrate on restart.
"""
import sqlite3
import uuid


# 分集维度表：这些表持有各自 ep 的数据，需要 episode_id 列
EPISODE_SCOPED_TABLES = (
    "novel_versions",
    "segments",
    "jobs",
    "exports",
    "agent_tasks",
    "agent_patches",
    "reviews",
)


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cols = [r[1] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def migrate_episodes(conn: sqlite3.Connection) -> None:
    """幂等迁移：创建 episodes 表 + 给分集表加 episode_id + 旧数据回填默认第1集。"""
    c = conn.cursor()

    # 启动时兜底切 WAL（幂等）：写不阻塞读，支撑 worker 后台写 + 前端读并发。
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    conn.execute("PRAGMA busy_timeout=5000")


    # 1) episodes 表
    c.execute(
        """CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            episode_no INTEGER NOT NULL,
            title TEXT,
            summary TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            current_novel_version_id TEXT,
            target_duration_seconds INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        )"""
    )

    # 2) 分集表加 episode_id 列
    for table in EPISODE_SCOPED_TABLES:
        if not _column_exists(c, table, "episode_id"):
            c.execute(f"ALTER TABLE {table} ADD COLUMN episode_id TEXT")

    # 3) 回填：每个未删除项目若无分集，创建默认第1集并把现有行归属过去
    projects = c.execute(
        "SELECT id FROM projects WHERE deleted_at IS NULL"
    ).fetchall()
    for (pid,) in projects:
        ep = c.execute(
            "SELECT id FROM episodes WHERE project_id=? AND deleted_at IS NULL "
            "ORDER BY episode_no LIMIT 1",
            (pid,),
        ).fetchone()
        if ep:
            eid = ep[0]
        else:
            eid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO episodes (id,project_id,episode_no,title,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (eid, pid, 1, "第1集", "draft", "1970-01-01T00:00:00", "1970-01-01T00:00:00"),
            )
        for table in EPISODE_SCOPED_TABLES:
            c.execute(
                f"UPDATE {table} SET episode_id=? WHERE project_id=? AND episode_id IS NULL",
                (eid, pid),
            )

    conn.commit()


def migrate_agent(conn: sqlite3.Connection) -> None:
    """幂等迁移：AI 助手会话/消息持久化表 + 项目数据变更版本号表（多人协同实时刷新地基）。

    - agent_sessions：UI 会话头（按项目共享，多人在同一项目看到同一组会话/历史）
    - agent_messages：消息逐条（content_json 存序列化内容，禁止 localStorage）
    - project_version：agent 写操作完成后 bump，前端轮询/SSE 感知变更
    """
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS agent_sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,          -- user/assistant/tool/permission
            type TEXT,                    -- 子类型（text/tool/permission）
            content_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS project_version (
            project_id TEXT PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON agent_messages(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_agent_sessions_project ON agent_sessions(project_id)")
    # 对话上下文感知：记录「哪个用户 · 哪个项目 · 哪个页面 · 哪个分集」与其对话
    for col in ("episode_id", "page", "operator"):
        if not _column_exists(c, "agent_sessions", col):
            c.execute(f"ALTER TABLE agent_sessions ADD COLUMN {col} TEXT")
    conn.commit()
