import sqlite3
from app.config import DB_PATH

# SQLite 并发优化：
# - journal_mode=WAL：写不阻塞读（worker 后台写库时 API 读不再被锁），是"worker 写 + 前端读"并发的基础。
#   WAL 是库级持久设置，但每次连接再显式触发一次是幂等的（返回当前模式），保证任何新连接都处于 WAL。
# - busy_timeout=5000：多进程并发写时遇到锁等待 5s 而非立即报错（缓解 worker 与 API 同写冲突）。
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass  # 某些只读/内存场景不支持，降级为默认模式
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
