from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

from app.services.acp_bridge import get_mgr

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status")
async def agent_status():
    return {"success": True, "data": await get_mgr().status()}


@router.post("/chat")
async def agent_chat(request: Request):
    body = await request.json()
    project_id = body.get("project_id")
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"success": False, "error": {"code": "BAD_INPUT", "message": "text 不能为空"}}, status_code=400)
    mgr = get_mgr()
    try:
        session_id = await mgr.get_session(project_id or "default")
    except Exception as e:
        return JSONResponse({"success": False, "error": {"code": "ACP_ERR", "message": f"无法建立 ACP 会话: {e}"}}, status_code=502)
    sess = mgr.sessions[session_id]

    # 后台发起 prompt
    bg = asyncio_create_task(mgr.prompt(session_id, text))

    async def gen():
        try:
            # 先发一条会话建立事件
            yield sse({"type": "session", "sessionId": session_id})
            while True:
                ev = await sess.queue.get()
                yield sse(ev)
                if ev.get("type") in ("done", "error"):
                    break
        finally:
            if not bg.done():
                bg.cancel()
            yield sse({"type": "close"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


def sse(obj: dict) -> str:
    import json
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def asyncio_create_task(coro):
    import asyncio
    return asyncio.create_task(coro)
