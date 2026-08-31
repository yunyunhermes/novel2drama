"""进程内 SSE 事件总线：project_id -> set[asyncio.Queue]。

单 worker uvicorn 进程内广播（勿改多 worker/Redis）。agent 写操作完成时
broadcast(project_id, {"type":"data_changed","version":N})，前端订阅收到后刷新。
连接断开务必 unsubscribe 清理，防内存泄漏。
"""
import asyncio

# project_id -> set[Queue]
_subs = {}


def subscribe(project_id):
    q = asyncio.Queue()
    _subs.setdefault(project_id, set()).add(q)
    return q


def unsubscribe(project_id, q):
    s = _subs.get(project_id)
    if s and q in s:
        s.discard(q)
        if not s:
            _subs.pop(project_id, None)


def broadcast(project_id, event):
    for q in list(_subs.get(project_id, ())):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def subscriber_count(project_id):
    return len(_subs.get(project_id, ()))
