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
