from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

from app.services.acp_bridge import get_mgr
from app.services import agent_store as astore

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status")
async def agent_status():
    return {"success": True, "data": await get_mgr().status()}


@router.post("/chat")
async def agent_chat(request: Request):
    body = await request.json()
    project_id = body.get("project_id")
    session_key = body.get("session_key")       # UI 会话 id（1:1 映射 ACP session）
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"success": False, "error": {"code": "BAD_INPUT", "message": "text 不能为空"}}, status_code=400)

    # 确保 UI 会话存在：session_key 无效/缺省时新建
    ui_sess = None
    if session_key:
        ui_sess = astore.get_session(session_key)
    if not ui_sess:
        ui_sess = astore.create_session(project_id or "default")
        session_key = ui_sess["id"]
    else:
        astore.touch_session(session_key)

    # 持久化用户消息（全后端，禁止 localStorage）
    astore.add_message(session_key, "user", "text", {"text": text})

    mgr = get_mgr()
    try:
        session_id = await mgr.get_session(project_id or "default", session_key)
    except Exception as e:
        return JSONResponse({"success": False, "error": {"code": "ACP_ERR", "message": f"无法建立 ACP 会话: {e}"}}, status_code=502)
    sess = mgr.sessions[session_id]

    # 本轮收集，用于结束回写持久化（避免逐条刷库）
    collected = {"text": "", "tools": {}, "perms": {}}

    bg = asyncio_create_task(mgr.prompt(session_id, text))

    async def gen():
        try:
            # 会话建立事件：同时给出 ACP sid（取消用）和 UI session key
            yield sse({"type": "session", "sessionId": session_id, "sessionKey": session_key})
            while True:
                ev = await sess.queue.get()
                yield sse(ev)
                t = ev.get("type")
                if t == "agent_chunk":
                    collected["text"] += ev.get("text", "")
                elif t == "tool":
                    collected["tools"][ev.get("label", "执行工具")] = ev.get("status", "pending")
                elif t == "permission":
                    collected["perms"][ev.get("request_id", "")] = ev.get("card", "执行操作")
                if t in ("done", "error"):
                    break
        finally:
            if not bg.done():
                bg.cancel()
            _persist_collected(session_key, collected)
            yield sse({"type": "close"})

    # 后端保险：显式 charset=utf-8（item⑤），确认 UTF-8 传输
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Content-Type": "text/event-stream; charset=utf-8"})


@router.post("/permission/{request_id}")
async def agent_permission(request_id: str, request: Request):
    body = await request.json()
    option_id = body.get("option_id")
    if option_id not in ("once", "always", "reject"):
        return JSONResponse({"success": False, "error": {"code": "BAD_INPUT", "message": "option_id 必须是 once/always/reject"}}, status_code=400)
    ok = await get_mgr().resolve_permission(request_id, option_id)
    return {"success": ok, "data": {"resolved": ok}}


@router.post("/cancel")
async def agent_cancel(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    if session_id:
        await get_mgr().cancel(session_id)
    return {"success": True, "data": {"cancelled": True}}


# ---------- AI 助手会话（全后端持久化，多人共享） ----------
@router.get("/sessions")
async def list_agent_sessions(project_id: str = None):
    if not project_id:
        return {"success": True, "data": []}
    return {"success": True, "data": astore.list_sessions(project_id)}


@router.post("/sessions")
async def create_agent_session(request: Request):
    body = await request.json()
    project_id = body.get("project_id")
    title = body.get("title")
    if not project_id:
        return JSONResponse({"success": False, "error": {"code": "BAD_INPUT", "message": "project_id 必填"}}, status_code=400)
    return {"success": True, "data": astore.create_session(project_id, title)}


@router.get("/sessions/{session_id}")
async def get_agent_session(session_id: str):
    sess = astore.get_session(session_id)
    if not sess:
        return JSONResponse({"success": False, "error": {"code": "NOT_FOUND", "message": "会话不存在"}}, status_code=404)
    msgs = astore.list_messages(session_id)
    return {"success": True, "data": {"session": sess, "messages": msgs}}


def _persist_collected(session_key, collected):
    """本轮 assistant/tool/permission 落库（结束时一次性）。"""
    try:
        if collected["text"] and collected["text"].strip():
            astore.add_message(session_key, "assistant", "text", {"text": collected["text"]})
        for label, status in collected["tools"].items():
            astore.add_message(session_key, "tool", "tool", {"label": label, "status": status})
        for rid, card in collected["perms"].items():
            astore.add_message(session_key, "permission", "permission",
                               {"request_id": rid, "card": card, "resolution": "pending"})
    except Exception:
        pass


def sse(obj: dict) -> str:
    import json
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def asyncio_create_task(coro):
    import asyncio
    return asyncio.create_task(coro)
