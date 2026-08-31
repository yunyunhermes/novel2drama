"""novel2drama -> opencode(ACP) 桥接层。

用 asyncio 子进程运行 `opencode acp`，按 ACP 协议(stdio 换行分隔 JSON-RPC)与之对话。
前端通过 SSE 拉取 agent 流式输出；写操作(n2d 改库)先弹前端行为卡片确认再执行。

协议要点（实测 opencode 1.18.18 ACP 行为）：
- 帧：stdout 每次一行 JSON（MUST 无内嵌换行）。
- initialize -> {protocolVersion:1, clientCapabilities, clientInfo} 返回 agentCapabilities/agentInfo。
- session/new {cwd, mcpServers:[]} -> {sessionId, configOptions}。
- session/prompt {sessionId, prompt:[{type:text,text}]} -> 响应 {stopReason,...}。
- session/update 通知：agent_message_chunk / tool_call / tool_call_update / usage_update / available_commands_update。
- session/request_permission 请求：params{toolCall{title,kind,rawInput{command}}, options[{optionId,kind,name}]}；
  客户端批准响应 = {"jsonrpc":"2.0","id":reqId,"result":{"outcome":{"outcome":"selected","optionId":"once|always|reject"}}}。
"""
import asyncio
import json
import os
import uuid

from app.services.n2d_cards import is_write_cmd, render_action

OPENCODE_CMD = os.getenv("N2D_OPENCODE_CMD", "opencode")
ACP_CWD = os.getenv("N2D_ACP_CWD", "/data/projects/novel2drama")
AUTO_OPTION = "once"          # 读操作/普通工具 自动批准（仅本次）
CLIENT_INFO = {"name": "novel2drama", "title": "Novel2Drama Workbench", "version": "0.1"}


class AgentSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.queue = asyncio.Queue()          # 出站 SSE 事件
        self.pending_perms = {}               # request_id -> (future, command)
        self.prompt_lock = asyncio.Lock()


class ACPManager:
    """单例：管理一个 `opencode acp` 子进程与若干 ACP session。"""

    def __init__(self):
        self.proc = None
        self.reader_task = None
        self.err_task = None
        self.sessions = {}                     # sid -> AgentSession
        self.by_project = {}                   # project_id -> sid
        self.pending_requests = {}             # msg_id -> future
        self.msg_id = 0
        self.init_done = False
        self._life = asyncio.Lock()

    # ---- 生命周期 ----
    async def ensure(self):
        async with self._life:
            if self.proc is None or self.proc.returncode is not None:
                await self._start()
            if not self.init_done:
                await self._request("initialize", {
                    "protocolVersion": 1,
                    "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                    "clientInfo": CLIENT_INFO,
                })
                self.init_done = True

    async def _start(self):
        self.proc = await asyncio.create_subprocess_exec(
            OPENCODE_CMD, "acp", "--cwd", ACP_CWD,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=ACP_CWD)
        self.reader_task = asyncio.create_task(self._reader())
        self.err_task = asyncio.create_task(self._stderr())

    # ---- 底层 IO ----
    async def _send(self, obj):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
            await self.proc.stdin.drain()

    async def _request(self, method, params, timeout=60):
        self.msg_id += 1
        mid = self.msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending_requests[mid] = fut
        await self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.pending_requests.pop(mid, None)
            raise RuntimeError(f"ACP {method} 超时")

    async def _reader(self):
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            await self._dispatch(msg)

    async def _stderr(self):
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break

    async def _dispatch(self, msg):
        method = msg.get("method")
        # 权限请求（带 id 的请求）
        if method == "session/request_permission":
            await self._handle_permission(msg)
            return
        # 请求响应（resolve pending request）
        if msg.get("id") is not None and ("result" in msg or "error" in msg):
            fut = self.pending_requests.pop(msg["id"], None)
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(RuntimeError(msg["error"].get("message", "ACP error")))
                else:
                    fut.set_result(msg["result"])
            return
        # 通知：session/update
        params = msg.get("params") or {}
        sid = params.get("sessionId")
        sess = self.sessions.get(sid)
        if not sess:
            return
        upd = params.get("update") or {}
        await self._emit_update(sess, upd)

    # ---- 事件翻译 -> 前端 SSE ----
    async def _emit_update(self, sess, upd):
        kind = upd.get("sessionUpdate")
        if kind == "agent_message_chunk":
            await sess.queue.put({"type": "agent_chunk", "text": (upd.get("content") or {}).get("text", "")})
        elif kind == "tool_call":
            await sess.queue.put({"type": "tool", "status": "pending",
                                  "label": render_action(_cmd_of(upd)), "kind": upd.get("kind")})
        elif kind == "tool_call_update":
            cmd = _cmd_of(upd)
            await sess.queue.put({"type": "tool", "status": upd.get("status"),
                                  "label": render_action(cmd), "kind": upd.get("kind"),
                                  "is_write": is_write_cmd(cmd)})
        elif kind == "usage_update":
            pass  # 暂不上抛
        elif kind == "plan":
            pass

    # ---- 权限 ----
    async def _handle_permission(self, msg):
        params = msg.get("params") or {}
        sid = params.get("sessionId")
        sess = self.sessions.get(sid)
        req_id = msg["id"]
        tool = params.get("toolCall") or {}
        cmd = (tool.get("rawInput") or {}).get("command") or ""
        if sess is None or not is_write_cmd(cmd):
            # 读操作/普通工具：自动批准一次
            await self._send({"jsonrpc": "2.0", "id": req_id,
                              "result": {"outcome": {"outcome": "selected", "optionId": AUTO_OPTION}}})
            return
        # 写操作：投递可读行为卡片，等前端决策
        fut = asyncio.get_running_loop().create_future()
        sess.pending_perms[req_id] = (fut, cmd)
        await sess.queue.put({
            "type": "permission",
            "request_id": req_id,
            "sessionId": sid,
            "card": render_action(cmd),
            "is_write": True,
        })
        try:
            option_id = await asyncio.wait_for(fut, timeout=600)
        except asyncio.TimeoutError:
            option_id = "reject"
        if option_id is None:
            option_id = "reject"
        await self._send({"jsonrpc": "2.0", "id": req_id,
                          "result": {"outcome": {"outcome": "selected", "optionId": option_id}}})

    async def resolve_permission(self, request_id, option_id):
        """由 POST /agent/permission 调用：给定前端决策。"""
        for sess in self.sessions.values():
            if request_id in sess.pending_perms:
                fut = sess.pending_perms.pop(request_id)[0]
                if not fut.done():
                    fut.set_result(option_id)
                return True
        return False

    # ---- 会话 ----
    async def get_session(self, project_id):
        await self.ensure()
        if project_id in self.by_project:
            return self.by_project[project_id]
        res = await self._request("session/new", {"cwd": ACP_CWD, "mcpServers": []})
        sid = res.get("sessionId")
        if not sid:
            raise RuntimeError("opencode 未返回 sessionId")
        self.sessions[sid] = AgentSession(sid)
        self.by_project[project_id] = sid
        return sid

    async def prompt(self, session_id, text):
        sess = self.sessions.get(session_id)
        if not sess:
            raise RuntimeError("session 不存在")
        async with sess.prompt_lock:
            # 清空旧事件
            while not sess.queue.empty():
                try:
                    sess.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            try:
                await self._request("session/prompt", {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": text}],
                }, timeout=1800)
                await sess.queue.put({"type": "done", "stopReason": "end_turn"})
            except Exception as e:
                await sess.queue.put({"type": "error", "message": str(e)})

    async def cancel(self, session_id):
        await self._send({"jsonrpc": "2.0", "method": "session/cancel",
                          "params": {"sessionId": session_id}})

    async def status(self):
        alive = self.proc is not None and self.proc.returncode is None
        return {"alive": alive, "sessions": list(self.sessions.keys()),
                "by_project": self.by_project}


def _cmd_of(upd):
    raw = upd.get("rawInput") or {}
    return raw.get("command") or raw.get("cwd") or ""


# 单例
_mgr = None


def get_mgr():
    global _mgr
    if _mgr is None:
        _mgr = ACPManager()
    return _mgr
